from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timezone
from typing import Any


_ENGLISH_STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "been", "but", "by", "can",
    "for", "from", "has", "have", "in", "into", "is", "it", "its", "may",
    "of", "on", "or", "our", "paper", "results", "study", "that", "the",
    "their", "these", "this", "to", "using", "was", "we", "were", "which",
    "with", "within",
}
_ELEMENT_TYPES = {"figure", "table", "formula"}


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        return ", ".join(_text(item) for item in value if _text(item))
    return str(value).strip()


def _split_values(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        values = [_text(item) for item in value]
    else:
        values = re.split(r"[,;，；|\n]+", _text(value))
    return [item.strip() for item in values if item and item.strip()]


def _normalized(value: str) -> str:
    return re.sub(r"[^\w\u3400-\u9fff.-]+", "_", value.casefold(), flags=re.UNICODE).strip("_.") or "item"


def _deduplicate(values: list[str], limit: int = 20) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = value.casefold().strip()
        if key and key not in seen:
            seen.add(key)
            result.append(value.strip())
        if len(result) >= limit:
            break
    return result


def _fallback_keywords(record: dict[str, Any]) -> list[str]:
    text = " ".join(_text(record.get(key)) for key in ("title", "abstract", "contentSummary"))
    english = [
        word for word in re.findall(r"[A-Za-z][A-Za-z0-9-]{2,}", text)
        if word.casefold() not in _ENGLISH_STOP_WORDS
    ]
    english_counts = Counter(word.casefold() for word in english)
    english_display: dict[str, str] = {}
    for word in english:
        english_display.setdefault(word.casefold(), word)

    chinese_candidates: list[str] = []
    for segment in re.findall(r"[\u3400-\u9fff]{2,}", text):
        if len(segment) <= 6:
            chinese_candidates.append(segment)
        else:
            for size in (4, 3, 2):
                chinese_candidates.extend(segment[index:index + size] for index in range(len(segment) - size + 1))
    chinese_counts = Counter(chinese_candidates)
    ranked = [(count, english_display[key]) for key, count in english_counts.items()]
    ranked.extend((count, value) for value, count in chinese_counts.items())
    ranked.sort(key=lambda item: (-item[0], -len(item[1]), item[1].casefold()))
    return _deduplicate([value for _, value in ranked], 20)


def _keywords(record: dict[str, Any]) -> tuple[list[str], str]:
    for key in ("extracted_keywords", "keywordsText", "matchedKeywordsText", "topicTagsText"):
        values = _deduplicate(_split_values(record.get(key)), 20)
        if values:
            return values, f"metadata.{key}"
    return _fallback_keywords(record), "local_fallback"


def _authors(record: dict[str, Any]) -> list[str]:
    for key in ("authors", "author", "authorsText"):
        raw = record.get(key)
        values: list[str] = []
        if isinstance(raw, (list, tuple, set)):
            for item in raw:
                if isinstance(item, dict):
                    nested = item.get("author") if isinstance(item.get("author"), dict) else {}
                    name = (
                        item.get("display_name") or item.get("displayName") or item.get("name")
                        or item.get("authorName") or item.get("full_name")
                        or nested.get("display_name") or nested.get("name")
                    )
                    if name:
                        values.append(_text(name))
                else:
                    values.extend(_split_values(item))
        elif isinstance(raw, dict):
            name = raw.get("display_name") or raw.get("displayName") or raw.get("name") or raw.get("authorName")
            if name:
                values.append(_text(name))
        else:
            values = _split_values(raw)
        if values:
            return _deduplicate(values, 50)
    return []


def build_knowledge_graph(record: dict, extraction_index: dict | None = None) -> dict:
    """Build a deterministic, offline per-paper knowledge graph."""
    record = dict(record or {})
    extraction_index = dict(extraction_index or {})
    record_id = _text(record.get("recordId") or record.get("id") or "record")
    title = _text(record.get("title")) or "Untitled"
    paper_id = f"paper:{record_id}"
    keywords, keyword_evidence = _keywords(record)
    abstract = _text(record.get("abstract"))
    content_summary = _text(record.get("contentSummary"))

    nodes: list[dict[str, Any]] = [{
        "id": paper_id,
        "type": "paper",
        "label": title,
        "weight": 1.0,
        "details": {"doi": _text(record.get("doi")), "pdfPath": _text(record.get("localPdfPath"))},
    }]
    edges: list[dict[str, Any]] = []

    def add_node(kind: str, key: str, label: str, relation: str, evidence: str, details: dict | None = None) -> None:
        node_id = f"{kind}:{_normalized(key)}"
        if any(node["id"] == node_id for node in nodes):
            return
        nodes.append({"id": node_id, "type": kind, "label": label, "weight": 1.0, "details": details or {}})
        edges.append({"source": paper_id, "target": node_id, "type": relation, "weight": 1.0, "evidence": evidence})

    for keyword in keywords:
        add_node("keyword", keyword, keyword, "has_keyword", keyword_evidence)
    for author in _authors(record):
        add_node("author", author, author, "written_by", "metadata.authors")

    journal = _text(record.get("journalTitle") or record.get("journalName") or record.get("journal"))
    if journal:
        add_node("journal", journal, journal, "published_in", "metadata.journal")
    year = _text(record.get("year") or record.get("publicationYear") or record.get("publicationDate"))[:4]
    if year:
        add_node("year", year, year, "published_in_year", "metadata.year")
    if abstract:
        add_node("abstract", record_id, "Abstract", "has_abstract", "metadata.abstract", {"text": abstract})
    if content_summary:
        add_node("summary", record_id, "主要内容", "has_summary", "metadata.contentSummary", {"text": content_summary})

    type_counts: Counter[str] = Counter()
    for index, element in enumerate(extraction_index.get("elements") or []):
        if not isinstance(element, dict):
            continue
        kind = _text(element.get("type")).casefold()
        if kind not in _ELEMENT_TYPES:
            continue
        type_counts[kind] += 1
        element_key = f"{record_id}:{_text(element.get('id')) or f'{kind}-{index + 1}'}"
        label = _text(element.get("caption")) or f"{kind.title()} {type_counts[kind]}"
        details = {key: element.get(key) for key in ("caption", "markdown", "latex", "page", "bbox") if element.get(key) not in (None, "", [])}
        add_node(kind, element_key, label, f"has_{kind}", "extraction_index.elements", details)

    return {
        "version": 1,
        "recordId": record_id,
        "title": title,
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": {
            "pdfPath": _text(record.get("localPdfPath") or extraction_index.get("sourcePath")),
            "extractionEngine": _text(extraction_index.get("engine")),
            "sourceSha256": _text(extraction_index.get("sourceSha256")),
        },
        "summary": {"keywords": keywords, "contentSummary": content_summary, "abstract": abstract},
        "nodes": nodes,
        "edges": edges,
    }


def merge_knowledge_graphs(graphs: list[dict], record_id: str = "comparison") -> dict:
    """Merge paper graphs while sharing semantic metadata nodes."""
    valid = [dict(graph) for graph in graphs if isinstance(graph, dict)]
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    node_ids: set[str] = set()
    edge_keys: set[tuple[str, str, str]] = set()
    keywords: list[str] = []
    record_ids: list[str] = []

    for graph in valid:
        graph_record_id = _text(graph.get("recordId"))
        if graph_record_id:
            record_ids.append(graph_record_id)
        keywords.extend((graph.get("summary") or {}).get("keywords") or [])
        for node in graph.get("nodes") or []:
            if isinstance(node, dict) and _text(node.get("id")) not in node_ids:
                node_ids.add(_text(node.get("id")))
                nodes.append(dict(node))
        for edge in graph.get("edges") or []:
            if not isinstance(edge, dict):
                continue
            key = (_text(edge.get("source")), _text(edge.get("target")), _text(edge.get("type")))
            if key not in edge_keys:
                edge_keys.add(key)
                edges.append(dict(edge))

    return {
        "version": 1,
        "recordId": record_id,
        "title": f"对比知识图谱（{len(valid)} 篇）",
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": {"pdfPath": "", "extractionEngine": "mixed", "sourceSha256": ""},
        "summary": {"keywords": _deduplicate(keywords, 100), "contentSummary": "", "abstract": ""},
        "comparisonRecordIds": record_ids,
        "nodes": nodes,
        "edges": edges,
    }
