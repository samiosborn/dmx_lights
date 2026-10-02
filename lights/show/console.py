# lights/show/console.py

import queue
import threading
from dataclasses import dataclass


# Commands supported by the interactive show console
COMMANDS = {
    "status",
    "next",
    "phase",
    "pause",
    "resume",
    "blackout",
    "restore",
    "reload",
    "quit",
    "help",
}


# One parsed console command
@dataclass(frozen=True)
class ConsoleCommand:
    name: str
    args: list[str]


# Read interactive commands without blocking the main show loop
class ShowConsole:
    def __init__(self) -> None:
        self.commands: queue.Queue[ConsoleCommand] = queue.Queue()
        self.running = False
        self.thread: threading.Thread | None = None

    # Start the background console thread
    def start(self) -> None:
        if self.running:
            return

        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    # Read commands from stdin
    def _run(self) -> None:
        while self.running:
            try:
                line = input("> ").strip()
            except EOFError:
                self.commands.put(ConsoleCommand(name="quit", args=[]))
                return

            if not line:
                continue

            command = self.parse(line)

            if command is not None:
                self.commands.put(command)

    # Parse one line of console input
    def parse(self, line: str) -> ConsoleCommand | None:
        parts = line.split()
        name = parts[0].lower()
        args = parts[1:]

        if name not in COMMANDS:
            print(f"Unknown command: {name}")
            print("Type 'help' for available commands")
            return None

        if name == "phase" and len(args) != 1:
            print("Usage: phase <name>")
            return None

        if name != "phase" and args:
            print(f"Command '{name}' does not accept arguments")
            return None

        return ConsoleCommand(name=name, args=args)

    # Return the next queued command without blocking
    def get_command(self) -> ConsoleCommand | None:
        try:
            return self.commands.get_nowait()
        except queue.Empty:
            return None

    # Stop accepting new console commands
    def stop(self) -> None:
        self.running = False


# Print available interactive commands
def print_help() -> None:
    print(
        """
Commands:
  status            Show the current phase and active effects
  next              Jump to the next phase
  phase <name>      Jump to a named phase
  pause             Freeze the show clock
  resume            Resume the show clock
  blackout          Turn the lights off while the show continues
  restore           Restore normal show output
  reload            Reload the show YAML
  quit              Black out and exit
  help              Show this help
""".strip()
    )