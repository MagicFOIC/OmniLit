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

TYPE_ORDER = {
    "paper": 0, "section": 1, "problem": 2, "researchgap": 3, "researchquestion": 3, "concept": 4,
    "contribution": 5, "method": 6, "algorithm": 7, "model": 8,
    "experiment": 9, "dataset": 10, "metric": 11, "baseline": 12,
    "result": 13, "claim": 14, "conclusion": 14, "limitation": 15, "futurework": 16,
    "figure": 17, "table": 18, "equation": 19,
}

STAGE_NAMES = {
    0: "paper", 1: "context", 2: "approach", 3: "evaluation", 4: "findings", 5: "evidence",
}


def academic_layout(nodes: list[dict[str, Any]], comparison: bool = False) -> dict[str, dict[str, float | int | str]]:
    """Return deterministic normalized positions for a layered academic graph."""
    layers: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for node in nodes:
        kind = str(node.get("type") or "concept").casefold()
        layers[LAYER_ORDER.get(kind, 2)].append(node)
    for values in layers.values():
        values.sort(key=lambda item: (
            TYPE_ORDER.get(str(item.get("type") or "concept").casefold(), 99),
            -float(item.get("importance", item.get("weight", 0.5)) or 0.0),
            str(item.get("label") or "").casefold(),
            str(item.get("id") or ""),
        ))

    result: dict[str, dict[str, float | int | str]] = {}
    per_row = 6
    row_counts = {layer: max(1, math.ceil(len(values) / per_row)) for layer, values in layers.items()}
    total_rows = sum(row_counts.values())
    row_cursor = 0
    for layer in sorted(layers):
        values = layers[layer]
        row_count = row_counts[layer]
        for index, node in enumerate(values):
            if comparison and str(node.get("type") or "").casefold() == "paper":
                x = (index + 1) / (len(values) + 1)
                y = 0.06
            else:
                row = index // per_row
                position = index % per_row
                items_in_row = min(per_row, len(values) - row * per_row)
                x = (position + 1) / (items_in_row + 1)
                y = (row_cursor + row + 1) / (total_rows + 1)
            kind = str(node.get("type") or "concept").casefold()
            result[str(node.get("id") or "")] = {
                "x": round(x, 6),
                "y": round(y, 6),
                "layer": layer,
                "order": index,
                "lane": str((node.get("details") or {}).get("only_in") or kind),
                "stage": STAGE_NAMES.get(layer, "approach"),
                "type_lane": kind,
            }
        row_cursor += row_count
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
