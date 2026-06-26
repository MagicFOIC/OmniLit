from __future__ import annotations

import hashlib
import math
import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Callable


WORD_CLOUD_VERSION = 2

STOP_WORDS = {
    "the", "and", "for", "with", "from", "this", "that", "using", "use", "used",
    "paper", "study", "result", "results", "method", "model", "based", "show", "shows",
    "into", "between", "within", "without", "were", "was", "are", "is", "our", "their",
    "over", "under", "than", "then", "also", "can", "could", "would", "should", "has", "have",
    "a", "an",
    "本文", "本研究", "结果", "方法", "研究", "使用", "基于", "通过", "以及", "其中", "对于",
}

ALIASES = {
    "acc": "accuracy", "acc.": "accuracy", "f1-score": "f1", "f1 score": "f1",
    "data set": "dataset", "数据集合": "数据集", "transformers": "transformer",
    "large language model": "llm", "large language models": "llm", "language model": "llm",
    "retrieval-augmented generation": "retrieval augmented generation",
    "graph neural networks": "graph neural network",
}

TERM_TYPES = {
    "concept", "problem", "researchgap", "method", "algorithm", "model", "dataset", "metric",
    "experiment", "result", "contribution", "limitation", "futurework",
}

CATEGORY_BY_TYPE = {
    "method": "Method", "algorithm": "Method", "model": "Method", "contribution": "Method",
    "dataset": "Dataset", "experiment": "Dataset", "baseline": "Dataset",
    "metric": "Metric",
    "result": "Result", "limitation": "Result", "futurework": "Result",
    "concept": "Concept", "problem": "Concept", "researchgap": "Concept",
}

CHINESE_TERMS = re.compile(
    r"知识图谱|大语言模型|语言模型|检索增强生成|图神经网络|深度学习|机器学习|"
    r"注意力机制|命名实体识别|关系抽取|自然语言处理|数据集|准确率|召回率|精确率"
)

ChineseTokenizer = Callable[[str], list[str]]


def _normalize(text: str) -> str:
    value = re.sub(r"\s+", " ", str(text or "")).strip().casefold()
    value = value.strip(".,;:()[]{}，。；：（）")
    return ALIASES.get(value, value)


def _english_words(text: str) -> list[str]:
    return [word.casefold() for word in re.findall(r"[A-Za-z][A-Za-z0-9+.-]{1,}", text)]


def _english_phrases(text: str) -> list[str]:
    words = _english_words(text)
    phrases: list[str] = []
    segment: list[str] = []
    for word in words + [""]:
        normalized = _normalize(word)
        if not normalized or normalized in STOP_WORDS:
            if len(segment) >= 2:
                for size in (3, 2):
                    phrases.extend(" ".join(segment[index:index + size]) for index in range(len(segment) - size + 1))
            segment = []
        else:
            segment.append(normalized)
    return list(dict.fromkeys(_normalize(item) for item in phrases if len(_normalize(item)) >= 4))


def _chinese_phrases(text: str, tokenizer: ChineseTokenizer | None = None) -> list[str]:
    phrases: list[str] = []
    if tokenizer is not None:
        phrases.extend(str(item).strip() for item in tokenizer(text) if 2 <= len(str(item).strip()) <= 12)
    phrases.extend(match.group(0) for match in CHINESE_TERMS.finditer(text))
    for chunk in re.findall(r"[\u3400-\u9fff]{2,12}", text):
        if 2 <= len(chunk) <= 8 and chunk not in STOP_WORDS:
            phrases.append(chunk)
    return list(dict.fromkeys(_normalize(item) for item in phrases if _normalize(item) not in STOP_WORDS))


def extract_phrases(text: str, chinese_tokenizer: ChineseTokenizer | None = None) -> list[str]:
    return _english_phrases(text) + _chinese_phrases(text, chinese_tokenizer)


def _short_node_label(node: dict[str, Any]) -> str:
    label = str(node.get("label") or "").strip()
    if 2 <= len(label) <= 48 and len(label.split()) <= 6:
        return label
    summary = str(node.get("summary") or label)
    chinese = _chinese_phrases(summary)
    if chinese:
        return chinese[0]
    content = [word for word in _english_words(summary) if _normalize(word) not in STOP_WORDS]
    return " ".join(content[:4])


def _noise_weight(node: dict[str, Any], evidence: dict[str, Any]) -> float:
    kind = str(node.get("type") or "").casefold()
    source = str(evidence.get("source") or "").casefold()
    section = str(node.get("source_section") or (node.get("details") or {}).get("section") or "").casefold()
    excerpt = str(evidence.get("excerpt") or "")
    if kind in {"formula", "equation", "citation"} or "formula" in source or "equation" in source:
        return 0.05
    if section in {"references", "bibliography"} or "reference" in source:
        return 0.10
    if any(marker in source for marker in ("header", "footer", "page_number")):
        return 0.08
    if len(re.findall(r"[=+*/\\{}_^]", excerpt)) > max(3, len(excerpt) // 12):
        return 0.12
    return 1.0


def _overlaps(rect: tuple[float, float, float, float], existing: list[tuple[float, float, float, float]]) -> bool:
    x1, y1, x2, y2 = rect
    return any(x1 < right and x2 > left and y1 < bottom and y2 > top for left, top, right, bottom in existing)


def _layout(terms: list[dict[str, Any]], width: int = 1000, height: int = 650) -> list[dict[str, Any]]:
    occupied: list[tuple[float, float, float, float]] = []
    result: list[dict[str, Any]] = []
    for index, term in enumerate(terms):
        font_size = float(term["fontSize"])
        visual_length = sum(1.0 if ord(char) > 255 else 0.58 for char in term["text"])
        word_width = max(30.0, visual_length * font_size + 12)
        word_height = font_size * 1.35
        placed = None
        for step in range(900):
            angle = step * 0.42 + index * 0.17
            radius = 2.1 * math.sqrt(step)
            cx = width / 2 + math.cos(angle) * radius * 2.8
            cy = height / 2 + math.sin(angle) * radius * 1.75
            rect = (cx - word_width / 2, cy - word_height / 2, cx + word_width / 2, cy + word_height / 2)
            if rect[0] < 8 or rect[1] < 8 or rect[2] > width - 8 or rect[3] > height - 8 or _overlaps(rect, occupied):
                continue
            placed = (cx, cy, rect)
            break
        if placed is None:
            continue
        cx, cy, rect = placed
        occupied.append(rect)
        item = dict(term)
        item.update({
            "x": round(cx / width, 6), "y": round(cy / height, 6),
            "width": round(word_width / width, 6), "height": round(word_height / height, 6),
        })
        result.append(item)
    return result


def _entry(aggregate: dict[str, dict[str, Any]], normalized: str, label: str) -> dict[str, Any]:
    return aggregate.setdefault(normalized, {
        "text": label, "normalized": normalized, "score": 0.0, "count": 0,
        "types": set(), "categories": defaultdict(float), "paperIds": set(),
        "nodeRefs": set(), "evidence": [], "sourceKinds": set(),
    })


def _add_evidence(entry: dict[str, Any], evidence: dict[str, Any]) -> None:
    if evidence not in entry["evidence"] and len(entry["evidence"]) < 6:
        entry["evidence"].append(evidence)


def build_word_cloud(
    graphs: list[dict[str, Any]],
    scope: str,
    title: str,
    limit: int,
    chinese_tokenizer: ChineseTokenizer | None = None,
) -> dict[str, Any]:
    aggregate: dict[str, dict[str, Any]] = {}
    fingerprints: list[str] = []
    for graph in graphs:
        record_id = str(graph.get("record_id") or graph.get("recordId") or "")
        fingerprints.append(str(graph.get("source_fingerprint") or record_id))
        for node in graph.get("nodes") or []:
            kind = str(node.get("type") or "").casefold() if isinstance(node, dict) else ""
            if not isinstance(node, dict) or kind not in TERM_TYPES:
                continue
            node_id = str(node.get("id") or "")
            category = CATEGORY_BY_TYPE.get(kind, "Concept")
            label = _short_node_label(node)
            normalized = _normalize(label)
            importance = float(node.get("importance", node.get("weight", 0.5)) or 0.0)
            confidence = float(node.get("confidence", 1.0) or 0.0)
            evidence = [item for item in node.get("evidence") or [] if isinstance(item, dict)]

            if normalized and normalized not in STOP_WORDS and len(normalized) >= 2:
                entry = _entry(aggregate, normalized, label)
                keyword_bonus = 0.8 if "keyword" in [str(tag).casefold() for tag in node.get("tags") or []] else 0.0
                node_score = 2.4 + importance * 2.4 + confidence * 0.8 + min(3, len(evidence)) * 0.25 + keyword_bonus
                entry["score"] += node_score
                entry["count"] += 1
                entry["types"].add(kind)
                entry["categories"][category] += node_score
                entry["sourceKinds"].add("graph_node")
                if record_id:
                    entry["paperIds"].add(record_id)
                if node_id:
                    entry["nodeRefs"].add((record_id, node_id))
                for item in evidence[:4]:
                    _add_evidence(entry, item)

            for item in evidence[:4]:
                noise = _noise_weight(node, item)
                for phrase in extract_phrases(str(item.get("excerpt") or ""), chinese_tokenizer)[:36]:
                    phrase_key = _normalize(phrase)
                    if not phrase_key or phrase_key in STOP_WORDS or phrase_key == normalized:
                        continue
                    phrase_entry = _entry(aggregate, phrase_key, "LLM" if phrase_key == "llm" else phrase)
                    phrase_score = (0.20 + importance * 0.16 + confidence * 0.08) * noise
                    phrase_entry["score"] += phrase_score
                    phrase_entry["count"] += 1
                    phrase_entry["types"].add(kind)
                    phrase_entry["categories"][category] += phrase_score
                    phrase_entry["sourceKinds"].add("evidence_phrase")
                    if record_id:
                        phrase_entry["paperIds"].add(record_id)
                    if node_id:
                        phrase_entry["nodeRefs"].add((record_id, node_id))
                    _add_evidence(phrase_entry, item)

    valid = [item for item in aggregate.values() if item["nodeRefs"]]
    ranked = sorted(valid, key=lambda item: (-item["score"], -item["count"], item["normalized"]))[:max(1, limit)]
    low = min((item["score"] for item in ranked), default=0.0)
    high = max((item["score"] for item in ranked), default=0.0)
    terms: list[dict[str, Any]] = []
    for item in ranked:
        scale = (item["score"] - low) / max(0.001, high - low)
        category = max(item["categories"], key=item["categories"].get)
        node_refs = [{"recordId": record, "nodeId": node} for record, node in sorted(item["nodeRefs"])]
        terms.append({
            "text": item["text"], "normalized": item["normalized"], "weight": round(item["score"], 4),
            "count": item["count"], "fontSize": round((14 if scope == "record" else 12) + scale * (34 if scope == "record" else 32), 2),
            "type": sorted(item["types"])[0], "types": sorted(item["types"]), "category": category,
            "paperIds": sorted(item["paperIds"]), "nodeIds": sorted({item["nodeId"] for item in node_refs}),
            "nodeRefs": node_refs, "primaryNodeId": node_refs[0]["nodeId"],
            "evidence": item["evidence"], "colorGroup": category.casefold(),
            "sourceKinds": sorted(item["sourceKinds"]),
        })
    cache_payload = "\n".join(sorted(fingerprints)) + f"\n{scope}\n{WORD_CLOUD_VERSION}"
    return {
        "version": WORD_CLOUD_VERSION,
        "scope": scope,
        "title": title,
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "cacheKey": hashlib.sha256(cache_payload.encode("utf-8")).hexdigest(),
        "terms": _layout(terms),
        "sourceCount": len(graphs),
        "conceptCount": len(terms),
    }
