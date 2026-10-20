"""Protocol-independent aggregation of board packet-result events."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from statistics import median
from typing import Any, Iterable


@dataclass
class PacketSummary:
    attempts: int = 0
    echoed: int = 0
    timeouts: int = 0
    send_errors: int = 0
    duplicate_results: int = 0
    rtt_us: list[int] = field(default_factory=list)
    rssi_dbm: list[int] = field(default_factory=list)
    delivered_payload_bytes: int = 0
    first_observed_us: int | None = None
    last_observed_us: int | None = None

    @property
    def packet_delivery_ratio(self) -> float | None:
        return self.echoed / self.attempts if self.attempts else None

    def rtt_percentile_us(self, percentile: float) -> float | None:
        if not self.rtt_us:
            return None
        ordered = sorted(self.rtt_us)
        return ordered[round((len(ordered) - 1) * percentile)]

    @property
    def active_duration_us(self) -> int | None:
        if self.first_observed_us is None or self.last_observed_us is None:
            return None
        return self.last_observed_us - self.first_observed_us

    @property
    def goodput_bytes_per_second(self) -> float | None:
        duration_us = self.active_duration_us
        if duration_us is None or duration_us <= 0:
            return None
        return self.delivered_payload_bytes * 1_000_000 / duration_us

    def to_dict(self) -> dict[str, Any]:
        return {
            "attempts": self.attempts, "echoed": self.echoed, "timeouts": self.timeouts,
            "send_errors": self.send_errors, "duplicate_results": self.duplicate_results,
            "packet_delivery_ratio": self.packet_delivery_ratio,
            "delivered_payload_bytes": self.delivered_payload_bytes,
            "active_duration_us": self.active_duration_us,
            "goodput_bytes_per_second": self.goodput_bytes_per_second,
            "rtt_min_us": min(self.rtt_us) if self.rtt_us else None,
            "rtt_median_us": median(self.rtt_us) if self.rtt_us else None,
            "rtt_p95_us": self.rtt_percentile_us(0.95),
            "rtt_max_us": max(self.rtt_us) if self.rtt_us else None,
            "rssi_min_dbm": min(self.rssi_dbm) if self.rssi_dbm else None,
            "rssi_median_dbm": median(self.rssi_dbm) if self.rssi_dbm else None,
            "rssi_max_dbm": max(self.rssi_dbm) if self.rssi_dbm else None,
        }


def summarize_packet_results(events: Iterable[dict[str, Any]]) -> PacketSummary:
    """Summarize one terminal result per sequence; retain raw events elsewhere."""
    summary = PacketSummary()
    seen_sequences: set[int] = set()
    for event in events:
        if event.get("event") != "packet_result":
            continue
        sequence = event.get("sequence")
        if not isinstance(sequence, int):
            continue
        if sequence in seen_sequences:
            summary.duplicate_results += 1
            continue
        seen_sequences.add(sequence)
        summary.attempts += 1
        observed_us = event.get("observed_monotonic_us")
        if isinstance(observed_us, int):
            summary.first_observed_us = observed_us if summary.first_observed_us is None else min(summary.first_observed_us, observed_us)
            summary.last_observed_us = observed_us if summary.last_observed_us is None else max(summary.last_observed_us, observed_us)
        rssi_dbm = event.get("rssi_dbm")
        if isinstance(rssi_dbm, int):
            summary.rssi_dbm.append(rssi_dbm)
        status = event.get("status")
        if status == "echoed":
            summary.echoed += 1
            summary.delivered_payload_bytes += int(event.get("payload_bytes", 0))
            rtt_us = event.get("rtt_us")
            if isinstance(rtt_us, int) and rtt_us >= 0:
                summary.rtt_us.append(rtt_us)
        elif status == "timeout":
            summary.timeouts += 1
        elif status == "send_error":
            summary.send_errors += 1
    return summary


def summarize_ndjson_file(events_path: Path) -> dict[str, Any]:
    """Load collected raw events and return reproducible derived metrics."""
    events = [
        json.loads(line)
        for line in events_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return summarize_packet_results(events).to_dict()
