# lights/show/scheduler.py

import hashlib
import random
from dataclasses import dataclass
from typing import Any


# Layers currently supported by the show engine
SHOW_LAYERS = (
    "colour",
    "movement",
    "intensity",
    "strobe",
)


# One scheduled effect and its local elapsed time
@dataclass(frozen=True)
class ScheduledEffect:
    config: dict[str, Any]
    elapsed: float


# Complete scheduled state at one point in the show
@dataclass(frozen=True)
class ScheduleState:
    phase_name: str
    phase_index: int
    phase_elapsed: float
    effects: dict[str, ScheduledEffect]


# Build a stable integer seed from several deterministic values
def stable_seed(*values: Any) -> int:
    text = "|".join(str(value) for value in values)
    digest = hashlib.sha256(text.encode("utf-8")).digest()

    return int.from_bytes(digest[:8], byteorder="big")


# Find the active phase and elapsed time within that phase
def get_phase(show: dict[str, Any], elapsed: float) -> tuple[int, dict[str, Any], float]:
    if elapsed < 0:
        raise ValueError("Elapsed time cannot be negative")

    phases = show["phases"]
    phase_start = 0.0

    for index, phase in enumerate(phases):
        phase_end = phase_start + phase["duration"]

        if elapsed < phase_end:
            return index, phase, elapsed - phase_start

        phase_start = phase_end

    # Keep the final phase running after the configured show duration
    final_index = len(phases) - 1
    final_phase = phases[final_index]
    final_phase_start = phase_start - final_phase["duration"]

    return final_index, final_phase, elapsed - final_phase_start


# Select the active effect for one layer
def schedule_layer(layer: dict[str, Any], elapsed: float, seed: int, phase_name: str, layer_name: str) -> ScheduledEffect:
    if "choices" not in layer:
        return ScheduledEffect(config=layer, elapsed=elapsed)

    change_every = layer["change_every"]
    step = int(elapsed // change_every)
    effect_elapsed = elapsed - step * change_every

    rng = random.Random(stable_seed(seed, phase_name, layer_name, step))
    choice = rng.choice(layer["choices"])

    return ScheduledEffect(config=choice, elapsed=effect_elapsed)


# Resolve the complete show state for one elapsed time
def schedule_show(show: dict[str, Any], elapsed: float) -> ScheduleState:
    phase_index, phase, phase_elapsed = get_phase(show=show, elapsed=elapsed)

    effects = {}

    for layer_name in SHOW_LAYERS:
        effects[layer_name] = schedule_layer(
            layer=phase[layer_name],
            elapsed=phase_elapsed,
            seed=show["seed"],
            phase_name=phase["name"],
            layer_name=layer_name,
        )

    return ScheduleState(
        phase_name=phase["name"],
        phase_index=phase_index,
        phase_elapsed=phase_elapsed,
        effects=effects,
    )
