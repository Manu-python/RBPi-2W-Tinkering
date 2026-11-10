import json
import pytest

from range_lab.telemetry import summarize_ndjson_file
from range_lab.storage import TrialRepository
from range_lab.udp_protocol import Packet, PacketValidationError, decode_packet, deterministic_payload, encode_packet, session_id_for
from range_lab.dual_telemetry import summarize_dual_events


def test_packet_round_trip_and_crc_validation():
    session = session_id_for("trial-diagnostics")
    packet = Packet(session, 7, 12345, deterministic_payload(session, 7))
    encoded = encode_packet(packet)
    assert decode_packet(encoded) == packet
    corrupted = bytearray(encoded); corrupted[-1] ^= 1
    with pytest.raises(PacketValidationError, match="crc_failed"):
        decode_packet(bytes(corrupted))
    with pytest.raises(PacketValidationError, match="too_short"):
        decode_packet(b"short")


def test_dual_device_summary_distinguishes_late_and_unobserved():
    events = [
        {"collector_source": "pico", "event": "session_config", "packet_bytes": 128, "packet_interval_ms": 200, "echo_timeout_ms": 1000, "monotonic_us": 1},
        *[{"collector_source": "pico", "event": "packet_tx", "status": "sent", "sequence": n, "datagram_bytes": 128, "rssi_dbm": -50, "monotonic_us": n * 100} for n in (1, 2, 3)],
        *[{"collector_source": "esp32", "event": "packet_rx", "status": "received", "validation": "valid", "sequence": n} for n in (1, 2)],
        *[{"collector_source": "esp32", "event": "echo_attempt", "status": "attempted", "sequence": n} for n in (1, 2)],
        {"collector_source": "esp32", "event": "echo_result", "status": "api_success", "sequence": 1},
        {"collector_source": "esp32", "event": "echo_result", "status": "api_failure", "sequence": 2},
        {"collector_source": "pico", "event": "packet_rx", "status": "echo_on_time", "validation": "valid", "sequence": 1, "rtt_us": 1000, "rssi_dbm": -51, "monotonic_us": 1000},
        {"collector_source": "pico", "event": "packet_deadline", "status": "deadline_expired", "sequence": 2, "monotonic_us": 2000},
        {"collector_source": "pico", "event": "packet_rx", "status": "echo_late", "validation": "valid", "sequence": 2, "rtt_us": 3000, "rssi_dbm": -54, "monotonic_us": 3000},
        {"collector_source": "pico", "event": "packet_finalized", "status": "unobserved", "sequence": 3, "monotonic_us": 4000},
        {"collector_source": "pico", "event": "packet_rx", "status": "duplicate", "sequence": 1},
        {"collector_source": "pico", "event": "packet_rx", "status": "unexpected", "sequence": 99},
        {"collector_source": "pico", "event": "packet_rx", "status": "invalid", "validation": "crc_failed"},
    ]
    summary = summarize_dual_events(events)
    assert summary["metrics_reliability"] == "complete"
    assert summary["packets_transmitted_observed_by_pico"] == 3
    assert summary["packets_received_observed_by_esp32"] == 2
    assert summary["on_time_echoes"] == 1 and summary["late_echoes"] == 1
    assert summary["unobserved_after_grace"] == 1
    assert summary["maximum_consecutive_unobserved_streak"] == 1
    assert summary["duplicate_packets_observed"] == 1 and summary["unexpected_packets_observed"] == 1
    assert summary["echo_send_api_failures_observed_by_esp32"] == 1
    assert summary["end_to_end_echo_success_ratio"] == pytest.approx(2 / 3)


def test_marks_missing_or_interrupted_telemetry_incomplete():
    summary = summarize_dual_events([
        {"collector_source": "pico", "event": "packet_tx", "status": "sent", "sequence": 1, "monotonic_us": 1},
        {"collector_source": "pico", "event": "collection_state", "status": "serial_error"},
    ])
    assert summary["metrics_reliability"] == "incomplete_telemetry"
    assert summary["packets_received_observed_by_esp32"] is None


def test_v1_ndjson_parser_remains_compatible(tmp_path):
    path = tmp_path / "legacy.events.ndjson"
    path.write_text(json.dumps({"event": "packet_result", "sequence": 1, "status": "echoed", "payload_bytes": 128, "rtt_us": 10, "observed_monotonic_us": 10, "rssi_dbm": -40}) + "\n", encoding="utf-8")
    assert summarize_ndjson_file(path)["packet_delivery_ratio"] == 1.0


def test_versioned_summary_does_not_replace_legacy_summary(tmp_path):
    repository = TrialRepository(tmp_path)
    v1_path = repository.save_summary("trial-v2-test", {"packet_delivery_ratio": 1.0})
    v2_path = repository.save_dual_summary("trial-diagnostics-test", {"schema_version": 2}, {"echo_timeout_ms": 1000})
    assert v1_path.name == "trial-v2-test.summary.json"
    assert v2_path.name == "trial-diagnostics-test.v2.summary.json"
    assert json.loads(v1_path.read_text(encoding="utf-8"))["schema_version"] == 1
    assert json.loads(v2_path.read_text(encoding="utf-8"))["schema_version"] == 2
