from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

from .pdf_extraction_caption import find_nearby_caption
from .pdf_extraction_quality import apply_quality, quality_summary
from .pdf_extraction_schema import ensure_version_3, normalize_bbox, normalize_element
from .pdf_extraction_table_utils import non_empty_cell_ratio, table_shape


def fuse_pymupdf_mineru_indexes(pymupdf_index: dict[str, Any], mineru_index: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    base = ensure_version_3(pymupdf_index, "pymupdf")
    mineru = ensure_version_3(mineru_index, "mineru")
    pages = deepcopy(base.get("pages") or [])
    text_blocks_by_page = {int(page.get("page") or 0): list(page.get("textBlocks") or []) for page in pages}

    report: dict[str, Any] = {
        "sourcePdf": base.get("sourcePath", ""),
        "pymupdfElementCount": len(base.get("elements") or []),
        "mineruElementCount": len(mineru.get("elements") or []),
        "fusionElementCount": 0,
        "matchedTables": [],
        "matchedFigures": [],
        "matchedFormulas": [],
        "unmatchedPymupdf": [],
        "unmatchedMineru": [],
        "qualitySummary": {},
    }

    used_mineru: set[str] = set()
    fused: list[dict[str, Any]] = []
    pymupdf_elements = [normalize_element(item, "pymupdf") for item in base.get("elements") or []]
    mineru_elements = [normalize_element(item, "mineru") for item in mineru.get("elements") or []]

    for element in pymupdf_elements:
        kind = str(element.get("type") or "")
        if kind == "table":
            match = _best_iou_match(element, mineru_elements, "table", used_mineru, 0.55)
            if match:
                fused_item = _fuse_table(element, match)
                used_mineru.add(str(match.get("id") or ""))
                report["matchedTables"].append([element.get("id"), match.get("id")])
            else:
                fused_item = _with_sources(element, ["pymupdf"])
                report["unmatchedPymupdf"].append(element.get("id"))
            fused.append(_finalize_element(fused_item, text_blocks_by_page, output_dir))
        elif kind in {"figure", "chart"}:
            if _overlaps_existing_table(element, fused):
                item = _with_sources(element, ["pymupdf"])
                item["qualityFlags"] = list(dict.fromkeys(list(item.get("qualityFlags") or []) + ["duplicate_of_table"]))
                report["unmatchedPymupdf"].append(element.get("id"))
                continue
            match = _best_iou_match(element, mineru_elements, {"figure", "chart"}, used_mineru, 0.45)
            if match:
                fused_item = _fuse_figure(element, match)
                used_mineru.add(str(match.get("id") or ""))
                report["matchedFigures"].append([element.get("id"), match.get("id")])
            else:
                fused_item = _with_sources(element, ["pymupdf"])
                report["unmatchedPymupdf"].append(element.get("id"))
            fused.append(_finalize_element(fused_item, text_blocks_by_page, output_dir))
        elif kind == "formula":
            match = _best_formula_match(element, mineru_elements, used_mineru)
            if match:
                fused_item = _fuse_formula(element, match)
                used_mineru.add(str(match.get("id") or ""))
                report["matchedFormulas"].append([element.get("id"), match.get("id")])
            else:
                fused_item = _with_sources(element, ["pymupdf"])
                report["unmatchedPymupdf"].append(element.get("id"))
            fused.append(_finalize_element(fused_item, text_blocks_by_page, output_dir))
        else:
            fused.append(_finalize_element(_with_sources(element, ["pymupdf"]), text_blocks_by_page, output_dir))

    for element in mineru_elements:
        element_id = str(element.get("id") or "")
        if element_id in used_mineru:
            continue
        if str(element.get("type") or "") in {"table", "figure", "chart"} and _overlaps_existing_table(element, fused):
            element = dict(element)
            element["qualityFlags"] = list(dict.fromkeys(list(element.get("qualityFlags") or []) + ["duplicate_of_table"]))
        report["unmatchedMineru"].append(element_id)
        fused.append(_finalize_element(_with_sources(element, ["mineru"]), text_blocks_by_page, output_dir))

    fused = _dedupe_fused(fused)
    summary = quality_summary(fused)
    report["fusionElementCount"] = len(fused)
    report["qualitySummary"] = summary
    report_path = output_dir / "fusion_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    raw_outputs = dict(base.get("rawOutputs") or {})
    for key, value in (mineru.get("rawOutputs") or {}).items():
        if value:
            raw_outputs[key] = value
    chain: list[str] = []
    for name in list(base.get("engineChain") or []) + list(mineru.get("engineChain") or []) + ["fusion"]:
        if name and name not in chain:
            chain.append(str(name))
    return {
        **deepcopy(base),
        "version": 3,
        "engine": "fusion",
        "engineChain": chain,
        "pages": pages,
        "pageCount": int(base.get("pageCount") or len(pages)),
        "elements": _sort_elements(fused),
        "markdownPath": mineru.get("markdownPath") or base.get("markdownPath") or "",
        "rawOutputs": raw_outputs,
        "engineErrors": list(base.get("engineErrors") or []) + list(mineru.get("engineErrors") or []),
        "qualitySummary": summary,
        "debugFiles": {
            "mineruLayoutPdf": str((mineru.get("debugFiles") or {}).get("mineruLayoutPdf") or ""),
            "fusionReportJson": str(report_path),
        },
    }


def _fuse_table(pymupdf: dict[str, Any], mineru: dict[str, Any]) -> dict[str, Any]:
    table_choice = _choose_table_candidate(
        [
            ("pymupdf", pymupdf),
            ("mineru", mineru),
        ]
    )
    table_engine, table_element, table_score = table_choice
    rows = table_element.get("table") or []
    item = _with_sources(pymupdf, ["pymupdf", "mineru"], mineru)
    location_engine, location_element = _choose_location_candidate(
        [
            ("pymupdf", pymupdf),
            ("mineru", mineru),
        ]
    )
    if location_engine and location_element is not pymupdf:
        item["bbox"] = normalize_bbox(location_element.get("bbox"))
        item["pageSize"] = list(location_element.get("pageSize") or item.get("pageSize") or [])
    row_count, col_count = table_shape(rows)
    metadata = dict(item.get("metadata") or {})
    metadata.update(
        {
            "tableSourceEngine": table_engine,
            "tableEvidenceScore": round(table_score, 3),
            "tableShape": [row_count, col_count],
            "locationSourceEngine": location_engine,
        }
    )
    item.update(
        {
            "engine": "fusion",
            "table": rows,
            "text": table_element.get("text") or _table_text(rows) or pymupdf.get("text") or mineru.get("text") or "",
            "csvPath": table_element.get("csvPath") or pymupdf.get("csvPath") or mineru.get("csvPath") or "",
            "jsonPath": table_element.get("jsonPath") or pymupdf.get("jsonPath") or mineru.get("jsonPath") or "",
            "html": table_element.get("html") or pymupdf.get("html") or mineru.get("html") or "",
            "markdown": table_element.get("markdown") or pymupdf.get("markdown") or mineru.get("markdown") or "",
            "caption": mineru.get("caption") or pymupdf.get("caption") or "",
            "metadata": metadata,
            "raw": {"pymupdf": pymupdf.get("raw") or {}, "mineru": mineru.get("raw") or {}},
        }
    )
    if table_score < 0.58:
        item["qualityFlags"] = list(dict.fromkeys(list(item.get("qualityFlags") or []) + ["weak_table_evidence"]))
    return item


def _fuse_figure(pymupdf: dict[str, Any], mineru: dict[str, Any]) -> dict[str, Any]:
    item = _with_sources(pymupdf, ["pymupdf", "mineru"], mineru)
    item.update(
        {
            "engine": "fusion",
            "type": "chart" if str(mineru.get("type") or "") == "chart" else "figure",
            "caption": mineru.get("caption") or pymupdf.get("caption") or "",
            "text": mineru.get("text") or pymupdf.get("text") or "",
            "pngPath": pymupdf.get("pngPath") or mineru.get("pngPath") or "",
            "raw": {"pymupdf": pymupdf.get("raw") or {}, "mineru": mineru.get("raw") or {}},
        }
    )
    return item


def _fuse_formula(pymupdf: dict[str, Any], mineru: dict[str, Any]) -> dict[str, Any]:
    text_engine, latex, text_score = _choose_formula_text(
        [
            ("pymupdf", pymupdf),
            ("mineru", mineru),
        ]
    )
    location_engine, location_element = _choose_location_candidate(
        [
            ("pymupdf", pymupdf),
            ("mineru", mineru),
        ]
    )
    match_score = _formula_match_score(pymupdf, mineru)
    item = _with_sources(pymupdf, ["pymupdf", "mineru"], mineru)
    if location_engine and location_element is not pymupdf:
        item["bbox"] = normalize_bbox(location_element.get("bbox"))
        item["pageSize"] = list(location_element.get("pageSize") or item.get("pageSize") or [])
    metadata = dict(item.get("metadata") or {})
    metadata.update(
        {
            "formulaSourceEngine": text_engine,
            "formulaTextScore": round(text_score, 3),
            "formulaMatchScore": round(match_score, 3),
            "locationSourceEngine": location_engine,
        }
    )
    item.update(
        {
            "engine": "fusion",
            "latex": latex,
            "text": latex,
            "markdown": mineru.get("markdown") or pymupdf.get("markdown") or "",
            "metadata": metadata,
            "raw": {"pymupdf": pymupdf.get("raw") or {}, "mineru": mineru.get("raw") or {}},
        }
    )
    if match_score < 0.35:
        item["qualityFlags"] = list(dict.fromkeys(list(item.get("qualityFlags") or []) + ["weak_formula_match"]))
    return item


def _with_sources(element: dict[str, Any], engines: list[str], other: dict[str, Any] | None = None) -> dict[str, Any]:
    item = normalize_element(element, str(element.get("engine") or ""))
    item["sourceEngines"] = list(dict.fromkeys(engines))
    ids = [str(element.get("id") or "")]
    if other is not None:
        ids.append(str(other.get("id") or ""))
    item["sourceElementIds"] = [value for value in ids if value]
    item["engine"] = "fusion" if len(item["sourceEngines"]) > 1 else item["sourceEngines"][0]
    return item


def _finalize_element(element: dict[str, Any], text_blocks_by_page: dict[int, list[dict[str, Any]]], output_dir: Path) -> dict[str, Any]:
    item = normalize_element(element, str(element.get("engine") or "fusion"))
    if item.get("type") in {"table", "figure", "chart"} and not item.get("caption"):
        caption = find_nearby_caption(item.get("bbox") or [], text_blocks_by_page.get(int(item.get("page") or 0), []), item.get("pageSize") or [], str(item.get("type") or ""))
        if caption:
            item["caption"] = caption.get("text", "")
            item["captionBBox"] = caption.get("bbox", [])
    item.setdefault("captionBBox", [])
    item.setdefault("sourceEngines", [item.get("engine")] if item.get("engine") else [])
    item.setdefault("sourceElementIds", [item.get("sourceElementId")] if item.get("sourceElementId") else [])
    item.setdefault("qualityFlags", [])
    item = _clip_bbox_to_page(item)
    item = apply_quality(item)
    return item


def _best_iou_match(
    element: dict[str, Any],
    candidates: list[dict[str, Any]],
    kind: str | set[str],
    used: set[str],
    threshold: float,
) -> dict[str, Any] | None:
    kinds = {kind} if isinstance(kind, str) else kind
    best: tuple[float, dict[str, Any]] | None = None
    for candidate in candidates:
        if str(candidate.get("id") or "") in used or str(candidate.get("type") or "") not in kinds:
            continue
        if int(candidate.get("page") or 0) != int(element.get("page") or 0):
            continue
        score = _bbox_iou(element.get("bbox") or [], candidate.get("bbox") or [])
        if score >= threshold and (best is None or score > best[0]):
            best = (score, candidate)
    return best[1] if best else None


def _best_formula_match(element: dict[str, Any], candidates: list[dict[str, Any]], used: set[str]) -> dict[str, Any] | None:
    best: tuple[float, dict[str, Any]] | None = None
    for candidate in candidates:
        if str(candidate.get("id") or "") in used or str(candidate.get("type") or "") != "formula":
            continue
        if int(candidate.get("page") or 0) != int(element.get("page") or 0):
            continue
        score = _formula_match_score(element, candidate)
        if score > 0.35 and (best is None or score > best[0]):
            best = (score, candidate)
    return best[1] if best else None


def _choose_table_candidate(candidates: list[tuple[str, dict[str, Any]]]) -> tuple[str, dict[str, Any], float]:
    scored = [(_table_candidate_score(element), engine, element) for engine, element in candidates]
    scored.sort(
        key=lambda item: (
            item[0],
            "<table" in str(item[2].get("html") or "").lower(),
            _valid_bbox({"bbox": item[2].get("bbox")}),
            len(item[2].get("table") or []),
        ),
        reverse=True,
    )
    score, engine, element = scored[0] if scored else (0.0, "", {})
    return engine, element, score


def _table_candidate_score(element: dict[str, Any]) -> float:
    rows = element.get("table") or []
    row_count, col_count = table_shape(rows)
    if row_count == 0 or col_count == 0:
        return 0.0
    widths = [len(row or []) for row in rows if row is not None]
    dominant_width = max(set(widths), key=widths.count) if widths else 0
    width_consistency = widths.count(dominant_width) / max(1, len(widths)) if dominant_width else 0.0
    filled_ratio = non_empty_cell_ratio(rows)
    numeric_or_unit_cells = sum(
        1
        for row in rows
        for cell in row
        if re.search(r"[-+]?\d|%|mAh|mg|cm|kg|mol|V|A|Wh|°C|K\b", str(cell or ""), flags=re.IGNORECASE)
    )
    numeric_ratio = numeric_or_unit_cells / max(1, row_count * col_count)
    score = 0.0
    score += min(0.22, row_count / 8.0 * 0.22)
    score += min(0.18, col_count / 6.0 * 0.18)
    score += width_consistency * 0.18
    score += filled_ratio * 0.18
    score += min(0.14, numeric_ratio * 0.28)
    if element.get("caption"):
        score += 0.06
    if "<table" in str(element.get("html") or "").lower():
        score += 0.1
    if _valid_bbox(element):
        score += 0.04
    return max(0.0, min(1.0, score))


def _choose_location_candidate(candidates: list[tuple[str, dict[str, Any]]]) -> tuple[str, dict[str, Any]]:
    valid = [(engine, element) for engine, element in candidates if _valid_bbox(element)]
    if not valid:
        return "", {}
    for engine, element in valid:
        if engine == "pymupdf":
            return engine, element
    return valid[0]


def _choose_formula_text(candidates: list[tuple[str, dict[str, Any]]]) -> tuple[str, str, float]:
    scored: list[tuple[float, int, str, str]] = []
    preference = {"mineru": 3, "paddleocr_vl": 2, "pymupdf": 1}
    for engine, element in candidates:
        text = str(element.get("latex") or element.get("text") or element.get("markdown") or "").strip()
        if not text:
            continue
        score = 0.0
        score += min(0.30, len(text) / 80.0 * 0.30)
        if re.search(r"=|\\frac|\\sum|\\int|\^|_|[+\-*/]", text):
            score += 0.28
        if element.get("latex"):
            score += 0.12
        if re.search(r"\(\s*\d+[A-Za-z]?\s*\)\s*$", text):
            score += 0.06
        if _valid_bbox(element):
            score += 0.08
        score += preference.get(engine, 0) * 0.03
        if _looks_like_sentence_formula_noise(text):
            score -= 0.18
        scored.append((score, preference.get(engine, 0), engine, text))
    if not scored:
        return "", "", 0.0
    scored.sort(reverse=True)
    score, _preference, engine, text = scored[0]
    return engine, text, max(0.0, min(1.0, score))


def _formula_match_score(left: dict[str, Any], right: dict[str, Any]) -> float:
    return max(
        _bbox_iou(left.get("bbox") or [], right.get("bbox") or []),
        _text_similarity(left.get("text") or left.get("latex") or "", right.get("text") or right.get("latex") or ""),
    )


def _looks_like_sentence_formula_noise(text: str) -> bool:
    value = str(text or "").strip()
    words = re.findall(r"[A-Za-z]{3,}", value)
    if len(words) >= 8 and re.search(r"\b(the|and|with|from|this|that|where|when|for)\b", value, flags=re.IGNORECASE):
        return True
    return bool(re.search(r"[.!?]\s*$", value) and len(words) >= 5)


def _valid_bbox(element: dict[str, Any]) -> bool:
    bbox = normalize_bbox(element.get("bbox"))
    return len(bbox) >= 4 and bbox != [0.0, 0.0, 0.0, 0.0] and bbox[2] > bbox[0] and bbox[3] > bbox[1]


def _table_text(rows: list[list[Any]]) -> str:
    return "\n".join("\t".join(str(cell or "") for cell in row) for row in rows or [])


def _overlaps_existing_table(element: dict[str, Any], elements: list[dict[str, Any]]) -> bool:
    for table in elements:
        if str(table.get("type") or "") == "table" and int(table.get("page") or 0) == int(element.get("page") or 0):
            if _bbox_iou(element.get("bbox") or [], table.get("bbox") or []) > 0.4:
                return True
    return False


def _dedupe_fused(elements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for element in elements:
        if any(
            int(existing.get("page") or 0) == int(element.get("page") or 0)
            and str(existing.get("type") or "") == str(element.get("type") or "")
            and _bbox_iou(existing.get("bbox") or [], element.get("bbox") or []) > 0.82
            for existing in result
        ):
            continue
        result.append(element)
    return result


def _clip_bbox_to_page(element: dict[str, Any]) -> dict[str, Any]:
    item = dict(element)
    bbox = normalize_bbox(item.get("bbox"))
    page_size = item.get("pageSize") or []
    if len(bbox) < 4 or len(page_size) < 2 or bbox == [0.0, 0.0, 0.0, 0.0]:
        return item
    width = float(page_size[0] or 0)
    height = float(page_size[1] or 0)
    if width <= 0 or height <= 0:
        return item
    clipped = [max(0.0, min(width, bbox[0])), max(0.0, min(height, bbox[1])), max(0.0, min(width, bbox[2])), max(0.0, min(height, bbox[3]))]
    if clipped != bbox:
        item["bbox"] = clipped
        item["qualityFlags"] = list(dict.fromkeys(list(item.get("qualityFlags") or []) + ["bbox_out_of_page", "bbox_clipped"]))
    return item


def _bbox_iou(left: list[float], right: list[float]) -> float:
    left = normalize_bbox(left)
    right = normalize_bbox(right)
    if len(left) < 4 or len(right) < 4 or left == [0.0, 0.0, 0.0, 0.0] or right == [0.0, 0.0, 0.0, 0.0]:
        return 0.0
    x0 = max(left[0], right[0])
    y0 = max(left[1], right[1])
    x1 = min(left[2], right[2])
    y1 = min(left[3], right[3])
    intersection = max(0.0, x1 - x0) * max(0.0, y1 - y0)
    left_area = max(0.0, left[2] - left[0]) * max(0.0, left[3] - left[1])
    right_area = max(0.0, right[2] - right[0]) * max(0.0, right[3] - right[1])
    union = left_area + right_area - intersection
    return intersection / union if union > 0 else 0.0


def _text_similarity(left: str, right: str) -> float:
    a = set(re.findall(r"[A-Za-z0-9]+|\\[A-Za-z]+|[=+\-*/^_]", str(left or "")))
    b = set(re.findall(r"[A-Za-z0-9]+|\\[A-Za-z]+|[=+\-*/^_]", str(right or "")))
    if not a or not b:
        return 0.0
    return len(a & b) / max(len(a), len(b))


def _sort_elements(elements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    order = {"table": 0, "figure": 1, "chart": 1, "formula": 2, "text_block": 3}
    return sorted(
        elements,
        key=lambda item: (
            int(item.get("page") or 0),
            order.get(str(item.get("type") or ""), 99),
            float((item.get("bbox") or [0, 0, 0, 0])[1]),
            float((item.get("bbox") or [0, 0, 0, 0])[0]),
        ),
    )
