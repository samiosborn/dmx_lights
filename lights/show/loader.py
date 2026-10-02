# lights/show/loader.py

from pathlib import Path
from typing import Any

import yaml


# Time suffixes supported by show YAML files
TIME_UNITS = {
    "s": 1.0,
    "m": 60.0,
    "h": 3600.0,
}

TIME_FIELDS = {
    "duration",
    "change_every",
    "period",
    "interval",
}


# Required fields for each supported effect
EFFECT_FIELDS = {
    "colour": {
        "static_colour": {"colour"},
        "palette_fade": {"palette", "period"},
        "palette_step": {"palette", "period"},
        "random_colour": {"palette", "interval"},
        "rainbow": {"period"},
    },
    "movement": {
        "static_position": {"position"},
        "sweep": {"period"},
        "position_sequence": {"positions", "interval"},
        "random_position": {"positions", "interval"},
    },
    "intensity": {
        "static_intensity": {"value"},
        "pulse": {"minimum", "maximum", "period"},
    },
    "strobe": {
        "static_strobe": set(),
        "strobe_burst": {"interval", "duration"},
        "random_strobe_burst": {"chance_per_minute", "duration"},
    },
}


# Convert values such as 2.5s, 5m and 1h into seconds
def parse_duration(value: str | int | float) -> float:
    if isinstance(value, int | float):
        seconds = float(value)

        if seconds < 0:
            raise ValueError("Duration cannot be negative")

        return seconds

    if not isinstance(value, str):
        raise ValueError(f"Invalid duration: {value}")

    value = value.strip().lower()

    if len(value) < 2:
        raise ValueError(f"Invalid duration: {value}")

    unit = value[-1]

    if unit not in TIME_UNITS:
        raise ValueError(f"Unsupported duration unit: {value}")

    try:
        amount = float(value[:-1])
    except ValueError as exc:
        raise ValueError(f"Invalid duration: {value}") from exc

    if amount < 0:
        raise ValueError("Duration cannot be negative")

    return amount * TIME_UNITS[unit]


# Recursively convert timing fields into seconds
def normalise_times(value: Any) -> Any:
    if isinstance(value, list):
        return [normalise_times(item) for item in value]

    if not isinstance(value, dict):
        return value

    normalised = {}

    for key, item in value.items():
        if key in TIME_FIELDS:
            normalised[key] = parse_duration(item)
        else:
            normalised[key] = normalise_times(item)

    return normalised


# Validate a numeric value lies inside a range
def validate_range(value: Any, minimum: float, maximum: float, context: str) -> None:
    if not isinstance(value, int | float):
        raise ValueError(f"{context} must be numeric")

    if not minimum <= value <= maximum:
        raise ValueError(f"{context} must be between {minimum} and {maximum}")


# Validate required effect fields are present
def validate_required_fields(effect: dict[str, Any], required: set[str], context: str) -> None:
    missing = required - effect.keys()

    if missing:
        raise ValueError(f"{context} is missing fields: {sorted(missing)}")


# Validate shared timing fields
def validate_effect_times(effect: dict[str, Any], context: str) -> None:
    for field in ("period", "interval"):
        if field in effect and effect[field] <= 0:
            raise ValueError(f"{context} {field} must be greater than zero")

    if "duration" in effect and effect["duration"] < 0:
        raise ValueError(f"{context} duration cannot be negative")


# Validate effect-specific values
def validate_effect_values(effect: dict[str, Any], layer_name: str, context: str) -> None:
    effect_name = effect["effect"]

    validate_effect_times(effect, context)

    if layer_name == "colour":
        if "colour" in effect and not isinstance(effect["colour"], str):
            raise ValueError(f"{context} colour must be a string")

        if "palette" in effect and not isinstance(effect["palette"], str):
            raise ValueError(f"{context} palette must be a string")

        if "saturation" in effect:
            validate_range(effect["saturation"], 0.0, 1.0, f"{context} saturation")

        if "brightness" in effect:
            validate_range(effect["brightness"], 0.0, 1.0, f"{context} brightness")

        if "direction" in effect and effect["direction"] not in {"forward", "reverse"}:
            raise ValueError(f"{context} direction must be 'forward' or 'reverse'")

    if layer_name == "movement":
        if "positions" in effect:
            positions = effect["positions"]

            if not isinstance(positions, list) or not positions:
                raise ValueError(f"{context} positions must be a non-empty list")

        if "motor_speed" in effect:
            validate_range(effect["motor_speed"], 0, 255, f"{context} motor_speed")

    if layer_name == "intensity":
        if effect_name == "static_intensity":
            validate_range(effect["value"], 0.0, 1.0, f"{context} value")

        if effect_name == "pulse":
            validate_range(effect["minimum"], 0.0, 1.0, f"{context} minimum")
            validate_range(effect["maximum"], 0.0, 1.0, f"{context} maximum")

            if effect["minimum"] > effect["maximum"]:
                raise ValueError(f"{context} minimum cannot exceed maximum")

    if layer_name == "strobe":
        if "value" in effect:
            validate_range(effect["value"], 0, 255, f"{context} value")

        if effect_name == "strobe_burst" and effect["duration"] > effect["interval"]:
            raise ValueError(f"{context} duration cannot exceed interval")

        if effect_name == "random_strobe_burst":
            validate_range(effect["chance_per_minute"], 0.0, 1.0, f"{context} chance_per_minute")

            if effect["duration"] > 60:
                raise ValueError(f"{context} duration cannot exceed 60 seconds")


# Validate one effect definition
def validate_effect(effect: dict[str, Any], layer_name: str, context: str) -> None:
    if "effect" not in effect:
        raise ValueError(f"{context} is missing an effect")

    effect_name = effect["effect"]

    if not isinstance(effect_name, str):
        raise ValueError(f"{context} effect must be a string")

    supported = EFFECT_FIELDS[layer_name]

    if effect_name not in supported:
        raise ValueError(f"{context} has unsupported effect: {effect_name}")

    validate_required_fields(effect, supported[effect_name], context)
    validate_effect_values(effect, layer_name, context)


# Validate one show layer
def validate_layer(layer: dict[str, Any], layer_name: str, context: str) -> None:
    if "choices" in layer:
        choices = layer["choices"]

        if not isinstance(choices, list) or not choices:
            raise ValueError(f"{context} choices must be a non-empty list")

        if "change_every" not in layer:
            raise ValueError(f"{context} with choices requires change_every")

        if layer["change_every"] <= 0:
            raise ValueError(f"{context} change_every must be greater than zero")

        for index, choice in enumerate(choices):
            if not isinstance(choice, dict):
                raise ValueError(f"{context} choice {index} must be a mapping")

            validate_effect(choice, layer_name, f"{context} choice {index}")

        return

    validate_effect(layer, layer_name, context)


# Validate the overall show structure
def validate_show(show: dict[str, Any]) -> None:
    required = {
        "seed",
        "fixtures",
        "phases",
    }

    missing = required - show.keys()

    if missing:
        raise ValueError(f"Show is missing sections: {sorted(missing)}")

    if not isinstance(show["seed"], int):
        raise ValueError("Show seed must be an integer")

    fixtures = show["fixtures"]

    if not isinstance(fixtures, list) or not fixtures:
        raise ValueError("Show fixtures must be a non-empty list")

    if not all(isinstance(fixture, str) for fixture in fixtures):
        raise ValueError("Show fixture names must be strings")

    phases = show["phases"]

    if not isinstance(phases, list) or not phases:
        raise ValueError("Show phases must be a non-empty list")

    phase_names = set()

    for index, phase in enumerate(phases):
        if not isinstance(phase, dict):
            raise ValueError(f"Phase {index} must be a mapping")

        if "name" not in phase:
            raise ValueError(f"Phase {index} is missing a name")

        name = phase["name"]

        if not isinstance(name, str):
            raise ValueError(f"Phase {index} name must be a string")

        if name in phase_names:
            raise ValueError(f"Duplicate phase name: {name}")

        phase_names.add(name)

        if "duration" not in phase:
            raise ValueError(f"Phase '{name}' is missing a duration")

        if phase["duration"] <= 0:
            raise ValueError(f"Phase '{name}' duration must be greater than zero")

        for layer_name in EFFECT_FIELDS:
            if layer_name not in phase:
                raise ValueError(f"Phase '{name}' is missing {layer_name}")

            layer = phase[layer_name]

            if not isinstance(layer, dict):
                raise ValueError(f"Phase '{name}' {layer_name} must be a mapping")

            validate_layer(layer, layer_name, f"Phase '{name}' {layer_name}")


# Load, normalise and validate a show YAML file
def load_show(path: str | Path) -> dict[str, Any]:
    path = Path(path)

    with path.open("r", encoding="utf-8") as file:
        show = yaml.safe_load(file)

    if not isinstance(show, dict):
        raise ValueError(f"Invalid show config: {path}")

    show = normalise_times(show)
    validate_show(show)

    return show
