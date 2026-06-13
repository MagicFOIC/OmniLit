from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

from .pdf_extraction_caption import find_nearby_caption
from .pdf_extraction_quality import apply_quality, quality_summary
from .pdf_extraction_schema import ensure_version_3, normalize_bbox, normalize_element


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
    rows = mineru.get("table") or pymupdf.get("table") or []
    item = _with_sources(pymupdf, ["pymupdf", "mineru"], mineru)
    item.update(
        {
            "engine": "fusion",
            "table": rows,
            "text": mineru.get("text") or pymupdf.get("text") or "",
            "csvPath": mineru.get("csvPath") or pymupdf.get("csvPath") or "",
            "jsonPath": mineru.get("jsonPath") or pymupdf.get("jsonPath") or "",
            "html": mineru.get("html") or pymupdf.get("html") or "",
            "markdown": mineru.get("markdown") or pymupdf.get("markdown") or "",
            "caption": mineru.get("caption") or pymupdf.get("caption") or "",
            "raw": {"pymupdf": pymupdf.get("raw") or {}, "mineru": mineru.get("raw") or {}},
        }
    )
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
    latex = mineru.get("latex") or mineru.get("text") or pymupdf.get("latex") or pymupdf.get("text") or ""
    item = _with_sources(pymupdf, ["pymupdf", "mineru"], mineru)
    item.update(
        {
            "engine": "fusion",
            "latex": latex,
            "text": latex,
            "markdown": mineru.get("markdown") or pymupdf.get("markdown") or "",
            "raw": {"pymupdf": pymupdf.get("raw") or {}, "mineru": mineru.get("raw") or {}},
        }
    )
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
        score = max(
            _bbox_iou(element.get("bbox") or [], candidate.get("bbox") or []),
            _text_similarity(element.get("text") or element.get("latex") or "", candidate.get("text") or candidate.get("latex") or ""),
        )
        if score > 0.35 and (best is None or score > best[0]):
            best = (score, candidate)
    return best[1] if best else None


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
