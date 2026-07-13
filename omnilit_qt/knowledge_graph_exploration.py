from __future__ import annotations

from collections import Counter
from typing import Any


RELATION_FAMILIES: dict[str, set[str]] = {
    "references": {"CITES"},
    "cited_by": {"CITES"},
    "authors": {"AUTHOR_OF", "WRITTEN_BY"},
    "institutions": {"AFFILIATED_WITH", "ASSOCIATED_WITH"},
    "topics": {"HAS_TOPIC", "MENTIONS", "HAS_KEYWORD"},
    "venues": {"PUBLISHED_IN"},
}


def _mode_matches(edge: dict[str, Any], node_id: str, mode: str) -> bool:
    relation_type = str(edge.get("type") or "").upper()
    source = str(edge.get("source") or "")
    target = str(edge.get("target") or "")
    if mode == "all":
        return True
    if relation_type not in RELATION_FAMILIES.get(mode, set()):
        return False
    if mode == "references":
        return source == node_id
    if mode == "cited_by":
        return target == node_id
    return True


def neighbor_candidates(graph: dict[str, Any], node_id: str, mode: str = "all") -> list[dict[str, Any]]:
    """Return deterministic incident-edge candidates for progressive expansion."""
    node_id = str(node_id or "")
    selected_mode = str(mode or "all").casefold()
    nodes = {
        str(item.get("id") or ""): item
        for item in graph.get("nodes") or []
        if isinstance(item, dict) and item.get("id")
    }
    candidates_by_node: dict[str, dict[str, Any]] = {}
    for edge in graph.get("edges") or []:
        if not isinstance(edge, dict):
            continue
        source = str(edge.get("source") or "")
        target = str(edge.get("target") or "")
        if node_id not in {source, target} or not _mode_matches(edge, node_id, selected_mode):
            continue
        neighbor_id = target if source == node_id else source
        neighbor = nodes.get(neighbor_id)
        if neighbor is None:
            continue
        candidate = candidates_by_node.setdefault(neighbor_id, {"node": neighbor, "edges": []})
        candidate["edges"].append(edge)
    candidates = list(candidates_by_node.values())
    candidates.sort(key=lambda item: (
        -float((item["node"].get("importance", item["node"].get("weight", 0.5)) or 0.0)),
        str(item["node"].get("label") or "").casefold(),
        str(item["edges"][0].get("id") or ""),
    ))
    return candidates


def neighbor_page(
    graph: dict[str, Any],
    node_id: str,
    mode: str = "all",
    offset: int = 0,
    limit: int = 12,
) -> dict[str, Any]:
    candidates = neighbor_candidates(graph, node_id, mode)
    safe_offset = max(0, int(offset))
    safe_limit = max(1, min(100, int(limit)))
    page = candidates[safe_offset:safe_offset + safe_limit]
    next_offset = safe_offset + len(page)
    return {
        "nodeId": str(node_id or ""),
        "relationMode": str(mode or "all").casefold(),
        "status": "ready" if page else "empty",
        "nodeIds": [str(item["node"].get("id") or "") for item in page],
        "edgeIds": list(dict.fromkeys(
            str(edge.get("id") or "")
            for item in page for edge in item["edges"] if edge.get("id")
        )),
        "offset": safe_offset,
        "nextOffset": next_offset,
        "revealed": len(page),
        "total": len(candidates),
        "hasMore": next_offset < len(candidates),
    }


def neighbor_summary(graph: dict[str, Any], node_id: str) -> dict[str, int]:
    counts = {mode: len(neighbor_candidates(graph, node_id, mode)) for mode in RELATION_FAMILIES}
    counts["all"] = len(neighbor_candidates(graph, node_id, "all"))
    return counts


def seed_node_ids(graph: dict[str, Any]) -> list[str]:
    papers = [
        str(item.get("id") or "")
        for item in graph.get("nodes") or []
        if isinstance(item, dict) and str(item.get("type") or "").casefold() == "paper" and item.get("id")
    ]
    record_id = str(graph.get("recordId") or graph.get("record_id") or "")
    preferred = f"paper:{record_id}" if record_id else ""
    if preferred and preferred in papers:
        return [preferred]
    if papers:
        return [papers[0]]
    nodes = [item for item in graph.get("nodes") or [] if isinstance(item, dict) and item.get("id")]
    nodes.sort(key=lambda item: -float(item.get("importance", item.get("weight", 0.5)) or 0.0))
    return [str(nodes[0].get("id") or "")] if nodes else []


def relation_counts(graph: dict[str, Any]) -> dict[str, int]:
    return dict(Counter(str(item.get("type") or "").upper() for item in graph.get("edges") or [] if isinstance(item, dict)))
