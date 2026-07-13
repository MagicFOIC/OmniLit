from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from typing import Any


SEMANTIC_COMPARISON_VERSION = 1
MAX_ITEMS_PER_CELL = 8

DIMENSIONS = (
    {"key": "problem", "label": "研究问题", "types": ("researchquestion", "problem", "researchgap"), "description": "论文试图解决的问题或明确指出的研究空白。"},
    {"key": "method", "label": "方法", "types": ("method", "algorithm", "experiment"), "description": "研究采用或提出的方法、算法和实验方案。"},
    {"key": "model", "label": "模型", "types": ("model",), "description": "论文使用、提出或比较的具体模型。"},
    {"key": "dataset", "label": "数据集", "types": ("dataset",), "description": "用于训练、验证或评估的数据集。"},
    {"key": "metric", "label": "指标", "types": ("metric",), "description": "论文报告或采用的评价指标。"},
    {"key": "result", "label": "实验结果", "types": ("result",), "description": "有原文证据支持的定量或定性实验结论。"},
    {"key": "contribution", "label": "贡献", "types": ("contribution", "claim", "conclusion"), "description": "作者声明的主要贡献和结论性主张。"},
    {"key": "limitation", "label": "局限性", "types": ("limitation",), "description": "论文明确陈述的限制、适用边界或失败情形。"},
    {"key": "futurework", "label": "未来工作", "types": ("futurework",), "description": "作者提出的后续研究方向。"},
)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _record_id(graph: dict[str, Any]) -> str:
    return str(graph.get("recordId") or graph.get("record_id") or "")


def _evidence_values(node: dict[str, Any], record_id: str) -> list[dict[str, Any]]:
    result = []
    for value in node.get("evidence") or []:
        if not isinstance(value, dict):
            continue
        item = dict(value)
        item["record_id"] = str(item.get("record_id") or item.get("recordId") or record_id)
        item["page"] = int(item.get("page", -1) if item.get("page") is not None else -1)
        item["bbox"] = list(item.get("bbox") or [])
        result.append(item)
    return result


def normalize_reviews(value: dict[str, Any] | None) -> dict[str, Any]:
    revisions = {}
    raw = dict(value or {}).get("revisions") or {}
    if not isinstance(raw, dict):
        raw = {}
    for dimension, review in raw.items():
        if not isinstance(review, dict) or str(dimension) not in {item["key"] for item in DIMENSIONS}:
            continue
        action = str(review.get("action") or "").casefold()
        if action not in {"confirm", "replace", "add", "reject"}:
            continue
        revisions[str(dimension)] = {
            "action": action,
            "label": str(review.get("label") or "").strip(),
            "note": str(review.get("note") or "").strip(),
            "originalNodeId": str(review.get("originalNodeId") or review.get("original_node_id") or ""),
            "updatedAt": str(review.get("updatedAt") or ""),
            "source": "human_review",
        }
    return {"version": 1, "revisions": revisions}


def make_review(
    current: dict[str, Any] | None, dimension: str, action: str, label: str = "", note: str = "",
    original_node_id: str = "",
) -> dict[str, Any]:
    normalized = normalize_reviews(current)
    dimension_value = str(dimension or "")
    action_value = str(action or "").casefold()
    if dimension_value not in {item["key"] for item in DIMENSIONS} or action_value not in {"confirm", "replace", "add", "reject"}:
        raise ValueError("invalid semantic review")
    if action_value in {"replace", "add"} and not str(label or "").strip():
        raise ValueError("replacement label is required")
    normalized["revisions"][dimension_value] = {
        "action": action_value, "label": str(label or "").strip(), "note": str(note or "").strip(),
        "originalNodeId": str(original_node_id or ""),
        "updatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"), "source": "human_review",
    }
    return normalized


def clear_review(current: dict[str, Any] | None, dimension: str) -> dict[str, Any]:
    normalized = normalize_reviews(current)
    normalized["revisions"].pop(str(dimension or ""), None)
    return normalized


def _cell(
    graph: dict[str, Any], record_id: str, dimension: dict[str, Any], review: dict[str, Any] | None,
) -> dict[str, Any]:
    accepted_types = set(dimension["types"])
    candidates = []
    for node in graph.get("nodes") or []:
        if not isinstance(node, dict):
            continue
        kind = str(node.get("type") or "").casefold().replace("_", "")
        tags = {str(item).casefold() for item in node.get("tags") or []}
        if kind not in accepted_types and not (dimension["key"] == "model" and "model" in tags):
            continue
        evidence = _evidence_values(node, record_id)
        confidence = max(0.0, min(1.0, _safe_float(node.get("confidence"), 0.0)))
        candidates.append({
            "nodeId": str(node.get("id") or ""), "type": str(node.get("type") or ""),
            "label": str(node.get("label") or ""), "summary": str(node.get("summary") or ""),
            "confidence": round(confidence, 4), "needsReview": bool(node.get("needs_review", node.get("needsReview", False))) or confidence < 0.6,
            "reviewReasons": [str(item) for item in node.get("review_reasons") or node.get("reviewReasons") or []],
            "extractionMethod": str(node.get("extraction_method") or node.get("extractionMethod") or "unknown"),
            "sourceSection": str(node.get("source_section") or node.get("sourceSection") or ""),
            "evidence": evidence, "evidenceCount": len(evidence), "source": "automatic_extraction",
        })
    candidates.sort(key=lambda item: (-item["confidence"], -item["evidenceCount"], item["label"], item["nodeId"]))
    automatic = candidates[:MAX_ITEMS_PER_CELL]
    review_value = dict(review or {})
    action = str(review_value.get("action") or "")
    effective = list(automatic)
    status = "present" if automatic else "missing"
    if action == "reject":
        effective = []
        status = "reviewed_missing"
    elif action in {"replace", "add"}:
        human_item = {
            "nodeId": "", "type": dimension["key"], "label": str(review_value.get("label") or ""), "summary": str(review_value.get("note") or ""),
            "confidence": 1.0, "needsReview": False, "reviewReasons": [], "extractionMethod": "human_review",
            "sourceSection": "", "evidence": [], "evidenceCount": 0, "source": "human_review",
        }
        effective = [human_item] if action == "replace" else [*automatic, human_item]
        status = "reviewed"
    elif action == "confirm":
        status = "confirmed" if automatic else "confirmed_missing"
    confidence = max((_safe_float(item.get("confidence")) for item in effective), default=0.0)
    evidence_count = sum(int(item.get("evidenceCount") or 0) for item in effective)
    needs_review = any(bool(item.get("needsReview")) for item in effective) and action not in {"confirm", "replace", "add", "reject"}
    if status in {"missing", "confirmed_missing"}:
        explanation = "当前自动抽取未识别到该维度；这表示信息缺失或尚未抽取到，不表示论文明确没有该内容。"
    elif status == "reviewed_missing":
        explanation = "人工审阅已将该维度标记为不采用；原始自动抽取仍保留在 automaticItems 中。"
    elif action:
        explanation = "当前展示包含人工审阅结果；原始自动抽取仍保留，可随时撤销审阅。"
    else:
        explanation = f"自动抽取识别到 {len(automatic)} 项，最高置信度 {confidence:.2f}，共 {evidence_count} 条原文证据。"
    return {
        "recordId": record_id, "dimension": dimension["key"], "status": status,
        "automaticItems": automatic, "items": effective, "itemCount": len(effective),
        "confidence": round(confidence, 4), "evidenceCount": evidence_count, "needsReview": needs_review,
        "review": review_value, "explanation": explanation,
    }


def _result_conflicts(papers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    positive = ("improve", "outperform", "increase", "higher", "提升", "优于", "增加")
    negative = ("not ", "underperform", "decrease", "lower", "降低", "不显著", "未提升")
    results = []
    for paper in papers:
        cell = next((item for item in paper["cells"] if item["dimension"] == "result"), {})
        for item in cell.get("items") or []:
            text = f"{item.get('label', '')} {item.get('summary', '')}".casefold()
            tokens = set(text.replace("/", " ").replace("-", " ").split())
            results.append((paper["recordId"], item, text, tokens))
    conflicts = []
    for index, (left_id, left, left_text, left_tokens) in enumerate(results):
        for right_id, right, right_text, right_tokens in results[index + 1:]:
            if left_id == right_id:
                continue
            opposite = (any(token in left_text for token in positive) and any(token in right_text for token in negative)) or (any(token in right_text for token in positive) and any(token in left_text for token in negative))
            similarity = len(left_tokens & right_tokens) / max(1, len(left_tokens | right_tokens))
            if opposite and similarity >= 0.20:
                conflicts.append({
                    "leftRecordId": left_id, "rightRecordId": right_id,
                    "leftNodeId": left.get("nodeId", ""), "rightNodeId": right.get("nodeId", ""),
                    "confidence": round(min(0.75, max(0.5, similarity)), 4),
                    "explanation": "两篇论文对相似结果对象使用了方向相反的表述；这是待核验提示，不是自动判定谁正确。",
                    "evidence": [*(left.get("evidence") or []), *(right.get("evidence") or [])],
                })
    conflicts.sort(key=lambda item: (-item["confidence"], item["leftRecordId"], item["rightRecordId"]))
    return conflicts[:40]


def build_semantic_comparison(
    graphs: list[dict[str, Any]], records: list[dict[str, Any]] | None = None,
    reviews: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    graph_values = [dict(item) for item in graphs if isinstance(item, dict) and _record_id(item)]
    graph_values.sort(key=_record_id)
    record_values = {str(item.get("recordId") or item.get("id") or ""): dict(item) for item in records or [] if isinstance(item, dict)}
    review_values = {str(key): normalize_reviews(value) for key, value in (reviews or {}).items()}
    papers = []
    for graph in graph_values:
        record_id = _record_id(graph)
        record = record_values.get(record_id, {})
        paper = dict(graph.get("paper") or {})
        cells = [
            _cell(graph, record_id, dimension, (review_values.get(record_id, {}).get("revisions") or {}).get(dimension["key"]))
            for dimension in DIMENSIONS
        ]
        papers.append({
            "recordId": record_id, "title": str(record.get("title") or paper.get("title") or graph.get("title") or record_id),
            "year": record.get("year") or paper.get("year") or "", "cells": cells,
            "presentDimensionCount": sum(bool(cell["items"]) for cell in cells),
            "reviewedDimensionCount": sum(bool(cell["review"]) for cell in cells),
        })
    coverage = []
    for dimension in DIMENSIONS:
        cells = [next(item for item in paper["cells"] if item["dimension"] == dimension["key"]) for paper in papers]
        present = sum(bool(cell["items"]) for cell in cells)
        evidence = sum(int(cell["evidenceCount"]) for cell in cells)
        coverage.append({
            "dimension": dimension["key"], "label": dimension["label"], "paperCount": present,
            "coverage": round(present / max(1, len(papers)), 4), "evidenceCount": evidence,
            "needsReviewCount": sum(bool(cell["needsReview"]) for cell in cells),
        })
    signature = {
        "version": SEMANTIC_COMPARISON_VERSION,
        "graphs": [
            (_record_id(graph), [(node.get("id"), node.get("type"), node.get("label"), node.get("confidence"), node.get("evidence")) for node in graph.get("nodes") or [] if isinstance(node, dict)])
            for graph in graph_values
        ],
        "reviews": review_values,
    }
    return {
        "version": SEMANTIC_COMPARISON_VERSION,
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "cacheKey": hashlib.sha256(json.dumps(signature, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest(),
        "dimensions": [{key: value for key, value in dimension.items() if key != "types"} for dimension in DIMENSIONS],
        "papers": papers, "coverage": coverage, "conflicts": _result_conflicts(papers),
        "diagnostics": {
            "paperCount": len(papers), "dimensionCount": len(DIMENSIONS),
            "cellCount": len(papers) * len(DIMENSIONS),
            "automaticItemCount": sum(len(cell["automaticItems"]) for paper in papers for cell in paper["cells"]),
            "reviewedCellCount": sum(bool(cell["review"]) for paper in papers for cell in paper["cells"]),
            "method": "evidence_backed_orkg_matrix_v1",
        },
    }
