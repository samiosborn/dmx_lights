# tools/dmx_cli.py

import argparse
import threading
import time
from pathlib import Path

from lights.rig import load_node_transport


# Rig configuration and refresh settings
CONFIG = Path(__file__).resolve().parents[1] / "config/rig.yaml"
HZ = 40.0


# Manage raw DMX channels and continuous Art-Net transmission
class DMXController:
    # Initialize DMX state, transport, and the sender thread
    def __init__(self, config_path: str | Path = CONFIG, node_name: str | None = None):
        self.dmx = bytearray(512)
        self.lock = threading.Lock()
        self.running = True

        self.transport = load_node_transport(config_path, node_name)
        self.local_ip = self.transport.local_ip

        self.thread = threading.Thread(
            target=self._sender,
            daemon=True,
        )
        self.thread.start()

    # Send the current frame at the configured refresh rate
    def _sender(self):
        delay = 1.0 / HZ

        while self.running:
            with self.lock:
                frame = bytes(self.dmx)

            self.transport.send(frame)

            time.sleep(delay)

    # Validate and update one raw channel
    def set(self, channel: int, value: int):
        if not 1 <= channel <= 512:
            raise ValueError("Channel must be 1-512")

        if not 0 <= value <= 255:
            raise ValueError("Value must be 0-255")

        with self.lock:
            self.dmx[channel - 1] = value

    # Clear all DMX channels
    def zero(self):
        with self.lock:
            self.dmx[:] = bytes(512)

    # Display raw channel values
    def show(self, count=20):
        with self.lock:
            values = list(self.dmx[:count])

        for start in range(0, count, 10):
            row = []
            for i in range(start, min(start + 10, count)):
                row.append(f"{i + 1:>3}:{values[i]:>3}")
            print("  ".join(row))

    # Sweep a raw channel until Ctrl+C
    def sweep(self, channel: int):
        print(
            f"Sweeping CH{channel}. "
            "Press Ctrl+C to stop sweep."
        )

        try:
            while True:
                for value in range(0, 256, 4):
                    self.set(channel, value)
                    time.sleep(0.025)

                for value in range(255, -1, -4):
                    self.set(channel, value)
                    time.sleep(0.025)

        except KeyboardInterrupt:
            print("\nSweep stopped.")

    # Stop the sender before closing the transport
    def close(self):
        self.running = False
        self.thread.join(timeout=1)
        self.transport.close()


# Describe the available raw-channel commands
def print_help():
    print(
        """
Commands:

  set CH VALUE       Set one channel
  s CH VALUE         Same as set

  show               Show channels 1-20
  show N             Show channels 1-N

  zero               Set all 512 channels to 0
  sweep CH           Continuously sweep one channel 0-255-0

  help               Show this help
  quit               Exit

Examples:

  set 1 128
  set 3 255
  set 5 255
  sweep 1
  zero
"""
    )


# Start the console and dispatch interactive commands
def main() -> None:
    parser = argparse.ArgumentParser(description="Interactive raw DMX debugging console")
    parser.parse_args()

    try:
        controller = DMXController()
    except (OSError, ValueError) as exc:
        print(f"Could not connect to EasyNode network: {exc}")
        print("Check the rig configuration and network connection.")
        return

    # Show connection details and command help
    print()
    print("Art-Net DMX console")
    print("-------------------")
    print(f"Local IP : {controller.local_ip}")
    print(f"Target   : {controller.transport.target_ip}:{controller.transport.port}")
    print(f"Universe : {controller.transport.universe}")
    print(f"Rate     : {HZ:g} Hz")
    print()

    print_help()

    # Handle commands until EOF, quit, or Ctrl+C
    try:
        while True:
            try:
                command = input("dmx> ").strip()
            except EOFError:
                break

            if not command:
                continue

            parts = command.lower().split()
            cmd = parts[0]

            try:
                if cmd in {"set", "s"}:
                    if len(parts) != 3:
                        print("Usage: set CH VALUE")
                        continue

                    channel = int(parts[1])
                    value = int(parts[2])

                    controller.set(channel, value)
                    print(f"CH{channel} = {value}")

                elif cmd == "zero":
                    controller.zero()
                    print("All channels = 0")

                elif cmd == "show":
                    count = 20

                    if len(parts) == 2:
                        count = int(parts[1])

                    count = max(1, min(count, 512))
                    controller.show(count)

                elif cmd == "sweep":
                    if len(parts) != 2:
                        print("Usage: sweep CH")
                        continue

                    controller.sweep(int(parts[1]))

                elif cmd in {"help", "?"}:
                    print_help()

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