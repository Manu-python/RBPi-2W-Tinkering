"""Persistence for trial metadata; intentionally independent of the UI."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from range_lab.models import TrialMetadata
from range_lab.trial_ids import TrialCondition, condition_from_metadata, parse_trial_id


class TrialRepository:
    """Stores one rich JSON record per trial and a flat CSV index for plotting."""

    INDEX_COLUMNS = (
        "trial_id", "created_at", "operator", "radio_technology",
        "communication_mode", "endpoint_a_type", "endpoint_a_label",
        "endpoint_b_type", "endpoint_b_label", "distance_m",
        "reference_distance_m", "environment", "location", "line_of_sight",
        "channel", "tx_power",
    )

    def __init__(self, data_directory: Path) -> None:
        self.data_directory = data_directory
        self.trials_directory = data_directory / "trials"
        self.index_path = data_directory / "trial_index.csv"

    @classmethod
    def from_project_root(cls) -> "TrialRepository":
        return cls(Path(__file__).resolve().parents[1] / "data")

    def save(self, trial: TrialMetadata) -> Path:
        trial.validate()
        self.trials_directory.mkdir(parents=True, exist_ok=True)
        if self.trial_id_exists(trial.trial_id):
            raise FileExistsError(f"Trial already exists: {trial.trial_id}")
        if trial.condition_id:
            record_path = self.trials_directory / trial.trial_id / "metadata.json"
            record_path.parent.mkdir(parents=True, exist_ok=False)
        else:
            record_path = self.trials_directory / f"{trial.trial_id}.json"

        temporary_path = record_path.with_suffix(".json.tmp")
        temporary_path.write_text(json.dumps(trial.to_dict(), indent=2), encoding="utf-8")
        temporary_path.replace(record_path)
        self._append_index(trial)
        return record_path

    def attempt_directory(self, trial_id: str) -> Path:
        """Return the folder containing one automatic trial attempt."""
        try:
            parse_trial_id(trial_id)
        except ValueError as error:
            raise ValueError("An attempt folder requires an automatic trial ID.") from error
        return self.trials_directory / trial_id

    def metadata_path(self, trial_id: str) -> Path:
        directory_path = self.trials_directory / trial_id / "metadata.json"
        return directory_path if directory_path.exists() else self.trials_directory / f"{trial_id}.json"

    def create_automatic_trial(self, *, distance_m: float, rotation_deg: int, timeout_ms: int,
                        experiment_date: Any = None, **metadata: Any) -> TrialMetadata:
        """Build, but do not save, the next human-readable trial record."""
        condition = condition_from_metadata(
            distance_m=distance_m, rotation_deg=rotation_deg, timeout_ms=timeout_ms,
            experiment_date=experiment_date,
        )
        attempt = self.next_attempt_for(condition)
        return TrialMetadata.new(
            trial_id=condition.trial_id(attempt), distance_m=distance_m,
            rotation_deg=rotation_deg, timeout_ms=timeout_ms, attempt_number=attempt,
            condition_id=condition.condition_id, experiment_date=condition.experiment_date.isoformat(),
            schema_version=2, **metadata,
        )

    def next_attempt_for(self, condition: TrialCondition) -> int:
        used_attempts: set[int] = set()
        if self.trials_directory.exists():
            for path in self._metadata_paths():
                try:
                    parsed, attempt = parse_trial_id(path.parent.name if path.name == "metadata.json" else path.stem)
                except ValueError:
                    continue  # Legacy V1 IDs are intentionally ignored.
                if parsed.condition_id == condition.condition_id:
                    used_attempts.add(attempt)
        for attempt in range(1, 100):
            candidate = condition.trial_id(attempt)
            if attempt not in used_attempts and not self.trial_id_exists(candidate):
                return attempt
        raise FileExistsError(f"All 99 attempts are already used for {condition.condition_id}")

    def trial_id_exists(self, trial_id: str) -> bool:
        if not self.trials_directory.exists():
            return False
        return any(path.name == trial_id or path.name.startswith(f"{trial_id}.") for path in self.trials_directory.iterdir())

    def ensure_collection_available(self, trial_id: str) -> None:
        """Require saved automatic metadata and refuse to append to prior collection data."""
        try:
            parse_trial_id(trial_id)
        except ValueError as error:
            raise ValueError("Collection requires an automatically generated trial ID.") from error
        metadata_path = self.metadata_path(trial_id)
        if not metadata_path.exists():
            raise FileNotFoundError(f"Save the trial setup before collecting: {trial_id}")
        trial_directory = self.attempt_directory(trial_id)
        has_folder_artifacts = trial_directory.exists() and any(
            path.name not in {"metadata.json", ".stop-request"} for path in trial_directory.iterdir()
        )
        if has_folder_artifacts or any(self.trials_directory.glob(f"{trial_id}.v2.*")):
            raise FileExistsError(f"Collection data already exists for {trial_id}; create a new attempt.")

    def save_summary(self, trial_id: str, metrics: dict[str, Any]) -> Path:
        """Atomically save derived metrics without modifying immutable raw events."""
        self.trials_directory.mkdir(parents=True, exist_ok=True)
        summary_path = self.trials_directory / f"{trial_id}.summary.json"
        metadata_path = self.metadata_path(trial_id)
        metadata = (
            json.loads(metadata_path.read_text(encoding="utf-8"))
            if metadata_path.exists()
            else None
        )
        document = {
            "schema_version": 1,
            "trial_id": trial_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "metadata": metadata,
            "metrics": metrics,
        }
        temporary_path = summary_path.with_suffix(".json.tmp")
        temporary_path.write_text(json.dumps(document, indent=2), encoding="utf-8")
        temporary_path.replace(summary_path)
        return summary_path

    def load_summary(self, trial_id: str) -> dict[str, Any] | None:
        summary_path = self.trials_directory / f"{trial_id}.summary.json"
        if not summary_path.exists():
            return None
        return json.loads(summary_path.read_text(encoding="utf-8"))

    def load_any_summary(self, trial_id: str) -> dict[str, Any] | None:
        """Load a folder summary when available, otherwise retain legacy behavior."""
        folder_summary_path = self.trials_directory / trial_id / "summary.json"
        if folder_summary_path.exists():
            return json.loads(folder_summary_path.read_text(encoding="utf-8"))
        legacy_flat_summary_path = self.trials_directory / f"{trial_id}.v2.summary.json"
        if legacy_flat_summary_path.exists():
            return json.loads(legacy_flat_summary_path.read_text(encoding="utf-8"))
        return self.load_summary(trial_id)

    def save_dual_summary(self, trial_id: str, metrics: dict[str, Any], configuration: dict[str, Any]) -> Path:
        """Save a dual-device report without overwriting an existing summary."""
        self.trials_directory.mkdir(parents=True, exist_ok=True)
        metadata_path = self.metadata_path(trial_id)
        metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.exists() else None
        document = {
            "schema_version": 2,
            "trial_id": trial_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "metadata": metadata,
            "configuration": configuration,
            "metrics": metrics,
        }
        directory = self.trials_directory / trial_id
        path = directory / "summary.json" if directory.exists() else self.trials_directory / f"{trial_id}.v2.summary.json"
        if path.exists():
            raise FileExistsError(f"Summary already exists: {path}")
        temporary_path = path.with_suffix(".json.tmp")
        temporary_path.write_text(json.dumps(document, indent=2), encoding="utf-8")
        temporary_path.replace(path)
        return path

    def list_trial_ids(self) -> list[str]:
        if not self.trials_directory.exists():
            return []
        return sorted({path.parent.name if path.name == "metadata.json" else path.stem
                       for path in self._metadata_paths()}, reverse=True)

    def _metadata_paths(self) -> list[Path]:
        if not self.trials_directory.exists():
            return []
        legacy = [path for path in self.trials_directory.glob("*.json")
                  if ".v2." not in path.name and not path.name.endswith(".summary.json")]
        folders = [path / "metadata.json" for path in self.trials_directory.iterdir()
                   if path.is_dir() and (path / "metadata.json").exists()]
        return legacy + folders

    def _append_index(self, trial: TrialMetadata) -> None:
        row = {
            "trial_id": trial.trial_id,
            "created_at": trial.created_at,
            "operator": trial.operator,
            "radio_technology": trial.radio_technology,
            "communication_mode": trial.communication_mode,
            "endpoint_a_type": trial.endpoint_a.device_type,
            "endpoint_a_label": trial.endpoint_a.label,
            "endpoint_b_type": trial.endpoint_b.device_type,
            "endpoint_b_label": trial.endpoint_b.label,
            "distance_m": trial.distance_m,
            "reference_distance_m": trial.reference_distance_m if trial.reference_distance_m is not None else "",
            "environment": trial.environment,
            "location": trial.location,
            "line_of_sight": trial.line_of_sight,
            "channel": trial.channel,
            "tx_power": trial.tx_power,
        }
        self.data_directory.mkdir(parents=True, exist_ok=True)
        write_header = not self.index_path.exists()
        with self.index_path.open("a", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=self.INDEX_COLUMNS)
            if write_header:
                writer.writeheader()
            writer.writerow(row)
