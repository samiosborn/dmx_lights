# lights/show/controller.py

import time
from dataclasses import dataclass
from pathlib import Path

from lights.show.engine import ShowEngine
from lights.show.loader import load_show
from lights.show.scheduler import ScheduleState, schedule_show


# Current user-facing state of the show controller
@dataclass(frozen=True)
class ControllerStatus:
    elapsed: float
    phase_name: str
    phase_index: int
    phase_elapsed: float
    paused: bool
    blackout: bool
    effects: dict[str, str]


# Control show timing, phase changes, pausing and blackout
class ShowController:
    def __init__(self, engine: ShowEngine, show_path: str | Path) -> None:
        self.engine = engine
        self.rig = engine.rig
        self.show = engine.show
        self.show_path = Path(show_path)

        self.running = True
        self.paused = False
        self.is_blackout = False

        self._started_at = time.monotonic()
        self._paused_elapsed = 0.0

    # Return the current virtual show time
    def elapsed(self) -> float:
        if self.paused:
            return self._paused_elapsed

        return time.monotonic() - self._started_at

    # Move the virtual show clock to a specific elapsed time
    def seek(self, elapsed: float) -> None:
        if elapsed < 0:
            raise ValueError("Elapsed time cannot be negative")

        if self.paused:
            self._paused_elapsed = elapsed
        else:
            self._started_at = time.monotonic() - elapsed

    # Return the start time of every configured phase
    def phase_starts(self) -> dict[str, float]:
        starts = {}
        elapsed = 0.0

        for phase in self.show["phases"]:
            starts[phase["name"]] = elapsed
            elapsed += phase["duration"]

        return starts

    # Jump directly to the start of a named phase
    def set_phase(self, name: str) -> None:
        starts = self.phase_starts()

        if name not in starts:
            raise ValueError(f"Unknown phase: {name}")

        self.seek(starts[name])

    # Jump directly to the next phase
    def next_phase(self) -> str | None:
        state = schedule_show(self.show, self.elapsed())
        next_index = state.phase_index + 1

        if next_index >= len(self.show["phases"]):
            return None

        next_phase = self.show["phases"][next_index]
        self.set_phase(next_phase["name"])

        return next_phase["name"]

    # Freeze the virtual show clock
    def pause(self) -> None:
        if self.paused:
            return

        self._paused_elapsed = self.elapsed()
        self.paused = True

    # Continue the virtual show clock from the paused position
    def resume(self) -> None:
        if not self.paused:
            return

        self._started_at = time.monotonic() - self._paused_elapsed
        self.paused = False

    # Send a blackout state to every fixture used by the show
    def blackout(self) -> None:
        self.is_blackout = True

        for fixture_name in self.show["fixtures"]:
            fixture = self.rig.get_fixture(fixture_name)

            fixture.set_many(
                master_dimmer=0,
                strobe=0,
                red=0,
                green=0,
                blue=0,
                white=0,
                builtin_effect=0,
                sound_reactive=False,
            )

        self.rig.send()

    # Restore normal show output at the current show time
    def restore(self) -> None:
        self.is_blackout = False
        self.engine.update(self.elapsed())

    # Reload the show YAML while preserving the current show time
    def reload(self) -> None:
        new_show = load_show(self.show_path)

        new_engine = ShowEngine(
            rig=self.rig,
            show=new_show,
            colours=self.engine.colours,
            palettes=self.engine.palettes,
        )

        self.show = new_show
        self.engine = new_engine

    # Return the current phase and controller state
    def status(self) -> ControllerStatus:
        elapsed = self.elapsed()
        state = schedule_show(self.show, elapsed)

        effects = {
            layer_name: scheduled.config["effect"]
            for layer_name, scheduled in state.effects.items()
        }

        return ControllerStatus(
            elapsed=elapsed,
            phase_name=state.phase_name,
            phase_index=state.phase_index,
            phase_elapsed=state.phase_elapsed,
            paused=self.paused,
            blackout=self.is_blackout,
            effects=effects,
        )

    # Update the active show unless output is blacked out
    def update(self) -> ScheduleState:
        elapsed = self.elapsed()

        if self.is_blackout:
            return schedule_show(self.show, elapsed)

        return self.engine.update(elapsed)

    # Black out the rig and stop the controller
    def stop(self) -> None:
        self.blackout()
        self.running = False
        