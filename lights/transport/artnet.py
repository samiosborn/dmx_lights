# lights/transport/artnet.py

import socket
import struct
from collections.abc import Sequence


# Art-Net protocol constants
ARTNET_PORT = 6454
ARTNET_PROTOCOL_VERSION = 14
ARTDMX_OPCODE = 0x5000
DMX_CHANNELS = 512


# Resolve the local network interface used to reach an Art-Net node
def get_local_ip(target_ip: str, port: int = ARTNET_PORT) -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    try:
        sock.connect((target_ip, port))
        return sock.getsockname()[0]
    finally:
        sock.close()


# Build one ArtDMX packet from a complete DMX universe
def build_artdmx(
    dmx: Sequence[int],
    universe: int = 0,
    sequence: int = 1,
) -> bytes:
    if len(dmx) != DMX_CHANNELS:
        raise ValueError(f"DMX frame must contain exactly {DMX_CHANNELS} channels")

    if not all(0 <= value <= 255 for value in dmx):
        raise ValueError("DMX channel values must be between 0 and 255")

    if not 0 <= universe <= 32767:
        raise ValueError("Art-Net universe must be between 0 and 32767")

    if not 0 <= sequence <= 255:
        raise ValueError("Art-Net sequence must be between 0 and 255")

    # Art-Net Port-Address:
    # bits 0-3  = universe
    # bits 4-7  = subnet
    # bits 8-14 = net
    subuni = universe & 0xFF
    net = (universe >> 8) & 0x7F

    header = (
        b"Art-Net\x00"
        + struct.pack("<H", ARTDMX_OPCODE)
        + struct.pack(">H", ARTNET_PROTOCOL_VERSION)
        + bytes([sequence, 0])
        + bytes([subuni, net])
        + struct.pack(">H", DMX_CHANNELS)
    )

    return header + bytes(dmx)


# Send DMX frames to one Art-Net node
class ArtNetTransport:
    def __init__(
        self,
        target_ip: str,
        universe: int = 0,
        port: int = ARTNET_PORT,
        local_ip: str | None = None,
    ) -> None:
        self.target_ip = target_ip
        self.universe = universe
        self.port = port

        # Automatically select the correct local interface unless explicitly set
        self.local_ip = local_ip or get_local_ip(
            target_ip=self.target_ip,
            port=self.port,
        )

        self._sequence = 1

        self._socket = socket.socket(
            socket.AF_INET,
            socket.SOCK_DGRAM,
        )

        self._socket.bind((self.local_ip, 0))

    # Send one complete 512-channel DMX frame
    def send(self, dmx: Sequence[int]) -> None:
        packet = build_artdmx(
            dmx=dmx,
            universe=self.universe,
            sequence=self._sequence,
        )

        self._socket.sendto(
            packet,
            (self.target_ip, self.port),
        )

        self._advance_sequence()

    # Advance Art-Net's optional packet sequence counter.
    def _advance_sequence(self) -> None:
        self._sequence += 1

        if self._sequence > 255:
            self._sequence = 1

    # Close the underlying UDP socket.
    def close(self) -> None:
        self._socket.close()

    # Allow use with a Python context manager.
    def __enter__(self) -> "ArtNetTransport":
        return self

    def __exit__(
        self,
        exc_type,
        exc_value,
        traceback,
    ) -> None:
        self.close()