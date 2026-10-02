# lights/effects/strobe.py

import random


# Return one fixed strobe value
def static_strobe(value: int = 0) -> int:
    if not 0 <= value <= 255:
        raise ValueError("Strobe value must be between 0 and 255")

    return value


# Trigger a regular strobe burst within each interval
def strobe_burst(
    elapsed: float,
    interval: float,
    duration: float,
    value: int = 128,
) -> int:
    if interval <= 0:
        raise ValueError("Interval must be greater than zero")

    if duration < 0:
        raise ValueError("Duration cannot be negative")

    if duration > interval:
        raise ValueError("Duration cannot exceed interval")

    if not 0 <= value <= 255:
        raise ValueError("Strobe value must be between 0 and 255")

    phase = elapsed % interval

    return value if phase < duration else 0


# Trigger deterministic random strobe bursts on a per-minute basis
def random_strobe_burst(
    elapsed: float,
    chance_per_minute: float,
    duration: float,
    seed: int,
    value: int = 128,
) -> int:
    if not 0.0 <= chance_per_minute <= 1.0:
        raise ValueError("Chance per minute must be between 0.0 and 1.0")

    if not 0.0 <= duration <= 60.0:
        raise ValueError("Duration must be between 0 and 60 seconds")

    if not 0 <= value <= 255:
        raise ValueError("Strobe value must be between 0 and 255")

    minute = int(elapsed // 60)
    elapsed_in_minute = elapsed % 60

    rng = random.Random(seed + minute)

    if rng.random() >= chance_per_minute:
        return 0

    burst_start = rng.uniform(0.0, max(0.0, 60.0 - duration))
    burst_end = burst_start + duration

    return value if burst_start <= elapsed_in_minute < burst_end else 0
