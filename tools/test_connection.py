# tools/test_connection.py

import argparse
import platform
import subprocess
import time
from pathlib import Path

from lights.rig import Rig


# Project paths
ROOT = Path(__file__).resolve().parents[1]
RIG_PATH = ROOT / "config" / "rig.yaml"

FLASH_COUNT = 3
FLASH_TIME = 0.5
MASTER_DIMMER = 80


# Check whether a network device responds to ping
def ping(host: str, timeout: int = 1000) -> bool:
    if platform.system() == "Windows":
        command = ["ping", "-n", "1", "-w", str(timeout), host]
    else:
        command = ["ping", "-c", "1", "-W", str(max(1, timeout // 1000)), host]

    result = subprocess.run(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    return result.returncode == 0


# Set one fixture to a visible white test state
def light_on(fixture) -> None:
    fixture.set_many(
        position="centre",
        motor_speed=128,
        master_dimmer=MASTER_DIMMER,
        strobe=0,
        red=0,
        green=0,
        blue=0,
        white=255,
        builtin_effect=0,
        sound_reactive=False,
    )


# Black out one fixture
def light_off(fixture) -> None:
    fixture.set_many(
        master_dimmer=0,
        strobe=0,
        red=0,
        green=0,
        blue=0,
        white=0,
    )


# Test network connectivity to every Art-Net node
def test_nodes(rig: Rig) -> None:
    for node_name, transport in rig.transports.items():
        print(f"Node     : {node_name}")
        print(f"Target   : {transport.target_ip}:{transport.port}")
        print(f"Universe : {transport.universe}")
        print("Ping     : ", end="", flush=True)

        if not ping(transport.target_ip):
            print("FAILED")
            raise ConnectionError(f"Cannot reach node '{node_name}' at {transport.target_ip}")

        print("OK")
        print()


# Flash every fixture to verify the complete DMX connection
def test_fixtures(rig: Rig) -> None:
    print(f"Fixtures : {', '.join(rig.fixtures)}")
    print(f"Test     : {FLASH_COUNT} white flashes")
    print()

    for flash in range(FLASH_COUNT):
        print(f"Flash {flash + 1}/{FLASH_COUNT}")

        for fixture in rig.fixtures.values():
            light_on(fixture)

        rig.send()
        time.sleep(FLASH_TIME)

        for fixture in rig.fixtures.values():
            light_off(fixture)

        rig.send()
        time.sleep(FLASH_TIME)


# Run the connection test
def main() -> None:
    parser = argparse.ArgumentParser(description="Check node connectivity and flash the configured fixtures")
    parser.parse_args()

    print("DMX connection test")
    print()

    with Rig(RIG_PATH) as rig:
        try:
            test_nodes(rig)
        except ConnectionError as exc:
            print()
            print(f"Connection failed: {exc}")
            raise SystemExit(1)

        try:
            test_fixtures(rig)
        finally:
            for fixture in rig.fixtures.values():
                light_off(fixture)

            rig.send()

    print()
    print("Network connection passed")
    print("If the fixture flashed, the complete Art-Net --> DMX chain is working")


# Run only when invoked as a module
if __name__ == "__main__":
    main()