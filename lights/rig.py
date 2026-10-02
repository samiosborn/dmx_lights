# lights/rig.py

from pathlib import Path
from typing import Any

import yaml

from lights.fixtures.fixture import Fixture, load_fixture_config
from lights.transport.artnet import ArtNetTransport


# Load a YAML file
def load_yaml(path: str | Path) -> dict[str, Any]:
    path = Path(path)

    with path.open("r", encoding="utf-8") as file:
        config = yaml.safe_load(file)

    if not isinstance(config, dict):
        raise ValueError(f"Invalid config: {path}")

    return config


# Create a transport from one configured node
def create_node_transport(node_config: dict[str, Any]) -> ArtNetTransport:
    if node_config["transport"] != "artnet":
        raise ValueError(f"Unsupported transport: {node_config['transport']}")

    return ArtNetTransport(target_ip=node_config["target_ip"], universe=int(node_config["universe"]), port=int(node_config["port"]))


# Load one node for raw DMX tools without creating fixtures
def load_node_transport(config_path: str | Path, node_name: str | None = None) -> ArtNetTransport:
    nodes = load_yaml(config_path)["nodes"]

    if node_name is None:
        if len(nodes) != 1:
            raise ValueError("Specify a node name when the rig does not contain exactly one node")
        node_name = next(iter(nodes))

    if node_name not in nodes:
        raise ValueError(f"Unknown node: {node_name}")

    return create_node_transport(nodes[node_name])


# Represent the physical lighting rig
class Rig:
    def __init__(self, config_path: str | Path) -> None:
        self.config_path = Path(config_path)
        self.config_dir = self.config_path.parent
        self.config = load_yaml(self.config_path)

        self.transports: dict[str, ArtNetTransport] = {}
        self.fixtures: dict[str, Fixture] = {}
        self.fixture_nodes: dict[str, str] = {}

        self._load_nodes()
        self._load_fixtures()
        self._validate_fixture_addresses()

    # Create transport objects for every node in the rig
    def _load_nodes(self) -> None:
        nodes = self.config["nodes"]

        for name, node_config in nodes.items():
            self.transports[name] = create_node_transport(node_config)

    # Create fixture objects from the physical rig definition
    def _load_fixtures(self) -> None:
        fixtures = self.config["fixtures"]

        for name, fixture_config in fixtures.items():
            fixture_type = fixture_config["type"]
            node_name = fixture_config["node"]
            start_address = int(fixture_config["start_address"])

            if node_name not in self.transports:
                raise ValueError(f"Unknown node '{node_name}' for fixture '{name}'")

            definition_path = self.config_dir / "fixtures" / f"{fixture_type}.yaml"
            definition = load_fixture_config(definition_path)

            self.fixtures[name] = Fixture(config=definition, start_address=start_address)
            self.fixture_nodes[name] = node_name

    # Check fixtures on the same node do not use overlapping DMX addresses
    def _validate_fixture_addresses(self) -> None:
        occupied: dict[str, dict[int, str]] = {}

        for fixture_name, fixture in self.fixtures.items():
            node_name = self.fixture_nodes[fixture_name]
            node_channels = occupied.setdefault(node_name, {})

            first_channel = fixture.start_address
            last_channel = fixture.start_address + fixture.channel_count - 1

            for channel in range(first_channel, last_channel + 1):
                if channel in node_channels:
                    other_fixture = node_channels[channel]
                    raise ValueError(f"DMX channel {channel} overlaps between '{other_fixture}' and '{fixture_name}' on node '{node_name}'")

                node_channels[channel] = fixture_name

    # Return one fixture by its rig instance name
    def get_fixture(self, name: str) -> Fixture:
        if name not in self.fixtures:
            raise ValueError(f"Unknown fixture: {name}")

        return self.fixtures[name]

    # Build one combined 512-channel frame for a node
    def render_node(self, node_name: str) -> bytearray:
        if node_name not in self.transports:
            raise ValueError(f"Unknown node: {node_name}")

        dmx = bytearray(512)

        for fixture_name, fixture in self.fixtures.items():
            if self.fixture_nodes[fixture_name] != node_name:
                continue

            fixture_dmx = fixture.render()

            start = fixture.start_address - 1
            end = start + fixture.channel_count

            dmx[start:end] = fixture_dmx[start:end]

        return dmx

    # Render and send the current state of every fixture
    def send(self) -> None:
        for node_name, transport in self.transports.items():
            dmx = self.render_node(node_name)
            transport.send(dmx)

    # Restore every fixture to its configured defaults
    def reset(self) -> None:
        for fixture in self.fixtures.values():
            fixture.reset()

    # Close every transport
    def close(self) -> None:
        for transport in self.transports.values():
            transport.close()

    # Allow the rig to be used with a context manager
    def __enter__(self) -> "Rig":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()
        