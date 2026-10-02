# lights/effects/intensity.py

import math


# Return one fixed brightness level
def static_intensity(value: float) -> float:
    if not 0.0 <= value <= 1.0:
        raise ValueError("Intensity must be between 0.0 and 1.0")

    return value


# Smoothly pulse brightness between minimum and maximum
def pulse(
    elapsed: float,
    period: float,
    minimum: float = 0.0,
    maximum: float = 1.0,
) -> float:
    if period <= 0:
        raise ValueError("Period must be greater than zero")

    if not 0.0 <= minimum <= 1.0:
        raise ValueError("Minimum intensity must be between 0.0 and 1.0")

    if not 0.0 <= maximum <= 1.0:
        raise ValueError("Maximum intensity must be between 0.0 and 1.0")

    if minimum > maximum:
        raise ValueError("Minimum intensity cannot be greater than maximum intensity")

    phase = 2 * math.pi * elapsed / period
    amount = (math.sin(phase) + 1.0) / 2.0

    return minimum + (maximum - minimum) * amount
