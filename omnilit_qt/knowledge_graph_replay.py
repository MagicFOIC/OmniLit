from __future__ import annotations

import re
from collections import defaultdict
from typing import Any


RELATION_CUES = {
    "PROPOSES": ("propose", "introduce", "present", "develop", "提出", "介绍"),
    "USES": ("use", "uses", "using", "employ", "采用", "使用"),
    "EVALUATES_ON": ("evaluate", "dataset", "benchmark", "corpus", "数据集", "评估"),
    "MEASURED_BY": ("accuracy", "precision", "recall", "f1", "auc", "measured", "指标"),
    "ACHIEVES": ("achieve", "outperform", "improve", "result", "达到", "提升", "优于"),
    "LIMITS": ("limit", "limitation", "drawback", "局限", "不足"),
    "SUPPORTS": ("show", "demonstrate", "support", "表明", "支持"),
    "CITES": ("et al", "cite", "引用"),
}


def _evidence_key(evidence: dict[str, Any]) -> tuple[int, str, str]:
    try:
        page = int(evidence.get("page", -1) if evidence.get("page") is not None else -1)
    except (TypeError, ValueError):
        page = -1
    element = str(evidence.get("element_id") or evidence.get("elementId") or "")
    excerpt = re.sub(r"\s+", " ", str(evidence.get("excerpt") or "")).strip()
    return page, element, excerpt


def _sort_key(event: dict[str, Any]) -> tuple[int, float, float, str]:
    bbox = event.get("bbox") or []
    try:
        top = float(bbox[1]) if len(bbox) >= 4 else 1e9
        left = float(bbox[0]) if len(bbox) >= 4 else 1e9
    except (TypeError, ValueError):
        top = left = 1e9
    return (
        int(event.get("page", -1)),
        top,
        left,
        str(event.get("elementId") or ""),
    )


def _cue_ranges(text: str, relation_types: list[str]) -> list[dict[str, Any]]:
    folded = text.casefold()
    result: list[dict[str, Any]] = []
    seen: set[tuple[int, int]] = set()
    for relation_type in relation_types:
        for cue in RELATION_CUES.get(relation_type, ()):
            start = folded.find(cue.casefold())
            if start < 0 or (start, start + len(cue)) in seen:
                continue
            seen.add((start, start + len(cue)))
            result.append({"start": start, "length": len(cue), "text": text[start:start + len(cue)], "relationType": relation_type})
            break
    return result


def build_replay_events(graph: dict[str, Any]) -> list[dict[str, Any]]:
    """Group graph mutations by source evidence in document reading order."""
    groups: dict[tuple[int, str, str], dict[str, Any]] = {}
    node_event: dict[str, tuple[int, str, str]] = {}
    nodes = [item for item in graph.get("nodes") or [] if isinstance(item, dict)]
    edges = [item for item in graph.get("edges") or [] if isinstance(item, dict)]
    nodes_by_id = {str(item.get("id") or ""): item for item in nodes if item.get("id")}

    def ensure_event(key: tuple[int, str, str], evidence: dict[str, Any]) -> dict[str, Any]:
        return groups.setdefault(key, {
            "page": key[0], "elementId": key[1], "excerpt": key[2],
            "bbox": list(evidence.get("bbox") or []), "section": str(evidence.get("section") or ""),
            "nodeIds": [], "edgeIds": [], "relationCues": [],
        })

    for node in nodes:
        if str(node.get("type") or "").casefold() == "paper":
            continue
        evidence = next((item for item in node.get("evidence") or [] if isinstance(item, dict) and item.get("excerpt")), None)
        if not evidence:
            continue
        key = _evidence_key(evidence)
        event = ensure_event(key, evidence)
        node_id = str(node.get("id") or "")
        if node_id and node_id not in event["nodeIds"]:
            event["nodeIds"].append(node_id)
            node_event[node_id] = key

    for edge in edges:
        source = str(edge.get("source") or "")
        target = str(edge.get("target") or "")
        keys = [node_event[item] for item in (source, target) if item in node_event]
        evidence = next((item for item in edge.get("relation_evidence") or edge.get("evidence") or [] if isinstance(item, dict) and item.get("excerpt")), None)
        key = _evidence_key(evidence) if evidence else (keys[0] if keys else None)
        if key is None:
            continue
        event = ensure_event(key, evidence) if evidence else groups.get(key)
        if event is None:
            continue
        # A semantic edge appears with the sentence that supplied its evidence.
        edge_id = str(edge.get("id") or "")
        if edge_id and edge_id not in event["edgeIds"]:
            event["edgeIds"].append(edge_id)
        # Relation-only evidence must still reveal its non-paper endpoints so the
        # newly revealed edge has something to connect on the canvas.
        if evidence:
            for node_id in (source, target):
                node = nodes_by_id.get(node_id)
                if node and str(node.get("type") or "").casefold() != "paper" and node_id not in node_event:
                    event["nodeIds"].append(node_id)
                    node_event[node_id] = key

    events = sorted(groups.values(), key=_sort_key)
    for index, event in enumerate(events):
        relation_types = [
            str(edge.get("type") or "") for edge in edges
            if str(edge.get("id") or "") in set(event["edgeIds"])
        ]
        event["relationCues"] = _cue_ranges(str(event["excerpt"]), relation_types)
        event["index"] = index
        event["nodeCount"] = len(event["nodeIds"])
        event["edgeCount"] = len(event["edgeIds"])
    return events
