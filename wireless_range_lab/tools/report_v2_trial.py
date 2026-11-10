"""Generate a small human-readable Markdown report from a saved dual-device summary."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from range_lab.storage import TrialRepository

def main() -> None:
    parser=argparse.ArgumentParser(); parser.add_argument("--trial-id",required=True); args=parser.parse_args()
    repo=TrialRepository.from_project_root(); path=repo.attempt_directory(args.trial_id)/"summary.json"
    if not path.exists(): raise SystemExit(f"No summary found: {path}")
    summary=json.loads(path.read_text(encoding="utf-8")); metrics=summary["metrics"]; metadata=summary.get("metadata") or {}
    lines=[f"# Trial report: `{args.trial_id}`","",f"Telemetry reliability: **{metrics['metrics_reliability']}**.","","## Configuration","", "```json",json.dumps(summary.get("configuration",{}),indent=2),"```","","## Results","", "| Metric | Value |","| --- | --- |"]
    for key in ("packets_transmitted_observed_by_pico","packets_received_observed_by_esp32","echo_attempts_observed_by_esp32","echo_send_api_failures_observed_by_esp32","valid_echoes_received_by_pico","on_time_echoes","late_echoes","pico_deadlines_observed","unobserved_after_grace","end_to_end_echo_success_ratio","esp32_observed_reception_ratio","rtt_median_us","rtt_p95_us","rtt_p99_us","rtt_jitter_mean_abs_delta_us","maximum_consecutive_unobserved_streak","rssi_median_dbm","goodput_payload_bytes_per_second"):
        lines.append(f"| {key} | {metrics.get(key)} |")
    lines += ["","## Interpretation","", "ESP32 reception values mean *observed by ESP32 telemetry*, not proof that all unlogged packets were lost. `api_success` means only the ESP32 UDP send call succeeded; Pico echo receipt is the end-to-end observation.", "", "## Metadata snapshot","", "```json",json.dumps(metadata,indent=2),"```",""]
    output=repo.attempt_directory(args.trial_id)/"report.md"; output.write_text("\n".join(lines),encoding="utf-8"); print(output)
if __name__ == "__main__": main()
