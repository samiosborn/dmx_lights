# artnet.py

import argparse
import socket
import struct
import time


ARTNET_PORT = 6454
DEFAULT_TARGET = "192.168.4.1"


def get_local_ip_for(target: str) -> str:
    """Ask Windows which local interface/IP it would use to reach target."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect((target, ARTNET_PORT))
        return sock.getsockname()[0]
    finally:
        sock.close()


def build_artdmx(
    channels: list[int],
    universe: int,
    sequence: int,
) -> bytes:
    if not 0 <= universe <= 32767:
        raise ValueError("Universe must be 0..32767")

    # Art-Net Port-Address:
    # bits 0-3  = Universe
    # bits 4-7  = Subnet
    # bits 8-14 = Net
    subuni = universe & 0xFF
    net = (universe >> 8) & 0x7F

    header = (
        b"Art-Net\x00"
        + struct.pack("<H", 0x5000)       # OpCode ArtDMX
        + struct.pack(">H", 14)           # Protocol version
        + bytes([sequence, 0])            # sequence, physical
        + bytes([subuni, net])            # universe/subnet, net
        + struct.pack(">H", len(channels))
    )

    return header + bytes(channels)


def parse_assignment(text: str) -> tuple[int, int]:
    try:
        channel_text, value_text = text.split("=", 1)
        channel = int(channel_text)
        value = int(value_text)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"Expected CHANNEL=VALUE, got {text!r}"
        )

    if not 1 <= channel <= 512:
        raise argparse.ArgumentTypeError("Channel must be 1..512")

    if not 0 <= value <= 255:
        raise argparse.ArgumentTypeError("Value must be 0..255")

    return channel, value


def main():
    parser = argparse.ArgumentParser(
        description="Send raw Art-Net DMX to the Pknight EasyNode."
    )
    parser.add_argument(
        "assignments",
        nargs="*",
        type=parse_assignment,
        metavar="CH=VALUE",
        help="DMX values, e.g. 3=255 5=255",
    )
    parser.add_argument(
        "--target",
        default=DEFAULT_TARGET,
        help=f"Art-Net node IP (default: {DEFAULT_TARGET})",
    )
    parser.add_argument(
        "--universe",
        type=int,
        default=0,
        help="Art-Net universe / Port-Address (default: 0)",
    )
    parser.add_argument(
        "--hz",
        type=float,
        default=40.0,
        help="Transmit rate (default: 40 Hz)",
    )
    parser.add_argument(
        "--seconds",
        type=float,
        default=None,
        help="Stop after N seconds; otherwise run until Ctrl+C",
    )
    parser.add_argument(
        "--blackout",
        action="store_true",
        help="Send all 512 channels as zero",
    )

    args = parser.parse_args()

    channels = [0] * 512

    if not args.blackout:
        for channel, value in args.assignments:
            channels[channel - 1] = value

    local_ip = get_local_ip_for(args.target)

    print(f"Local IP : {local_ip}")
    print(f"Target   : {args.target}:{ARTNET_PORT}")
    print(f"Universe : {args.universe}")

    if args.blackout:
        print("DMX      : BLACKOUT")
    else:
        print(
            "DMX      : "
            + ", ".join(
                f"CH{channel}={value}"
                for channel, value in args.assignments
            )
        )

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.bind((local_ip, 0))

    delay = 1.0 / args.hz
    start = time.monotonic()
    sequence = 1

    try:
        while True:
            packet = build_artdmx(
                channels=channels,
                universe=args.universe,
                sequence=sequence,
            )

            sock.sendto(packet, (args.target, ARTNET_PORT))

            sequence += 1
            if sequence > 255:
                sequence = 1

            if (
                args.seconds is not None
                and time.monotonic() - start >= args.seconds
            ):
                break

            time.sleep(delay)

    except KeyboardInterrupt:
        print("\nStopped.")

    finally:
        sock.close()


if __name__ == "__main__":
    main()
