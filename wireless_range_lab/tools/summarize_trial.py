"""Calculate a packet-test summary from immutable collected NDJSON events."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from range_lab.storage import TrialRepository
from range_lab.telemetry import summarize_ndjson_file


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize a Wireless Range Lab trial")
    parser.add_argument("--trial-id", required=True)
    arguments = parser.parse_args()
    repository = TrialRepository.from_project_root()
    events_path = repository.trials_directory / f"{arguments.trial_id}.events.ndjson"
    if not events_path.exists():
        raise SystemExit(f"No collected events found: {events_path}")
    metrics = summarize_ndjson_file(events_path)
    summary_path = repository.save_summary(arguments.trial_id, metrics)
    print(json.dumps(metrics, indent=2))
    print(f"Saved summary to {summary_path}")


if __name__ == "__main__":
    main()
