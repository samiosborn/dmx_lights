# tests/test_show.py

from copy import deepcopy
from pathlib import Path

import pytest

from lights.show.loader import load_show, parse_duration, validate_show
from lights.show.scheduler import get_phase, schedule_show


# Project paths
ROOT = Path(__file__).resolve().parents[1]
HALLOWEEN_PATH = ROOT / "shows" / "halloween.yaml"


# Build the smallest valid show for validation tests
def make_show() -> dict:
    return {
        "seed": 42,
        "fixtures": ["zq06141_1"],
        "phases": [
            {
                "name": "test",
                "duration": 60.0,
                "colour": {
                    "effect": "static_colour",
                    "colour": "purple",
                },
                "movement": {
                    "effect": "static_position",
                    "position": "centre",
                },
                "intensity": {
                    "effect": "static_intensity",
                    "value": 0.75,
                },
                "strobe": {
                    "effect": "static_strobe",
                    "value": 0,
                },
            }
        ],
    }


# Duration strings are converted into seconds
def test_parse_duration() -> None:
    assert parse_duration("2.5s") == 2.5
    assert parse_duration("5m") == 300.0
    assert parse_duration("1h") == 3600.0
    assert parse_duration(12) == 12.0
    assert parse_duration(2.5) == 2.5


# Invalid durations fail immediately
def test_parse_duration_rejects_invalid_values() -> None:
    with pytest.raises(ValueError):
        parse_duration("-1s")

    with pytest.raises(ValueError):
        parse_duration("10d")

    with pytest.raises(ValueError):
        parse_duration("hello")


# The real Halloween show loads and validates successfully
def test_halloween_show_loads() -> None:
    show = load_show(HALLOWEEN_PATH)

    assert show["seed"] == 42
    assert show["fixtures"] == ["zq06141_1"]
    assert len(show["phases"]) == 6


# Timing values in the Halloween show are normalised into seconds
def test_halloween_show_times_are_normalised() -> None:
    show = load_show(HALLOWEEN_PATH)

    arrival = show["phases"][0]
    peak_2 = show["phases"][4]

    assert arrival["duration"] == 3600.0
    assert arrival["colour"]["change_every"] == 480.0
    assert arrival["colour"]["choices"][0]["period"] == 40.0
    assert peak_2["movement"]["choices"][1]["interval"] == 2.5


# Duplicate phase names are rejected
def test_duplicate_phase_names_are_rejected() -> None:
    show = make_show()
    duplicate = deepcopy(show["phases"][0])
    show["phases"].append(duplicate)

    with pytest.raises(ValueError, match="Duplicate phase name"):
        validate_show(show)


# Unknown effects are rejected
def test_unknown_effect_is_rejected() -> None:
    show = make_show()
    show["phases"][0]["colour"] = {
        "effect": "disco_inferno",
    }

    with pytest.raises(ValueError, match="unsupported effect"):
        validate_show(show)


# Palette step requires a period rather than an interval
def test_palette_step_requires_period() -> None:
    show = make_show()
    show["phases"][0]["colour"] = {
        "effect": "palette_step",
        "palette": "halloween_dark",
        "interval": 10.0,
    }

    with pytest.raises(ValueError, match="period"):
        validate_show(show)


# Rainbow direction is restricted to supported values
def test_invalid_rainbow_direction_is_rejected() -> None:
    show = make_show()
    show["phases"][0]["colour"] = {
        "effect": "rainbow",
        "period": 20.0,
        "direction": "sideways",
    }

    with pytest.raises(ValueError, match="direction"):
        validate_show(show)


# Motor speed must fit inside one DMX byte
def test_invalid_motor_speed_is_rejected() -> None:
    show = make_show()
    show["phases"][0]["movement"] = {
        "effect": "sweep",
        "period": 10.0,
        "motor_speed": 300,
    }

    with pytest.raises(ValueError, match="motor_speed"):
        validate_show(show)


# Pulse bounds must be valid and ordered
def test_invalid_pulse_range_is_rejected() -> None:
    show = make_show()
    show["phases"][0]["intensity"] = {
        "effect": "pulse",
        "minimum": 0.9,
        "maximum": 0.4,
        "period": 5.0,
    }

    with pytest.raises(ValueError, match="minimum cannot exceed maximum"):
        validate_show(show)


# Strobe bursts cannot last longer than their interval
def test_invalid_strobe_duration_is_rejected() -> None:
    show = make_show()
    show["phases"][0]["strobe"] = {
        "effect": "strobe_burst",
        "interval": 2.0,
        "duration": 3.0,
    }

    with pytest.raises(ValueError, match="duration cannot exceed interval"):
        validate_show(show)


# Scheduler produces exactly the same state for the same show and time
def test_scheduler_is_deterministic() -> None:
    show = load_show(HALLOWEEN_PATH)

    first = schedule_show(show, elapsed=4321.5)
    second = schedule_show(show, elapsed=4321.5)

    assert first == second


# Phase changes happen exactly at the configured boundaries
def test_phase_boundaries() -> None:
    show = load_show(HALLOWEEN_PATH)

    _, phase, phase_elapsed = get_phase(show, 3599.999)
    assert phase["name"] == "arrival"
    assert phase_elapsed == pytest.approx(3599.999)

    _, phase, phase_elapsed = get_phase(show, 3600.0)
    assert phase["name"] == "build"
    assert phase_elapsed == 0.0

    _, phase, phase_elapsed = get_phase(show, 7200.0)
    assert phase["name"] == "colourful"
    assert phase_elapsed == 0.0


# The final phase continues after the configured six-hour show
def test_final_phase_continues_forever() -> None:
    show = load_show(HALLOWEEN_PATH)

    _, phase, phase_elapsed = get_phase(show, 25000.0)

    assert phase["name"] == "late"
    assert phase_elapsed == 7000.0


# Negative elapsed time is invalid
def test_negative_elapsed_is_rejected() -> None:
    show = load_show(HALLOWEEN_PATH)

    with pytest.raises(ValueError, match="cannot be negative"):
        get_phase(show, -1.0)
