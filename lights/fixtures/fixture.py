# lights/fixtures/fixture.py

from pathlib import Path
from typing import Any

import yaml


# DMX universe size
DMX_CHANNELS = 512


# Load and validate a fixture definition from YAML
def load_fixture_config(path: str | Path) -> dict[str, Any]:
    path = Path(path)

    with path.open("r", encoding="utf-8") as file:
        config = yaml.safe_load(file)

    if not isinstance(config, dict):
        raise ValueError(f"Invalid fixture config: {path}")

    required_sections = {
        "fixture",
        "defaults",
        "channels",
    }

    missing = required_sections - config.keys()

    if missing:
        raise ValueError(f"Fixture config is missing sections: {sorted(missing)}")

    return config


# Represent one physical DMX fixture and its current semantic state
class Fixture:
    def __init__(
        self,
        config: dict[str, Any],
        start_address: int = 1,
    ) -> None:
        self.config = config
        self.start_address = start_address

        self.fixture_config = config["fixture"]
        self.channels = config["channels"]
        self.positions = config.get("positions", {})
        self.defaults = config["defaults"]

        self.channel_count = int(self.fixture_config["channel_count"])

        self._validate_start_address()

        # Keep semantic values here rather than raw DMX values
        self.state: dict[str, Any] = {}

        self.reset()

    # Ensure the fixture fits inside one 512-channel DMX universe
    def _validate_start_address(self) -> None:
        if not 1 <= self.start_address <= DMX_CHANNELS:
            raise ValueError(f"Start address must be between 1 and {DMX_CHANNELS}")

        last_channel = self.start_address + self.channel_count - 1

        if last_channel > DMX_CHANNELS:
            raise ValueError("Fixture extends beyond the end of the DMX universe")

    # Restore the fixture to the defaults defined in its YAML config
    def reset(self) -> None:
        self.state = dict(self.defaults)

    # Set one semantic fixture control
    def set(
        self,
        control: str,
        value: Any,
    ) -> None:
        if control not in self.channels:
            raise ValueError(f"Unknown fixture control: {control}")

        self._validate_control_value(control=control, value=value)

        self.state[control] = value

    # Set several fixture controls at once
    def set_many(
        self,
        **controls: Any,
    ) -> None:
        for control, value in controls.items():
            self.set(control, value)

    # Read the current semantic value of one control
    def get(
        self,
        control: str,
    ) -> Any:
        if control not in self.state:
            raise ValueError(f"Unknown fixture control: {control}")

        return self.state[control]

    # Validate a semantic value before storing it
    def _validate_control_value(
        self,
        control: str,
        value: Any,
    ) -> None:
        channel_config = self.channels[control]
        control_type = channel_config["type"]

        if control == "position" and isinstance(value, str):
            if value not in self.positions:
                raise ValueError(f"Unknown position: {value}")

            return

        if control_type == "boolean":
            if not isinstance(value, bool):
                raise ValueError(f"{control} expects True or False")

            return

        if control_type == "continuous":
            if not isinstance(value, int):
                raise ValueError(f"{control} expects an integer")

            minimum, maximum = channel_config.get("range", [0, 255])

            if not minimum <= value <= maximum:
                raise ValueError(f"{control} must be between " f"{minimum} and {maximum}")

            return

        raise ValueError(f"Unsupported control type: {control_type}")

    # Convert a semantic fixture value into its raw DMX value
    def _encode_value(
        self,
        control: str,
        value: Any,
    ) -> int:
        channel_config = self.channels[control]
        control_type = channel_config["type"]

        # Resolve named motor positions such as "centre"
        if control == "position" and isinstance(value, str):
            return int(self.positions[value])

        # Resolve boolean controls through their fixture mapping
        if control_type == "boolean":
            values = channel_config["values"]

            # PyYAML normally parses false/true keys as booleans
            if value in values:
                return int(values[value])

            # Also tolerate string keys if the YAML parser/config changes
            key = "true" if value else "false"

            if key in values:
                return int(values[key])

            raise ValueError(f"No DMX mapping for {control}={value}")

        # Continuous controls are already expressed as raw 0-255 values
        if control_type == "continuous":
            return int(value)

        raise ValueError(f"Unsupported control type: {control_type}")

    # Resolve a fixture-relative channel into an absolute DMX channel
    def _absolute_channel(
        self,
        relative_channel: int,
    ) -> int:
        return self.start_address + relative_channel - 1

    # Render the current fixture state into a complete DMX universe
    def render(self) -> bytearray:
        dmx = bytearray(DMX_CHANNELS)

        for control, channel_config in self.channels.items():
            if control not in self.state:
                continue

            relative_channel = int(channel_config["channel"])

            absolute_channel = self._absolute_channel(relative_channel)

            value = self._encode_value(control=control, value=self.state[control])

            # Python arrays are zero-indexed while DMX addresses are one-indexed
            dmx[absolute_channel - 1] = value

        return dmx
    