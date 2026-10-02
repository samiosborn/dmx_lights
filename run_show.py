# run_show.py

import argparse
import time
from pathlib import Path

from lights.effects.colour import load_colours, load_palettes
from lights.rig import Rig
from lights.show.engine import ShowEngine
from lights.show.loader import load_show


# Project paths
ROOT = Path(__file__).resolve().parent
RIG_PATH = ROOT / "config" / "rig.yaml"
COLOURS_PATH = ROOT / "config" / "colours.yaml"
PALETTES_PATH = ROOT / "config" / "palettes.yaml"

UPDATE_HZ = 20.0


# Resolve a show path relative to the project root
def resolve_show_path(path: str) -> Path:
    show_path = Path(path)

    if show_path.is_absolute():
        return show_path

    return ROOT / show_path


# Black out every fixture used by the show
def blackout(rig: Rig, show: dict) -> None:
    for fixture_name in show["fixtures"]:
        fixture = rig.get_fixture(fixture_name)

        fixture.set_many(
            master_dimmer=0,
            strobe=0,
            red=0,
            green=0,
            blue=0,
            white=0,
        )

    rig.send()


# Run the show using monotonic elapsed time
def run_show(engine: ShowEngine) -> None:
    start_time = time.monotonic()
    frame_interval = 1.0 / UPDATE_HZ
    last_phase = None

    while True:
        elapsed = time.monotonic() - start_time
        state = engine.update(elapsed)

        if state.phase_name != last_phase:
            print(f"Phase: {state.phase_name}")
            last_phase = state.phase_name

        time.sleep(frame_interval)


# Parse command-line arguments
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a DMX lighting show")
    parser.add_argument("show", help="Path to the show YAML file")

    return parser.parse_args()


# Load configuration and run the lighting show
def main() -> None:
    args = parse_args()

    show_path = resolve_show_path(args.show)

    show = load_show(show_path)
    colours = load_colours(COLOURS_PATH)
    palettes = load_palettes(PALETTES_PATH, colours)

    print(f"Show    : {show_path.name}")
    print(f"Fixtures: {', '.join(show['fixtures'])}")
    print(f"Seed    : {show['seed']}")
    print("Press Ctrl+C to stop")

    with Rig(RIG_PATH) as rig:
        engine = ShowEngine(
            rig=rig,
            show=show,
            colours=colours,
            palettes=palettes,
        )

        try:
            run_show(engine)
        except KeyboardInterrupt:
            print("\nStopping show")
        finally:
            blackout(rig, show)


if __name__ == "__main__":
    main()