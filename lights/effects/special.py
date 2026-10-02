# lights/effects/special.py

import random


# Return one fixed built-in fixture effect value
def builtin_effect(value: int = 0) -> int:
    if not 0 <= value <= 255:
        raise ValueError("Built-in effect value must be between 0 and 255")

    return value


# Step through a sequence of built-in fixture effects
def builtin_effect_sequence(
    values: list[int],
    elapsed: float,
    interval: float,
) -> int:
    if not values:
        raise ValueError("Built-in effect values cannot be empty")

    if interval <= 0:
        raise ValueError("Interval must be greater than zero")

    for value in values:
        if not 0 <= value <= 255:
            raise ValueError("Built-in effect values must be between 0 and 255")

    index = int(elapsed // interval) % len(values)

    return values[index]


# Choose a deterministic random built-in fixture effect at each interval
def random_builtin_effect(
    values: list[int],
    elapsed: float,
    interval: float,
    seed: int,
) -> int:
    if not values:
        raise ValueError("Built-in effect values cannot be empty")

    if interval <= 0:
        raise ValueError("Interval must be greater than zero")

    for value in values:
        if not 0 <= value <= 255:
            raise ValueError("Built-in effect values must be between 0 and 255")

    step = int(elapsed // interval)
    rng = random.Random(seed + step)

    return rng.choice(values)


# Return whether the fixture sound-reactive mode is enabled
def sound_reactive(enabled: bool = False) -> bool:
    if not isinstance(enabled, bool):
        raise ValueError("Sound reactive must be True or False")

    return enabled
