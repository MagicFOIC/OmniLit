from __future__ import annotations

import re
from typing import Any


LITERATURE_NODE_TYPES = {"paper", "citation"}
SORT_KEYS = {"relevance", "title", "year", "authors", "citations", "importance"}


def _text(value: Any) -> str:
    if isinstance(value, (list, tuple, set)):
        return ", ".join(str(item).strip() for item in value if str(item).strip())
    return str(value or "").strip()


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _year(node: dict[str, Any], details: dict[str, Any], evidence: list[dict[str, Any]]) -> str:
    explicit = _text(details.get("year") or node.get("year"))[:4]
    if re.fullmatch(r"(?:18|19|20|21)\d{2}", explicit):
        return explicit
    source = " ".join((_text(node.get("label")), _text(node.get("summary")), " ".join(_text(item.get("excerpt")) for item in evidence)))
    match = re.search(r"\b((?:18|19|20|21)\d{2})\b", source)
    return match.group(1) if match else ""


def _relevance(row: dict[str, Any], query: str) -> float:
    importance = _number(row.get("importance"), 0.5)
    folded = query.casefold().strip()
    if not folded:
        return round(importance, 6)
    title = str(row.get("title") or "").casefold()
    authors = str(row.get("authors") or "").casefold()
    venue = str(row.get("venue") or "").casefold()
    score = importance * 0.25
    if title == folded:
        score += 3.0
    elif folded in title:
        score += 2.0
    if folded in authors:
        score += 1.25
    if folded in venue:
        score += 0.75
    if folded in str(row.get("searchText") or "").casefold():
        score += 0.5
    return round(score, 6)


def project_literature_rows(
    graph: dict[str, Any],
    visible_node_ids: set[str] | None = None,
    query: str = "",
    selected_node_id: str = "",
    hovered_node_id: str = "",
    sort_key: str = "relevance",
    descending: bool = True,
) -> list[dict[str, Any]]:
    visible = set(visible_node_ids) if visible_node_ids is not None else None
    central_paper = dict(graph.get("paper") or {})
    incident_cites: dict[str, int] = {}
    for edge in graph.get("edges") or []:
        if not isinstance(edge, dict) or str(edge.get("type") or "").upper() != "CITES":
            continue
        source, target = str(edge.get("source") or ""), str(edge.get("target") or "")
        incident_cites[source] = incident_cites.get(source, 0) + 1
        incident_cites[target] = incident_cites.get(target, 0) + 1

    rows: list[dict[str, Any]] = []
    for node in graph.get("nodes") or []:
        if not isinstance(node, dict):
            continue
        node_id = str(node.get("id") or "")
        kind = str(node.get("type") or "").casefold()
        if not node_id or kind not in LITERATURE_NODE_TYPES or (visible is not None and node_id not in visible):
            continue
        details = dict(node.get("details") or {})
        if kind == "paper":
            details = {**central_paper, **details}
        evidence = [item for item in node.get("evidence") or [] if isinstance(item, dict)]
        title = _text(details.get("title") or node.get("label") or "Untitled")
        authors = _text(details.get("authors") or node.get("authors"))
        venue = _text(details.get("source") or details.get("venue") or details.get("journal") or node.get("venue"))
        citations = int(_number(details.get("citationCount", details.get("citations", incident_cites.get(node_id, 0))), 0))
        importance = _number(node.get("importance", node.get("weight", 0.5)), 0.5)
        paper_ids = details.get("paper_ids") or []
        inferred_record_id = node_id.split(":", 1)[1] if kind == "paper" and node_id.startswith("paper:") else ""
        row = {
            "nodeId": node_id,
            "recordId": str(details.get("recordId") or details.get("record_id") or (paper_ids[0] if paper_ids else "") or inferred_record_id),
            "kind": kind,
            "title": title,
            "year": _year(node, details, evidence),
            "authors": authors,
            "venue": venue,
            "citations": max(0, citations),
            "importance": round(importance, 6),
            "confidence": _number(node.get("confidence"), 1.0),
            "evidenceCount": len(evidence),
            "selected": node_id == str(selected_node_id or ""),
            "hovered": node_id == str(hovered_node_id or ""),
            "searchText": " ".join((title, authors, venue, _text(node.get("summary")), " ".join(_text(tag) for tag in node.get("tags") or []))),
        }
        row["relevance"] = _relevance(row, query)
        rows.append(row)

    selected_sort = str(sort_key or "relevance").casefold()
    if selected_sort not in SORT_KEYS:
        selected_sort = "relevance"

    def key(row: dict[str, Any]) -> tuple[Any, ...]:
        if selected_sort == "title":
            primary: Any = str(row["title"]).casefold()
        elif selected_sort == "year":
            primary = int(row["year"] or 0)
        elif selected_sort == "authors":
            primary = str(row["authors"]).casefold()
        elif selected_sort == "citations":
            primary = int(row["citations"])
        else:
            primary = float(row[selected_sort])
        return primary, str(row["title"]).casefold(), str(row["nodeId"])

    rows.sort(key=key, reverse=bool(descending))
    return rows
