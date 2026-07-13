from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


VIEW_SNAPSHOT_VERSION = 2


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _bounded_float(value: Any, default: float, minimum: float, maximum: float) -> float:
    try:
        return max(minimum, min(maximum, float(value)))
    except (TypeError, ValueError):
        return default


def _bounded_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        return max(minimum, min(maximum, int(value)))
    except (TypeError, ValueError):
        return default


def normalize_viewport(value: dict[str, Any] | None) -> dict[str, Any]:
    raw = dict(value or {})
    display_style = str(raw.get("displayStyle") or "overview").casefold()
    if display_style not in {"overview", "academic", "radial", "focus"}:
        display_style = "overview"
    return {
        "displayStyle": display_style,
        "focusDepth": _bounded_int(raw.get("focusDepth"), 0, 0, 2),
        "reviewMode": bool(raw.get("reviewMode", False)),
        "graphScale": _bounded_float(raw.get("graphScale"), 1.0, 0.45, 2.5),
        "panX": _bounded_float(raw.get("panX"), 0.0, -100000.0, 100000.0),
        "panY": _bounded_float(raw.get("panY"), 0.0, -100000.0, 100000.0),
        "showArrows": bool(raw.get("showArrows", False)),
        "showLabels": bool(raw.get("showLabels", False)),
        "dimUnrelated": bool(raw.get("dimUnrelated", True)),
        "textFadeThreshold": _bounded_float(raw.get("textFadeThreshold"), 1.15, 0.6, 2.2),
        "nodeSizeScale": _bounded_float(raw.get("nodeSizeScale"), 1.0, 0.6, 1.8),
        "linkThickness": _bounded_float(raw.get("linkThickness"), 1.0, 0.5, 2.5),
        "animateLayout": bool(raw.get("animateLayout", False)),
    }


def normalize_snapshot(value: dict[str, Any], record_id: str = "") -> dict[str, Any] | None:
    raw = dict(value or {})
    snapshot_record = str(raw.get("recordId") or raw.get("record_id") or record_id or "")
    if record_id and snapshot_record and snapshot_record != record_id:
        return None
    name = str(raw.get("name") or "未命名视图").strip()[:80] or "未命名视图"
    created_at = str(raw.get("createdAt") or raw.get("created_at") or _timestamp())
    updated_at = str(raw.get("updatedAt") or raw.get("updated_at") or created_at)
    exploration = dict(raw.get("exploration") or {})
    filters = dict(raw.get("filters") or {})
    selection = dict(raw.get("selection") or {})
    path = dict(raw.get("path") or {})
    pages: dict[str, int] = {}
    for key, offset in (exploration.get("pages") or {}).items():
        try:
            pages[str(key)] = max(0, int(offset))
        except (TypeError, ValueError):
            continue
    return {
        "version": VIEW_SNAPSHOT_VERSION,
        "id": str(raw.get("id") or f"view-{uuid4().hex}"),
        "name": name,
        "recordId": snapshot_record or str(record_id or ""),
        "createdAt": created_at,
        "updatedAt": updated_at,
        "graphFingerprint": str(raw.get("graphFingerprint") or raw.get("graph_fingerprint") or ""),
        "exploration": {
            "nodeIds": list(dict.fromkeys(str(item) for item in exploration.get("nodeIds") or [] if item)),
            "edgeIds": list(dict.fromkeys(str(item) for item in exploration.get("edgeIds") or [] if item)),
            "pages": pages,
        },
        "filters": {
            "mode": str(filters.get("mode") or "all").casefold(),
            "searchText": str(filters.get("searchText") or "")[:500],
            "density": str(filters.get("density") or "normal").casefold(),
            "literatureSortKey": str(filters.get("literatureSortKey") or "relevance").casefold(),
            "literatureSortDescending": bool(filters.get("literatureSortDescending", True)),
            "facets": {
                key: str(value).strip()[:200]
                for key, value in dict(filters.get("facets") or {}).items()
                if key in {"year", "topic", "author", "institution", "venue"} and str(value).strip()
            },
        },
        "selection": {
            "nodeId": str(selection.get("nodeId") or ""),
            "edgeId": str(selection.get("edgeId") or ""),
        },
        "path": {
            "startId": str(path.get("startId") or ""),
            "endId": str(path.get("endId") or ""),
            "directed": bool(path.get("directed", False)),
            "relationFilter": str(path.get("relationFilter") or "all").upper(),
        },
        "viewport": normalize_viewport(raw.get("viewport") or {}),
    }


def make_snapshot(
    record_id: str,
    name: str,
    graph_fingerprint: str,
    exploration: dict[str, Any],
    filters: dict[str, Any],
    selection: dict[str, Any],
    viewport: dict[str, Any],
    existing: dict[str, Any] | None = None,
    path: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = _timestamp()
    raw = {
        "id": (existing or {}).get("id") or f"view-{uuid4().hex}",
        "name": name,
        "recordId": record_id,
        "createdAt": (existing or {}).get("createdAt") or now,
        "updatedAt": now,
        "graphFingerprint": graph_fingerprint,
        "exploration": exploration,
        "filters": filters,
        "selection": selection,
        "path": path or {},
        "viewport": viewport,
    }
    return normalize_snapshot(raw, record_id) or {}


def reconcile_snapshot(snapshot: dict[str, Any], graph: dict[str, Any]) -> tuple[dict[str, Any], dict[str, int]]:
    normalized = normalize_snapshot(snapshot, str(graph.get("recordId") or graph.get("record_id") or ""))
    if normalized is None:
        return {}, {"missingNodes": 0, "missingEdges": 0}
    node_ids = {
        str(item.get("id") or "") for item in graph.get("nodes") or []
        if isinstance(item, dict) and item.get("id")
    }
    edge_ids = {
        str(item.get("id") or "") for item in graph.get("edges") or []
        if isinstance(item, dict) and item.get("id")
    }
    requested_nodes = normalized["exploration"]["nodeIds"]
    requested_edges = normalized["exploration"]["edgeIds"]
    valid_nodes = [item for item in requested_nodes if item in node_ids]
    valid_edges = [item for item in requested_edges if item in edge_ids]
    normalized["exploration"]["nodeIds"] = valid_nodes
    normalized["exploration"]["edgeIds"] = valid_edges
    if normalized["selection"]["nodeId"] not in node_ids:
        normalized["selection"]["nodeId"] = ""
    if normalized["selection"]["edgeId"] not in edge_ids:
        normalized["selection"]["edgeId"] = ""
    if normalized["path"]["startId"] not in node_ids:
        normalized["path"]["startId"] = ""
    if normalized["path"]["endId"] not in node_ids:
        normalized["path"]["endId"] = ""
    return normalized, {
        "missingNodes": len(requested_nodes) - len(valid_nodes),
        "missingEdges": len(requested_edges) - len(valid_edges),
    }


def view_summaries(views: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for item in views:
        normalized = normalize_snapshot(item)
        if normalized:
            result.append({key: normalized[key] for key in ("id", "name", "recordId", "createdAt", "updatedAt", "graphFingerprint")})
    result.sort(key=lambda item: (str(item["updatedAt"]), str(item["name"]).casefold()), reverse=True)
    return result
