# tests/test_show.py

from copy import deepcopy
from pathlib import Path

import pytest

from lights.show.console import ShowConsole
from lights.show.controller import ShowController
from lights.show.loader import load_show, parse_duration, validate_show
from lights.show.scheduler import get_phase, schedule_show


# Project paths
ROOT = Path(__file__).resolve().parents[1]
HALLOWEEN_PATH = ROOT / "shows" / "halloween.yaml"


# Minimal fake fixture for controller tests
class FakeFixture:
    def __init__(self) -> None:
        self.state = {}

    def set_many(self, **controls) -> None:
        self.state.update(controls)


# Minimal fake rig for controller tests
class FakeRig:
    def __init__(self, fixture_names: list[str]) -> None:
        self.fixtures = {
            name: FakeFixture()
            for name in fixture_names
        }
        self.send_count = 0

    def get_fixture(self, name: str) -> FakeFixture:
        return self.fixtures[name]

    def send(self) -> None:
        self.send_count += 1


# Minimal fake engine for controller tests
class FakeEngine:
    def __init__(self, rig: FakeRig, show: dict, colours=None, palettes=None) -> None:
        self.rig = rig
        self.show = show
        self.colours = colours or {}
        self.palettes = palettes or {}
        self.update_calls = []

    def update(self, elapsed: float):
        self.update_calls.append(elapsed)
        return schedule_show(self.show, elapsed)


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


# Build a simple two-phase show for controller tests
def make_controller_show() -> dict:
    show = make_show()

    show["phases"][0]["name"] = "first"
    show["phases"][0]["duration"] = 60.0

    second = deepcopy(show["phases"][0])
    second["name"] = "second"
    second["duration"] = 120.0

    show["phases"].append(second)

    return show


# Build a controller using fake hardware
def make_controller(show: dict | None = None) -> tuple[ShowController, FakeEngine, FakeRig]:
    show = show or make_controller_show()
    rig = FakeRig(show["fixtures"])
    engine = FakeEngine(rig=rig, show=show)

    controller = ShowController(
        engine=engine,
        show_path=HALLOWEEN_PATH,
    )

    return controller, engine, rig


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


# Controller elapsed time follows the monotonic clock
def test_controller_elapsed(monkeypatch) -> None:
    current_time = 100.0
    monkeypatch.setattr("lights.show.controller.time.monotonic", lambda: current_time)

    controller, _, _ = make_controller()

    current_time = 125.0

    assert controller.elapsed() == 25.0


# Controller can seek to a specific show time
def test_controller_seek(monkeypatch) -> None:
    current_time = 100.0
    monkeypatch.setattr("lights.show.controller.time.monotonic", lambda: current_time)

    controller, _, _ = make_controller()

    controller.seek(45.0)

    assert controller.elapsed() == 45.0


# Controller can jump directly to a named phase
def test_controller_set_phase(monkeypatch) -> None:
    current_time = 100.0
    monkeypatch.setattr("lights.show.controller.time.monotonic", lambda: current_time)

    controller, _, _ = make_controller()

    controller.set_phase("second")

    status = controller.status()

    assert status.phase_name == "second"
    assert status.phase_elapsed == 0.0
    assert status.elapsed == 60.0


# Unknown phase names are rejected
def test_controller_rejects_unknown_phase(monkeypatch) -> None:
    monkeypatch.setattr("lights.show.controller.time.monotonic", lambda: 100.0)

    controller, _, _ = make_controller()

    with pytest.raises(ValueError, match="Unknown phase"):
        controller.set_phase("missing")


# Controller can jump to the next phase
def test_controller_next_phase(monkeypatch) -> None:
    current_time = 100.0
    monkeypatch.setattr("lights.show.controller.time.monotonic", lambda: current_time)

    controller, _, _ = make_controller()

    next_phase = controller.next_phase()

    assert next_phase == "second"
    assert controller.status().phase_name == "second"
    assert controller.elapsed() == 60.0


# Next phase returns None when already in the final phase
def test_controller_next_phase_at_end(monkeypatch) -> None:
    current_time = 100.0
    monkeypatch.setattr("lights.show.controller.time.monotonic", lambda: current_time)

    controller, _, _ = make_controller()

    controller.set_phase("second")

    assert controller.next_phase() is None


# Pause freezes the virtual show clock
def test_controller_pause(monkeypatch) -> None:
    current_time = 100.0
    monkeypatch.setattr("lights.show.controller.time.monotonic", lambda: current_time)

    controller, _, _ = make_controller()

    current_time = 125.0
    controller.pause()

    current_time = 200.0

    assert controller.paused is True
    assert controller.elapsed() == 25.0


# Resume continues from the paused show time
def test_controller_resume(monkeypatch) -> None:
    current_time = 100.0
    monkeypatch.setattr("lights.show.controller.time.monotonic", lambda: current_time)

    controller, _, _ = make_controller()

    current_time = 125.0
    controller.pause()

    current_time = 200.0
    controller.resume()

    current_time = 210.0

    assert controller.paused is False
    assert controller.elapsed() == 35.0


# Blackout turns off fixture output without pausing the clock
def test_controller_blackout(monkeypatch) -> None:
    current_time = 100.0
    monkeypatch.setattr("lights.show.controller.time.monotonic", lambda: current_time)

    controller, _, rig = make_controller()

    current_time = 110.0
    controller.blackout()

    fixture = rig.get_fixture("zq06141_1")

    assert controller.is_blackout is True
    assert fixture.state["master_dimmer"] == 0
    assert fixture.state["strobe"] == 0
    assert fixture.state["red"] == 0
    assert fixture.state["green"] == 0
    assert fixture.state["blue"] == 0
    assert fixture.state["white"] == 0
    assert rig.send_count == 1

    current_time = 120.0

    assert controller.elapsed() == 20.0


# Update does not drive the show engine while blacked out
def test_controller_update_during_blackout(monkeypatch) -> None:
    current_time = 100.0
    monkeypatch.setattr("lights.show.controller.time.monotonic", lambda: current_time)

    controller, engine, _ = make_controller()

    controller.blackout()

    current_time = 110.0
    state = controller.update()

    assert state.phase_name == "first"
    assert engine.update_calls == []


# Restore resumes normal output at the current show time
def test_controller_restore(monkeypatch) -> None:
    current_time = 100.0
    monkeypatch.setattr("lights.show.controller.time.monotonic", lambda: current_time)

    controller, engine, _ = make_controller()

    current_time = 105.0
    controller.blackout()

    current_time = 120.0
    controller.restore()

    assert controller.is_blackout is False
    assert engine.update_calls[-1] == 20.0


# Controller status reports active effects and state
def test_controller_status(monkeypatch) -> None:
    current_time = 100.0
    monkeypatch.setattr("lights.show.controller.time.monotonic", lambda: current_time)

    controller, _, _ = make_controller()

    current_time = 110.0
    status = controller.status()

    assert status.elapsed == 10.0
    assert status.phase_name == "first"
    assert status.phase_index == 0
    assert status.phase_elapsed == 10.0
    assert status.paused is False
    assert status.blackout is False
    assert status.effects == {
        "colour": "static_colour",
        "movement": "static_position",
        "intensity": "static_intensity",
        "strobe": "static_strobe",
    }


# Stop blackouts the fixture and stops the controller
def test_controller_stop(monkeypatch) -> None:
    monkeypatch.setattr("lights.show.controller.time.monotonic", lambda: 100.0)

    controller, _, rig = make_controller()

    controller.stop()

    assert controller.running is False
    assert controller.is_blackout is True
    assert rig.send_count == 1


# Console parses simple commands
def test_console_parses_simple_command() -> None:
    console = ShowConsole()

    command = console.parse("next")

    assert command is not None
    assert command.name == "next"
    assert command.args == []


# Console parses phase commands
def test_console_parses_phase_command() -> None:
    console = ShowConsole()

    command = console.parse("phase peak_1")

    assert command is not None
    assert command.name == "phase"
    assert command.args == ["peak_1"]


# Console rejects unknown commands
def test_console_rejects_unknown_command() -> None:
    console = ShowConsole()

    assert console.parse("explode") is None


# Console rejects invalid phase syntax
def test_console_rejects_invalid_phase_command() -> None:
    console = ShowConsole()

    assert console.parse("phase") is None
    assert console.parse("phase peak_1 extra") is None


# Console rejects arguments for commands that do not accept them
def test_console_rejects_unexpected_arguments() -> None:
    console = ShowConsole()

    assert console.parse("pause now") is None