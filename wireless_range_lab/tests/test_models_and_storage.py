import csv
import json

from range_lab.models import Endpoint, TrialMetadata
from range_lab.storage import TrialRepository
from range_lab.telemetry import summarize_packet_results


def test_saves_rich_json_and_flat_csv_index(tmp_path):
    repository = TrialRepository(tmp_path)
    trial = TrialMetadata.new(
        operator="Ada", endpoint_a=Endpoint("ESP32-S3", "esp-a"), endpoint_b=Endpoint("Raspberry Pi Pico 2 W", "pico-b"),
        radio_technology="Wi-Fi", communication_mode="Client to hotspot", distance_m=12.5,
        reference_distance_m=None, environment="Open field", location="North lawn", line_of_sight=True,
        obstacles="", channel="6", tx_power="10 dBm", notes="Calm day",
    )

    record_path = repository.save(trial)

    assert json.loads(record_path.read_text(encoding="utf-8"))["trial_id"] == trial.trial_id
    with repository.index_path.open(newline="", encoding="utf-8") as index_file:
        rows = list(csv.DictReader(index_file))
    assert rows == [
        {"trial_id": trial.trial_id, "created_at": trial.created_at, "operator": "Ada", "radio_technology": "Wi-Fi", "communication_mode": "Client to hotspot", "endpoint_a_type": "ESP32-S3", "endpoint_a_label": "esp-a", "endpoint_b_type": "Raspberry Pi Pico 2 W", "endpoint_b_label": "pico-b", "distance_m": "12.5", "reference_distance_m": "", "environment": "Open field", "location": "North lawn", "line_of_sight": "True", "channel": "6", "tx_power": "10 dBm"}
    ]
    summary_path = repository.save_summary(trial.trial_id, {"packet_delivery_ratio": 1.0})
    saved_summary = repository.load_summary(trial.trial_id)
    assert saved_summary["metrics"]["packet_delivery_ratio"] == 1.0
    assert saved_summary["metadata"]["trial_id"] == trial.trial_id
    assert summary_path.name == f"{trial.trial_id}.summary.json"
    assert repository.list_trial_ids() == [trial.trial_id]


def test_summarizes_loss_and_rtt_without_counting_duplicate_results():
    summary = summarize_packet_results([
        {"event": "packet_result", "sequence": 1, "status": "echoed", "payload_bytes": 128, "rtt_us": 1000, "observed_monotonic_us": 1000, "rssi_dbm": -55},
        {"event": "packet_result", "sequence": 2, "status": "timeout", "payload_bytes": 128, "rtt_us": 0, "observed_monotonic_us": 2000, "rssi_dbm": -65},
        {"event": "packet_result", "sequence": 3, "status": "echoed", "payload_bytes": 128, "rtt_us": 3000, "observed_monotonic_us": 3000, "rssi_dbm": -60},
        {"event": "packet_result", "sequence": 3, "status": "echoed", "payload_bytes": 128, "rtt_us": 3000, "observed_monotonic_us": 3000, "rssi_dbm": -60},
    ])

    assert summary.attempts == 3
    assert summary.echoed == 2
    assert summary.timeouts == 1
    assert summary.duplicate_results == 1
    assert summary.packet_delivery_ratio == 2 / 3
    assert summary.to_dict()["rtt_median_us"] == 2000
    assert summary.to_dict()["goodput_bytes_per_second"] == 128000
    assert summary.to_dict()["rssi_median_dbm"] == -60
