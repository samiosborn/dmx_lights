# tools/light_cli.py

import argparse
import threading
import time
from pathlib import Path

from lights.fixtures.fixture import Fixture, load_fixture_config
from lights.rig import Rig


# Physical rig configuration
CONFIG = Path(__file__).resolve().parents[1] / "config/rig.yaml"


# Load and validate the YAML fixture definition
def load_config(path: Path) -> dict:
    return load_fixture_config(path)


# Manage configured controls and continuous Art-Net output
class LightController:
    # Initialize configured controls and the sender thread
    def __init__(self, rig: Rig, fixture_name: str, config: dict | None = None):
        self.rig = rig
        self.fixture = rig.get_fixture(fixture_name)
        self.config = config if config is not None else self.fixture.config
        config = self.config
        self.start_address = self.fixture.start_address
        self.transport = rig.transports[rig.fixture_nodes[fixture_name]]

        self.target = self.transport.target_ip
        self.port = self.transport.port
        self.universe = self.transport.universe
        self.hz = 40.0

        # Render the semantic defaults into the initial DMX state
        self.dmx = rig.render_node(rig.fixture_nodes[fixture_name])
        if config is not self.fixture.config:
            self._apply_fixture_frame(Fixture(config, start_address=self.start_address).render())
        self.lock = threading.Lock()
        self.running = True

        self.channels_by_number = {
            self.start_address + int(data["channel"]) - 1: {**data, "name": name}
            for name, data in config["channels"].items()
        }
        self.channel_by_name = {
            name.lower(): self.start_address + int(data["channel"]) - 1
            for name, data in config["channels"].items()
        }

        self.local_ip = self.transport.local_ip

        self.thread = threading.Thread(target=self._sender, daemon=True)
        self.thread.start()

    # Replace only the selected fixture's channels in the node frame
    def _apply_fixture_frame(self, frame):
        start = self.start_address - 1
        end = start + int(self.config["fixture"]["channel_count"])
        self.dmx[start:end] = frame[start:end]

    # Transmit DMX state at the configured rate
    def _sender(self):
        delay = 1.0 / self.hz

        while self.running:
            with self.lock:
                frame = bytes(self.dmx)

            self.transport.send(frame)

            time.sleep(delay)

    # Validate and update a raw channel
    def set_channel(self, channel: int, value: int):
        if not 1 <= channel <= 512:
            raise ValueError("Channel must be 1..512")
        if not 0 <= value <= 255:
            raise ValueError("Value must be 0..255")

        with self.lock:
            self.dmx[channel - 1] = value

    # Resolve channel numbers, configured names, or unique prefixes
    def resolve_control(self, control: str) -> int:
        control = control.lower()

        if control.isdigit():
            channel = int(control)
            if 1 <= channel <= 512:
                return channel
            raise ValueError("Channel must be 1..512")

        if control in self.channel_by_name:
            return self.channel_by_name[control]

        matches = [
            (name, ch)
            for name, ch in self.channel_by_name.items()
            if name.startswith(control)
        ]

        if len(matches) == 1:
            return matches[0][1]

        if len(matches) > 1:
            names = ", ".join(name for name, _ in matches)
            raise ValueError(f"Ambiguous control {control!r}: {names}")

        raise ValueError(f"Unknown control: {control}")

    # Parse values using the configured channel type
    def parse_value_for_channel(self, channel: int, raw_value: str) -> int:
        data = self.channels_by_number.get(channel)
        if data is None:
            value = int(raw_value)
            if not 0 <= value <= 255:
                raise ValueError("Value must be 0..255")
            return value

        token = raw_value.lower()
        if data["type"] == "boolean":
            if token in {"on", "true", "yes", "1"}:
                value = True
            elif token in {"off", "false", "no", "0"}:
                value = False
            else:
                raise ValueError(f"{data['name']} is boolean; use on/off")
        elif data["name"] == "position" and token in self.config.get("positions", {}):
            value = token
        else:
            value = int(raw_value)

        # Delegate semantic validation and DMX encoding to the shared fixture
        fixture = Fixture(self.config, start_address=self.start_address)
        fixture.set(data["name"], value)
        return fixture.render()[channel - 1]

    # Set a control through its configured name
    def set_named(self, control: str, raw_value: str):
        channel = self.resolve_control(control)
        value = self.parse_value_for_channel(channel, raw_value)
        self.set_channel(channel, value)
        return channel, value

    # Toggle sound-reactive effects using configured values
    def set_sound(self, enabled: bool):
        return self.set_named("sound_reactive", "on" if enabled else "off")

    # Replace DMX state with a configured preset
    def apply_preset(self, name: str):
        presets = self.config.get("presets", {})

        if name not in presets:
            raise ValueError(
                f"Unknown preset {name!r}. "
                f"Available: {', '.join(sorted(presets))}"
            )

        # Presets use semantic control names from the YAML definition
        fixture = Fixture(self.config, start_address=self.start_address)
        fixture.set_many(**presets[name])
        with self.lock:
            self._apply_fixture_frame(fixture.render())

    # Turn off the master dimmer
    def blackout(self):
        dimmer_channel = self.channel_by_name.get("master_dimmer")
        if dimmer_channel is None:
            raise ValueError("No master_dimmer channel in config")

        self.set_channel(dimmer_channel, 0)

    # Clear every DMX channel
    def zero(self):
        with self.lock:
            self.dmx[:] = bytes(512)

    # Display boolean values as on/off
    def format_value(self, channel: int, value: int) -> str:
        data = self.channels_by_number.get(channel, {})
        if data.get("type") == "boolean":
            values = data.get("values", {})
            if value == values.get(True, values.get("true", 255)):
                return "on"
            if value == values.get(False, values.get("false", 0)):
                return "off"
        return str(value)

    # Show the current values of configured channels
    def status(self):
        rows = []
        with self.lock:
            for channel in sorted(self.channels_by_number):
                data = self.channels_by_number[channel]
                value = self.dmx[channel - 1]
                rows.append(
                    (
                        channel,
                        data.get("name", "unknown"),
                        self.format_value(channel, value),
                    )
                )

        width = max(len(name) for _, name, _ in rows)

        for channel, name, value in rows:
            print(
                f"CH{channel:>2}  "
                f"{name:<{width}}  "
                f"{value:>5}"
            )

    # Describe configured controls and observations
    def list_controls(self):
        for channel in sorted(self.channels_by_number):
            data = self.channels_by_number[channel]
            name = data.get("name", "unknown")
            channel_type = data.get("type", "continuous")
            notes = data.get("notes", [])

            print(f"CH{channel:>2}  {name:<22} ({channel_type})")

            if channel_type == "boolean":
                values = data.get("values", {})
                if values:
                    print(
                        "      "
                        + ", ".join(f"{k}={v}" for k, v in values.items())
                    )

            for note in notes:
                print(f"      {note}")

            observations = data.get("known_values", {})
            for value, observation in observations.items():
                print(f"      {value:>3}: {observation}")

    # List available presets
    def list_presets(self):
        presets = self.config.get("presets", {})
        if not presets:
            print("No presets configured")
        for name in sorted(presets):
            print(name)

    # Stop transmission and close the transport
    def close(self):
        self.running = False
        self.thread.join(timeout=1)
        self.rig.close()


# Interactive command reference
HELP = """
Commands

  set CONTROL VALUE      Set a named control or raw channel
  raw CH VALUE           Set a raw DMX channel value

  sound on|off           Toggle sound-reactive mode for CH9 effects

  preset NAME            Apply a preset from the YAML config
  presets                List presets

  status                 Show current values for configured channels
  controls               Show channel names, types and notes

  blackout               Set master dimmer to 0, keep other state
  zero                   Set all 512 channels to 0

  help                    Show this help
  quit                    Exit

Examples

  set position centre
  set position 128
  set motor_speed 128
  set master_dimmer 255
  set red 255
  set strobe 0
  set builtin_effect 60

  set sound_reactive on
  sound on
  sound off

  raw 9 128

  presets

Notes

  - Fixture and channel mapping are selected through config/rig.yaml.
  - CH10 is treated as a boolean sound-reactive switch:
      off = 0
      on  = 255
  - Use uv run python -m tools.dmx_cli for low-level raw channel debugging.
"""


# Start the controller and process interactive commands
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Named CLI controller for the ZQ06141 via Art-Net."
    )
    parser.add_argument(
        "--config",
        type=Path,
        help="Override the selected fixture YAML definition",
    )
    parser.add_argument("--rig", type=Path, default=CONFIG, help="Path to physical rig YAML config")
    parser.add_argument("--fixture", help="Fixture instance name (required when the rig has multiple fixtures)")
    args = parser.parse_args()

    rig = None
    try:
        config = load_config(args.config) if args.config else None
        rig = Rig(args.rig)
        fixture_name = args.fixture
        if fixture_name is None:
            if len(rig.fixtures) != 1:
                raise ValueError("Specify --fixture when the rig does not contain exactly one fixture")
            fixture_name = next(iter(rig.fixtures))
        controller = LightController(rig, fixture_name, config)
    except (OSError, ValueError) as exc:
        if rig is not None:
            rig.close()
        print(f"Could not start Art-Net output: {exc}")
        print("Check the rig configuration and network connection.")
        return

    # Show connection settings before accepting commands
    fixture = controller.config["fixture"]

    print()
    print(f"{fixture['name']} controller ({fixture['mode']})")
    print("-" * 36)
    print(f"Rig      : {args.rig}")
    print(f"Fixture  : {fixture_name}")
    if args.config:
        print(f"Config   : {args.config}")
    print(f"Local IP : {controller.local_ip}")
    print(f"Target   : {controller.target}:{controller.port}")
    print(f"Universe : {controller.universe}")
    print(f"Rate     : {controller.hz:g} Hz")
    print()
    print("Type 'help' for commands.")
    print()

    # Dispatch commands to the config-driven controller
    try:
        while True:
            try:
                line = input("light> ").strip()
            except EOFError:
                break

            if not line:
                continue

            parts = line.split()
            cmd = parts[0].lower()

            try:
                if cmd == "set":
                    if len(parts) != 3:
                        print("Usage: set CONTROL VALUE")
                        continue

                    control = parts[1]
                    channel, value = controller.set_named(control, parts[2])

                    data = controller.channels_by_number.get(channel, {})
                    name = data.get("name", f"CH{channel}")
                    display_value = controller.format_value(channel, value)
                    print(f"{name} (CH{channel}) = {display_value}")

                elif cmd == "raw":
                    if len(parts) != 3:
                        print("Usage: raw CH VALUE")
                        continue

                    channel = int(parts[1])
                    value = int(parts[2])
                    controller.set_channel(channel, value)
                    print(f"CH{channel} = {value}")

                elif cmd == "sound":
                    if len(parts) != 2 or parts[1].lower() not in {"on", "off"}:
                        print("Usage: sound on|off")
                        continue

                    enabled = parts[1].lower() == "on"
                    channel, value = controller.set_sound(enabled)
                    print(
                        f"sound_reactive (CH{channel}) = "
                        f"{'on' if enabled else 'off'}"
                    )

                elif cmd == "preset":
                    if len(parts) != 2:
                        print("Usage: preset NAME")
                        continue

                    controller.apply_preset(parts[1])
                    print(f"Preset: {parts[1]}")

                elif cmd == "presets":
                    controller.list_presets()

                elif cmd == "status":
                    controller.status()

                elif cmd == "controls":
                    controller.list_controls()

                elif cmd == "blackout":
                    controller.blackout()
                    print("Master dimmer = 0")

                elif cmd == "zero":
                    controller.zero()
                    print("All channels = 0")

                elif cmd in {"help", "?"}:
                    print(HELP)

                elif cmd in {"quit", "exit", "q"}:
                    break

                else:
                    print(f"Unknown command: {cmd}")

            except ValueError as exc:
                print(f"Error: {exc}")

    except KeyboardInterrupt:
        print()

    finally:
        controller.close()

    print("Stopped.")


# Run only when invoked as a module
if __name__ == "__main__":
    main()
