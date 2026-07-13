from __future__ import annotations

import hashlib
import math
import time
from collections import Counter, defaultdict
from typing import Any, Iterable


RENDER_BUDGETS = {"overview": 240, "normal": 480, "detail": 900}
MAX_RENDER_NODES = 1_200
MAX_AGGREGATE_NODES = 32
SMALL_GRAPH_THRESHOLD = 180
PROJECTION_LATENCY_BUDGET_MS = 120.0


def normalize_render_viewport(viewport: dict[str, Any] | None) -> dict[str, float]:
    value = dict(viewport or {})

    def finite(name: str, default: float, minimum: float, maximum: float) -> float:
        try:
            number = float(value.get(name, default))
        except (TypeError, ValueError):
            number = default
        if not math.isfinite(number):
            number = default
        return max(minimum, min(maximum, number))

    return {
        "width": finite("width", 960.0, 1.0, 16_384.0),
        "height": finite("height", 640.0, 1.0, 16_384.0),
        "scale": finite("scale", 1.0, 0.25, 8.0),
        "panX": finite("panX", 0.0, -1_000_000.0, 1_000_000.0),
        "panY": finite("panY", 0.0, -1_000_000.0, 1_000_000.0),
        "overscan": finite("overscan", 120.0, 0.0, 800.0),
    }


def render_level(scale: Any, total_nodes: int) -> str:
    try:
        zoom = float(scale)
    except (TypeError, ValueError):
        zoom = 1.0
    if total_nodes <= SMALL_GRAPH_THRESHOLD or zoom >= 1.45:
        return "detail"
    if zoom >= 0.78:
        return "normal"
    return "overview"


def render_budget(scale: Any, total_nodes: int) -> int:
    if total_nodes <= SMALL_GRAPH_THRESHOLD:
        return max(1, total_nodes)
    return min(MAX_RENDER_NODES, RENDER_BUDGETS[render_level(scale, total_nodes)])


def _stable_fraction(value: str, salt: str) -> float:
    digest = hashlib.blake2b(f"{salt}:{value}".encode("utf-8", "replace"), digest_size=8).digest()
    return int.from_bytes(digest, "big") / float(2**64 - 1)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _position(node: dict[str, Any], layout: dict[str, Any]) -> tuple[float, float, int]:
    node_id = str(node.get("id") or "")
    point = layout.get(node_id) if isinstance(layout, dict) else None
    if isinstance(point, dict):
        try:
            x = float(point.get("x", 0.5))
            y = float(point.get("y", 0.5))
            layer = int(point.get("layer", 0))
            if math.isfinite(x) and math.isfinite(y):
                return max(0.0, min(1.0, x)), max(0.0, min(1.0, y)), layer
        except (TypeError, ValueError):
            pass
    return 0.04 + _stable_fraction(node_id, "x") * 0.92, 0.05 + _stable_fraction(node_id, "y") * 0.90, 0


def _is_in_view(position: tuple[float, float, int], viewport: dict[str, float]) -> bool:
    width = viewport["width"]
    height = viewport["height"]
    x = 36.0 + position[0] * max(120.0, width - 72.0)
    y = 42.0 + position[1] * max(120.0, height - 92.0)
    screen_x = (x - width / 2.0) * viewport["scale"] + width / 2.0 + viewport["panX"]
    screen_y = (y - height / 2.0) * viewport["scale"] + height / 2.0 + viewport["panY"]
    margin = viewport["overscan"]
    return -margin <= screen_x <= width + margin and -margin <= screen_y <= height + margin


def _node_priority(node: dict[str, Any], degree: int, pinned: bool) -> tuple[Any, ...]:
    node_type = str(node.get("type") or "").casefold()
    try:
        importance = float(node.get("importance", node.get("weight", 0.5)) or 0.0)
    except (TypeError, ValueError):
        importance = 0.0
    try:
        confidence = float(node.get("confidence", 1.0) or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    evidence_count = len(node.get("evidence") or [])
    return (
        1 if pinned else 0,
        1 if node_type == "paper" else 0,
        importance,
        min(1000, degree),
        evidence_count,
        confidence,
        str(node.get("label") or "").casefold(),
        str(node.get("id") or ""),
    )


def _aggregate_group(node_type: str) -> str:
    kind = str(node_type or "unknown").casefold()
    if kind in {"method", "algorithm", "model", "contribution", "comparison"}:
        return "method"
    if kind in {"experiment", "dataset", "metric", "baseline"}:
        return "experiment"
    if kind in {"result", "claim", "conclusion"}:
        return "result"
    if kind in {"author", "institution", "venue"}:
        return "source"
    if kind in {"citation", "paper"}:
        return "literature"
    if kind in {"limitation", "futurework", "missinginfo", "conflict"}:
        return "review"
    if kind in {"figure", "table", "equation"}:
        return "artifact"
    return "concept"


_GROUP_LABELS = {
    "method": "方法",
    "experiment": "实验",
    "result": "结果",
    "source": "作者与来源",
    "literature": "文献",
    "review": "局限与冲突",
    "artifact": "图表与公式",
    "concept": "概念",
}


def _cluster_key(node: dict[str, Any], position: tuple[float, float, int]) -> tuple[str, int, int]:
    return (
        _aggregate_group(str(node.get("type") or "")),
        min(5, max(0, int(position[0] * 6))),
        min(3, max(0, int(position[1] * 4))),
    )


def _cluster_id(key: tuple[str, int, int]) -> str:
    return f"cluster:{key[0]}:{key[1]}:{key[2]}"


def _aggregate_edge_id(source: str, target: str, relation_type: str) -> str:
    digest = hashlib.blake2b(f"{source}|{target}|{relation_type}".encode("utf-8", "replace"), digest_size=8).hexdigest()
    return f"aggregate-edge:{digest}"


def project_render_graph(
    nodes: Iterable[dict[str, Any]],
    edges: Iterable[dict[str, Any]],
    layout: dict[str, Any] | None,
    viewport: dict[str, Any] | None,
    *,
    pinned_node_ids: Iterable[str] = (),
    pinned_edge_ids: Iterable[str] = (),
    layout_style: str = "academic",
) -> dict[str, Any]:
    started = time.perf_counter()
    source_nodes = [item for item in nodes if isinstance(item, dict) and item.get("id")]
    source_edges = [item for item in edges if isinstance(item, dict)]
    normalized_viewport = normalize_render_viewport(viewport)
    total_nodes = len(source_nodes)
    level = render_level(normalized_viewport["scale"], total_nodes)
    budget = render_budget(normalized_viewport["scale"], total_nodes)
    pinned_nodes = {str(item) for item in pinned_node_ids if str(item)}
    pinned_edges = {str(item) for item in pinned_edge_ids if str(item)}
    source_layout = dict(layout or {})

    positions = {str(node.get("id")): _position(node, source_layout) for node in source_nodes}
    degrees: Counter[str] = Counter()
    for edge in source_edges:
        degrees[str(edge.get("source") or "")] += 1
        degrees[str(edge.get("target") or "")] += 1

    spatial_culling = str(layout_style or "academic").casefold() == "academic"
    if total_nodes <= SMALL_GRAPH_THRESHOLD or not spatial_culling:
        candidates = list(source_nodes)
    else:
        candidates = [
            node for node in source_nodes
            if str(node.get("id") or "") in pinned_nodes
            or _is_in_view(positions[str(node.get("id"))], normalized_viewport)
        ]
    candidate_ids = {str(node.get("id")) for node in candidates}
    ranked = sorted(
        candidates,
        key=lambda node: _node_priority(
            node, degrees[str(node.get("id") or "")], str(node.get("id") or "") in pinned_nodes
        ),
        reverse=True,
    )

    aggregate_nodes: list[dict[str, Any]] = []
    node_target: dict[str, str] = {}
    if len(ranked) <= budget:
        real_nodes = ranked
        for node in real_nodes:
            node_id = str(node.get("id"))
            node_target[node_id] = node_id
    else:
        cluster_reserve = min(MAX_AGGREGATE_NODES, max(8, budget // 8))
        real_budget = max(len(pinned_nodes & candidate_ids), budget - cluster_reserve)
        real_nodes = ranked[:real_budget]
        for node in real_nodes:
            node_id = str(node.get("id"))
            node_target[node_id] = node_id

        grouped: dict[tuple[str, int, int], list[dict[str, Any]]] = defaultdict(list)
        for node in ranked[real_budget:]:
            grouped[_cluster_key(node, positions[str(node.get("id"))])].append(node)
        ordered_groups = sorted(grouped.items(), key=lambda item: (-len(item[1]), item[0]))[:cluster_reserve]
        kept_group_keys = {key for key, _ in ordered_groups}
        for key, members in grouped.items():
            if key not in kept_group_keys:
                nearest = min(
                    kept_group_keys,
                    key=lambda other: (0 if other[0] == key[0] else 10) + abs(other[1] - key[1]) + abs(other[2] - key[2]),
                )
                grouped[nearest].extend(members)

        for key, members in ordered_groups:
            members = grouped[key]
            cluster_id = _cluster_id(key)
            xs = [positions[str(item.get("id"))][0] for item in members]
            ys = [positions[str(item.get("id"))][1] for item in members]
            confidences = [_safe_float(item.get("confidence", 1.0), 0.0) for item in members]
            cluster = {
                "id": cluster_id,
                "type": "cluster",
                "label": f"{_GROUP_LABELS.get(key[0], key[0])} · {len(members)}",
                "summary": f"聚合了 {len(members)} 个当前层级暂不展开的节点；放大可查看细节。",
                "aggregate": True,
                "memberCount": len(members),
                "memberSample": [str(item.get("id")) for item in members[:8]],
                "importance": max((_safe_float(item.get("importance", item.get("weight", 0.5)), 0.0) for item in members), default=0.5),
                "confidence": sum(confidences) / max(1, len(confidences)),
                "needs_review": any(bool(item.get("needs_review")) for item in members),
                "evidence": [],
            }
            aggregate_nodes.append(cluster)
            positions[cluster_id] = (sum(xs) / len(xs), sum(ys) / len(ys), 0)
            for member in members:
                node_target[str(member.get("id"))] = cluster_id

    rendered_nodes = [dict(node) for node in real_nodes] + aggregate_nodes
    rendered_ids = {str(node.get("id")) for node in rendered_nodes}

    real_edges: list[dict[str, Any]] = []
    aggregate_edges: dict[tuple[str, str, str], dict[str, Any]] = {}
    for edge in source_edges:
        source_id = str(edge.get("source") or "")
        target_id = str(edge.get("target") or "")
        rendered_source = node_target.get(source_id)
        rendered_target = node_target.get(target_id)
        if not rendered_source or not rendered_target or rendered_source == rendered_target:
            continue
        if rendered_source == source_id and rendered_target == target_id:
            real_edges.append(dict(edge))
            continue
        relation_type = str(edge.get("type") or edge.get("label") or "RELATED_TO").upper()
        key = (rendered_source, rendered_target, relation_type)
        aggregate = aggregate_edges.setdefault(key, {
            "id": _aggregate_edge_id(*key),
            "source": rendered_source,
            "target": rendered_target,
            "type": relation_type,
            "label": relation_type,
            "aggregate": True,
            "count": 0,
            "confidence": 0.0,
            "evidence": [],
        })
        aggregate["count"] += 1
        aggregate["confidence"] += _safe_float(edge.get("confidence", 1.0), 0.0)
    for edge in aggregate_edges.values():
        edge["confidence"] /= max(1, int(edge["count"]))
        edge["label"] = f"{edge['type']} · {edge['count']}"

    edge_budget = max(400, budget * 3)
    real_edges.sort(key=lambda edge: (str(edge.get("id") or "") in pinned_edges, _safe_float(edge.get("confidence", 1.0), 0.0)), reverse=True)
    combined_edges = real_edges + sorted(aggregate_edges.values(), key=lambda edge: int(edge["count"]), reverse=True)
    rendered_edges = [
        edge for edge in combined_edges
        if str(edge.get("source") or "") in rendered_ids and str(edge.get("target") or "") in rendered_ids
    ][:edge_budget]
    render_layout = {
        node_id: {"x": point[0], "y": point[1], "layer": point[2]}
        for node_id, point in positions.items() if node_id in rendered_ids
    }
    aggregated_count = sum(int(node.get("memberCount") or 0) for node in aggregate_nodes)
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    degraded = bool(aggregate_nodes or len(candidate_ids) < total_nodes or len(combined_edges) > len(rendered_edges))
    status = {
        "status": "ready" if rendered_nodes else "empty",
        "level": level,
        "layoutStyle": str(layout_style or "academic"),
        "spatialCulling": spatial_culling,
        "budget": budget,
        "totalSemanticNodes": total_nodes,
        "viewportCandidates": len(candidates),
        "renderedNodes": len(rendered_nodes),
        "realNodes": len(real_nodes),
        "aggregateNodes": len(aggregate_nodes),
        "aggregatedNodes": aggregated_count,
        "culledNodes": max(0, total_nodes - len(candidate_ids)),
        "renderedEdges": len(rendered_edges),
        "totalSemanticEdges": len(source_edges),
        "degraded": degraded,
        "latencyMs": round(elapsed_ms, 3),
        "latencyBudgetMs": PROJECTION_LATENCY_BUDGET_MS,
        "budgetExceeded": elapsed_ms > PROJECTION_LATENCY_BUDGET_MS,
        "performanceStatus": "over_budget" if elapsed_ms > PROJECTION_LATENCY_BUDGET_MS else "ready",
    }
    status["message"] = (
        f"{level} 层级：渲染 {len(rendered_nodes)} / {total_nodes} 个节点"
        + (f"，聚合 {aggregated_count} 个" if aggregated_count else "")
    )
    return {"nodes": rendered_nodes, "edges": rendered_edges, "layout": render_layout, "status": status}
