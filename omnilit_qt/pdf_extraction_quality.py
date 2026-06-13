from __future__ import annotations

from typing import Any

from .pdf_extraction_schema import normalize_bbox
from .pdf_extraction_table_utils import non_empty_cell_ratio, table_shape


def score_table(element: dict[str, Any]) -> tuple[float, list[str]]:
    rows = element.get("table") or []
    row_count, col_count = table_shape(rows)
    ratio = non_empty_cell_ratio(rows)
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
    if _looks_numbered(latex):
        score += 0.05
    if _has_source_pair(element):
        score += 0.1
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


def _finalize(score: float, flags: list[str]) -> tuple[float, list[str]]:
    return round(max(0.05, min(0.99, score)), 3), list(dict.fromkeys(flags))


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
