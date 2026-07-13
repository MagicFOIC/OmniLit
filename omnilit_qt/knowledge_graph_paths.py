from __future__ import annotations

from collections import deque
from typing import Any

from .knowledge_graph_ontology import canonical_relation_filter, canonical_relation_type


def _label(node: dict[str, Any] | None, node_id: str) -> str:
    return str((node or {}).get("label") or node_id)


def _confidence(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def shortest_path(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    start_id: str,
    end_id: str,
    *,
    directed: bool = False,
    relation_types: set[str] | None = None,
    max_visited: int = 50_000,
) -> dict[str, Any]:
    """Find and explain a deterministic unweighted shortest path."""
    start = str(start_id or "")
    end = str(end_id or "")
    node_map = {
        str(item.get("id") or ""): item
        for item in nodes if isinstance(item, dict) and item.get("id")
    }
    if start not in node_map or end not in node_map:
        return {
            "status": "invalid", "message": "路径端点不在当前探索子图中。",
            "nodeIds": [], "edgeIds": [], "steps": [], "length": 0, "visited": 0,
        }
    if start == end:
        return {
            "status": "ready", "message": "起点和终点是同一节点。",
            "nodeIds": [start], "edgeIds": [], "steps": [], "length": 0, "visited": 1,
        }

    allowed = {canonical_relation_filter(str(item)) for item in relation_types or set() if str(item).strip()}
    allowed.discard("all")
    adjacency: dict[str, list[tuple[str, dict[str, Any], bool]]] = {node_id: [] for node_id in node_map}
    for edge in edges:
        if not isinstance(edge, dict):
            continue
        source = str(edge.get("source") or "")
        target = str(edge.get("target") or "")
        relation = canonical_relation_type(str(edge.get("type") or "MENTIONS"))
        if source not in node_map or target not in node_map or (allowed and relation not in allowed):
            continue
        adjacency[source].append((target, edge, True))
        if not directed:
            adjacency[target].append((source, edge, False))
    for neighbors in adjacency.values():
        neighbors.sort(key=lambda item: (
            str(item[0]), str(item[1].get("type") or ""), str(item[1].get("id") or ""), not item[2],
        ))

    queue = deque([start])
    previous: dict[str, tuple[str, dict[str, Any], bool] | None] = {start: None}
    while queue:
        current = queue.popleft()
        if len(previous) > max(1, int(max_visited)):
            return {
                "status": "too_large", "message": f"路径搜索超过 {max_visited} 个节点，已安全停止。",
                "nodeIds": [], "edgeIds": [], "steps": [], "length": 0, "visited": len(previous),
            }
        for neighbor, edge, forward in adjacency.get(current, []):
            if neighbor in previous:
                continue
            previous[neighbor] = (current, edge, forward)
            if neighbor == end:
                queue.clear()
                break
            queue.append(neighbor)

    if end not in previous:
        return {
            "status": "no_path", "message": "当前探索子图和关系过滤条件下不存在路径。",
            "nodeIds": [], "edgeIds": [], "steps": [], "length": 0, "visited": len(previous),
        }

    reversed_steps: list[tuple[str, str, dict[str, Any], bool]] = []
    cursor = end
    while cursor != start:
        parent, edge, forward = previous[cursor]  # type: ignore[misc]
        reversed_steps.append((parent, cursor, edge, forward))
        cursor = parent
    path_steps = list(reversed(reversed_steps))
    node_ids = [start] + [target for _, target, _, _ in path_steps]
    edge_ids = [str(edge.get("id") or "") for _, _, edge, _ in path_steps]
    steps: list[dict[str, Any]] = []
    for index, (source_id, target_id, edge, forward) in enumerate(path_steps):
        relation = canonical_relation_type(str(edge.get("type") or "MENTIONS"))
        source_label = _label(node_map.get(source_id), source_id)
        target_label = _label(node_map.get(target_id), target_id)
        arrow = "→" if forward else "←"
        direction_text = "沿关系方向" if forward else "逆关系方向"
        reason = str(edge.get("direction_reason") or edge.get("directionReason") or "")
        confidence = _confidence(edge.get("confidence", edge.get("weight", 1.0)))
        explanation = f"{source_label} {arrow}[{relation}] {target_label}（{direction_text}）"
        if reason:
            explanation += f"；{reason}"
        steps.append({
            "index": index, "sourceId": source_id, "targetId": target_id,
            "sourceLabel": source_label, "targetLabel": target_label,
            "edgeId": str(edge.get("id") or ""), "relationType": relation,
            "forward": forward, "confidence": round(confidence, 4),
            "explanation": explanation,
        })
    return {
        "status": "ready",
        "message": f"找到包含 {len(path_steps)} 条关系的最短路径。",
        "nodeIds": node_ids, "edgeIds": edge_ids, "steps": steps,
        "length": len(path_steps), "visited": len(previous),
    }


def available_relation_types(edges: list[dict[str, Any]]) -> list[str]:
    return sorted({
        canonical_relation_type(str(item.get("type") or ""))
        for item in edges if isinstance(item, dict) and item.get("type")
    })
