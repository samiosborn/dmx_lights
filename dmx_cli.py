# dmx_cli.py

import socket
import struct
import threading
import time


TARGET = "192.168.4.1"
PORT = 6454
UNIVERSE = 0
HZ = 40.0


def get_local_ip(target: str) -> str:
    """Find the Windows interface used to reach the EasyNode."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect((target, PORT))
        return sock.getsockname()[0]
    finally:
        sock.close()


def build_artdmx(dmx: bytearray, sequence: int) -> bytes:
    return (
        b"Art-Net\x00"
        + struct.pack("<H", 0x5000)   # ArtDMX opcode
        + struct.pack(">H", 14)       # Art-Net protocol version
        + bytes([sequence, 0])        # sequence, physical
        + struct.pack("<H", UNIVERSE)
        + struct.pack(">H", len(dmx))
        + bytes(dmx)
    )


class DMXController:
    def __init__(self):
        self.dmx = bytearray(512)
        self.lock = threading.Lock()
        self.running = True
        self.sequence = 1

        self.local_ip = get_local_ip(TARGET)

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((self.local_ip, 0))

        self.thread = threading.Thread(
            target=self._sender,
            daemon=True,
        )
        self.thread.start()

    def _sender(self):
        delay = 1.0 / HZ

        while self.running:
            with self.lock:
                packet = build_artdmx(self.dmx, self.sequence)

            self.sock.sendto(packet, (TARGET, PORT))

            self.sequence += 1
            if self.sequence > 255:
                self.sequence = 1

            time.sleep(delay)

    def set(self, channel: int, value: int):
        if not 1 <= channel <= 512:
            raise ValueError("Channel must be 1-512")

        if not 0 <= value <= 255:
            raise ValueError("Value must be 0-255")

        with self.lock:
            self.dmx[channel - 1] = value

    def zero(self):
        with self.lock:
            self.dmx[:] = bytes(512)

    def show(self, count=20):
        with self.lock:
            values = list(self.dmx[:count])

        for start in range(0, count, 10):
            row = []
            for i in range(start, min(start + 10, count)):
                row.append(f"{i + 1:>3}:{values[i]:>3}")
            print("  ".join(row))

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

    def close(self):
        self.running = False
        self.thread.join(timeout=1)
        self.sock.close()


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


def main():
    try:
        controller = DMXController()
    except OSError as exc:
        print(f"Could not connect to EasyNode network: {exc}")
        print("Make sure Windows is connected to PKNIGHT.WIFI.")
        return

    print()
    print("Art-Net DMX console")
    print("-------------------")
    print(f"Local IP : {controller.local_ip}")
    print(f"Target   : {TARGET}:{PORT}")
    print(f"Universe : {UNIVERSE}")
    print(f"Rate     : {HZ:g} Hz")
    print()

    print_help()

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


if __name__ == "__main__":
    main()