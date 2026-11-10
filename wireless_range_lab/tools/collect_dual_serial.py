"""Collect synchronized-by-sequence telemetry from Pico and ESP32 serial ports."""
from __future__ import annotations
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from queue import Empty, Queue
import sys
import time
from threading import Event, Thread
from typing import Any
import serial

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from range_lab.storage import TrialRepository
from range_lab.dual_telemetry import load_dual_ndjson, summarize_dual_events


def stamped(source: str, event: dict[str, Any], trial_id: str) -> dict[str, Any]:
    event["collector_received_at"] = datetime.now(timezone.utc).isoformat()
    event["collector_source"] = source
    event["trial_id"] = trial_id
    return event


class SerialWorker(Thread):
    def __init__(self, source: str, port: str, baud: int, trial_id: str, output: Queue, stop: Event) -> None:
        super().__init__(daemon=True); self.source, self.port, self.baud, self.trial_id, self.output, self.stop = source, port, baud, trial_id, output, stop

    def put_state(self, status: str, **extra: Any) -> None:
        self.output.put(("event", stamped(self.source, {"schema_version": 2, "event": "collection_state", "status": status, **extra}, self.trial_id)))

    def run(self) -> None:
        while not self.stop.is_set():
            try:
                if self.source == "esp32":
                    # Closing COM17 with its control lines asserted resets the
                    # ESP32-S3 and restarts its access point. Configure the
                    # USB Serial/JTAG port before opening it to keep both low.
                    device = serial.Serial(
                        port=None, baudrate=self.baud, timeout=1,
                        rtscts=False, dsrdtr=False,
                    )
                    device.dtr = False
                    device.rts = False
                    device.port = self.port
                    device.open()
                else:
                    # Arduino-Pico's USB serial interface needs normal host
                    # control-line behavior to deliver its telemetry after boot.
                    device = serial.Serial(
                        self.port, self.baud, timeout=1,
                        rtscts=False, dsrdtr=False,
                    )
                try:
                    self.put_state("connected", port=self.port, baud=self.baud)
                    if self.source == "pico":
                        device.write(f"RLAB_SESSION {self.trial_id}\n".encode("ascii"))
                        device.flush()
                        self.put_state("session_command_sent", port=self.port)
                    while not self.stop.is_set():
                        raw = device.readline().decode("utf-8", errors="replace").strip()
                        if not raw: continue
                        try: event = json.loads(raw)
                        except json.JSONDecodeError as error:
                            self.output.put(("malformed", {"collector_received_at": datetime.now(timezone.utc).isoformat(), "collector_source": self.source, "port": self.port, "raw_line": raw, "error": str(error)})); continue
                        self.output.put(("event", stamped(self.source, event, self.trial_id)))
                finally:
                    device.close()
            except serial.SerialException as error:
                self.put_state("serial_error", port=self.port, error=str(error))
                if self.stop.wait(2): break
            finally:
                # A planned Ctrl+C stop is not a telemetry fault; an unexpected close is.
                if not self.stop.is_set(): self.put_state("disconnected", port=self.port)


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect Wireless Range Lab Pico + ESP32 telemetry")
    parser.add_argument("--trial-id", required=True); parser.add_argument("--pico-port", required=True); parser.add_argument("--esp32-port", required=True)
    parser.add_argument("--baud", type=int, default=115200); parser.add_argument("--label", default="")
    parser.add_argument("--expected-packet-interval-ms", type=int); parser.add_argument("--expected-echo-timeout-ms", type=int)
    parser.add_argument("--expected-packet-bytes", type=int); parser.add_argument("--grace-period-ms", type=int)
    parser.add_argument("--duration-s", type=float, help="Stop cleanly after this many seconds")
    parser.add_argument("--stop-file", help="A host-created file that requests a clean stop")
    arguments = parser.parse_args(); repository = TrialRepository.from_project_root(); repository.ensure_collection_available(arguments.trial_id); trials = repository.attempt_directory(arguments.trial_id)
    metadata = json.loads((trials / "metadata.json").read_text(encoding="utf-8"))
    expected_timeout_ms = arguments.expected_echo_timeout_ms if arguments.expected_echo_timeout_ms is not None else metadata.get("timeout_ms")
    raw_path = trials / "events.ndjson"; malformed_path = trials / "malformed.ndjson"
    snapshot = {"trial_id": arguments.trial_id, "condition_id": metadata.get("condition_id"), "label": arguments.label, "pico_port": arguments.pico_port, "esp32_port": arguments.esp32_port, "baud": arguments.baud, "expected_packet_interval_ms": arguments.expected_packet_interval_ms, "expected_echo_timeout_ms": expected_timeout_ms, "expected_packet_bytes": arguments.expected_packet_bytes, "collection_grace_period_ms": arguments.grace_period_ms, "started_at": datetime.now(timezone.utc).isoformat()}
    stop, queue = Event(), Queue(); workers = [SerialWorker("pico", arguments.pico_port, arguments.baud, arguments.trial_id, queue, stop), SerialWorker("esp32", arguments.esp32_port, arguments.baud, arguments.trial_id, queue, stop)]
    for worker in workers: worker.start()
    print(f"Collecting Pico {arguments.pico_port} and ESP32 {arguments.esp32_port}. Press Ctrl+C to stop.")
    try:
        with raw_path.open("x", encoding="utf-8") as raw, malformed_path.open("x", encoding="utf-8") as malformed:
            deadline = time.monotonic() + arguments.duration_s if arguments.duration_s else None
            stop_file = Path(arguments.stop_file) if arguments.stop_file else None
            while True:
                if deadline is not None and time.monotonic() >= deadline:
                    print("Configured collection duration reached."); break
                if stop_file is not None and stop_file.exists():
                    print("Stop requested by host."); break
                try: kind, record = queue.get(timeout=.25)
                except Empty: continue
                record["trial_id"] = arguments.trial_id
                destination = raw if kind == "event" else malformed
                destination.write(json.dumps(record, separators=(",", ":")) + "\n"); destination.flush()
                print(json.dumps(record))
    except KeyboardInterrupt: print("Collector stopping; finalizing summary.")
    finally:
        stop.set()
        for worker in workers: worker.join(timeout=3)
    snapshot["stopped_at"] = datetime.now(timezone.utc).isoformat()
    events = load_dual_ndjson(raw_path); metrics = summarize_dual_events(events); snapshot["observed_firmware_configuration"] = metrics["observed_configuration"]
    mismatches = {}
    for expected_key, observed_key in (("expected_echo_timeout_ms", "echo_timeout_ms"), ("expected_packet_interval_ms", "packet_interval_ms"), ("expected_packet_bytes", "packet_bytes")):
        expected, observed = snapshot.get(expected_key), metrics["observed_configuration"].get(observed_key)
        if expected is not None and observed is not None and expected != observed: mismatches[observed_key] = {"expected": expected, "observed": observed}
    metrics["configuration_mismatches"] = mismatches
    config_path = trials / "config.json"; config_path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    summary_path = repository.save_dual_summary(arguments.trial_id, metrics, snapshot)
    print(f"Saved raw telemetry to {raw_path}\nSaved malformed lines to {malformed_path}\nSaved summary to {summary_path}")
    print(json.dumps(metrics, indent=2))

if __name__ == "__main__": main()
