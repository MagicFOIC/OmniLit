from __future__ import annotations

import csv
import hashlib
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


MATH_PATTERN = re.compile(r"(=|≈|≠|≤|≥|∑|∫|√|π|α|β|γ|Δ|λ|μ|σ|θ|×|÷|\^|\\frac|[A-Za-z]\s*[=+\-*/]\s*)")
EQUATION_NUMBER_PATTERN = re.compile(r"(\(\s*\d+[A-Za-z]?\s*\)|（\s*\d+[A-Za-z]?\s*）)\s*$")
CAPTION_PATTERN = re.compile(r"^\s*(fig(?:ure)?\.?|图|table|表)\s*\d+", re.IGNORECASE)


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

            tables = _extract_tables(page, page_index, page_size, target)
            elements.extend(tables)
            table_rects = [_rect_from_bbox(item["bbox"]) for item in tables]
            elements.extend(_extract_figures(page, page_index, page_size, target, text_blocks, table_rects))
            elements.extend(_extract_formulas(page, page_index, page_size, target))

    index = {
        "version": 1,
        "sourcePath": str(source),
        "sourceSha256": sha256_file(source),
        "analyzedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "pageCount": len(pages),
        "pages": pages,
        "elements": _sort_elements(_dedupe_elements(elements)),
    }
    index_path = target / "extraction_index.json"
    with index_path.open("w", encoding="utf-8") as handle:
        json.dump(index, handle, ensure_ascii=False, indent=2)
    return index


def _extract_text_blocks(page: Any) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for raw in page.get_text("blocks") or []:
        if len(raw) < 5:
            continue
        text = str(raw[4] or "").strip()
        if not text:
            continue
        blocks.append(
            {
                "bbox": [float(raw[0]), float(raw[1]), float(raw[2]), float(raw[3])],
                "text": text,
                "blockNo": int(raw[5]) if len(raw) > 5 and isinstance(raw[5], int) else len(blocks),
            }
        )
    return blocks


def _extract_tables(page: Any, page_index: int, page_size: list[float], output_dir: Path) -> list[dict[str, Any]]:
    tables: list[dict[str, Any]] = []
    finder = getattr(page, "find_tables", None)
    if finder is None:
        return tables
    try:
        result = finder()
    except Exception:
        return tables

    for table_index, table in enumerate(getattr(result, "tables", []) or []):
        bbox = _bbox_from_any(getattr(table, "bbox", None))
        if not bbox:
            continue
        rows = _safe_table_extract(table)
        if not rows:
            continue
        element_id = f"p{page_index + 1}_table_{table_index + 1}"
        csv_path = output_dir / "tables" / f"{element_id}.csv"
        json_path = output_dir / "tables" / f"{element_id}.json"
        _write_table_csv(csv_path, rows)
        _write_table_json(json_path, rows)
        row_count = len(rows)
        col_count = max((len(row) for row in rows), default=0)
        tables.append(
            {
                "id": element_id,
                "type": "table",
                "page": page_index,
                "bbox": bbox,
                "pageSize": page_size,
                "label": f"Table {table_index + 1}",
                "caption": "",
                "text": _table_text(rows),
                "table": rows,
                "csvPath": str(csv_path),
                "jsonPath": str(json_path),
                "pngPath": "",
                "metadata": {"rows": row_count, "columns": col_count},
            }
        )
    return tables


def _extract_figures(
    page: Any,
    page_index: int,
    page_size: list[float],
    output_dir: Path,
    text_blocks: list[dict[str, Any]],
    table_rects: list[Any],
) -> list[dict[str, Any]]:
    candidates: list[list[float]] = []
    for block in (page.get_text("dict") or {}).get("blocks", []):
        if block.get("type") == 1:
            bbox = _bbox_from_any(block.get("bbox"))
            if bbox:
                candidates.append(bbox)

    for drawing in page.get_drawings() or []:
        rect = drawing.get("rect")
        bbox = _bbox_from_any(rect)
        if not bbox:
            continue
        width = bbox[2] - bbox[0]
        height = bbox[3] - bbox[1]
        area = width * height
        if width < 35 or height < 25 or area < 1800:
            continue
        if any(_overlap_ratio(_rect_from_bbox(bbox), table_rect) > 0.35 for table_rect in table_rects):
            continue
        candidates.append(bbox)

    figures: list[dict[str, Any]] = []
    for figure_index, bbox in enumerate(_dedupe_bboxes(candidates), start=1):
        element_id = f"p{page_index + 1}_figure_{figure_index}"
        png_path = output_dir / "clips" / f"{element_id}.png"
        image_meta = _render_clip(page, bbox, png_path)
        caption = _caption_near_bbox(bbox, text_blocks)
        figures.append(
            {
                "id": element_id,
                "type": "figure",
                "page": page_index,
                "bbox": bbox,
                "pageSize": page_size,
                "label": f"Figure {figure_index}",
                "caption": caption,
                "text": caption,
                "table": [],
                "csvPath": "",
                "jsonPath": "",
                "pngPath": str(png_path),
                "metadata": {
                    "width": round(bbox[2] - bbox[0], 2),
                    "height": round(bbox[3] - bbox[1], 2),
                    **image_meta,
                },
            }
        )
    return figures


def _extract_formulas(page: Any, page_index: int, page_size: list[float], output_dir: Path) -> list[dict[str, Any]]:
    formulas: list[dict[str, Any]] = []
    page_width = float(page.rect.width)
    for line_index, line in enumerate(_text_lines(page), start=1):
        text = line["text"].strip()
        bbox = line["bbox"]
        if not _looks_like_formula(text, bbox, page_width):
            continue
        element_id = f"p{page_index + 1}_formula_{line_index}"
        png_path = output_dir / "clips" / f"{element_id}.png"
        padded = _pad_bbox(bbox, page.rect, 4)
        image_meta = _render_clip(page, padded, png_path)
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
                "pngPath": str(png_path),
                "metadata": {"lineIndex": line_index, **image_meta},
            }
        )
    return formulas


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
    has_math = bool(MATH_PATTERN.search(text))
    has_number = bool(EQUATION_NUMBER_PATTERN.search(text))
    center = (bbox[0] + bbox[2]) / 2.0
    centered = abs(center - page_width / 2.0) < page_width * 0.22
    short = (bbox[2] - bbox[0]) < page_width * 0.78
    alpha_count = sum(1 for char in compact if char.isalpha())
    return has_math and short and (centered or has_number or alpha_count <= max(12, len(compact) // 2))


def _safe_table_extract(table: Any) -> list[list[str]]:
    try:
        rows = table.extract()
    except Exception:
        rows = []
    cleaned: list[list[str]] = []
    for row in rows or []:
        cleaned.append([str(cell or "").strip() for cell in (row or [])])
    return [row for row in cleaned if any(cell for cell in row)]


def _write_table_csv(path: Path, rows: list[list[str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerows(rows)


def _write_table_json(path: Path, rows: list[list[str]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump({"rows": rows}, handle, ensure_ascii=False, indent=2)


def _table_text(rows: list[list[str]]) -> str:
    return "\n".join("\t".join(row) for row in rows)


def _render_clip(page: Any, bbox: list[float], path: Path) -> dict[str, int]:
    import fitz

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), clip=fitz.Rect(bbox), alpha=False)
        pixmap.save(str(path))
        return {"imageWidth": int(pixmap.width), "imageHeight": int(pixmap.height)}
    except Exception:
        return {}


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
    for bbox in candidates:
        rect = _rect_from_bbox(bbox)
        if any(_overlap_ratio(rect, _rect_from_bbox(existing)) > 0.75 for existing in result):
            continue
        result.append(bbox)
    return result


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
