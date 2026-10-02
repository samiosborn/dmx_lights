# tools/sweep.py

import argparse
import time
from pathlib import Path

from lights.rig import load_node_transport
from lights.transport.artnet import DMX_CHANNELS


# Physical rig configuration
CONFIG = Path(__file__).resolve().parents[1] / "config/rig.yaml"


# Sweep raw DMX channel 1 continuously until Ctrl+C
def main() -> None:
    parser = argparse.ArgumentParser(description="Continuously sweep raw DMX channel 1")
    parser.parse_args()

    with load_node_transport(CONFIG) as transport:
        print(f"{transport.local_ip} -> {transport.target_ip}:{transport.port}")
        print("Sweeping DMX CH1 continuously. Ctrl+C to stop.")
        dmx = bytearray(DMX_CHANNELS)

        try:
            while True:
                # Sweep from left to right
                for value in range(0, 256, 4):
                    dmx[0] = value
                    transport.send(dmx)
                    time.sleep(0.025)

                # Sweep from right to left
                for value in range(255, -1, -4):
                    dmx[0] = value
                    transport.send(dmx)
                    time.sleep(0.025)
        except KeyboardInterrupt:
            print("\nStopped.")


# Run only when invoked as a module
if __name__ == "__main__":
    main()
