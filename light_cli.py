import argparse
import json
import socket
import struct
import threading
import time
from pathlib import Path


ARTNET_PORT_DEFAULT = 6454


def load_config(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def get_local_ip(target: str, port: int) -> str:
    """Ask Windows which local interface/IP it would use to reach the EasyNode."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect((target, port))
        return sock.getsockname()[0]
    finally:
        sock.close()


def build_artdmx(dmx: bytearray, universe: int, sequence: int) -> bytes:
    if not 0 <= universe <= 32767:
        raise ValueError("Universe must be 0..32767")

    subuni = universe & 0xFF
    net = (universe >> 8) & 0x7F

    return (
        b"Art-Net\x00"
        + struct.pack("<H", 0x5000)
        + struct.pack(">H", 14)
        + bytes([sequence, 0])
        + bytes([subuni, net])
        + struct.pack(">H", len(dmx))
        + bytes(dmx)
    )


class LightController:
    def __init__(self, config: dict):
        self.config = config

        artnet = config["fixture"]["artnet"]
        self.target = artnet["target_ip"]
        self.port = int(artnet.get("port", ARTNET_PORT_DEFAULT))
        self.universe = int(artnet.get("universe", 0))
        self.hz = float(artnet.get("refresh_hz", 40))

        self.dmx = bytearray(512)
        self.lock = threading.Lock()
        self.running = True
        self.sequence = 1

        self.channels_by_number = {
            int(number): data
            for number, data in config["channels"].items()
        }

        self.channel_by_name = {
            data["name"].lower(): number
            for number, data in self.channels_by_number.items()
            if data.get("name") and data["name"] != "unknown"
        }

        self.local_ip = get_local_ip(self.target, self.port)

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((self.local_ip, 0))

        self.thread = threading.Thread(target=self._sender, daemon=True)
        self.thread.start()

    def _sender(self):
        delay = 1.0 / self.hz

        while self.running:
            with self.lock:
                packet = build_artdmx(
                    self.dmx,
                    universe=self.universe,
                    sequence=self.sequence,
                )

            self.sock.sendto(packet, (self.target, self.port))

            self.sequence += 1
            if self.sequence > 255:
                self.sequence = 1

            time.sleep(delay)

    def set_channel(self, channel: int, value: int):
        if not 1 <= channel <= 512:
            raise ValueError("Channel must be 1..512")
        if not 0 <= value <= 255:
            raise ValueError("Value must be 0..255")

        with self.lock:
            self.dmx[channel - 1] = value

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

    def parse_value_for_channel(self, channel: int, raw_value: str) -> int:
        data = self.channels_by_number.get(channel, {})
        channel_type = data.get("type", "continuous")

        if channel_type == "boolean":
            values = data.get("values", {"off": 0, "on": 255})
            token = raw_value.lower()

            if token in values:
                return int(values[token])

            if token in {"true", "yes", "1"}:
                return int(values["on"])

            if token in {"false", "no", "0"}:
                return int(values["off"])

            raise ValueError(
                f"{data.get('name', f'CH{channel}')} is boolean; use on/off"
            )

        value = int(raw_value)
        if not 0 <= value <= 255:
            raise ValueError("Value must be 0..255")
        return value

    def set_named(self, control: str, raw_value: str):
        channel = self.resolve_control(control)
        value = self.parse_value_for_channel(channel, raw_value)
        self.set_channel(channel, value)
        return channel, value

    def set_sound(self, enabled: bool):
        channel = self.resolve_control("sound_reactive")
        data = self.channels_by_number[channel]
        values = data.get("values", {"off": 0, "on": 255})
        value = int(values["on" if enabled else "off"])
        self.set_channel(channel, value)
        return channel, value

    def apply_preset(self, name: str):
        presets = self.config.get("presets", {})

        if name not in presets:
            raise ValueError(
                f"Unknown preset {name!r}. "
                f"Available: {', '.join(sorted(presets))}"
            )

        with self.lock:
            self.dmx[:] = bytes(512)
            for channel, value in presets[name].items():
                self.dmx[int(channel) - 1] = int(value)

    def blackout(self):
        dimmer_channel = self.channel_by_name.get("master_dimmer")
        if dimmer_channel is None:
            raise ValueError("No master_dimmer channel in config")

        self.set_channel(dimmer_channel, 0)

    def zero(self):
        with self.lock:
            self.dmx[:] = bytes(512)

    def format_value(self, channel: int, value: int) -> str:
        data = self.channels_by_number.get(channel, {})
        if data.get("type") == "boolean":
            values = data.get("values", {})
            if value == values.get("on", 255):
                return "on"
            if value == values.get("off", 0):
                return "off"
        return str(value)

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
                        data.get("status", ""),
                        self.format_value(channel, value),
                    )
                )

        width = max(len(name) for _, name, _, _ in rows)

        for channel, name, status, value in rows:
            print(
                f"CH{channel:>2}  "
                f"{name:<{width}}  "
                f"{value:>5}  "
                f"[{status}]"
            )

    def list_controls(self):
        for channel in sorted(self.channels_by_number):
            data = self.channels_by_number[channel]
            name = data.get("name", "unknown")
            status = data.get("status", "")
            channel_type = data.get("type", "continuous")
            notes = data.get("notes", "")

            print(f"CH{channel:>2}  {name:<22} [{status}] ({channel_type})")

            if channel_type == "boolean":
                values = data.get("values", {})
                if values:
                    print(
                        "      "
                        + ", ".join(f"{k}={v}" for k, v in values.items())
                    )

            if notes:
                print(f"      {notes}")

            observations = data.get("observations", {})
            for value, observation in observations.items():
                print(f"      {value:>3}: {observation}")

    def list_presets(self):
        presets = self.config.get("presets", {})
        for name in sorted(presets):
            print(name)

    def close(self):
        self.running = False
        self.thread.join(timeout=1)
        self.sock.close()


HELP = """
Commands

  set CONTROL VALUE      Set a named control or raw channel
  raw CH VALUE           Set a raw DMX channel value

  sound on|off           Toggle sound-reactive mode for CH9 effects

  preset NAME            Apply a preset from the JSON config
  presets                List presets

  status                 Show current values for configured channels
  controls               Show channel names, confidence and observations

  blackout               Set master dimmer to 0, keep other state
  zero                   Set all 512 channels to 0

  help                    Show this help
  quit                    Exit

Examples

  set position 128
  set master_dimmer 255
  set red 255
  set strobe 0
  set effect_selector 60

  set sound_reactive on
  sound on
  sound off

  raw 9 128

  preset solid_red
  preset solid_blue

Notes

  - Channel mapping is loaded from zq06141_11ch.json.
  - CH10 is treated as a boolean sound-reactive switch:
      off = 0
      on  = 255
  - dmx_cli.py remains the low-level tool for discovering raw channel behaviour.
"""


def main():
    parser = argparse.ArgumentParser(
        description="Named CLI controller for the ZQ06141 via Art-Net."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).with_name("zq06141_11ch.json"),
        help="Path to fixture JSON config",
    )
    args = parser.parse_args()

    try:
        config = load_config(args.config)
    except FileNotFoundError:
        print(f"Config not found: {args.config}")
        print("Put zq06141_11ch.json beside this script or use --config PATH")
        return

    try:
        controller = LightController(config)
    except OSError as exc:
        print(f"Could not start Art-Net output: {exc}")
        print("Make sure Windows is connected to the PKNIGHT Wi-Fi.")
        return

    fixture = config["fixture"]

    print()
    print(f"{fixture['model']} controller ({fixture['mode']})")
    print("-" * 36)
    print(f"Config   : {args.config}")
    print(f"Local IP : {controller.local_ip}")
    print(f"Target   : {controller.target}:{controller.port}")
    print(f"Universe : {controller.universe}")
    print(f"Rate     : {controller.hz:g} Hz")
    print()
    print("Type 'help' for commands.")
    print()

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


if __name__ == "__main__":
    main()
