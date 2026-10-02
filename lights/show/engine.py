# lights/show/engine.py

from typing import Any

from lights.effects.colour import Colour, palette_fade, palette_step, random_colour, rainbow, static_colour
from lights.effects.intensity import pulse, static_intensity
from lights.effects.movement import Movement, position_sequence, random_position, static_position, sweep
from lights.effects.strobe import random_strobe_burst, static_strobe, strobe_burst
from lights.rig import Rig
from lights.show.scheduler import ScheduleState, schedule_show, stable_seed


# Convert a normalised 0-1 value into an 8-bit DMX value
def to_dmx(value: float) -> int:
    value = max(0.0, min(1.0, value))
    return round(value * 255)


# Resolve a named colour
def get_colour(name: str, colours: dict[str, Colour]) -> Colour:
    if name not in colours:
        raise ValueError(f"Unknown colour: {name}")

    return colours[name]


# Resolve a named palette
def get_palette(name: str, palettes: dict[str, list[Colour]]) -> list[Colour]:
    if name not in palettes:
        raise ValueError(f"Unknown palette: {name}")

    return palettes[name]


# Evaluate one colour effect
def evaluate_colour(config: dict[str, Any], elapsed: float, colours: dict[str, Colour], palettes: dict[str, list[Colour]], seed: int) -> Colour:
    effect = config["effect"]

    if effect == "static_colour":
        return static_colour(get_colour(config["colour"], colours))

    if effect == "palette_fade":
        return palette_fade(
            palette=get_palette(config["palette"], palettes),
            elapsed=elapsed,
            period=config["period"],
        )

    if effect == "palette_step":
        return palette_step(
            palette=get_palette(config["palette"], palettes),
            elapsed=elapsed,
            period=config["interval"],
        )

    if effect == "random_colour":
        return random_colour(
            palette=get_palette(config["palette"], palettes),
            elapsed=elapsed,
            interval=config["interval"],
            seed=seed,
        )

    if effect == "rainbow":
        return rainbow(
            elapsed=elapsed,
            period=config["period"],
            saturation=float(config.get("saturation", 1.0)),
            brightness=float(config.get("brightness", 1.0)),
            direction=config.get("direction", "forward"),
        )

    raise ValueError(f"Unsupported colour effect: {effect}")


# Evaluate one movement effect
def evaluate_movement(config: dict[str, Any], elapsed: float, seed: int) -> Movement:
    effect = config["effect"]
    motor_speed = int(config.get("motor_speed", 128))

    if effect == "static_position":
        return static_position(
            position=config["position"],
            motor_speed=motor_speed,
        )

    if effect == "sweep":
        return sweep(
            elapsed=elapsed,
            period=config["period"],
            start=config.get("start", "left"),
            end=config.get("end", "right"),
            motor_speed=motor_speed,
        )

    if effect == "position_sequence":
        return position_sequence(
            positions=config["positions"],
            elapsed=elapsed,
            interval=config["interval"],
            motor_speed=motor_speed,
        )

    if effect == "random_position":
        return random_position(
            positions=config["positions"],
            elapsed=elapsed,
            interval=config["interval"],
            seed=seed,
            motor_speed=motor_speed,
        )

    raise ValueError(f"Unsupported movement effect: {effect}")


# Evaluate one intensity effect
def evaluate_intensity(config: dict[str, Any], elapsed: float) -> float:
    effect = config["effect"]

    if effect == "static_intensity":
        return static_intensity(float(config["value"]))

    if effect == "pulse":
        return pulse(
            elapsed=elapsed,
            period=config["period"],
            minimum=float(config["minimum"]),
            maximum=float(config["maximum"]),
        )

    raise ValueError(f"Unsupported intensity effect: {effect}")


# Evaluate one strobe effect
def evaluate_strobe(config: dict[str, Any], elapsed: float, seed: int) -> int:
    effect = config["effect"]

    if effect == "static_strobe":
        return static_strobe(int(config.get("value", 0)))

    if effect == "strobe_burst":
        return strobe_burst(
            elapsed=elapsed,
            interval=config["interval"],
            duration=config["duration"],
            value=int(config.get("value", 128)),
        )

    if effect == "random_strobe_burst":
        return random_strobe_burst(
            elapsed=elapsed,
            chance_per_minute=float(config["chance_per_minute"]),
            duration=config["duration"],
            seed=seed,
            value=int(config.get("value", 128)),
        )

    raise ValueError(f"Unsupported strobe effect: {effect}")


# Evaluate scheduled effects and apply them to the physical rig
class ShowEngine:
    def __init__(self, rig: Rig, show: dict[str, Any], colours: dict[str, Colour], palettes: dict[str, list[Colour]]) -> None:
        self.rig = rig
        self.show = show
        self.colours = colours
        self.palettes = palettes

        self._validate_fixtures()

    # Check every fixture referenced by the show exists in the rig
    def _validate_fixtures(self) -> None:
        for fixture_name in self.show["fixtures"]:
            if fixture_name not in self.rig.fixtures:
                raise ValueError(f"Show references unknown fixture: {fixture_name}")

    # Build a deterministic seed for an effect within its current scheduling window
    def _effect_seed(self, state: ScheduleState, layer_name: str) -> int:
        layer = self.show["phases"][state.phase_index][layer_name]

        if "choices" in layer:
            step = int(state.phase_elapsed // layer["change_every"])
        else:
            step = 0

        return stable_seed(
            self.show["seed"],
            state.phase_name,
            layer_name,
            step,
            "effect",
        )

    # Evaluate the show at one elapsed time and send the resulting DMX frame
    def update(self, elapsed: float) -> ScheduleState:
        state = schedule_show(show=self.show, elapsed=elapsed)

        colour_effect = state.effects["colour"]
        movement_effect = state.effects["movement"]
        intensity_effect = state.effects["intensity"]
        strobe_effect = state.effects["strobe"]

        colour = evaluate_colour(
            config=colour_effect.config,
            elapsed=colour_effect.elapsed,
            colours=self.colours,
            palettes=self.palettes,
            seed=self._effect_seed(state, "colour"),
        )

        movement = evaluate_movement(
            config=movement_effect.config,
            elapsed=movement_effect.elapsed,
            seed=self._effect_seed(state, "movement"),
        )

        intensity = evaluate_intensity(
            config=intensity_effect.config,
            elapsed=intensity_effect.elapsed,
        )

        strobe = evaluate_strobe(
            config=strobe_effect.config,
            elapsed=strobe_effect.elapsed,
            seed=self._effect_seed(state, "strobe"),
        )

        for fixture_name in self.show["fixtures"]:
            fixture = self.rig.get_fixture(fixture_name)

            fixture.set_many(
                position=movement.position,
                motor_speed=movement.motor_speed,
                master_dimmer=to_dmx(intensity),
                strobe=strobe,
                red=to_dmx(colour.r),
                green=to_dmx(colour.g),
                blue=to_dmx(colour.b),
                white=to_dmx(colour.w),
            )

        self.rig.send()

        return state