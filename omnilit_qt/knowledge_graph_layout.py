from __future__ import annotations

from collections import defaultdict
import math
from typing import Any


LAYER_ORDER = {
    "paper": 0,
    "problem": 1,
    "researchgap": 1,
    "section": 1,
    "concept": 1,
    "method": 2,
    "algorithm": 2,
    "model": 2,
    "contribution": 2,
    "dataset": 3,
    "metric": 3,
    "baseline": 3,
    "experiment": 3,
    "result": 4,
    "claim": 4,
    "limitation": 4,
    "futurework": 4,
    "figure": 5,
    "table": 5,
    "equation": 5,
    "comparison": 2,
    "conflict": 4,
    "missinginfo": 5,
}


def academic_layout(nodes: list[dict[str, Any]], comparison: bool = False) -> dict[str, dict[str, float | int | str]]:
    """Return deterministic normalized positions for a layered academic graph."""
    layers: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for node in nodes:
        kind = str(node.get("type") or "concept").casefold()
        layers[LAYER_ORDER.get(kind, 2)].append(node)
    for values in layers.values():
        values.sort(key=lambda item: (-float(item.get("importance", item.get("weight", 0.5)) or 0.0), str(item.get("label") or "").casefold(), str(item.get("id") or "")))

    result: dict[str, dict[str, float | int | str]] = {}
    max_layer = max(layers, default=0)
    for layer in sorted(layers):
        values = layers[layer]
        per_row = 7
        row_count = max(1, math.ceil(len(values) / per_row))
        for index, node in enumerate(values):
            if comparison and str(node.get("type") or "").casefold() == "paper":
                x = (index + 1) / (len(values) + 1)
                y = 0.08
            else:
                row = index // per_row
                position = index % per_row
                items_in_row = min(per_row, len(values) - row * per_row)
                x = (position + 1) / (items_in_row + 1)
                base_y = 0.08 + (layer / max(1, max_layer)) * 0.84
                y = max(0.04, min(0.96, base_y + (row - (row_count - 1) / 2) * 0.052))
            result[str(node.get("id") or "")] = {
                "x": round(x, 6),
                "y": round(y, 6),
                "layer": layer,
                "order": index,
                "lane": str((node.get("details") or {}).get("only_in") or ""),
            }
    return result


def adjacency_index(edges: list[dict[str, Any]]) -> dict[str, list[str]]:
    result: dict[str, set[str]] = defaultdict(set)
    for edge in edges:
        source = str(edge.get("source") or "")
        target = str(edge.get("target") or "")
        if source and target:
            result[source].add(target)
            result[target].add(source)
    return {key: sorted(values) for key, values in result.items()}
