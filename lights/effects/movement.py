# lights/effects/movement.py

import random
from dataclasses import dataclass


# Semantic movement state returned by movement effects
@dataclass(frozen=True)
class Movement:
    position: str | int
    motor_speed: int


# Return one fixed position
def static_position(
    position: str | int,
    motor_speed: int = 128,
) -> Movement:
    return Movement(
        position=position,
        motor_speed=motor_speed,
    )


# Alternate smoothly between two fixture positions
# The fixture handles the physical interpolation using its own motor controller
def sweep(
    elapsed: float,
    period: float,
    start: str | int = "left",
    end: str | int = "right",
    motor_speed: int = 128,
) -> Movement:
    if period <= 0:
        raise ValueError("Period must be greater than zero")

    half_period = period / 2
    phase = elapsed % period

    position = start if phase < half_period else end

    return Movement(
        position=position,
        motor_speed=motor_speed,
    )


# Step through a sequence of named or raw positions
def position_sequence(
    positions: list[str | int],
    elapsed: float,
    interval: float,
    motor_speed: int = 128,
) -> Movement:
    if not positions:
        raise ValueError("Positions cannot be empty")

    if interval <= 0:
        raise ValueError("Interval must be greater than zero")

    index = int(elapsed // interval) % len(positions)

    return Movement(
        position=positions[index],
        motor_speed=motor_speed,
    )


# Choose a deterministic random position at each interval
def random_position(
    positions: list[str | int],
    elapsed: float,
    interval: float,
    seed: int,
    motor_speed: int = 128,
) -> Movement:
    if not positions:
        raise ValueError("Positions cannot be empty")

    if interval <= 0:
        raise ValueError("Interval must be greater than zero")

    step = int(elapsed // interval)
    rng = random.Random(seed + step)

    return Movement(
        position=rng.choice(positions),
        motor_speed=motor_speed,
    )
