from __future__ import annotations

import csv
import hashlib
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .pdf_extraction_caption import find_nearby_caption
from .pdf_extraction_schema import normalize_element


MATH_PATTERN = re.compile(r"(=|≈|≠|≤|≥|∑|∫|√|π|α|β|γ|Δ|λ|μ|σ|θ|×|÷|\^|\\frac|[A-Za-z]\s*[=+\-*/]\s*)")
EQUATION_NUMBER_PATTERN = re.compile(r"(\(\s*\d+[A-Za-z]?\s*\)|（\s*\d+[A-Za-z]?\s*）)\s*$")
CAPTION_PATTERN = re.compile(r"^\s*(fig(?:ure)?\.?|图|table|表)\s*\d+", re.IGNORECASE)
FIGURE_CAPTION_PATTERN = re.compile(r"^\s*(fig(?:ure)?\.?\s*\d+[A-Za-z]?|图\s*\d+)", re.IGNORECASE)
TABLE_CAPTION_PATTERN = re.compile(r"^\s*(table\s*\d+[A-Za-z]?|表\s*\d+)", re.IGNORECASE)
ENABLE_VECTOR_FIGURE_DETECTION = False
MAX_VECTOR_DRAWINGS_PER_PAGE = 500


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def analyze_pdf(pdf_path: str | Path, output_dir: str | Path) -> dict[str, Any]:
    import fitz

    source = Path(pdf_path).expanduser().resolve()
    if not source.exists():
        raise FileNotFoundError(f"PDF 文件不存在：{source}")
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    (target / "tables").mkdir(exist_ok=True)
    (target / "clips").mkdir(exist_ok=True)

    pages: list[dict[str, Any]] = []
    elements: list[dict[str, Any]] = []
    with fitz.open(source) as document:
        for page_index in range(len(document)):
            page = document.load_page(page_index)
            rect = page.rect
            page_size = [float(rect.width), float(rect.height)]
            text_blocks = _extract_text_blocks(page)
            pages.append(
                {
                    "page": page_index,
                    "width": page_size[0],
                    "height": page_size[1],
                    "rect": _rect_list(rect),
                    "textBlocks": text_blocks,
                }
            )

            tables = extract_tables_pymupdf_multi_strategy(page, page_index, page_size, target, text_blocks)
            elements.extend(tables)
            table_rects = [_rect_from_bbox(item["bbox"]) for item in tables]
            elements.extend(extract_figures_pymupdf_enhanced(page, text_blocks, table_rects, page_index, page_size, target))
            elements.extend(extract_formula_candidates_pymupdf(page, text_blocks, page_index, page_size, target))

    index = {
        "version": 3,
        "sourcePath": str(source),
        "sourceSha256": sha256_file(source),
        "analyzedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "engine": "pymupdf",
        "engineChain": ["pymupdf"],
        "pageCount": len(pages),
        "pages": pages,
        "elements": _sort_elements(_dedupe_elements(_complete_element_schema(elements))),
        "markdownPath": "",
        "rawOutputs": {"pymupdf": str(target), "paddleocr_vl": "", "mineru": ""},
    }
    index_path = target / "extraction_index.json"
    with index_path.open("w", encoding="utf-8") as handle:
        json.dump(index, handle, ensure_ascii=False, indent=2)
    return index


def _extract_text_blocks(page: Any) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for line in _text_lines(page):
        text = str(line.get("text") or "").strip()
        bbox = line.get("bbox") or []
        if not text or len(bbox) < 4:
            continue
        blocks.append({"bbox": [float(value) for value in bbox], "text": text, "blockNo": len(blocks)})
    if blocks:
        return blocks
    for raw in page.get_text("blocks") or []:
        if len(raw) >= 5 and str(raw[4] or "").strip():
            blocks.append(
                {
                    "bbox": [float(raw[0]), float(raw[1]), float(raw[2]), float(raw[3])],
                    "text": str(raw[4] or "").strip(),
                    "blockNo": int(raw[5]) if len(raw) > 5 and isinstance(raw[5], int) else len(blocks),
                }
            )
    return blocks


def extract_tables_pymupdf_multi_strategy(
    page: Any,
    page_index: int,
    page_size: list[float],
    output_dir: Path,
    text_blocks: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    tables: list[dict[str, Any]] = []
    finder = getattr(page, "find_tables", None)
    if finder is None:
        return tables
    text_blocks = text_blocks or []
    table_captions = _table_caption_blocks(text_blocks)
    strategies = [
        {},
        {"vertical_strategy": "lines", "horizontal_strategy": "lines"},
        {"vertical_strategy": "lines", "horizontal_strategy": "lines", "snap_tolerance": 3, "join_tolerance": 3, "intersection_tolerance": 3},
    ]
    seen_strategy: set[tuple[tuple[str, Any], ...]] = set()
    table_index = 0
    for params in strategies:
        key = tuple(sorted(params.items()))
        if key in seen_strategy:
            continue
        seen_strategy.add(key)
        try:
            result = finder(**params)
        except TypeError:
            continue
        except Exception:
            continue
        for table in getattr(result, "tables", []) or []:
            bbox = _bbox_from_any(getattr(table, "bbox", None))
            if not bbox:
                continue
            rows = _safe_table_extract(table)
            if not rows:
                continue
            caption_info = _table_caption_for_bbox(bbox, text_blocks, page_size)
            if table_captions and not caption_info:
                continue
            if not _valid_table_candidate(rows, bbox, page_size, caption_info, params):
                continue
            table_index += 1
            element_id = f"p{page_index + 1}_table_{table_index}"
            row_count = len(rows)
            col_count = max((len(row) for row in rows), default=0)
            tables.append(
                {
                    "id": element_id,
                    "type": "table",
                    "page": page_index,
                    "bbox": bbox,
                    "pageSize": page_size,
                    "label": f"Table {table_index}",
                    "caption": caption_info.get("text", "") if caption_info else "",
                    "captionBBox": caption_info.get("bbox", []) if caption_info else [],
                    "text": _table_text(rows),
                    "table": rows,
                    "csvPath": "",
                    "jsonPath": "",
                    "pngPath": "",
                    "metadata": {
                        "rows": row_count,
                        "columns": col_count,
                        "strategy": params or {"default": True},
                        "structuralScore": round(_table_structural_score(rows), 3),
                        "textStrategy": _is_text_table_strategy(params),
                    },
                }
            )

    deduped = dedupe_tables_by_iou(tables)
    for next_index, table in enumerate(deduped, start=1):
        element_id = f"p{page_index + 1}_table_{next_index}"
        rows = table.get("table") or []
        csv_path = output_dir / "tables" / f"{element_id}.csv"
        json_path = output_dir / "tables" / f"{element_id}.json"
        png_path = output_dir / "clips" / f"{element_id}.png"
        _write_table_csv(csv_path, rows)
        _write_table_json(json_path, rows)
        crop_element_png(page, table["bbox"], png_path, zoom=2.5, padding=6)
        table.update({"id": element_id, "label": f"Table {next_index}", "csvPath": str(csv_path), "jsonPath": str(json_path), "pngPath": str(png_path)})
    return deduped


def _extract_tables(page: Any, page_index: int, page_size: list[float], output_dir: Path) -> list[dict[str, Any]]:
    return extract_tables_pymupdf_multi_strategy(page, page_index, page_size, output_dir, _extract_text_blocks(page))


def dedupe_tables_by_iou(tables: list[dict[str, Any]], iou_threshold: float = 0.72) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for table in sorted(tables, key=_table_quality_key, reverse=True):
        if any(int(existing.get("page") or 0) == int(table.get("page") or 0) and _bbox_iou(existing.get("bbox") or [], table.get("bbox") or []) >= iou_threshold for existing in result):
            continue
        result.append(table)
    return _sort_elements(result)


def extract_figures_pymupdf_enhanced(
    page: Any,
    text_blocks: list[dict[str, Any]],
    table_rects: list[Any],
    page_index: int,
    page_size: list[float],
    output_dir: Path,
) -> list[dict[str, Any]]:
    candidates: list[list[float]] = []
    for block in (page.get_text("dict") or {}).get("blocks", []):
        if block.get("type") == 1:
            bbox = _bbox_from_any(block.get("bbox"))
            if bbox:
                candidates.append(bbox)

    try:
        for info in page.get_image_info(hashes=True, xrefs=True) or []:
            bbox = _bbox_from_any(info.get("bbox"))
            if bbox:
                candidates.append(bbox)
    except Exception:
        pass

    drawings = []
    try:
        drawings = page.get_drawings() or []
    except Exception:
        drawings = []
    if len(drawings) > MAX_VECTOR_DRAWINGS_PER_PAGE and not ENABLE_VECTOR_FIGURE_DETECTION:
        drawings = []

    drawing_bboxes: list[list[float]] = []
    for drawing in drawings:
        rect = drawing.get("rect")
        bbox = _bbox_from_any(rect)
        if not bbox:
            continue
        width = bbox[2] - bbox[0]
        height = bbox[3] - bbox[1]
        area = width * height
        if width < 35 or height < 25 or area < 1800:
            continue
        drawing_bboxes.append(bbox)
    candidates.extend(_merge_nearby_bboxes(drawing_bboxes))
    candidates.extend(_caption_anchored_figure_bboxes(text_blocks, page_size, table_rects))

    figures: list[dict[str, Any]] = []
    filtered = []
    for bbox in candidates:
        if not _reasonable_figure_bbox(bbox, page_size):
            continue
        if any(_overlap_ratio(_rect_from_bbox(bbox), table_rect) > 0.35 for table_rect in table_rects):
            continue
        filtered.append(bbox)
    for figure_index, bbox in enumerate(_dedupe_bboxes(filtered), start=1):
        caption_info = find_nearby_caption(bbox, text_blocks, page_size, "figure")
        caption = caption_info.get("text", "") if caption_info else _caption_near_bbox(bbox, text_blocks)
        display_bbox = _union_bboxes([bbox, caption_info.get("bbox", []) if caption_info else []])
        element_id = f"p{page_index + 1}_figure_{figure_index}"
        png_path = output_dir / "clips" / f"{element_id}.png"
        image_meta = crop_element_png(page, display_bbox, png_path, zoom=2.5, padding=8)
        figures.append(
            {
                "id": element_id,
                "type": "figure",
                "page": page_index,
                "bbox": display_bbox,
                "pageSize": page_size,
                "label": f"Figure {figure_index}",
                "caption": caption,
                "captionBBox": caption_info.get("bbox", []) if caption_info else [],
                "text": caption,
                "table": [],
                "csvPath": "",
                "jsonPath": "",
                "pngPath": str(png_path),
                "metadata": {
                    "width": round(display_bbox[2] - display_bbox[0], 2),
                    "height": round(display_bbox[3] - display_bbox[1], 2),
                    "imageBBox": bbox,
                    **image_meta,
                },
            }
        )
    return figures


def _extract_figures(
    page: Any,
    page_index: int,
    page_size: list[float],
    output_dir: Path,
    text_blocks: list[dict[str, Any]],
    table_rects: list[Any],
) -> list[dict[str, Any]]:
    return extract_figures_pymupdf_enhanced(page, text_blocks, table_rects, page_index, page_size, output_dir)


def extract_formula_candidates_pymupdf(page: Any, text_blocks: list[dict[str, Any]], page_index: int, page_size: list[float], output_dir: Path) -> list[dict[str, Any]]:
    formulas: list[dict[str, Any]] = []
    page_width = float(page.rect.width)
    lines = _merge_formula_lines(_text_lines(page), page_width)
    for line_index, line in enumerate(lines, start=1):
        text = line["text"].strip()
        bbox = line["bbox"]
        if not _looks_like_formula(text, bbox, page_width):
            continue
        if not _is_isolated_formula_line(line, lines, page.rect):
            continue
        element_id = f"p{page_index + 1}_formula_{line_index}"
        padded = _pad_bbox(bbox, page.rect, 4)
        png_path = output_dir / "clips" / f"{element_id}.png"
        image_meta = crop_element_png(page, padded, png_path, zoom=3.0, padding=4)
        formulas.append(
            {
                "id": element_id,
                "type": "formula",
                "page": page_index,
                "bbox": padded,
                "pageSize": page_size,
                "label": f"Formula {len(formulas) + 1}",
                "caption": "",
                "text": text,
                "table": [],
                "csvPath": "",
                "jsonPath": "",
                "pngPath": str(png_path) if image_meta else "",
                "metadata": {"lineIndex": line_index, **image_meta},
            }
        )
    return formulas


def _extract_formulas(page: Any, page_index: int, page_size: list[float], output_dir: Path) -> list[dict[str, Any]]:
    return extract_formula_candidates_pymupdf(page, _extract_text_blocks(page), page_index, page_size, output_dir)


def _text_lines(page: Any) -> list[dict[str, Any]]:
    lines: list[dict[str, Any]] = []
    for block in (page.get_text("dict") or {}).get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []) or []:
            spans = line.get("spans", []) or []
            text = "".join(str(span.get("text", "")) for span in spans).strip()
            bbox = _bbox_from_any(line.get("bbox"))
            if text and bbox:
                lines.append({"text": text, "bbox": bbox})
    return lines


def _looks_like_formula(text: str, bbox: list[float], page_width: float) -> bool:
    compact = re.sub(r"\s+", "", text)
    if len(compact) < 3 or len(compact) > 180:
        return False
    lowered = text.strip().lower()
    if FIGURE_CAPTION_PATTERN.search(text) or TABLE_CAPTION_PATTERN.search(text):
        return False
    if lowered.startswith(("where ", "when ", "for ", "table ", "figure ", "fig. ", "fig ")):
        return False
    has_math = bool(MATH_PATTERN.search(text))
    has_number = bool(EQUATION_NUMBER_PATTERN.search(text))
    if not has_number:
        return False
    strong_math = _strong_formula_signal(text)
    center = (bbox[0] + bbox[2]) / 2.0
    centered = abs(center - page_width / 2.0) < page_width * 0.22
    short = (bbox[2] - bbox[0]) < page_width * 0.78
    numbered_position = has_number and (bbox[2] > page_width * 0.5 or centered)
    alpha_count = sum(1 for char in compact if char.isalpha())
    word_count = len(re.findall(r"[A-Za-z]{3,}", text))
    if word_count > 10 and not has_number:
        return False
    if word_count > 4 and not has_number and not any(token in text for token in ("∂", "∇", "∫", "∑", "\\frac", "\\sum", "\\int")):
        return False
    return has_math and short and numbered_position and (strong_math or alpha_count <= max(10, len(compact) // 2))


def _strong_formula_signal(text: str) -> bool:
    compact = re.sub(r"\s+", "", text)
    if any(token in text for token in ("∂", "∇", "∫", "∑", "√", "\\frac", "\\sum", "\\int", "≤", "≥", "≈", "≠")):
        return True
    if re.search(r"[A-Za-z]\s*[=≈]\s*[-+]?[\dA-Za-z]", text):
        return True
    if re.search(r"[A-Za-z0-9\)\]]\s*[+\-*/×÷]\s*[A-Za-z0-9\(]", text) and len(compact) <= 90:
        return True
    if EQUATION_NUMBER_PATTERN.search(text) and re.search(r"[=+\-*/×÷^_]", text):
        return True
    return False


def _is_isolated_formula_line(line: dict[str, Any], lines: list[dict[str, Any]], page_rect: Any) -> bool:
    bbox = line.get("bbox") or []
    if len(bbox) < 4:
        return False
    same_column_lines = []
    for other in lines:
        other_bbox = other.get("bbox") or []
        if other is line or len(other_bbox) < 4:
            continue
        overlap = max(0.0, min(bbox[2], other_bbox[2]) - max(bbox[0], other_bbox[0]))
        if overlap >= min(bbox[2] - bbox[0], other_bbox[2] - other_bbox[0]) * 0.12:
            same_column_lines.append(other_bbox)
    above_gap = float(bbox[1]) - float(page_rect.y0)
    below_gap = float(page_rect.y1) - float(bbox[3])
    for other_bbox in same_column_lines:
        if other_bbox[3] <= bbox[1]:
            above_gap = min(above_gap, bbox[1] - other_bbox[3])
        if other_bbox[1] >= bbox[3]:
            below_gap = min(below_gap, other_bbox[1] - bbox[3])
    line_height = max(8.0, float(bbox[3]) - float(bbox[1]))
    return above_gap >= line_height * 0.45 and below_gap >= line_height * 0.35


def _safe_table_extract(table: Any) -> list[list[str]]:
    try:
        rows = table.extract()
    except Exception:
        rows = []
    cleaned: list[list[str]] = []
    for row in rows or []:
        cleaned.append([str(cell or "").strip() for cell in (row or [])])
    return [row for row in cleaned if any(cell for cell in row)]


def _valid_table_candidate(
    rows: list[list[str]],
    bbox: list[float],
    page_size: list[float],
    caption_info: dict[str, Any] | None,
    strategy: dict[str, Any],
) -> bool:
    if len(bbox or []) < 4:
        return False
    row_count = len(rows)
    col_count = max((len(row or []) for row in rows), default=0)
    if row_count < 2 or col_count < 2:
        return False
    width = float(bbox[2]) - float(bbox[0])
    height = float(bbox[3]) - float(bbox[1])
    page_area = max(1.0, float(page_size[0] or 0) * float(page_size[1] or 0))
    if width < 80 or height < 24 or (width * height) / page_area < 0.003:
        return False
    structural_score = _table_structural_score(rows)
    has_caption = bool(caption_info and TABLE_CAPTION_PATTERN.search(str(caption_info.get("text") or "")))
    text_strategy = _is_text_table_strategy(strategy)
    if text_strategy and _looks_like_body_text_table(rows):
        return False
    if has_caption and structural_score >= 0.12:
        return True
    if text_strategy:
        return row_count >= 3 and col_count >= 3 and structural_score >= 0.38
    return structural_score >= 0.22


def _table_caption_blocks(text_blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [block for block in text_blocks or [] if TABLE_CAPTION_PATTERN.search(str(block.get("text") or "").strip())]


def _is_text_table_strategy(strategy: dict[str, Any]) -> bool:
    return str(strategy.get("vertical_strategy") or "") == "text" or str(strategy.get("horizontal_strategy") or "") == "text"


def _looks_like_body_text_table(rows: list[list[str]]) -> bool:
    if not rows:
        return False
    total = 0
    sentence_like = 0
    singleton = 0
    for row in rows:
        cells = [str(cell or "").strip() for cell in row or [] if str(cell or "").strip()]
        if not cells:
            continue
        row_text = " ".join(cells)
        total += 1
        if len(cells[0]) <= 1:
            singleton += 1
        if len(row_text) > 45 and len(re.findall(r"[A-Za-z]{4,}", row_text)) >= 5:
            sentence_like += 1
    return total > 0 and (sentence_like / total >= 0.25 or singleton / total >= 0.35)


def _table_structural_score(rows: list[list[str]]) -> float:
    if not rows:
        return 0.0
    row_count = len(rows)
    col_count = max((len(row or []) for row in rows), default=0)
    if row_count == 0 or col_count == 0:
        return 0.0
    non_empty = 0
    numericish = 0
    short_cells = 0
    total = 0
    lengths_by_row: list[int] = []
    for row in rows:
        cells = [str(cell or "").strip() for cell in row or []]
        lengths_by_row.append(len(cells))
        for cell in cells:
            if not cell:
                continue
            total += 1
            non_empty += 1
            if _looks_numericish(cell):
                numericish += 1
            if len(cell) <= 80:
                short_cells += 1
    density = non_empty / max(1, row_count * col_count)
    numeric_ratio = numericish / max(1, total)
    short_ratio = short_cells / max(1, total)
    width_consistency = lengths_by_row.count(col_count) / max(1, row_count)
    shape_bonus = min(0.24, row_count * col_count / 60.0)
    return density * 0.32 + numeric_ratio * 0.24 + short_ratio * 0.18 + width_consistency * 0.18 + shape_bonus


def _looks_numericish(text: str) -> bool:
    value = str(text or "").strip()
    if not value:
        return False
    if re.search(r"[-+]?\d+(?:\.\d+)?(?:\s*(?:%|[A-Za-z]+(?:\s*[-/]\s*[A-Za-z]+)?))?", value):
        return True
    return bool(re.search(r"^[<>≤≥~≈±−–—]?\s*\d", value))


def _write_table_csv(path: Path, rows: list[list[str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerows(rows)


def _write_table_json(path: Path, rows: list[list[str]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump({"rows": rows}, handle, ensure_ascii=False, indent=2)


def _table_text(rows: list[list[str]]) -> str:
    return "\n".join("\t".join(row) for row in rows)


def crop_element_png(page: Any, bbox: list[float], output_path: Path, zoom: float = 2.5, padding: float = 6) -> dict[str, int]:
    import fitz

    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        clip = fitz.Rect(_pad_bbox(bbox, page.rect, padding))
        if output_path.exists():
            return {}
        scale = max(1.0, float(zoom or 2.5))
        pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), clip=clip, alpha=False)
        pixmap.save(str(output_path))
        return {"imageWidth": int(pixmap.width), "imageHeight": int(pixmap.height)}
    except Exception:
        return {}


def _render_clip(page: Any, bbox: list[float], path: Path) -> dict[str, int]:
    return crop_element_png(page, bbox, path, zoom=2.5, padding=6)


def _caption_near_bbox(bbox: list[float], text_blocks: list[dict[str, Any]]) -> str:
    below: list[tuple[float, str]] = []
    above: list[tuple[float, str]] = []
    for block in text_blocks:
        block_bbox = block.get("bbox") or []
        text = str(block.get("text") or "").strip().replace("\n", " ")
        if not text:
            continue
        distance_below = float(block_bbox[1]) - bbox[3]
        distance_above = bbox[1] - float(block_bbox[3])
        horizontal_overlap = max(0.0, min(bbox[2], block_bbox[2]) - max(bbox[0], block_bbox[0]))
        if horizontal_overlap <= 0:
            continue
        if 0 <= distance_below <= 55:
            below.append((distance_below, text))
        if 0 <= distance_above <= 35:
            above.append((distance_above, text))
    for _distance, text in sorted(below + above, key=lambda item: item[0]):
        if CAPTION_PATTERN.search(text) or len(text) <= 180:
            return text[:240]
    return ""


def _table_caption_for_bbox(bbox: list[float], text_blocks: list[dict[str, Any]], page_size: list[float]) -> dict[str, Any]:
    if len(bbox or []) < 4:
        return {}
    max_distance = max(24.0, float(page_size[1] if len(page_size) > 1 else 0.0) * 0.08)
    candidates: list[tuple[float, dict[str, Any]]] = []
    for block in text_blocks or []:
        block_bbox = block.get("bbox") or []
        text = str(block.get("text") or "").strip().replace("\n", " ")
        if len(block_bbox) < 4 or not TABLE_CAPTION_PATTERN.search(text):
            continue
        if _bbox_iou(bbox, block_bbox) > 0.0 or _contains_bbox(bbox, block_bbox):
            continue
        overlap = max(0.0, min(bbox[2], block_bbox[2]) - max(bbox[0], block_bbox[0]))
        if overlap < min(bbox[2] - bbox[0], block_bbox[2] - block_bbox[0]) * 0.18:
            continue
        above = bbox[1] - block_bbox[3]
        below = block_bbox[1] - bbox[3]
        distance = above if above >= 0 else below if below >= 0 else -1.0
        if distance < 0 or distance > max_distance:
            continue
        direction_penalty = 0.0 if above >= 0 else 8.0
        candidates.append((distance + direction_penalty, {"text": text[:300], "bbox": [float(v) for v in block_bbox], "score": 0.9}))
    if not candidates:
        return {}
    candidates.sort(key=lambda item: item[0])
    return candidates[0][1]


def _caption_anchored_figure_bboxes(
    text_blocks: list[dict[str, Any]],
    page_size: list[float],
    table_rects: list[Any],
) -> list[list[float]]:
    result: list[list[float]] = []
    if len(page_size or []) < 2:
        return result
    page_width = float(page_size[0] or 0)
    page_height = float(page_size[1] or 0)
    if page_width <= 0 or page_height <= 0:
        return result
    text_rects = [_rect_from_bbox(block.get("bbox") or [0, 0, 0, 0]) for block in text_blocks or [] if len(block.get("bbox") or []) >= 4]
    for block in text_blocks or []:
        caption_bbox = block.get("bbox") or []
        caption_text = str(block.get("text") or "").strip().replace("\n", " ")
        if len(caption_bbox) < 4 or not FIGURE_CAPTION_PATTERN.search(caption_text):
            continue
        candidates = [
            [caption_bbox[0], max(0.0, caption_bbox[1] - page_height * 0.42), caption_bbox[2], max(0.0, caption_bbox[1] - 4)],
            [page_width * 0.08, max(0.0, caption_bbox[1] - page_height * 0.42), page_width * 0.92, max(0.0, caption_bbox[1] - 4)],
        ]
        for candidate in candidates:
            refined = _trim_candidate_against_text(candidate, text_rects, caption_bbox, page_size)
            if not _reasonable_figure_bbox(refined, page_size):
                continue
            rect = _rect_from_bbox(refined)
            if any(_overlap_ratio(rect, table_rect) > 0.25 for table_rect in table_rects):
                continue
            result.append(refined)
            break
    return result


def _trim_candidate_against_text(
    candidate: list[float],
    text_rects: list[Any],
    caption_bbox: list[float],
    page_size: list[float],
) -> list[float]:
    x0, y0, x1, y1 = [float(value) for value in candidate]
    blockers: list[float] = []
    candidate_rect = _rect_from_bbox([x0, y0, x1, y1])
    for rect in text_rects:
        bbox = _bbox_from_any(rect)
        if not bbox or abs(float(bbox[1]) - float(caption_bbox[1])) < 1 and abs(float(bbox[3]) - float(caption_bbox[3])) < 1:
            continue
        overlap_x = max(0.0, min(x1, bbox[2]) - max(x0, bbox[0]))
        if overlap_x < (x1 - x0) * 0.18:
            continue
        if bbox[1] >= y0 and bbox[3] <= y1 and bbox[3] < caption_bbox[1]:
            blockers.append(float(bbox[3]))
        if _overlap_ratio(_rect_from_bbox(bbox), candidate_rect) > 0.25:
            if bbox[3] < caption_bbox[1]:
                blockers.append(float(bbox[3]))
    if blockers:
        y0 = max(y0, max(blockers) + 4)
    min_height = max(36.0, float(page_size[1] or 0) * 0.05)
    if y1 - y0 < min_height:
        y0 = max(0.0, y1 - min_height)
    return [max(0.0, x0), max(0.0, y0), min(float(page_size[0] or x1), x1), min(float(page_size[1] or y1), y1)]


def _dedupe_elements(elements: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: list[dict[str, Any]] = []
    seen: set[tuple[int, str, int, int, int, int]] = set()
    for element in elements:
        bbox = element.get("bbox") or [0, 0, 0, 0]
        key = (
            int(element.get("page", 0)),
            str(element.get("type", "")),
            round(float(bbox[0])),
            round(float(bbox[1])),
            round(float(bbox[2])),
            round(float(bbox[3])),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(element)
    return unique


def _complete_element_schema(elements: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    completed: list[dict[str, Any]] = []
    confidence_by_type = {"table": 0.75, "figure": 0.65, "formula": 0.55}
    for element in elements:
        kind = str(element.get("type") or "")
        item = normalize_element(element, "pymupdf")
        item["engine"] = "pymupdf"
        item["confidence"] = float(item.get("confidence") or confidence_by_type.get(kind, 0.5))
        item["needsReview"] = bool(item.get("needsReview") or kind == "formula")
        completed.append(item)
    return completed


def _sort_elements(elements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    type_order = {"table": 0, "figure": 1, "formula": 2}
    return sorted(
        elements,
        key=lambda element: (
            int(element.get("page", 0)),
            type_order.get(str(element.get("type") or ""), 99),
            float((element.get("bbox") or [0, 0, 0, 0])[1]),
            float((element.get("bbox") or [0, 0, 0, 0])[0]),
        ),
    )


def _dedupe_bboxes(candidates: Iterable[list[float]]) -> list[list[float]]:
    result: list[list[float]] = []
    for bbox in sorted(candidates, key=_bbox_area, reverse=True):
        rect = _rect_from_bbox(bbox)
        if any(max(_overlap_ratio(rect, _rect_from_bbox(existing)), _overlap_ratio(_rect_from_bbox(existing), rect)) > 0.45 for existing in result):
            continue
        result.append(bbox)
    return result


def _bbox_area(bbox: list[float]) -> float:
    if len(bbox or []) < 4:
        return 0.0
    return max(0.0, float(bbox[2]) - float(bbox[0])) * max(0.0, float(bbox[3]) - float(bbox[1]))


def _union_bboxes(candidates: Iterable[list[float]]) -> list[float]:
    boxes = [box for box in candidates if len(box or []) >= 4]
    if not boxes:
        return []
    return [
        min(float(box[0]) for box in boxes),
        min(float(box[1]) for box in boxes),
        max(float(box[2]) for box in boxes),
        max(float(box[3]) for box in boxes),
    ]


def _table_quality_key(table: dict[str, Any]) -> tuple[int, float, float, int, int, float]:
    rows = table.get("table") or []
    row_count = len(rows)
    col_count = max((len(row or []) for row in rows), default=0)
    non_empty = sum(1 for row in rows for cell in row if str(cell or "").strip())
    bbox = table.get("bbox") or [0, 0, 0, 0]
    area = max(0.0, float(bbox[2]) - float(bbox[0])) * max(0.0, float(bbox[3]) - float(bbox[1]))
    metadata = table.get("metadata") if isinstance(table.get("metadata"), dict) else {}
    line_based = 0 if metadata.get("textStrategy") else 1
    structural_score = float(metadata.get("structuralScore") or 0.0)
    return line_based, structural_score, float(table.get("confidence") or 0.0), row_count, col_count, area


def _bbox_iou(left: list[float], right: list[float]) -> float:
    if len(left or []) < 4 or len(right or []) < 4:
        return 0.0
    x0 = max(float(left[0]), float(right[0]))
    y0 = max(float(left[1]), float(right[1]))
    x1 = min(float(left[2]), float(right[2]))
    y1 = min(float(left[3]), float(right[3]))
    intersection = max(0.0, x1 - x0) * max(0.0, y1 - y0)
    left_area = max(0.0, float(left[2]) - float(left[0])) * max(0.0, float(left[3]) - float(left[1]))
    right_area = max(0.0, float(right[2]) - float(right[0])) * max(0.0, float(right[3]) - float(right[1]))
    union = left_area + right_area - intersection
    return intersection / union if union > 0 else 0.0


def _contains_bbox(outer: list[float], inner: list[float], tolerance: float = 1.0) -> bool:
    if len(outer or []) < 4 or len(inner or []) < 4:
        return False
    return (
        float(outer[0]) - tolerance <= float(inner[0])
        and float(outer[1]) - tolerance <= float(inner[1])
        and float(outer[2]) + tolerance >= float(inner[2])
        and float(outer[3]) + tolerance >= float(inner[3])
    )


def _merge_nearby_bboxes(candidates: list[list[float]]) -> list[list[float]]:
    merged: list[list[float]] = []
    for bbox in candidates:
        expanded = [bbox[0] - 4, bbox[1] - 4, bbox[2] + 4, bbox[3] + 4]
        matched = False
        for index, existing in enumerate(merged):
            if _bbox_iou(expanded, existing) > 0.02 or _bboxes_touch(expanded, existing):
                merged[index] = [
                    min(existing[0], bbox[0]),
                    min(existing[1], bbox[1]),
                    max(existing[2], bbox[2]),
                    max(existing[3], bbox[3]),
                ]
                matched = True
                break
        if not matched:
            merged.append(list(bbox))
    return merged


def _bboxes_touch(left: list[float], right: list[float]) -> bool:
    horizontal_gap = max(0.0, max(left[0], right[0]) - min(left[2], right[2]))
    vertical_gap = max(0.0, max(left[1], right[1]) - min(left[3], right[3]))
    overlap_x = min(left[2], right[2]) > max(left[0], right[0])
    overlap_y = min(left[3], right[3]) > max(left[1], right[1])
    return (overlap_x and vertical_gap <= 8) or (overlap_y and horizontal_gap <= 8)


def _reasonable_figure_bbox(bbox: list[float], page_size: list[float]) -> bool:
    if len(bbox or []) < 4:
        return False
    width = float(bbox[2]) - float(bbox[0])
    height = float(bbox[3]) - float(bbox[1])
    if width < 32 or height < 24:
        return False
    page_area = max(1.0, float(page_size[0] or 0) * float(page_size[1] or 0))
    area = width * height
    ratio = max(width / max(height, 1.0), height / max(width, 1.0))
    if area / page_area < 0.006 or ratio > 12:
        return False
    if bbox[3] < float(page_size[1]) * 0.06 or bbox[1] > float(page_size[1]) * 0.94:
        return False
    return True


def _merge_formula_lines(lines: list[dict[str, Any]], page_width: float) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for line in lines:
        text = str(line.get("text") or "").strip()
        bbox = line.get("bbox") or []
        if current is not None and bbox and 0 <= float(bbox[1]) - float(current["bbox"][3]) <= 10:
            combined = f"{current['text']} {text}".strip()
            if _looks_like_formula(combined, [min(current["bbox"][0], bbox[0]), current["bbox"][1], max(current["bbox"][2], bbox[2]), bbox[3]], page_width):
                current = {
                    "text": combined,
                    "bbox": [min(current["bbox"][0], bbox[0]), current["bbox"][1], max(current["bbox"][2], bbox[2]), bbox[3]],
                }
                continue
        if current is not None:
            merged.append(current)
        current = {"text": text, "bbox": bbox}
    if current is not None:
        merged.append(current)
    return merged


def _bbox_from_any(value: Any) -> list[float]:
    if value is None:
        return []
    if hasattr(value, "x0"):
        return [float(value.x0), float(value.y0), float(value.x1), float(value.y1)]
    if isinstance(value, (list, tuple)) and len(value) >= 4:
        return [float(value[0]), float(value[1]), float(value[2]), float(value[3])]
    return []


def _rect_list(rect: Any) -> list[float]:
    return [float(rect.x0), float(rect.y0), float(rect.x1), float(rect.y1)]


def _rect_from_bbox(bbox: list[float]) -> Any:
    import fitz

    return fitz.Rect(float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3]))


def _overlap_ratio(left: Any, right: Any) -> float:
    area = max(0.0, left.get_area())
    if area <= 0:
        return 0.0
    intersection = left & right
    return max(0.0, intersection.get_area()) / area


def _pad_bbox(bbox: list[float], page_rect: Any, padding: float) -> list[float]:
    return [
        max(float(page_rect.x0), math.floor(bbox[0] - padding)),
        max(float(page_rect.y0), math.floor(bbox[1] - padding)),
        min(float(page_rect.x1), math.ceil(bbox[2] + padding)),
        min(float(page_rect.y1), math.ceil(bbox[3] + padding)),
    ]
