"""Correlation and conservative metrics for dual-device telemetry."""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
from statistics import median
from typing import Any, Iterable


def _unique_sequences(events: Iterable[dict[str, Any]], predicate) -> set[int]:
    return {event["sequence"] for event in events if predicate(event) and isinstance(event.get("sequence"), int)}


def _percentile(values: list[int], fraction: float) -> int | None:
    return sorted(values)[round((len(values) - 1) * fraction)] if values else None


def _source(event: dict[str, Any]) -> str:
    return str(event.get("collector_source") or event.get("device_role") or "")


def summarize_dual_events(events: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Summarize observed device reports without turning missing telemetry into radio loss."""
    all_events = list(events)
    packet_events = [event for event in all_events if isinstance(event.get("sequence"), int)]
    pico = [event for event in packet_events if _source(event) == "pico"]
    esp = [event for event in packet_events if _source(event) == "esp32"]
    sent = _unique_sequences(pico, lambda e: e.get("event") == "packet_tx" and e.get("status") == "sent")
    send_errors = _unique_sequences(pico, lambda e: e.get("event") == "packet_tx" and e.get("status") != "sent")
    esp_received = _unique_sequences(esp, lambda e: e.get("event") == "packet_rx" and e.get("status") == "received" and e.get("validation") == "valid")
    echo_attempted = _unique_sequences(esp, lambda e: e.get("event") == "echo_attempt")
    echo_failures = _unique_sequences(esp, lambda e: e.get("event") == "echo_result" and e.get("status") != "api_success")
    on_time = _unique_sequences(pico, lambda e: e.get("event") == "packet_rx" and e.get("status") == "echo_on_time" and e.get("validation") == "valid")
    late = _unique_sequences(pico, lambda e: e.get("event") == "packet_rx" and e.get("status") == "echo_late" and e.get("validation") == "valid")
    finalized = _unique_sequences(pico, lambda e: e.get("event") == "packet_finalized" and e.get("status") == "unobserved")
    deadline = _unique_sequences(pico, lambda e: e.get("event") == "packet_deadline")
    invalid = [e for e in all_events if e.get("event") == "packet_rx" and e.get("status") == "invalid"]
    duplicates = [e for e in pico if e.get("event") == "packet_rx" and e.get("status") == "duplicate"]
    unexpected = [e for e in pico if e.get("event") == "packet_rx" and e.get("status") == "unexpected"]
    valid_returns = on_time | late
    rtt = [int(e["rtt_us"]) for e in pico if e.get("event") == "packet_rx" and e.get("status") in {"echo_on_time", "echo_late"} and isinstance(e.get("rtt_us"), int)]
    rssi = [int(e["rssi_dbm"]) for e in pico if isinstance(e.get("rssi_dbm"), int)]
    ordered_rtt = [value for _, value in sorted((e.get("sequence"), int(e["rtt_us"])) for e in pico if e.get("event") == "packet_rx" and e.get("status") in {"echo_on_time", "echo_late"} and isinstance(e.get("rtt_us"), int))]
    jitter = [abs(right - left) for left, right in zip(ordered_rtt, ordered_rtt[1:])]
    terminal = [(e["sequence"], e.get("status")) for e in pico if e.get("event") in {"packet_rx", "packet_finalized"} and e.get("status") in {"echo_on_time", "echo_late", "unobserved"}]
    final_status = {sequence: status for sequence, status in terminal}
    streaks: list[int] = []; current = 0
    for sequence in sorted(final_status):
        if final_status[sequence] == "unobserved": current += 1
        elif current: streaks.append(current); current = 0
    if current: streaks.append(current)
    observed_us = [int(e["monotonic_us"]) for e in pico if isinstance(e.get("monotonic_us"), int)]
    duration = max(observed_us) - min(observed_us) if len(observed_us) >= 2 else None
    payload_bytes = next((int(e["datagram_bytes"]) - 28 for e in pico if e.get("event") == "packet_tx" and isinstance(e.get("datagram_bytes"), int)), 0)
    # A collector "connected" line proves the port opened, not that firmware telemetry arrived.
    sources = {_source(event) for event in all_events if event.get("event") != "collection_state"}
    collection_errors = [e for e in all_events if e.get("event") == "collection_state" and e.get("status") in {"serial_error", "disconnected"}]
    config = next((e for e in all_events if _source(e) == "pico" and e.get("event") == "session_config"), None)
    return {
        "schema_version": 2,
        "metrics_reliability": "complete" if {"pico", "esp32"} <= sources and not collection_errors else "incomplete_telemetry",
        "telemetry_sources_observed": sorted(source for source in sources if source in {"pico", "esp32"}),
        "collection_error_count": len(collection_errors),
        "packets_transmitted_observed_by_pico": len(sent),
        "pico_local_send_errors_observed": len(send_errors),
        "packets_received_observed_by_esp32": len(esp_received) if "esp32" in sources else None,
        "echo_attempts_observed_by_esp32": len(echo_attempted) if "esp32" in sources else None,
        "echo_send_api_failures_observed_by_esp32": len(echo_failures) if "esp32" in sources else None,
        "valid_echoes_received_by_pico": len(valid_returns), "on_time_echoes": len(on_time), "late_echoes": len(late),
        "pico_deadlines_observed": len(deadline), "unobserved_after_grace": len(finalized),
        "invalid_packets_observed": len(invalid), "duplicate_packets_observed": len(duplicates), "unexpected_packets_observed": len(unexpected),
        "unmatched_or_incomplete_observations": len((sent - valid_returns) - finalized),
        "end_to_end_echo_success_ratio": len(valid_returns) / len(sent) if sent else None,
        "esp32_observed_reception_ratio": len(esp_received) / len(sent) if sent and "esp32" in sources else None,
        "pico_observed_echo_return_ratio": len(valid_returns) / len(sent) if sent else None,
        "rtt_min_us": min(rtt) if rtt else None, "rtt_median_us": median(rtt) if rtt else None,
        "rtt_p95_us": _percentile(rtt, .95), "rtt_p99_us": _percentile(rtt, .99), "rtt_max_us": max(rtt) if rtt else None,
        "rtt_jitter_mean_abs_delta_us": sum(jitter) / len(jitter) if jitter else None,
        "maximum_consecutive_unobserved_streak": max(streaks, default=0), "unobserved_burst_lengths": streaks,
        "timeout_burst_frequency": dict(Counter(streaks)),
        "goodput_payload_bytes_per_second": len(valid_returns) * payload_bytes * 1_000_000 / duration if duration and duration > 0 else None,
        "active_duration_us": duration, "rssi_min_dbm": min(rssi) if rssi else None,
        "rssi_median_dbm": median(rssi) if rssi else None, "rssi_max_dbm": max(rssi) if rssi else None,
        "connection_events": sum(1 for e in all_events if _source(e) == "pico" and e.get("event") == "wifi_state"),
        "observed_configuration": {key: config[key] for key in ("packet_bytes", "packet_interval_ms", "echo_timeout_ms", "late_reply_grace_ms", "target_packet_count", "test_duration_ms") if config and key in config},
    }


def load_dual_ndjson(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
