# lights/effects/colour.py

import colorsys
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


# Normalised RGBW colour state
@dataclass(frozen=True)
class Colour:
    r: float
    g: float
    b: float
    w: float = 0.0

    def __post_init__(self) -> None:
        for name, value in vars(self).items():
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be between 0.0 and 1.0")


# Load named colours from YAML
def load_colours(path: str | Path) -> dict[str, Colour]:
    path = Path(path)

    with path.open("r", encoding="utf-8") as file:
        config = yaml.safe_load(file)

    if not isinstance(config, dict) or "colours" not in config:
        raise ValueError(f"Invalid colour config: {path}")

    colours: dict[str, Colour] = {}

    for name, values in config["colours"].items():
        colours[name] = Colour(
            r=float(values["r"]),
            g=float(values["g"]),
            b=float(values["b"]),
            w=float(values.get("w", 0.0)),
        )

    return colours


# Load palettes and resolve colour names
def load_palettes(path: str | Path, colours: dict[str, Colour]) -> dict[str, list[Colour]]:
    path = Path(path)

    with path.open("r", encoding="utf-8") as file:
        config = yaml.safe_load(file)

    if not isinstance(config, dict) or "palettes" not in config:
        raise ValueError(f"Invalid palette config: {path}")

    palettes: dict[str, list[Colour]] = {}

    for name, colour_names in config["palettes"].items():
        palette = []

        for colour_name in colour_names:
            if colour_name not in colours:
                raise ValueError(f"Unknown colour '{colour_name}' in palette '{name}'")

            palette.append(colours[colour_name])

        if not palette:
            raise ValueError(f"Palette '{name}' cannot be empty")

        palettes[name] = palette

    return palettes


# Clamp a floating-point value to the normalised colour range
def clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


# Linearly interpolate between two values
def lerp(start: float, end: float, amount: float) -> float:
    return start + (end - start) * amount


# Linearly interpolate between two RGBW colours
def lerp_colour(start: Colour, end: Colour, amount: float) -> Colour:
    amount = clamp(amount)

    return Colour(
        r=lerp(start.r, end.r, amount),
        g=lerp(start.g, end.g, amount),
        b=lerp(start.b, end.b, amount),
        w=lerp(start.w, end.w, amount),
    )


# Return one static colour
def static_colour(colour: Colour) -> Colour:
    return colour


# Smoothly cycle through every colour in a palette
# Period is the duration of one complete loop through the palette (seconds)
def palette_fade(palette: list[Colour], elapsed: float, period: float) -> Colour:
    if not palette:
        raise ValueError("Palette cannot be empty")

    if period <= 0:
        raise ValueError("Period must be greater than zero")

    if len(palette) == 1:
        return palette[0]

    position = (elapsed % period) / period * len(palette)
    index = int(position)
    next_index = (index + 1) % len(palette)
    amount = position - index

    return lerp_colour(palette[index], palette[next_index], amount)


# Step through every colour in a palette without interpolation
def palette_step(palette: list[Colour], elapsed: float, period: float) -> Colour:
    if not palette:
        raise ValueError("Palette cannot be empty")

    if period <= 0:
        raise ValueError("Period must be greater than zero")

    position = (elapsed % period) / period
    index = int(position * len(palette)) % len(palette)

    return palette[index]


# Choose a deterministic random colour at each interval
def random_colour(palette: list[Colour], elapsed: float, interval: float, seed: int) -> Colour:
    if not palette:
        raise ValueError("Palette cannot be empty")

    if interval <= 0:
        raise ValueError("Interval must be greater than zero")

    step = int(elapsed // interval)
    rng = random.Random(seed + step)

    return rng.choice(palette)


# Smoothly rotate around the HSV hue wheel
def rainbow(
    elapsed: float,
    period: float,
    saturation: float = 1.0,
    brightness: float = 1.0,
    direction: str = "forward",
) -> Colour:
    if period <= 0:
        raise ValueError("Period must be greater than zero")

    if direction not in {"forward", "reverse"}:
        raise ValueError("Direction must be 'forward' or 'reverse'")

    saturation = clamp(saturation)
    brightness = clamp(brightness)

    progress = (elapsed % period) / period

    if direction == "reverse":
        progress = 1.0 - progress

    r, g, b = colorsys.hsv_to_rgb(progress, saturation, brightness)

    return Colour(r=r, g=g, b=b, w=0.0)
