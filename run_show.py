# run_show.py

import argparse
import time
from pathlib import Path

from lights.effects.colour import load_colours, load_palettes
from lights.rig import Rig
from lights.show.console import ConsoleCommand, ShowConsole, print_help
from lights.show.controller import ShowController
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


# Format elapsed seconds for console output
def format_time(seconds: float) -> str:
    total_seconds = int(seconds)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


# Print the current show state
def print_status(controller: ShowController) -> None:
    status = controller.status()

    print(f"Elapsed       : {format_time(status.elapsed)}")
    print(f"Phase         : {status.phase_name}")
    print(f"Phase elapsed : {format_time(status.phase_elapsed)}")
    print(f"Paused        : {status.paused}")
    print(f"Blackout      : {status.blackout}")

    for layer_name, effect_name in status.effects.items():
        print(f"{layer_name.capitalize():<14}: {effect_name}")


# Handle one interactive console command
def handle_command(controller: ShowController, command: ConsoleCommand) -> None:
    if command.name == "status":
        print_status(controller)
        return

    if command.name == "next":
        phase_name = controller.next_phase()

        if phase_name is None:
            print("Already in final phase")
        else:
            print(f"Phase: {phase_name}")

        return

    if command.name == "phase":
        phase_name = command.args[0]
        controller.set_phase(phase_name)
        print(f"Phase: {phase_name}")
        return

    if command.name == "pause":
        controller.pause()
        print("Paused")
        return

    if command.name == "resume":
        controller.resume()
        print("Resumed")
        return

    if command.name == "blackout":
        controller.blackout()
        print("Blackout")
        return

    if command.name == "restore":
        controller.restore()
        print("Restored")
        return

    if command.name == "reload":
        controller.reload()
        print("Show reloaded")
        return

    if command.name == "help":
        print_help()
        return

    if command.name == "quit":
        controller.stop()


# Process every command currently waiting in the console queue
def process_commands(controller: ShowController, console: ShowConsole) -> None:
    while True:
        command = console.get_command()

        if command is None:
            return

        try:
            handle_command(controller, command)
        except Exception as exc:
            print(f"Command failed: {exc}")


# Run the interactive show loop
def run_show(controller: ShowController, console: ShowConsole) -> None:
    frame_interval = 1.0 / UPDATE_HZ
    last_phase = None

    while controller.running:
        process_commands(controller, console)

        if not controller.running:
            break

        state = controller.update()

        if state.phase_name != last_phase:
            print(f"Phase: {state.phase_name}")
            last_phase = state.phase_name

        time.sleep(frame_interval)


# Parse command-line arguments
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a DMX lighting show")
    parser.add_argument("show", help="Path to the show YAML file")

    return parser.parse_args()


# Load the rig and start the interactive show
def main() -> None:
    args = parse_args()
    show_path = resolve_show_path(args.show)

    show = load_show(show_path)
    colours = load_colours(COLOURS_PATH)
    palettes = load_palettes(PALETTES_PATH, colours)

    print(f"Show     : {show_path.name}")
    print(f"Fixtures : {', '.join(show['fixtures'])}")
    print(f"Seed     : {show['seed']}")
    print("Type 'help' for commands")
    print("Press Ctrl+C to stop")
    print()

    console = ShowConsole()

    with Rig(RIG_PATH) as rig:
        engine = ShowEngine(
            rig=rig,
            show=show,
            colours=colours,
            palettes=palettes,
        )

        controller = ShowController(
            engine=engine,
            show_path=show_path,
        )

        console.start()

        try:
            run_show(controller, console)
        except KeyboardInterrupt:
            print("\nStopping show")
        finally:
            console.stop()
            controller.stop()


if __name__ == "__main__":
    main()