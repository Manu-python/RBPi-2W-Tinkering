"""Persistence for trial metadata; intentionally independent of the UI."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from range_lab.models import TrialMetadata


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
        record_path = self.trials_directory / f"{trial.trial_id}.json"
        if record_path.exists():
            raise FileExistsError(f"Trial already exists: {trial.trial_id}")

        temporary_path = record_path.with_suffix(".json.tmp")
        temporary_path.write_text(json.dumps(trial.to_dict(), indent=2), encoding="utf-8")
        temporary_path.replace(record_path)
        self._append_index(trial)
        return record_path

    def save_summary(self, trial_id: str, metrics: dict[str, Any]) -> Path:
        """Atomically save derived metrics without modifying immutable raw events."""
        self.trials_directory.mkdir(parents=True, exist_ok=True)
        summary_path = self.trials_directory / f"{trial_id}.summary.json"
        metadata_path = self.trials_directory / f"{trial_id}.json"
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

    def list_trial_ids(self) -> list[str]:
        if not self.trials_directory.exists():
            return []
        return sorted(
            (path.stem for path in self.trials_directory.glob("trial-*.json") if not path.name.endswith(".summary.json")),
            reverse=True,
        )

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
