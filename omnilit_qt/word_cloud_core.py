from __future__ import annotations

import hashlib
import math
import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any


WORD_CLOUD_VERSION = 1
STOP_WORDS = {
    "the", "and", "for", "with", "from", "this", "that", "using", "use", "used",
    "paper", "study", "result", "results", "method", "model", "based", "show", "shows",
    "into", "between", "within", "without", "were", "was", "are", "is", "our", "their",
    "本文", "本研究", "结果", "方法", "研究", "使用", "基于", "通过", "以及", "其中", "对于",
}
ALIASES = {
    "acc": "accuracy", "acc.": "accuracy", "f1-score": "f1", "f1 score": "f1",
    "data set": "dataset", "数据集合": "数据集", "transformers": "transformer",
}
TERM_TYPES = {"concept", "problem", "researchgap", "method", "algorithm", "model", "dataset", "metric", "experiment", "result", "contribution", "limitation", "futurework"}


def _normalize(text: str) -> str:
    value = re.sub(r"\s+", " ", str(text or "")).strip().casefold()
    value = ALIASES.get(value, value)
    return value.strip(".,;:()[]{}，。；：（）")


def _tokens(text: str) -> list[str]:
    result = re.findall(r"[A-Za-z][A-Za-z0-9+.-]{2,}", text)
    result.extend(segment for segment in re.findall(r"[\u3400-\u9fff]{2,6}", text))
    return [token for token in result if _normalize(token) not in STOP_WORDS]


def _term_label(node: dict[str, Any]) -> str:
    label = str(node.get("label") or "").strip()
    if len(label) <= 42 and len(label.split()) <= 6:
        return label
    tags = node.get("tags") or []
    return str(tags[0]) if tags else ""


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
        item.update({"x": round(cx / width, 6), "y": round(cy / height, 6), "width": round(word_width / width, 6), "height": round(word_height / height, 6)})
        result.append(item)
    return result


def build_word_cloud(graphs: list[dict[str, Any]], scope: str, title: str, limit: int) -> dict[str, Any]:
    aggregate: dict[str, dict[str, Any]] = {}
    fingerprints: list[str] = []
    for graph in graphs:
        record_id = str(graph.get("record_id") or graph.get("recordId") or "")
        fingerprints.append(str(graph.get("source_fingerprint") or record_id))
        for node in graph.get("nodes") or []:
            if not isinstance(node, dict) or str(node.get("type") or "").casefold() not in TERM_TYPES:
                continue
            label = _term_label(node)
            normalized = _normalize(label)
            if not normalized or normalized in STOP_WORDS or len(normalized) < 2:
                continue
            entry = aggregate.setdefault(normalized, {"text": label, "normalized": normalized, "score": 0.0, "count": 0, "types": set(), "paperIds": set(), "evidence": []})
            importance = float(node.get("importance", node.get("weight", 0.5)) or 0.0)
            confidence = float(node.get("confidence", 1.0) or 0.0)
            evidence = [item for item in node.get("evidence") or [] if isinstance(item, dict)]
            keyword_bonus = 0.8 if "keyword" in [str(tag).casefold() for tag in node.get("tags") or []] else 0.0
            entry["score"] += 1.0 + importance * 2.0 + confidence * 0.5 + min(3, len(evidence)) * 0.25 + keyword_bonus
            entry["count"] += 1
            entry["types"].add(str(node.get("type") or "concept").casefold())
            if record_id:
                entry["paperIds"].add(record_id)
            for item in evidence[:4]:
                if item not in entry["evidence"]:
                    entry["evidence"].append(item)
                for token in _tokens(str(item.get("excerpt") or ""))[:24]:
                    token_key = _normalize(token)
                    if not token_key or token_key in STOP_WORDS:
                        continue
                    token_entry = aggregate.setdefault(token_key, {"text": ALIASES.get(token_key, token), "normalized": token_key, "score": 0.0, "count": 0, "types": set(), "paperIds": set(), "evidence": []})
                    token_entry["score"] += 0.18 + importance * 0.12
                    token_entry["count"] += 1
                    token_entry["types"].add(str(node.get("type") or "concept").casefold())
                    if record_id:
                        token_entry["paperIds"].add(record_id)
                    if item not in token_entry["evidence"] and len(token_entry["evidence"]) < 4:
                        token_entry["evidence"].append(item)

    ranked = sorted(aggregate.values(), key=lambda item: (-item["score"], -item["count"], item["normalized"]))[:max(1, limit)]
    if ranked:
        low = min(item["score"] for item in ranked)
        high = max(item["score"] for item in ranked)
    else:
        low = high = 0.0
    terms: list[dict[str, Any]] = []
    for item in ranked:
        scale = (item["score"] - low) / max(0.001, high - low)
        terms.append({
            "text": item["text"], "normalized": item["normalized"], "weight": round(item["score"], 4),
            "count": item["count"], "fontSize": round((14 if scope == "record" else 12) + scale * (34 if scope == "record" else 32), 2),
            "type": sorted(item["types"])[0], "types": sorted(item["types"]), "paperIds": sorted(item["paperIds"]),
            "evidence": item["evidence"], "colorGroup": sorted(item["types"])[0],
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
    }
