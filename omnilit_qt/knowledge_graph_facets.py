from __future__ import annotations

import re
from collections import defaultdict
from typing import Any


FACET_KEYS = ("year", "topic", "author", "institution", "venue")
LITERATURE_TYPES = {"paper", "citation"}


def _values(value: Any) -> list[str]:
    raw = value if isinstance(value, (list, tuple, set)) else re.split(r"[;|\n]", str(value or ""))
    result: list[str] = []
    for item in raw:
        if isinstance(item, dict):
            nested = item.get("author") if isinstance(item.get("author"), dict) else {}
            text = str(item.get("display_name") or item.get("displayName") or item.get("name") or item.get("authorName") or nested.get("display_name") or nested.get("name") or "").strip()
        else:
            text = str(item or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def _year(value: Any) -> str:
    match = re.search(r"\b((?:18|19|20|21)\d{2})\b", str(value or ""))
    return match.group(1) if match else ""


def paper_facets(graph: dict[str, Any]) -> dict[str, dict[str, set[str]]]:
    nodes = [item for item in graph.get("nodes") or [] if isinstance(item, dict)]
    node_map = {str(item.get("id") or ""): item for item in nodes if item.get("id")}
    papers: dict[str, dict[str, set[str]]] = {}
    central = dict(graph.get("paper") or {})
    for node_id, node in node_map.items():
        if str(node.get("type") or "").casefold() not in LITERATURE_TYPES:
            continue
        details = {**(central if str(node.get("type") or "").casefold() == "paper" else {}), **dict(node.get("details") or {})}
        papers[node_id] = {
            "year": set(filter(None, [_year(details.get("year") or node.get("year"))])),
            "topic": set(_values(details.get("topics") or details.get("topic") or details.get("topicName"))),
            "author": set(_values(details.get("authors") or node.get("authors"))),
            "institution": set(_values(details.get("institutions") or details.get("affiliations") or details.get("institution"))),
            "venue": set(_values(details.get("venue") or details.get("source") or details.get("journal") or node.get("venue"))),
        }

    author_papers: dict[str, set[str]] = defaultdict(set)
    author_institutions: dict[str, set[str]] = defaultdict(set)
    for edge in graph.get("edges") or []:
        if not isinstance(edge, dict):
            continue
        source, target = str(edge.get("source") or ""), str(edge.get("target") or "")
        relation = str(edge.get("type") or "").upper()
        source_node, target_node = node_map.get(source, {}), node_map.get(target, {})
        source_type, target_type = str(source_node.get("type") or "").casefold(), str(target_node.get("type") or "").casefold()
        if relation == "AUTHOR_OF" and source_type == "author" and target in papers:
            label = str(source_node.get("label") or "").strip()
            if label:
                papers[target]["author"].add(label)
                author_papers[source].add(target)
        elif relation == "PUBLISHED_IN" and source in papers and target_type == "venue":
            label = str(target_node.get("label") or "").strip()
            if label: papers[source]["venue"].add(label)
        elif relation == "HAS_TOPIC" and source in papers and target_type == "topic":
            label = str(target_node.get("label") or "").strip()
            if label: papers[source]["topic"].add(label)
        elif relation in {"ASSOCIATED_WITH", "AFFILIATED_WITH"}:
            if source in papers and target_type == "institution":
                label = str(target_node.get("label") or "").strip()
                if label: papers[source]["institution"].add(label)
            elif source_type == "author" and target_type == "institution":
                label = str(target_node.get("label") or "").strip()
                if label: author_institutions[source].add(label)
    for author_id, paper_ids in author_papers.items():
        for paper_id in paper_ids:
            papers[paper_id]["institution"].update(author_institutions.get(author_id, set()))
    return papers


def facet_options(graph: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    values = paper_facets(graph)
    result: dict[str, list[dict[str, Any]]] = {}
    for key in FACET_KEYS:
        counts: dict[str, int] = defaultdict(int)
        for item in values.values():
            for value in item[key]: counts[value] += 1
        ordered = sorted(counts.items(), key=lambda item: ((-int(item[0])) if key == "year" and item[0].isdigit() else 0, -item[1], item[0].casefold()))
        result[key] = [{"value": value, "label": value, "count": count} for value, count in ordered]
    return result


def normalize_facet_filters(value: dict[str, Any] | None) -> dict[str, str]:
    raw = dict(value or {})
    return {key: str(raw.get(key) or "").strip()[:200] for key in FACET_KEYS if str(raw.get(key) or "").strip()}


def facet_visible_node_ids(graph: dict[str, Any], filters: dict[str, Any] | None) -> set[str] | None:
    selected = normalize_facet_filters(filters)
    if not selected:
        return None
    facets = paper_facets(graph)
    matched = {
        paper_id for paper_id, values in facets.items()
        if all(expected in values[key] for key, expected in selected.items())
    }
    if not matched:
        return set()
    node_types = {
        str(item.get("id") or ""): str(item.get("type") or "").casefold()
        for item in graph.get("nodes") or [] if isinstance(item, dict)
    }
    visible = set(matched)
    edges = [item for item in graph.get("edges") or [] if isinstance(item, dict)]
    for edge in edges:
        source, target = str(edge.get("source") or ""), str(edge.get("target") or "")
        if source in matched or target in matched:
            visible.update((source, target))
    metadata_types = {"author", "institution", "venue", "topic"}
    metadata_nodes = {item for item in visible if node_types.get(item) in metadata_types}
    for edge in edges:
        source, target = str(edge.get("source") or ""), str(edge.get("target") or "")
        if source in metadata_nodes and node_types.get(target) in metadata_types:
            visible.add(target)
        if target in metadata_nodes and node_types.get(source) in metadata_types:
            visible.add(source)
    return visible
