from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .pdf_extraction_schema import normalize_bbox
from .pdf_extraction_table_utils import non_empty_cell_ratio, table_shape


def score_table(element: dict[str, Any]) -> tuple[float, list[str]]:
    rows = element.get("table") or []
    row_count, col_count = table_shape(rows)
    ratio = non_empty_cell_ratio(rows)
    metadata = element.get("metadata") or {}
    flags: list[str] = []
    score = 0.35
    if row_count >= 2:
        score += 0.15
    if col_count >= 2:
        score += 0.15
    if ratio >= 0.6:
        score += 0.12
    if element.get("caption"):
        score += 0.08
    if _valid_bbox(element):
        score += 0.08
    else:
        flags.append("missing_bbox")
    if row_count <= 1 or col_count <= 1:
        score -= 0.18
        flags.append("weak_table_shape")
    if _has_source_pair(element):
        score += 0.12
    evidence = _optional_float(metadata.get("tableEvidenceScore"))
    if evidence is not None:
        score += max(-0.08, min(0.10, (evidence - 0.58) * 0.25))
        if evidence < 0.45:
            flags.append("weak_table_evidence")
    if ratio < 0.35 and row_count >= 2 and col_count >= 2:
        flags.append("sparse_table_cells")
    bbox = normalize_bbox(element.get("bbox"))
    area_ratio = _area_ratio(bbox, element.get("pageSize") or [])
    if metadata.get("textStrategy") and not element.get("caption"):
        score -= 0.3
        flags.append("unanchored_text_table")
    if area_ratio > 0.58:
        score -= 0.24
        flags.append("page_sized_table")
    _page_bbox_flags(element, flags)
    return _finalize(score, flags)


def score_figure(element: dict[str, Any]) -> tuple[float, list[str]]:
    flags: list[str] = []
    score = 0.45
    bbox = normalize_bbox(element.get("bbox"))
    area_ratio = _area_ratio(bbox, element.get("pageSize") or [])
    if not _valid_bbox(element):
        flags.append("missing_bbox")
        score -= 0.15
    elif area_ratio < 0.01:
        flags.append("small_figure")
        score -= 0.12
    else:
        score += 0.08
    if element.get("caption"):
        score += 0.12
    if element.get("pngPath"):
        score += 0.1
    if "duplicate_of_table" in (element.get("qualityFlags") or []):
        score -= 0.2
        flags.append("duplicate_of_table")
    if _in_page_margin(bbox, element.get("pageSize") or []):
        score -= 0.12
        flags.append("page_margin")
    if _has_source_pair(element):
        score += 0.08
    _page_bbox_flags(element, flags)
    return _finalize(score, flags)


def score_formula(element: dict[str, Any]) -> tuple[float, list[str]]:
    flags: list[str] = []
    latex = str(element.get("latex") or element.get("text") or "").strip()
    metadata = element.get("metadata") or {}
    score = 0.35
    if latex:
        score += 0.22
    if _valid_bbox(element):
        score += 0.18
    else:
        flags.append("missing_bbox")
        score -= 0.12
    if len(latex) <= 2:
        score -= 0.18
        flags.append("short_latex")
    if any(token in latex for token in ("=", "\\frac", "^", "_", "\\sum", "\\int")):
        score += 0.12
    if _looks_numbered(latex) or str(metadata.get("formulaNumber") or "").strip():
        score += 0.05
    if _has_source_pair(element):
        score += 0.1
    elif str(element.get("engine") or "") in {"pymupdf", "mineru", "paddleocr_vl"}:
        flags.append("single_engine_formula")
    match_score = _optional_float(metadata.get("formulaMatchScore"))
    if match_score is not None:
        score += max(-0.08, min(0.08, (match_score - 0.35) * 0.20))
        if match_score < 0.35:
            flags.append("weak_formula_match")
    if _looks_like_sentence_formula_noise(latex):
        score -= 0.16
        flags.append("sentence_like_formula")
    _page_bbox_flags(element, flags)
    return _finalize(score, flags)


def apply_quality(element: dict[str, Any]) -> dict[str, Any]:
    item = dict(element)
    kind = str(item.get("type") or "")
    if kind == "table":
        confidence, flags = score_table(item)
    elif kind in {"figure", "chart"}:
        confidence, flags = score_figure(item)
    elif kind == "formula":
        confidence, flags = score_formula(item)
    else:
        confidence, flags = float(item.get("confidence") or 0.5), list(item.get("qualityFlags") or [])
    existing = [str(flag) for flag in item.get("qualityFlags") or []]
    item["qualityFlags"] = list(dict.fromkeys(existing + flags))
    item["confidence"] = max(0.0, min(0.99, float(confidence)))
    item["needsReview"] = bool(item.get("needsReview") or item["confidence"] < 0.65 or item["qualityFlags"])
    return item


def quality_summary(elements: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    result = {
        "tables": {"count": 0, "needsReview": 0},
        "figures": {"count": 0, "needsReview": 0},
        "formulas": {"count": 0, "needsReview": 0},
    }
    for element in elements or []:
        kind = str(element.get("type") or "")
        bucket = "tables" if kind == "table" else "figures" if kind in {"figure", "chart"} else "formulas" if kind == "formula" else ""
        if not bucket:
            continue
        result[bucket]["count"] += 1
        if element.get("needsReview"):
            result[bucket]["needsReview"] += 1
    return result


def build_quality_report(index: dict[str, Any]) -> dict[str, Any]:
    elements = [item for item in index.get("elements") or [] if isinstance(item, dict)]
    summary = quality_summary(elements)
    review_items = [_element_review_item(element) for element in elements if _element_needs_review(element)]
    low_confidence = [
        _element_review_item(element)
        for element in elements
        if _optional_float(element.get("confidence")) is not None and float(element.get("confidence") or 0.0) < 0.65
    ]
    schema_warnings = _schema_warnings(elements)
    engine_conflicts = _engine_conflicts(elements)
    manual_overrides = [_manual_override_item(element) for element in elements if _has_manual_override(element)]
    engine_errors = [dict(item) for item in index.get("engineErrors") or [] if isinstance(item, dict)]
    return {
        "version": 1,
        "sourcePath": str(index.get("sourcePath") or ""),
        "sourceSha256": str(index.get("sourceSha256") or ""),
        "engine": str(index.get("engine") or ""),
        "engineChain": [str(item) for item in index.get("engineChain") or [] if str(item or "").strip()],
        "pageCount": int(index.get("pageCount") or 0),
        "summary": {
            **summary,
            "reviewItems": len(review_items),
            "lowConfidence": len(low_confidence),
            "engineErrors": len(engine_errors),
            "engineConflicts": len(engine_conflicts),
            "schemaWarnings": len(schema_warnings),
            "manualOverrides": len(manual_overrides),
        },
        "reviewItems": review_items,
        "lowConfidenceElements": low_confidence,
        "manualOverrides": manual_overrides,
        "engineErrors": engine_errors,
        "engineConflicts": engine_conflicts,
        "schemaWarnings": schema_warnings,
    }


def write_quality_report(output_dir: str | Path, index: dict[str, Any]) -> Path:
    target = Path(output_dir) / "quality_report.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(build_quality_report(index), ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def _finalize(score: float, flags: list[str]) -> tuple[float, list[str]]:
    return round(max(0.05, min(0.99, score)), 3), list(dict.fromkeys(flags))


def _element_needs_review(element: dict[str, Any]) -> bool:
    return bool(element.get("needsReview") or element.get("qualityFlags") or float(element.get("confidence") or 0.0) < 0.65)


def _element_review_item(element: dict[str, Any]) -> dict[str, Any]:
    item = {
        "id": str(element.get("id") or ""),
        "type": str(element.get("type") or ""),
        "page": int(element.get("page") or 0),
        "bbox": normalize_bbox(element.get("bbox")),
        "confidence": float(element.get("confidence") or 0.0),
        "needsReview": bool(element.get("needsReview")),
        "qualityFlags": [str(flag) for flag in element.get("qualityFlags") or [] if str(flag or "").strip()],
        "caption": str(element.get("caption") or ""),
        "sourceEngines": [str(item) for item in element.get("sourceEngines") or [] if str(item or "").strip()],
        "sourceElementIds": [str(item) for item in element.get("sourceElementIds") or [] if str(item or "").strip()],
    }
    metadata = element.get("metadata") or {}
    if str(element.get("type") or "") == "formula" and metadata.get("formulaNumber"):
        item["formulaNumber"] = str(metadata.get("formulaNumber") or "")
    if _has_manual_override(element):
        item["manualOverride"] = True
        if metadata.get("overrideUpdatedAt"):
            item["overrideUpdatedAt"] = str(metadata.get("overrideUpdatedAt") or "")
    return item


def _has_manual_override(element: dict[str, Any]) -> bool:
    metadata = element.get("metadata") or {}
    return bool(element.get("manualOverride") or metadata.get("manualOverride"))


def _manual_override_item(element: dict[str, Any]) -> dict[str, Any]:
    item = _element_review_item(element)
    metadata = element.get("metadata") or {}
    item["manualOverride"] = True
    if metadata.get("overrideUpdatedAt"):
        item["overrideUpdatedAt"] = str(metadata.get("overrideUpdatedAt") or "")
    return item


def _engine_conflicts(elements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    conflict_flags = {
        "weak_formula_match",
        "weak_table_evidence",
        "duplicate_of_table",
        "bbox_clipped",
        "bbox_out_of_page",
    }
    conflicts: list[dict[str, Any]] = []
    for element in elements:
        flags = {str(flag) for flag in element.get("qualityFlags") or []}
        metadata = element.get("metadata") or {}
        source_engines = [str(item) for item in element.get("sourceEngines") or [] if str(item or "").strip()]
        source_disagreement = (
            len(set(source_engines)) > 1
            and (
                metadata.get("formulaMatchScore") is not None
                and float(_optional_float(metadata.get("formulaMatchScore")) or 0.0) < 0.55
                or metadata.get("tableEvidenceScore") is not None
                and float(_optional_float(metadata.get("tableEvidenceScore")) or 0.0) < 0.55
            )
        )
        matched_flags = sorted(flags.intersection(conflict_flags))
        if not matched_flags and not source_disagreement:
            continue
        item = _element_review_item(element)
        item["conflictFlags"] = matched_flags
        if metadata.get("formulaMatchScore") is not None:
            item["formulaMatchScore"] = float(_optional_float(metadata.get("formulaMatchScore")) or 0.0)
        if metadata.get("tableEvidenceScore") is not None:
            item["tableEvidenceScore"] = float(_optional_float(metadata.get("tableEvidenceScore")) or 0.0)
        conflicts.append(item)
    return conflicts


def _schema_warnings(elements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    for element in elements:
        kind = str(element.get("type") or "")
        missing: list[str] = []
        if kind == "table":
            if not element.get("table"):
                missing.append("table")
            if not element.get("jsonPath"):
                missing.append("jsonPath")
            if not element.get("csvPath"):
                missing.append("csvPath")
            if not element.get("pngPath"):
                missing.append("pngPath")
        elif kind == "formula":
            if not (element.get("latex") or element.get("text")):
                missing.append("latex")
            if not element.get("pngPath"):
                missing.append("pngPath")
        elif kind in {"figure", "chart"} and not element.get("pngPath"):
            missing.append("pngPath")
        if missing:
            warnings.append(
                {
                    "id": str(element.get("id") or ""),
                    "type": kind,
                    "page": int(element.get("page") or 0),
                    "missingFields": missing,
                    "message": "Element is missing expected extraction artifacts.",
                }
            )
    return warnings


def _valid_bbox(element: dict[str, Any]) -> bool:
    bbox = normalize_bbox(element.get("bbox"))
    return len(bbox) >= 4 and bbox != [0.0, 0.0, 0.0, 0.0] and bbox[2] > bbox[0] and bbox[3] > bbox[1]


def _has_source_pair(element: dict[str, Any]) -> bool:
    engines = {str(item) for item in element.get("sourceEngines") or []}
    return {"pymupdf", "mineru"}.issubset(engines)


def _area_ratio(bbox: list[float], page_size: list[Any]) -> float:
    if len(bbox) < 4 or not page_size or len(page_size) < 2:
        return 0.0
    page_area = max(1.0, float(page_size[0] or 0) * float(page_size[1] or 0))
    return max(0.0, (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])) / page_area


def _in_page_margin(bbox: list[float], page_size: list[Any]) -> bool:
    if len(bbox) < 4 or len(page_size or []) < 2:
        return False
    height = float(page_size[1] or 0)
    return height > 0 and (bbox[3] < height * 0.08 or bbox[1] > height * 0.92)


def _page_bbox_flags(element: dict[str, Any], flags: list[str]) -> None:
    bbox = normalize_bbox(element.get("bbox"))
    page_size = element.get("pageSize") or []
    if len(bbox) < 4 or len(page_size) < 2:
        return
    width = float(page_size[0] or 0)
    height = float(page_size[1] or 0)
    if width <= 0 or height <= 0:
        return
    if bbox[0] < 0 or bbox[1] < 0 or bbox[2] > width or bbox[3] > height:
        flags.append("bbox_out_of_page")


def _looks_numbered(text: str) -> bool:
    stripped = text.strip()
    return stripped.endswith(")") and "(" in stripped[-8:]


def _optional_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _looks_like_sentence_formula_noise(text: str) -> bool:
    value = str(text or "").strip()
    words = [word.lower() for word in re.findall(r"[A-Za-z]{3,}", value)]
    if len(words) < 6:
        return False
    common = {"the", "and", "with", "from", "this", "that", "where", "when", "for", "into", "were", "was"}
    return bool(common.intersection(words)) or value.endswith((".", "!", "?"))
