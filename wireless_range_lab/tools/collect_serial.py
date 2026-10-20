"""Persist board NDJSON telemetry against an existing trial ID."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

import serial

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from range_lab.storage import TrialRepository
from range_lab.telemetry import summarize_ndjson_file


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect Wireless Range Lab serial telemetry")
    parser.add_argument("--port", required=True, help="Board serial port, for example COM5")
    parser.add_argument("--trial-id", required=True, help="Trial ID saved by the desktop app")
    parser.add_argument("--baud", type=int, default=115200)
    arguments = parser.parse_args()
    repository = TrialRepository.from_project_root()
    output_path = repository.trials_directory / f"{arguments.trial_id}.events.ndjson"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"Collecting {arguments.port} at {arguments.baud} baud into {output_path}. Press Ctrl+C to stop.")
    with serial.Serial(arguments.port, arguments.baud, timeout=1) as device, output_path.open("a", encoding="utf-8") as output:
        try:
            while True:
                line = device.readline().decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    print(f"Ignored non-JSON serial line: {line}")
                    continue
                event["collector_received_at"] = datetime.now(timezone.utc).isoformat()
                event["trial_id"] = arguments.trial_id
                output.write(json.dumps(event, separators=(",", ":")) + "\n")
                output.flush()
                print(json.dumps(event))
        except KeyboardInterrupt:
            print("Collector stopped.")

    metrics = summarize_ndjson_file(output_path)
    summary_path = repository.save_summary(arguments.trial_id, metrics)
    print(f"Saved summary to {summary_path}")
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
