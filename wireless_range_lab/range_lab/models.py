"""Technology-neutral experiment metadata models.

The first stage deliberately stores setup data separately from measured samples.
Future collectors can attach RSSI, latency, packet-loss, and throughput samples
to the same trial identifier without changing this metadata schema.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


DEVICE_TYPES = (
    "Raspberry Pi Pico 2 W",
    "ESP32-S3",
    "ESP32-WROOM",
    "Laptop / host",
    "Other",
)

RADIO_TECHNOLOGIES = ("Wi-Fi", "Bluetooth Low Energy")
ANTENNA_TYPES = ("Integrated", "External", "Not applicable", "Unknown")


@dataclass(frozen=True)
class Endpoint:
    """One device participating in a test."""

    device_type: str
    label: str
    identifier: str = ""
    antenna_type: str = "Integrated"
    firmware_version: str = ""

    def validate(self, role: str) -> None:
        if not self.device_type:
            raise ValueError(f"{role} device type is required.")
        if not self.label.strip():
            raise ValueError(f"{role} label is required.")
        if self.antenna_type not in ANTENNA_TYPES:
            raise ValueError(f"{role} has an invalid antenna type.")


@dataclass(frozen=True)
class TrialMetadata:
    """Reproducible test setup information, saved before measurements begin."""

    trial_id: str
    created_at: str
    operator: str
    endpoint_a: Endpoint
    endpoint_b: Endpoint
    radio_technology: str
    communication_mode: str
    distance_m: float
    reference_distance_m: float | None
    environment: str
    location: str
    line_of_sight: bool
    obstacles: str
    channel: str
    tx_power: str
    notes: str
    schema_version: int = 1

    @classmethod
    def new(cls, **values: Any) -> "TrialMetadata":
        return cls(
            trial_id=f"trial-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:6]}",
            created_at=datetime.now(timezone.utc).isoformat(),
            **values,
        )

    def validate(self) -> None:
        self.endpoint_a.validate("Endpoint A")
        self.endpoint_b.validate("Endpoint B")
        if self.radio_technology not in RADIO_TECHNOLOGIES:
            raise ValueError("Choose Wi-Fi or Bluetooth Low Energy.")
        if not self.communication_mode.strip():
            raise ValueError("Communication mode is required.")
        if self.distance_m < 0:
            raise ValueError("Endpoint separation cannot be negative.")
        if self.reference_distance_m is not None and self.reference_distance_m < 0:
            raise ValueError("Reference distance cannot be negative.")
        if not self.environment.strip():
            raise ValueError("Environment is required.")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
