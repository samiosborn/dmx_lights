# tools/strobe_cycle.py

import argparse
import time
from pathlib import Path

from lights.rig import Rig


# Physical rig configuration
CONFIG = Path(__file__).resolve().parents[1] / "config/rig.yaml"

# Timing
HZ = 40

# Seconds between alternating left/right targets
MOVE_INTERVAL = 3.0

# Seconds spent transitioning to the next colour
COLOUR_PERIOD = 2.0

# Fixture movement speed
MOTOR_SPEED = 128

# Strobe amount
STROBE = 128

# RGB colour cycle
COLOURS = [
    (255, 0, 0),        # red
    (0, 0, 255),        # blue
    (0, 255, 0),        # green
    (180, 0, 255),      # purple
    (255, 180, 0),      # yellow
    (0, 255, 255),      # cyan
    (255, 0, 180),      # pink
]


# Interpolate a colour component
def lerp(a, b, x):
    return int(a + (b - a) * x)


# Blend continuously between colours
def colour_at_time(t):
    position = t / COLOUR_PERIOD

    i = int(position) % len(COLOURS)
    j = (i + 1) % len(COLOURS)

    blend = position % 1.0

    a = COLOURS[i]
    b = COLOURS[j]

    return tuple(
        lerp(a[k], b[k], blend)
        for k in range(3)
    )


# Transmit the strobe cycle and blackout on Ctrl+C
def main() -> None:
    parser = argparse.ArgumentParser(description="Run the fixture strobe and colour cycle")
    parser.parse_args()

    rig = Rig(CONFIG)
    if len(rig.fixtures) != 1:
        rig.close()
        raise ValueError("The strobe test requires exactly one configured fixture")
    fixture_name = next(iter(rig.fixtures))
    fixture = rig.get_fixture(fixture_name)
    config = fixture.config
    channels = {
        name: fixture.start_address + int(data["channel"]) - 2
        for name, data in config["channels"].items()
    }
    transport = rig.transports[rig.fixture_nodes[fixture_name]]

    print(f"{transport.local_ip} -> {transport.target_ip}:{transport.port}")
    print("Strobe cycle running. Ctrl+C to stop.")

    # Hold each motor destination for a full travel interval
    position = 0
    next_move = MOVE_INTERVAL
    start = time.monotonic()

    try:
        while True:
            t = time.monotonic() - start

            dmx = bytearray(512)

            # Change only the destination; CH2 controls travel between endpoints
            if t >= next_move:
                position = 255 - position
                next_move = t + MOVE_INTERVAL

            # Keep colour transitions independent of motor travel
            red, green, blue = colour_at_time(t)

            # Resolve DMX channels from the YAML fixture mapping
            dmx[channels["position"]] = position
            dmx[channels["motor_speed"]] = MOTOR_SPEED
            dmx[channels["master_dimmer"]] = 255
            dmx[channels["strobe"]] = STROBE

            dmx[channels["red"]] = red
            dmx[channels["green"]] = green
            dmx[channels["blue"]] = blue
            dmx[channels["white"]] = 0

            dmx[channels["builtin_effect"]] = 0
            dmx[channels["sound_reactive"]] = config["channels"]["sound_reactive"]["values"][False]
            dmx[channels["unknown_channel"]] = 0

            # Send the current frame continuously at the existing rate
            transport.send(dmx)

            time.sleep(1 / HZ)

    except KeyboardInterrupt:
        print("\nStopping...")

        # Repeat an all-zero frame for a clean blackout
        dmx = bytearray(512)

        for _ in range(10):
            transport.send(dmx)
            time.sleep(0.025)

    finally:
        rig.close()

    print("Done.")


# Run only when invoked as a module
if __name__ == "__main__":
    main()