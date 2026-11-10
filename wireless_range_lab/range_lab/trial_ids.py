"""Portable, metadata-derived identifiers for range experiments."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re

_CONDITION_PATTERN = re.compile(r"^(?P<date>\d{8})_D(?P<distance>\d{3,})cm_R(?P<rotation>[+-]\d{3})_T(?P<timeout>\d{4})$")
_TRIAL_PATTERN = re.compile(r"^(?P<date>\d{8})_D(?P<distance>\d{3,})cm_R(?P<rotation>[+-]\d{3})_A(?P<attempt>\d{2})_T(?P<timeout>\d{4})$")


@dataclass(frozen=True)
class TrialCondition:
    experiment_date: date
    distance_cm: int
    rotation_deg: int
    timeout_ms: int

    def validate(self) -> None:
        if not 0 <= self.distance_cm <= 999_999:
            raise ValueError("Distance must be between 0 and 999999 cm.")
        if not -999 <= self.rotation_deg <= 999:
            raise ValueError("Rotation must be between -999 and +999 degrees.")
        if not 1 <= self.timeout_ms <= 9999:
            raise ValueError("Timeout must be between 1 and 9999 ms.")

    @property
    def condition_id(self) -> str:
        self.validate()
        return f"{self.experiment_date:%Y%m%d}_D{self.distance_cm:03d}cm_R{self.rotation_deg:+04d}_T{self.timeout_ms:04d}"

    def trial_id(self, attempt_number: int) -> str:
        if not 1 <= attempt_number <= 99:
            raise ValueError("Attempt number must be between 1 and 99.")
        return f"{self.experiment_date:%Y%m%d}_D{self.distance_cm:03d}cm_R{self.rotation_deg:+04d}_A{attempt_number:02d}_T{self.timeout_ms:04d}"


def centimeters_from_meters(distance_m: float | Decimal) -> int:
    """Convert a measurement to cm; reject values that cannot be named at cm precision."""
    try:
        centimeters = Decimal(str(distance_m)) * Decimal("100")
    except (InvalidOperation, ValueError) as error:
        raise ValueError("Distance must be a finite numeric value.") from error
    rounded = centimeters.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    if centimeters != rounded:
        raise ValueError("Distance must be recorded to whole-centimeter precision for this ID format.")
    return int(rounded)


def local_experiment_date(value: date | datetime | None = None) -> date:
    if value is None:
        return datetime.now().astimezone().date()
    return value.date() if isinstance(value, datetime) else value


def condition_from_metadata(*, distance_m: float, rotation_deg: int, timeout_ms: int,
                            experiment_date: date | datetime | None = None) -> TrialCondition:
    condition = TrialCondition(local_experiment_date(experiment_date), centimeters_from_meters(distance_m), rotation_deg, timeout_ms)
    condition.validate()
    return condition


def parse_condition_id(value: str) -> TrialCondition:
    match = _CONDITION_PATTERN.fullmatch(value)
    if not match:
        raise ValueError(f"Invalid condition ID: {value}")
    return TrialCondition(
        date(int(match["date"][:4]), int(match["date"][4:6]), int(match["date"][6:])),
        int(match["distance"]), int(match["rotation"]), int(match["timeout"]),
    )


def parse_trial_id(value: str) -> tuple[TrialCondition, int]:
    match = _TRIAL_PATTERN.fullmatch(value)
    if not match:
        raise ValueError(f"Invalid automatic trial ID: {value}")
    condition = TrialCondition(
        date(int(match["date"][:4]), int(match["date"][4:6]), int(match["date"][6:])),
        int(match["distance"]), int(match["rotation"]), int(match["timeout"]),
    )
    condition.validate()
    attempt = int(match["attempt"])
    if not 1 <= attempt <= 99:
        raise ValueError(f"Invalid attempt number in trial ID: {value}")
    return condition, attempt
