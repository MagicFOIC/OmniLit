from __future__ import annotations

from typing import Any


BENCHMARK_SIZES = (100, 1_000, 5_000, 10_000)
_NODE_TYPES = ("method", "dataset", "result", "concept", "author", "citation", "limitation", "figure")


def make_lod_benchmark(node_count: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    size = max(1, int(node_count))
    columns = 100
    rows = max(1, (size + columns - 1) // columns)
    nodes: list[dict[str, Any]] = []
    layout: dict[str, Any] = {}
    for index in range(size):
        node_id = f"node:{index}"
        node_type = "paper" if index == 0 else _NODE_TYPES[index % len(_NODE_TYPES)]
        nodes.append({
            "id": node_id,
            "type": node_type,
            "label": f"Benchmark node {index:05d}",
            "importance": ((index * 37) % 100) / 100.0,
            "confidence": 0.55 + ((index * 17) % 45) / 100.0,
            "evidence": [{"page": index % 40}] if index % 7 == 0 else [],
        })
        layout[node_id] = {
            "x": ((index % columns) + 0.5) / columns,
            "y": ((index // columns) + 0.5) / rows,
            "layer": index % 6,
        }
    edges: list[dict[str, Any]] = []
    for index in range(1, size):
        edges.append({
            "id": f"edge:chain:{index}",
            "source": f"node:{index - 1}",
            "target": f"node:{index}",
            "type": "RELATED_TO",
            "confidence": 0.8,
        })
        if index >= 17:
            edges.append({
                "id": f"edge:skip:{index}",
                "source": f"node:{index - 17}",
                "target": f"node:{index}",
                "type": "USES" if index % 2 else "SUPPORTS",
                "confidence": 0.7,
            })
    return nodes, edges, layout

