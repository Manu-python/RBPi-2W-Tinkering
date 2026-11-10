from datetime import date

import pytest

from range_lab.models import Endpoint
from range_lab.storage import TrialRepository
from range_lab.trial_ids import condition_from_metadata, parse_condition_id, parse_trial_id


def test_generates_and_parses_requested_human_readable_format():
    condition = condition_from_metadata(distance_m=1.5, rotation_deg=-90, timeout_ms=1000, experiment_date=date(2026, 10, 29))
    assert condition.condition_id == "20261029_D150cm_R-090_T1000"
    assert condition.trial_id(2) == "20261029_D150cm_R-090_A02_T1000"
    parsed, attempt = parse_trial_id(condition.trial_id(2))
    assert parsed == condition and attempt == 2
    assert parse_condition_id(condition.condition_id) == condition
    with pytest.raises(ValueError):
        parse_trial_id("20261029_D150cm_R-090_A00_T1000")


@pytest.mark.parametrize("distance,rotation,timeout", [(1.555, 0, 1000), (-.01, 0, 1000), (1, 1000, 1000), (1, 0, 10000)])
def test_rejects_unrepresentable_or_invalid_condition_parameters(distance, rotation, timeout):
    with pytest.raises(ValueError):
        condition_from_metadata(distance_m=distance, rotation_deg=rotation, timeout_ms=timeout, experiment_date=date(2026, 10, 29))


def _metadata() -> dict:
    return {
        "operator": "test", "endpoint_a": Endpoint("Raspberry Pi Pico 2 W", "pico"), "endpoint_b": Endpoint("ESP32-WROOM", "esp"),
        "radio_technology": "Wi-Fi", "communication_mode": "UDP echo", "reference_distance_m": None,
        "environment": "lab", "location": "bench", "line_of_sight": True, "obstacles": "", "channel": "6", "tx_power": "default", "notes": "",
    }


def test_repository_assigns_repeated_attempts_and_rejects_collection_collision(tmp_path):
    repository = TrialRepository(tmp_path)
    first = repository.create_automatic_trial(distance_m=1.5, rotation_deg=-90, timeout_ms=1000, experiment_date=date(2026, 10, 29), **_metadata())
    repository.save(first)
    assert first.trial_id in repository.list_trial_ids()
    second = repository.create_automatic_trial(distance_m=1.5, rotation_deg=-90, timeout_ms=1000, experiment_date=date(2026, 10, 29), **_metadata())
    assert first.trial_id.endswith("_A01_T1000")
    assert second.trial_id.endswith("_A02_T1000")
    repository.save(second)
    repository.ensure_collection_available(first.trial_id)
    assert (repository.trials_directory / first.trial_id / "metadata.json").exists()
    (repository.trials_directory / first.trial_id / "events.ndjson").write_text("{}\n", encoding="utf-8")
    with pytest.raises(FileExistsError):
        repository.ensure_collection_available(first.trial_id)


def test_legacy_ids_remain_listed_and_are_not_accepted_as_new_sessions(tmp_path):
    repository = TrialRepository(tmp_path)
    (repository.trials_directory).mkdir()
    legacy = "trial-20261020-021221-64968f"
    (repository.trials_directory / f"{legacy}.json").write_text("{}", encoding="utf-8")
    assert legacy in repository.list_trial_ids()
    with pytest.raises(ValueError):
        repository.ensure_collection_available(legacy)
