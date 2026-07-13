from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any, Iterable

from .knowledge_graph_layout import academic_layout, adjacency_index
from .word_cloud_core import STOP_WORDS, extract_phrases


TOPIC_MAP_VERSION = 2
MAX_TOPICS = 12
MAX_FEATURES_PER_PAPER = 48
MAX_NEIGHBORS_PER_PAPER = 12

_EXCLUDED_NODE_TYPES = {
    "paper", "section", "paragraph", "author", "institution", "venue",
    "citation", "figure", "table", "equation", "formula", "missinginfo",
}
_TYPE_WEIGHTS = {
    "concept": 3.0, "problem": 3.2, "researchgap": 3.0, "researchquestion": 3.2,
    "method": 3.4, "algorithm": 3.4, "model": 3.3, "contribution": 3.0,
    "dataset": 2.6, "experiment": 2.4, "baseline": 2.0, "metric": 2.0,
    "result": 1.8, "claim": 1.8, "conclusion": 1.8, "limitation": 1.4, "futurework": 1.4,
}
_GENERIC_TERMS = {
    "paper", "study", "research", "method", "model", "result", "results", "dataset",
    "experiment", "analysis", "approach", "framework", "system", "本文", "研究", "方法",
    "模型", "结果", "实验", "数据集", "框架", "系统", "摘要", "总结",
}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _normalize(value: Any) -> str:
    text = re.sub(r"[^\w\u3400-\u9fff]+", " ", str(value or "").casefold()).strip()
    text = re.sub(r"\s+", " ", text)
    aliases = {
        "large language model": "llm", "large language models": "llm",
        "graph neural networks": "graph neural network", "transformers": "transformer",
        "data set": "dataset", "数据集合": "数据集",
    }
    return aliases.get(text, text)


def _year(value: Any) -> int | None:
    match = re.search(r"(?:19|20)\d{2}", str(value or ""))
    if not match:
        return None
    result = int(match.group(0))
    return result if 1900 <= result <= 2100 else None


def _record_id(graph: dict[str, Any], record: dict[str, Any] | None = None) -> str:
    value = dict(record or {})
    return str(value.get("recordId") or value.get("id") or graph.get("recordId") or graph.get("record_id") or "")


def _paper_details(graph: dict[str, Any], record: dict[str, Any] | None = None) -> dict[str, Any]:
    record_value = dict(record or {})
    paper = dict(graph.get("paper") or {})
    paper_node = next((item for item in graph.get("nodes") or [] if isinstance(item, dict) and str(item.get("type") or "").casefold() == "paper"), {})
    details = dict(paper_node.get("details") or {})
    record_id = _record_id(graph, record_value)
    title = str(record_value.get("title") or paper.get("title") or paper_node.get("label") or graph.get("title") or record_id)
    return {
        "recordId": record_id,
        "nodeId": str(paper_node.get("id") or f"paper:{record_id}"),
        "title": title,
        "year": _year(record_value.get("year") or record_value.get("publicationYear") or record_value.get("publicationDate") or paper.get("year") or details.get("year")),
        "authors": record_value.get("authors") or record_value.get("authorsText") or paper.get("authors") or details.get("authors") or [],
        "venue": str(record_value.get("journalTitle") or record_value.get("journalName") or record_value.get("venue") or paper.get("source") or details.get("source") or ""),
        "institutions": record_value.get("institutions") or record_value.get("affiliations") or record_value.get("institution") or record_value.get("affiliation") or details.get("institutions") or [],
        "doi": str(record_value.get("doi") or paper.get("doi") or details.get("doi") or "").casefold(),
        "record": record_value,
    }


def _add_feature(
    features: dict[str, dict[str, Any]], term: Any, display: Any, weight: float,
    source: str, node_id: str = "",
) -> None:
    normalized = _normalize(term)
    if not normalized or normalized in STOP_WORDS or normalized in _GENERIC_TERMS or len(normalized) < 2 or len(normalized) > 72:
        return
    entry = features.setdefault(normalized, {
        "term": normalized, "display": str(display or term).strip() or normalized,
        "weight": 0.0, "sources": set(), "nodeIds": set(),
    })
    entry["weight"] += max(0.0, weight)
    entry["sources"].add(source)
    if node_id:
        entry["nodeIds"].add(node_id)
    if 1 < len(str(display or "")) < len(entry["display"]):
        entry["display"] = str(display).strip()


def _metadata_keywords(graph: dict[str, Any], record: dict[str, Any]) -> list[str]:
    metadata = graph.get("metadata") or {}
    summary = metadata.get("summary") or graph.get("summary") or {}
    values: list[Any] = []
    values.extend(summary.get("keywords") or [])
    for key in ("keywords", "keywordsText", "matchedKeywords", "matchedKeywordsText", "topicTags", "topicTagsText"):
        value = record.get(key)
        if isinstance(value, list):
            values.extend(value)
        elif value:
            values.extend(re.split(r"[;,|，；]+", str(value)))
    return [str(item).strip() for item in values if str(item).strip()]


def _paper_features(graph: dict[str, Any], record: dict[str, Any] | None = None) -> dict[str, Any]:
    paper = _paper_details(graph, record)
    record_value = paper["record"]
    features: dict[str, dict[str, Any]] = {}
    for keyword in _metadata_keywords(graph, record_value):
        _add_feature(features, keyword, keyword, 4.5, "metadata.keyword")
    for node in graph.get("nodes") or []:
        if not isinstance(node, dict):
            continue
        kind = str(node.get("type") or "").casefold()
        if kind in _EXCLUDED_NODE_TYPES:
            continue
        label = str(node.get("label") or "").strip()
        if not label:
            continue
        importance = _safe_float(node.get("importance", node.get("weight", 0.5)), 0.5)
        confidence = _safe_float(node.get("confidence", 1.0), 0.5)
        keyword_bonus = 1.6 if "keyword" in {str(item).casefold() for item in node.get("tags") or []} else 0.0
        weight = _TYPE_WEIGHTS.get(kind, 1.8) * (0.45 + importance * 0.35 + confidence * 0.20) + keyword_bonus
        _add_feature(features, label, label, weight, f"node.{kind}", str(node.get("id") or ""))
        for tag in node.get("tags") or []:
            _add_feature(features, tag, tag, 0.35, f"tag.{kind}", str(node.get("id") or ""))
    for phrase in extract_phrases(paper["title"])[:18]:
        _add_feature(features, phrase, phrase, 0.75, "metadata.title")
    if not features:
        for token in re.findall(r"[A-Za-z][A-Za-z0-9+-]{2,}|[\u3400-\u9fff]{2,8}", paper["title"]):
            _add_feature(features, token, token, 0.5, "metadata.title_fallback")
    return {"paper": paper, "features": features, "graph": graph}


def extract_feature_documents(
    graphs: list[dict[str, Any]], records: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Return deterministic, JSON-safe per-paper semantic feature documents.

    This is the shared evidence boundary for topic clustering and downstream
    co-occurrence analysis.  It deliberately exposes sources and weights so an
    analysis result can explain why a term was included.
    """
    record_values = {
        str(item.get("recordId") or item.get("id") or ""): dict(item)
        for item in records or [] if isinstance(item, dict)
    }
    documents: list[dict[str, Any]] = []
    seen: set[str] = set()
    for graph in graphs:
        if not isinstance(graph, dict):
            continue
        record_id = _record_id(graph, record_values.get(_record_id(graph)))
        if not record_id or record_id in seen:
            continue
        seen.add(record_id)
        extracted = _paper_features(graph, record_values.get(record_id))
        paper = extracted["paper"]
        features = sorted(
            (
                {
                    "term": str(term),
                    "label": str(feature.get("display") or term),
                    "weight": round(_safe_float(feature.get("weight")), 6),
                    "sources": sorted(str(item) for item in feature.get("sources") or []),
                    "nodeIds": sorted(str(item) for item in feature.get("nodeIds") or []),
                }
                for term, feature in extracted["features"].items()
            ),
            key=lambda item: (-item["weight"], item["term"]),
        )[:MAX_FEATURES_PER_PAPER]
        documents.append({
            "recordId": record_id,
            "title": str(paper.get("title") or record_id),
            "year": paper.get("year") or "",
            "features": features,
        })
    documents.sort(key=lambda item: item["recordId"])
    return documents


def _record_aliases(paper: dict[str, Any]) -> set[str]:
    record = paper.get("record") or {}
    aliases = {str(paper.get("recordId") or "").casefold(), str(paper.get("doi") or "").casefold()}
    for key in ("openalexId", "openalex_id", "semanticScholarId", "semantic_scholar_id", "arxivId", "arxiv_id"):
        if record.get(key):
            aliases.add(str(record[key]).casefold())
    return {item for item in aliases if item}


def _graph_signature(graph: dict[str, Any]) -> str:
    explicit = str(graph.get("source_fingerprint") or (graph.get("metadata") or {}).get("source_fingerprint") or "")
    if explicit:
        return explicit
    payload = {
        "recordId": graph.get("recordId") or graph.get("record_id"),
        "paper": graph.get("paper") or {},
        "nodes": [
            {key: node.get(key) for key in ("id", "type", "label", "importance", "confidence", "tags")}
            for node in graph.get("nodes") or [] if isinstance(node, dict)
        ],
        "edges": [
            {key: edge.get(key) for key in ("id", "source", "target", "type", "confidence")}
            for edge in graph.get("edges") or [] if isinstance(edge, dict)
        ],
    }
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _reference_values(record: dict[str, Any]) -> list[Any]:
    result: list[Any] = []
    for key in ("references", "referencedWorks", "referenced_works", "citedWorks", "cited_works", "citations"):
        value = record.get(key)
        if isinstance(value, list):
            result.extend(value)
        elif value:
            result.append(value)
    return result


def _citation_links(papers: list[dict[str, Any]]) -> set[tuple[str, str]]:
    alias_index: dict[str, str] = {}
    title_index: dict[str, str] = {}
    for item in papers:
        record_id = str(item["paper"]["recordId"])
        for alias in _record_aliases(item["paper"]):
            alias_index[alias] = record_id
        title = _normalize(item["paper"]["title"])
        if title:
            title_index[title] = record_id
    links: set[tuple[str, str]] = set()
    for item in papers:
        source = str(item["paper"]["recordId"])
        candidates: list[tuple[str, str]] = []
        for value in _reference_values(item["paper"].get("record") or {}):
            if isinstance(value, dict):
                identifier = str(value.get("id") or value.get("doi") or value.get("recordId") or "").casefold()
                title = _normalize(value.get("title"))
            else:
                identifier = str(value).casefold()
                title = _normalize(value)
            candidates.append((identifier, title))
        for node in item["graph"].get("nodes") or []:
            if isinstance(node, dict) and str(node.get("type") or "").casefold() == "citation":
                details = node.get("details") or {}
                candidates.append((str(details.get("doi") or details.get("id") or "").casefold(), _normalize(node.get("label"))))
        for identifier, title in candidates:
            target = alias_index.get(identifier) or title_index.get(title)
            if not target and len(title) >= 16:
                matches = [record_id for known, record_id in title_index.items() if title in known or known in title]
                target = matches[0] if len(set(matches)) == 1 else ""
            if target and target != source:
                links.add((source, target))
    return links


def _vectorize(papers: list[dict[str, Any]]) -> tuple[dict[str, dict[str, float]], dict[str, dict[str, Any]], Counter[str]]:
    document_frequency: Counter[str] = Counter()
    labels: dict[str, dict[str, Any]] = {}
    for item in papers:
        for term, feature in item["features"].items():
            document_frequency[term] += 1
            label = labels.setdefault(term, {"display": feature["display"], "sources": set()})
            label["sources"].update(feature["sources"])
    count = max(1, len(papers))
    vectors: dict[str, dict[str, float]] = {}
    for item in papers:
        record_id = str(item["paper"]["recordId"])
        weighted: list[tuple[str, float]] = []
        for term, feature in item["features"].items():
            frequency = document_frequency[term]
            idf = math.log((count + 1) / (frequency + 1)) + 1.0
            if frequency / count > 0.72:
                idf *= 0.18
            weighted.append((term, math.log1p(_safe_float(feature["weight"], 0.0)) * idf))
        weighted.sort(key=lambda pair: (-pair[1], pair[0]))
        vector = dict(weighted[:MAX_FEATURES_PER_PAPER])
        norm = math.sqrt(sum(value * value for value in vector.values())) or 1.0
        vectors[record_id] = {term: value / norm for term, value in vector.items()}
    return vectors, labels, document_frequency


def _similarity_graph(
    vectors: dict[str, dict[str, float]], citation_links: set[tuple[str, str]],
) -> tuple[dict[str, dict[str, float]], dict[tuple[str, str], dict[str, Any]]]:
    ids = sorted(vectors)
    postings: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for record_id, vector in vectors.items():
        for term, value in vector.items():
            postings[term].append((record_id, value))
    pair_scores: dict[tuple[str, str], float] = defaultdict(float)
    max_postings = max(30, min(300, int(len(ids) * 0.40) or 30))
    for term in sorted(postings):
        values = sorted(postings[term])
        if len(values) > max_postings:
            # Preserve large coherent topics without materializing a quadratic
            # posting-list clique. Adjacent deterministic links are sufficient
            # for connected-component clustering and retain linear cost.
            for index, (left, left_weight) in enumerate(values):
                for offset in (1, 2):
                    if index + offset >= len(values):
                        break
                    right, right_weight = values[index + offset]
                    pair_scores[(left, right)] += left_weight * right_weight
            continue
        for left_index, (left, left_weight) in enumerate(values):
            for right, right_weight in values[left_index + 1:]:
                pair_scores[(left, right)] += left_weight * right_weight
    citation_pairs = {tuple(sorted(pair)) for pair in citation_links}
    for pair in citation_pairs:
        if pair[0] in vectors and pair[1] in vectors:
            pair_scores[pair] += 0.22
    neighbors: dict[str, list[tuple[str, float]]] = defaultdict(list)
    explanations: dict[tuple[str, str], dict[str, Any]] = {}
    for pair, score in pair_scores.items():
        if score < 0.10:
            continue
        left, right = pair
        neighbors[left].append((right, score))
        neighbors[right].append((left, score))
        shared = sorted(set(vectors[left]) & set(vectors[right]), key=lambda term: (-(vectors[left][term] * vectors[right][term]), term))[:5]
        explanations[pair] = {"score": round(min(1.0, score), 4), "sharedTerms": shared, "citation": pair in citation_pairs}
    adjacency: dict[str, dict[str, float]] = {record_id: {} for record_id in ids}
    for record_id in ids:
        for neighbor, score in sorted(neighbors.get(record_id, []), key=lambda item: (-item[1], item[0]))[:MAX_NEIGHBORS_PER_PAPER]:
            adjacency[record_id][neighbor] = score
            adjacency[neighbor][record_id] = max(score, adjacency[neighbor].get(record_id, 0.0))
    return adjacency, explanations


class _UnionFind:
    def __init__(self, values: Iterable[str]) -> None:
        self.parent = {value: value for value in values}

    def find(self, value: str) -> str:
        while self.parent[value] != value:
            self.parent[value] = self.parent[self.parent[value]]
            value = self.parent[value]
        return value

    def union(self, left: str, right: str) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root == right_root:
            return
        first, second = sorted((left_root, right_root))
        self.parent[second] = first


def _cluster_papers(ids: list[str], adjacency: dict[str, dict[str, float]]) -> tuple[list[dict[str, Any]], list[str]]:
    union = _UnionFind(ids)
    for left in ids:
        for right, score in adjacency.get(left, {}).items():
            if left < right and score >= 0.22:
                union.union(left, right)
    grouped: dict[str, list[str]] = defaultdict(list)
    for record_id in ids:
        grouped[union.find(record_id)].append(record_id)
    clusters = [
        {"paperIds": sorted(values), "kind": "topic" if len(values) >= 2 else "singleton"}
        for values in grouped.values() if len(values) >= 2 or len(ids) <= 4
    ]
    assigned = {record_id for cluster in clusters for record_id in cluster["paperIds"]}
    unassigned = sorted(set(ids) - assigned)
    if unassigned:
        clusters.append({"paperIds": unassigned, "kind": "unassigned"})
    clusters.sort(key=lambda item: (-len(item["paperIds"]), item["paperIds"]))
    if len(clusters) > MAX_TOPICS:
        kept = clusters[:MAX_TOPICS - 1]
        overflow = sorted(record_id for cluster in clusters[MAX_TOPICS - 1:] for record_id in cluster["paperIds"])
        kept.append({"paperIds": overflow, "kind": "unassigned"})
        clusters = kept
    return clusters, unassigned


def _centroid(member_ids: list[str], vectors: dict[str, dict[str, float]]) -> dict[str, float]:
    result: dict[str, float] = defaultdict(float)
    for record_id in member_ids:
        for term, value in vectors.get(record_id, {}).items():
            result[term] += value / max(1, len(member_ids))
    norm = math.sqrt(sum(value * value for value in result.values())) or 1.0
    return {term: value / norm for term, value in result.items()}


def _cosine(vector: dict[str, float], centroid: dict[str, float]) -> float:
    if len(vector) > len(centroid):
        vector, centroid = centroid, vector
    return sum(value * centroid.get(term, 0.0) for term, value in vector.items())


def _author_names(value: Any) -> list[str]:
    raw = value if isinstance(value, (list, tuple, set)) else re.split(r"[;|\n]", str(value or ""))
    result: list[str] = []
    for item in raw:
        if isinstance(item, dict):
            nested = item.get("author") if isinstance(item.get("author"), dict) else {}
            name = str(item.get("display_name") or item.get("displayName") or item.get("name") or item.get("authorName") or nested.get("display_name") or nested.get("name") or "").strip()
        else:
            name = str(item or "").strip()
        if name and name not in result:
            result.append(name)
    return result


def _growth(member_ids: list[str], paper_by_id: dict[str, dict[str, Any]]) -> tuple[list[dict[str, int]], dict[str, Any]]:
    years = [paper_by_id[item]["paper"]["year"] for item in member_ids if paper_by_id[item]["paper"]["year"]]
    counts = Counter(years)
    timeline = [{"year": year, "count": counts[year]} for year in sorted(counts)]
    if not years:
        return timeline, {"status": "unknown", "trend": "unknown", "rate": 0.0, "recentCount": 0, "previousCount": 0, "label": "年份数据不足"}
    end = max(years)
    recent = sum(count for year, count in counts.items() if end - 2 <= year <= end)
    previous = sum(count for year, count in counts.items() if end - 5 <= year <= end - 3)
    rate = (recent - previous) / max(1, previous)
    trend = "growing" if recent >= previous + 2 and rate >= 0.25 else "declining" if previous >= recent + 2 and rate <= -0.25 else "stable"
    labels = {"growing": "增长", "declining": "回落", "stable": "稳定"}
    return timeline, {
        "status": "ready", "trend": trend, "rate": round(rate, 4),
        "recentCount": recent, "previousCount": previous, "windowEnd": end,
        "label": labels[trend],
    }


def _bubble_layout(topics: list[dict[str, Any]]) -> None:
    if not topics:
        return
    maximum = max(int(item["size"]) for item in topics)
    largest_radius = min(0.19, 0.33 / math.sqrt(max(1, len(topics))))
    occupied: list[tuple[float, float, float]] = []
    golden = math.pi * (3.0 - math.sqrt(5.0))
    for index, topic in enumerate(topics):
        radius = 0.052 + max(0.0, largest_radius - 0.052) * math.sqrt(int(topic["size"]) / max(1, maximum))
        chosen = None
        for step in range(4_000):
            if index == 0 and step == 0:
                x, y = 0.5, 0.5
            else:
                angle = (step + index * 7) * golden
                distance = 0.012 * math.sqrt(step + 1)
                x = 0.5 + math.cos(angle) * distance * 1.22
                y = 0.5 + math.sin(angle) * distance * 0.82
            if x - radius < 0.03 or x + radius > 0.97 or y - radius < 0.04 or y + radius > 0.96:
                continue
            if any(math.hypot(x - ox, y - oy) < radius + other_radius + 0.018 for ox, oy, other_radius in occupied):
                continue
            chosen = (x, y)
            break
        if chosen is None:
            angle = index * golden
            chosen = (0.5 + math.cos(angle) * 0.30, 0.5 + math.sin(angle) * 0.22)
        occupied.append((chosen[0], chosen[1], radius))
        topic.update({"x": round(chosen[0], 6), "y": round(chosen[1], 6), "radius": round(radius, 6), "colorIndex": index % 8})


def build_topic_map(graphs: list[dict[str, Any]], records: list[dict[str, Any]] | None = None, title: str = "领域主题地图") -> dict[str, Any]:
    record_values = {str(item.get("recordId") or item.get("id") or ""): dict(item) for item in records or [] if isinstance(item, dict)}
    extracted = []
    seen: set[str] = set()
    for graph in graphs:
        if not isinstance(graph, dict):
            continue
        record_id = _record_id(graph, record_values.get(_record_id(graph)))
        if not record_id or record_id in seen:
            continue
        seen.add(record_id)
        extracted.append(_paper_features(graph, record_values.get(record_id)))
    extracted.sort(key=lambda item: str(item["paper"]["recordId"]))
    vectors, labels, document_frequency = _vectorize(extracted)
    citation_links = _citation_links(extracted)
    citation_pair_set = {tuple(sorted(pair)) for pair in citation_links}
    citation_directions_by_pair: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for source, target in sorted(citation_links):
        citation_directions_by_pair[tuple(sorted((source, target)))].append({"source": source, "target": target})
    adjacency, pair_explanations = _similarity_graph(vectors, citation_links)
    ids = sorted(vectors)
    raw_clusters, unassigned = _cluster_papers(ids, adjacency)
    paper_by_id = {str(item["paper"]["recordId"]): item for item in extracted}
    topics: list[dict[str, Any]] = []
    topic_centroids: dict[str, dict[str, float]] = {}
    assignments: list[dict[str, Any]] = []
    for cluster in raw_clusters:
        member_ids = cluster["paperIds"]
        centroid = _centroid(member_ids, vectors)
        ranked_terms = sorted(centroid, key=lambda term: (-centroid[term], term))
        meaningful_terms = [term for term in ranked_terms if document_frequency[term] < len(extracted) or len(extracted) == 1]
        top_terms = meaningful_terms[:6] or ranked_terms[:6]
        display_terms = [str(labels.get(term, {}).get("display") or term) for term in top_terms]
        if cluster["kind"] == "unassigned":
            topic_name = "其他与待归类方向"
        else:
            topic_name = " · ".join(display_terms[:2]) or "未命名主题"
        digest = hashlib.sha1((cluster["kind"] + "\n" + "\n".join(member_ids)).encode("utf-8")).hexdigest()[:12]
        topic_id = f"topic:{digest}"
        topic_centroids[topic_id] = centroid
        scores = {record_id: max(0.0, min(1.0, _cosine(vectors.get(record_id, {}), centroid))) for record_id in member_ids}
        representative = sorted(member_ids, key=lambda record_id: (-scores[record_id], -len(adjacency.get(record_id, {})), record_id))[:5]
        representatives = []
        for record_id in representative:
            shared = [term for term in top_terms if term in vectors.get(record_id, {})][:3]
            reason = "、".join(str(labels.get(term, {}).get("display") or term) for term in shared)
            representatives.append({
                "recordId": record_id,
                "title": paper_by_id[record_id]["paper"]["title"],
                "year": paper_by_id[record_id]["paper"]["year"] or "",
                "score": round(scores[record_id], 4),
                "reason": f"覆盖主题核心概念：{reason}" if reason else "该主题中的结构中心论文",
            })
        subtopics = []
        for term in top_terms[2:6]:
            paper_ids = [record_id for record_id in member_ids if term in vectors.get(record_id, {})]
            if paper_ids:
                subtopics.append({"name": str(labels.get(term, {}).get("display") or term), "count": len(paper_ids), "paperIds": paper_ids})
        timeline, growth = _growth(member_ids, paper_by_id)
        internal_links = []
        for left in member_ids:
            for right, weight in adjacency.get(left, {}).items():
                if left < right and right in scores:
                    pair = (left, right)
                    info = pair_explanations.get(pair, {"sharedTerms": [], "citation": False})
                    citation_directions = citation_directions_by_pair.get((left, right), [])
                    internal_links.append({
                        "source": left, "target": right, "weight": round(min(1.0, weight), 4),
                        "sharedTerms": info.get("sharedTerms") or [], "citation": bool(info.get("citation")),
                        "citationDirections": citation_directions,
                    })
        internal_links.sort(key=lambda item: (-int(bool(item["citation"])), -item["weight"], item["source"], item["target"]))
        topic_term_details = [{
            "term": term,
            "label": str(labels.get(term, {}).get("display") or term),
            "weight": round(centroid.get(term, 0.0), 4),
            "paperCount": sum(term in vectors.get(record_id, {}) for record_id in member_ids),
            "sources": sorted(labels.get(term, {}).get("sources") or []),
        } for term in top_terms]
        years = [paper_by_id[item]["paper"]["year"] for item in member_ids if paper_by_id[item]["paper"]["year"]]
        cohesion = sum(scores.values()) / max(1, len(scores))
        author_papers: dict[str, set[str]] = defaultdict(set)
        author_scores: dict[str, float] = defaultdict(float)
        for record_id in member_ids:
            for author in _author_names(paper_by_id[record_id]["paper"].get("authors")):
                author_papers[author].add(record_id)
                author_scores[author] += scores[record_id]
        representative_authors = [{
            "name": author,
            "paperCount": len(author_papers[author]),
            "score": round(author_scores[author] / max(1, len(author_papers[author])), 4),
            "paperIds": sorted(author_papers[author]),
            "reason": f"在该主题贡献 {len(author_papers[author])} 篇论文；论文平均主题中心度 {author_scores[author] / max(1, len(author_papers[author])):.2f}",
        } for author in sorted(author_papers, key=lambda item: (-len(author_papers[item]), -author_scores[item] / max(1, len(author_papers[item])), item.casefold()))[:8]]
        topic = {
            "id": topic_id, "name": topic_name, "kind": cluster["kind"],
            "size": len(member_ids), "share": round(len(member_ids) / max(1, len(extracted)), 4),
            "paperIds": member_ids, "representativePapers": representatives,
            "representativeAuthors": representative_authors,
            "subtopics": subtopics, "topTerms": topic_term_details,
            "yearStart": min(years) if years else "", "yearEnd": max(years) if years else "",
            "yearlyCounts": timeline, "growth": growth,
            "cohesion": round(cohesion, 4), "lowConfidence": cluster["kind"] != "topic" or cohesion < 0.18,
            "paperLinks": internal_links[:max(40, len(member_ids) * 4)],
            "explanation": {
                "method": "TF-IDF 加权语义实体、关键词相似度与馆藏内引文链接的确定性聚类",
                "sharedCitationLinks": sum(bool(item["citation"]) for item in internal_links),
                "reasons": [
                    f"{len(member_ids)} 篇论文共享核心语义特征",
                    f"主题内聚度 {cohesion:.2f}",
                    "低证据论文会标为待归类" if cluster["kind"] != "topic" else "代表论文按主题中心性排序",
                ],
            },
        }
        topics.append(topic)
        for record_id in member_ids:
            shared = [term for term in top_terms if term in vectors.get(record_id, {})][:4]
            citation_neighbors = sum(1 for neighbor in adjacency.get(record_id, {}) if neighbor in scores and tuple(sorted((record_id, neighbor))) in citation_pair_set)
            assignments.append({
                "recordId": record_id, "topicId": topic_id, "score": round(scores[record_id], 4),
                "topTerms": shared,
                "reasons": [
                    "共享概念：" + "、".join(str(labels.get(term, {}).get("display") or term) for term in shared) if shared else "语义证据不足，暂归入其他方向",
                    f"与主题内 {citation_neighbors} 篇论文存在馆藏引文联系" if citation_neighbors else "未检测到馆藏内直接引文联系",
                ],
            })
    topics.sort(key=lambda item: (-item["size"], item["name"], item["id"]))
    _bubble_layout(topics)
    topic_links: list[dict[str, Any]] = []
    for left_index, left in enumerate(topics):
        for right in topics[left_index + 1:]:
            similarity = max(0.0, min(1.0, _cosine(topic_centroids.get(left["id"], {}), topic_centroids.get(right["id"], {}))))
            if similarity < 0.04:
                continue
            left_terms = {str(item.get("term") or ""): str(item.get("label") or "") for item in left.get("topTerms") or []}
            right_terms = {str(item.get("term") or ""): str(item.get("label") or "") for item in right.get("topTerms") or []}
            shared = [left_terms[term] for term in left_terms if term in right_terms][:4]
            topic_links.append({
                "sourceTopicId": left["id"], "targetTopicId": right["id"],
                "similarity": round(similarity, 4), "sharedTerms": shared,
                "reason": ("共享核心主题词：" + "、".join(shared)) if shared else "主题质心在完整语义特征空间中相似",
            })
    topic_links.sort(key=lambda item: (-item["similarity"], item["sourceTopicId"], item["targetTopicId"]))
    degrees: Counter[str] = Counter()
    visible_topic_links = []
    for link in topic_links:
        source, target = link["sourceTopicId"], link["targetTopicId"]
        if degrees[source] >= 3 or degrees[target] >= 3:
            continue
        visible_topic_links.append(link)
        degrees[source] += 1
        degrees[target] += 1
    topic_order = {topic["id"]: index for index, topic in enumerate(topics)}
    assignments.sort(key=lambda item: (topic_order.get(item["topicId"], 999), -item["score"], item["recordId"]))
    assignment_topics = {str(item["recordId"]): str(item["topicId"]) for item in assignments}
    collection_citations = [{
        "source": source, "target": target,
        "sourceTopicId": assignment_topics.get(source, ""),
        "targetTopicId": assignment_topics.get(target, ""),
        "crossTopic": bool(assignment_topics.get(source) and assignment_topics.get(target) and assignment_topics.get(source) != assignment_topics.get(target)),
        "sourceKind": "collection_metadata",
    } for source, target in sorted(citation_links)]
    fingerprints = sorted(_graph_signature(graph) for graph in graphs if isinstance(graph, dict))
    record_signature = [{
        "id": key,
        **{field: value.get(field) for field in (
            "title", "year", "publicationYear", "publicationDate", "keywords", "keywordsText",
            "matchedKeywords", "matchedKeywordsText", "topicTags", "topicTagsText", "authors", "authorsText", "doi",
            "references", "referencedWorks", "referenced_works", "citedWorks", "cited_works",
        )},
    } for key, value in sorted(record_values.items())]
    cache_payload = json.dumps({"version": TOPIC_MAP_VERSION, "fingerprints": fingerprints, "records": record_signature}, ensure_ascii=False, sort_keys=True, default=str)
    return {
        "version": TOPIC_MAP_VERSION, "title": str(title or "领域主题地图"),
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "cacheKey": hashlib.sha256(cache_payload.encode("utf-8")).hexdigest(),
        "sourceCount": len(graphs), "analyzedPaperCount": len(extracted),
        "clusterCount": len(topics), "topics": topics, "assignments": assignments,
        "topicLinks": visible_topic_links,
        "citationLinks": collection_citations,
        "unassignedPaperIds": unassigned,
        "diagnostics": {
            "featureCount": len(labels), "similarityLinkCount": sum(len(value) for value in adjacency.values()) // 2,
            "citationLinkCount": len(citation_links), "maxTopics": MAX_TOPICS,
            "topicSimilarityLinkCount": len(visible_topic_links),
            "method": "deterministic_weighted_components_v1",
        },
    }


def build_topic_graph(
    topic_map: dict[str, Any], topic_id: str, graphs: list[dict[str, Any]], records: list[dict[str, Any]] | None = None,
    paper_ids: list[str] | None = None,
) -> dict[str, Any]:
    topic = next((item for item in topic_map.get("topics") or [] if str(item.get("id") or "") == str(topic_id or "")), None)
    if not isinstance(topic, dict):
        return {}
    member_ids = {str(item) for item in topic.get("paperIds") or []}
    if paper_ids is not None:
        member_ids &= {str(item) for item in paper_ids}
    if not member_ids:
        return {}
    record_values = {str(item.get("recordId") or item.get("id") or ""): dict(item) for item in records or [] if isinstance(item, dict)}
    graph_by_id = {_record_id(graph, record_values.get(_record_id(graph))): graph for graph in graphs if isinstance(graph, dict)}
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    for record_id in sorted(member_ids):
        graph = graph_by_id.get(record_id) or {}
        details = _paper_details(graph, record_values.get(record_id))
        original = next((item for item in graph.get("nodes") or [] if isinstance(item, dict) and str(item.get("type") or "").casefold() == "paper"), {})
        node = dict(original or {})
        node.update({
            "id": str(node.get("id") or f"paper:{record_id}"), "type": "paper",
            "label": details["title"], "importance": 1.0, "confidence": _safe_float(node.get("confidence", 1.0), 1.0),
            "details": {
                **dict(node.get("details") or {}), "recordId": record_id, "year": details["year"] or "",
                "topicId": topic_id, "topic": str(topic.get("name") or ""),
                "authors": details["authors"], "venue": details["venue"], "institutions": details["institutions"],
            },
        })
        nodes.append(node)
    paper_node_ids = {str((node.get("details") or {}).get("recordId")): str(node["id"]) for node in nodes}
    topic_node_id = f"topic-node:{hashlib.sha1(str(topic_id).encode('utf-8')).hexdigest()[:12]}"
    nodes.append({
        "id": topic_node_id, "type": "topic", "label": str(topic.get("name") or "未命名主题"),
        "summary": str((topic.get("explanation") or {}).get("method") or "领域主题聚类。"),
        "importance": 0.98, "confidence": max(0.4, _safe_float(topic.get("cohesion"), 0.5)),
        "tags": ["topic", "cluster"], "evidence": [],
        "details": {"topicId": topic_id, "paperCount": len(member_ids), "cohesion": topic.get("cohesion", 0.0)},
    })
    assignments = {str(item.get("recordId") or ""): item for item in topic_map.get("assignments") or [] if isinstance(item, dict)}
    edge_index = 0
    for record_id in sorted(member_ids):
        edge_index += 1
        edges.append({
            "id": f"topic-edge:{edge_index}", "source": paper_node_ids[record_id], "target": topic_node_id,
            "type": "HAS_TOPIC", "label": "研究主题", "confidence": _safe_float(assignments.get(record_id, {}).get("score"), 0.0),
            "evidence": [], "details": {"topicId": topic_id},
            "direction_reason": "主题聚类将论文归入该研究主题。",
        })
    term_node_ids: dict[str, str] = {}
    for index, term in enumerate((topic.get("topTerms") or [])[:8]):
        normalized = str(term.get("term") or "")
        node_id = f"topic-term:{hashlib.sha1((str(topic_id) + ':' + normalized).encode('utf-8')).hexdigest()[:12]}"
        term_node_ids[normalized] = node_id
        evidence = []
        for record_id in sorted(member_ids):
            for source_node in graph_by_id.get(record_id, {}).get("nodes") or []:
                if isinstance(source_node, dict) and _normalize(source_node.get("label")) == normalized:
                    evidence.extend(item for item in source_node.get("evidence") or [] if isinstance(item, dict))
        nodes.append({
            "id": node_id, "type": "concept", "label": str(term.get("label") or normalized),
            "summary": f"主题“{topic.get('name')}”的共享概念，覆盖 {term.get('paperCount', 0)} 篇论文。",
            "importance": 0.92 - index * 0.045, "confidence": min(1.0, 0.55 + _safe_float(term.get("weight"), 0.0)),
            "tags": ["topic", "shared_concept"], "evidence": evidence[:12],
            "details": {"topicId": topic_id, "paperCount": int(term.get("paperCount") or 0), "sources": term.get("sources") or []},
        })
    extracted = {_record_id(graph, record_values.get(_record_id(graph))): _paper_features(graph, record_values.get(_record_id(graph))) for graph in graphs if isinstance(graph, dict)}
    for record_id in sorted(member_ids):
        features = extracted.get(record_id, {}).get("features") or {}
        for term, term_node_id in term_node_ids.items():
            if term not in features:
                continue
            edge_index += 1
            edges.append({
                "id": f"topic-edge:{edge_index}", "source": paper_node_ids[record_id], "target": term_node_id,
                "type": "MENTIONS", "label": "主题特征", "confidence": min(1.0, _safe_float(features[term].get("weight"), 0.0) / 5.0),
                "evidence": [], "details": {"term": term, "sources": sorted(features[term].get("sources") or [])},
                "direction_reason": "论文的关键词或语义实体支持该主题特征",
            })
    for link in topic.get("paperLinks") or []:
        source = str(link.get("source") or "")
        target = str(link.get("target") or "")
        if source not in paper_node_ids or target not in paper_node_ids:
            continue
        citation_directions = [item for item in link.get("citationDirections") or [] if isinstance(item, dict)]
        if citation_directions:
            for direction in citation_directions:
                citation_source = str(direction.get("source") or "")
                citation_target = str(direction.get("target") or "")
                if citation_source not in paper_node_ids or citation_target not in paper_node_ids:
                    continue
                edge_index += 1
                edges.append({
                    "id": f"topic-edge:{edge_index}", "source": paper_node_ids[citation_source], "target": paper_node_ids[citation_target],
                    "type": "CITES", "label": "馆藏内引文", "confidence": _safe_float(link.get("weight"), 0.0),
                    "evidence": [], "details": {"sharedTerms": link.get("sharedTerms") or []},
                    "direction_reason": "馆藏元数据中的引文方向",
                })
        else:
            edge_index += 1
            edges.append({
                "id": f"topic-edge:{edge_index}", "source": paper_node_ids[source], "target": paper_node_ids[target],
                "type": "SIMILAR_TO", "label": "主题相似",
                "confidence": _safe_float(link.get("weight"), 0.0), "evidence": [],
                "details": {"sharedTerms": link.get("sharedTerms") or []},
                "direction_reason": "共享主题特征形成的无向相似关系",
            })
    layout = academic_layout(nodes, comparison=True)
    key = f"topic_{hashlib.sha1(str(topic_id).encode('utf-8')).hexdigest()[:12]}"
    metadata = {
        "comparison": True, "topic_graph": True, "topic_id": topic_id, "topic_name": topic.get("name"),
        "comparison_record_ids": sorted(member_ids), "builder_version": TOPIC_MAP_VERSION,
        "source": {"pdfPath": "", "extractionEngine": "topic_map", "sourceSha256": topic_map.get("cacheKey", "")},
        "summary": {"keywords": [item.get("label") for item in topic.get("topTerms") or []], "contentSummary": topic.get("explanation", {}).get("method", ""), "abstract": ""},
        "layout": layout, "adjacency": adjacency_index(edges),
        "quality_summary": {
            "node_count": len(nodes), "edge_count": len(edges), "evidence_coverage": round(sum(bool(node.get("evidence")) for node in nodes) / max(1, len(nodes)), 3),
            "topic_cohesion": topic.get("cohesion", 0.0), "topic_low_confidence": bool(topic.get("lowConfidence")),
        },
    }
    return {
        "version": 1, "schema_version": 1, "recordId": key, "record_id": key,
        "title": str(topic.get("name") or "主题局部图谱"),
        "paper": {"title": str(topic.get("name") or "主题局部图谱"), "authors": [], "year": "", "source": "topic_map", "pdf_path": ""},
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_fingerprint": str(topic_map.get("cacheKey") or ""),
        "nodes": nodes, "edges": edges, "metadata": metadata,
        "layout": layout, "adjacency": metadata["adjacency"], "quality_summary": metadata["quality_summary"],
    }
