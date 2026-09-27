"""
Campus graph loader.

OWNER: orchestrator. READ-ONLY for all agents.

    from shared.graph import Graph, load_graph
    g = load_graph()                      # loads shared/graph.json
    g = load_graph("acceptance/fixtures/test_graph.json")
    g.node_ids()                          # ["main_gate", ...] in file order
    g.locations()                         # list[Location]
    g.neighbors("library")                # {"admin_block": 250, "academic_block": 200, "cafeteria": 200}
    g.edge_len("library", "cafeteria")    # 200   (KeyError if no direct edge)
    g.has_node("library")                 # True

Shortest paths are NOT here. They live in dispatch/ (Agent A).
"""

import json
from pathlib import Path

from shared.models import Location

DEFAULT_GRAPH_PATH = Path(__file__).parent / "graph.json"


class Graph:
    def __init__(self, nodes: list[Location], edges: list[tuple[str, str, int]]):
        self.nodes: dict[str, Location] = {n.id: n for n in nodes}
        self.adj: dict[str, dict[str, int]] = {n.id: {} for n in nodes}
        for a, b, meters in edges:
            if a not in self.adj or b not in self.adj:
                raise ValueError(f"edge {a}-{b} uses an unknown node")
            self.adj[a][b] = meters
            self.adj[b][a] = meters

    def node_ids(self) -> list[str]:
        return list(self.nodes.keys())

    def locations(self) -> list[Location]:
        return list(self.nodes.values())

    def has_node(self, node_id: str) -> bool:
        return node_id in self.nodes

    def neighbors(self, node_id: str) -> dict[str, int]:
        return self.adj[node_id]

    def edge_len(self, a: str, b: str) -> int:
        return self.adj[a][b]


def load_graph(path: str | Path = DEFAULT_GRAPH_PATH) -> Graph:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    nodes = [Location(**n) for n in data["nodes"]]
    edges = [(e["a"], e["b"], int(e["meters"])) for e in data["edges"]]
    return Graph(nodes, edges)
