from __future__ import annotations

import csv
import hashlib
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

try:  # keep import-compatible with the existing package
    from .pdf_extraction_caption import find_nearby_caption as _legacy_find_nearby_caption
except Exception:  # pragma: no cover - direct module smoke tests
    _legacy_find_nearby_caption = None

try:
    from .pdf_extraction_schema import normalize_element
except Exception:  # pragma: no cover - direct module smoke tests
    def normalize_element(element: dict[str, Any], fallback_engine: str = "") -> dict[str, Any]:
        if fallback_engine and not element.get("engine"):
            element = dict(element)
            element["engine"] = fallback_engine
        return element

try:
    from .pdf_extraction_quality import apply_quality
except Exception:  # pragma: no cover - direct module smoke tests
    def apply_quality(element: dict[str, Any]) -> dict[str, Any]:
        return element

try:
    from .pdf_extraction_quality import quality_summary, write_quality_report
except Exception:  # pragma: no cover - direct module smoke tests
    def quality_summary(elements: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
        return {
            "tables": {"count": 0, "needsReview": 0},
            "figures": {"count": 0, "needsReview": 0},
            "formulas": {"count": 0, "needsReview": 0},
        }

    def write_quality_report(output_dir: str | Path, index: dict[str, Any]) -> Path:
        return Path(output_dir) / "quality_report.json"


MATH_PATTERN = re.compile(
    r"(=|≈|≠|≤|≥|∑|∫|√|π|α|β|γ|Δ|λ|μ|σ|θ|×|÷|\^|\\frac|[A-Za-z]\s*[=+\-*/]\s*)"
)
EQUATION_NUMBER_PATTERN = re.compile(r"(\(\s*\d+[A-Za-z]?\s*\)|（\s*\d+[A-Za-z]?\s*）)\s*$")
FORMULA_SYMBOL_PATTERN = re.compile(
    r"(=|<=|>=|≈|≠|≤|≥|±|×|÷|∑|∫|√|∞|∂|∆|Δ|"
    r"\\frac|\\sum|\\int|\\sqrt|\\alpha|\\beta|\\gamma|\\delta|\\mu|\\sigma|"
    r"[\u0370-\u03ff]|[A-Za-z0-9]\s*[\^_]|[A-Za-z]\s*[=+\-*/]\s*)"
)
FORMULA_SENTENCE_WORDS = {
    "the",
    "and",
    "with",
    "from",
    "this",
    "that",
    "where",
    "when",
    "for",
    "into",
    "were",
    "was",
    "are",
    "can",
    "should",
}
CAPTION_PATTERN = re.compile(r"^\s*(fig(?:ure)?[\.．]?|图|table|表)\s*\d+", re.IGNORECASE)
FIGURE_CAPTION_PATTERN = re.compile(
    r"^\s*(fig(?:ure)?[\.．]?|图)\s*([0-9]+[A-Za-z]?)\b", re.IGNORECASE
)
TABLE_CAPTION_PATTERN = re.compile(r"^\s*(table\s*\d+[A-Za-z]?|表\s*\d+)", re.IGNORECASE)
FIGURE_LABEL_EXTRACT_PATTERN = re.compile(r"^\s*(?:fig(?:ure)?[\.．]?|图)\s*([0-9]+[A-Za-z]?)", re.IGNORECASE)
DECORATIVE_FIGURE_TEXT_PATTERN = re.compile(
    r"(royal\s+society\s+of\s+chemistry|\brsc\s+advances\b|\bview\s+article\s+online\b|"
    r"\bview\s+journal\b|\bview\s+issue\b|\bcheck\s+for\s+updates\b|\barticle\s+online\b|"
    r"\bjournal\s+homepage\b|\bpaper\b|\bcommunication\b|\breview\s+article\b|\breceived\b|"
    r"\baccepted\b|\bpublished\b|\bdoi\s*:|www\.|copyright|creative\s+commons|"
    r"©|the\s+author\(s\)|downloaded\s+on)",
    re.IGNORECASE,
)

ENABLE_VECTOR_FIGURE_DETECTION = False
MAX_VECTOR_DRAWINGS_PER_PAGE = 500


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def analyze_pdf(pdf_path: str | Path, output_dir: str | Path) -> dict[str, Any]:
    """Analyze a PDF with PyMuPDF and write OmniLit extraction artifacts.

    Figure extraction deliberately uses a caption-anchored pipeline instead of
    grabbing arbitrary nearby text.  It fixes the RSC Advances cases where the
    previous logic selected footer/copyright text or a following table caption
    as the figure legend.
    """

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
            table_rects = [_rect_from_bbox(item.get("bbox") or []) for item in tables]
            elements.extend(extract_figures_pymupdf_enhanced(page, table_rects, page_index, page_size, target))
            elements.extend(extract_formula_candidates_pymupdf(page, text_blocks, page_index, page_size, target))

    completed_elements = _sort_elements(_dedupe_elements(_complete_element_schema(elements)))
    _rewrite_completed_table_jsons(completed_elements)
    markdown_path = _write_parsed_markdown(target, source, pages, completed_elements)
    index = {
        "version": 3,
        "sourcePath": str(source),
        "sourceSha256": sha256_file(source),
        "analyzedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "engine": "pymupdf",
        "engineChain": ["pymupdf"],
        "pageCount": len(pages),
        "pages": pages,
        "elements": completed_elements,
        "markdownPath": str(markdown_path),
        "rawOutputs": {"pymupdf": str(target), "paddleocr_vl": "", "mineru": ""},
        "qualitySummary": quality_summary(completed_elements),
        "debugFiles": {"mineruLayoutPdf": "", "fusionReportJson": "", "qualityReportJson": ""},
    }
    report_path = write_quality_report(target, index)
    index["debugFiles"]["qualityReportJson"] = str(report_path)
    index_path = target / "extraction_index.json"
    with index_path.open("w", encoding="utf-8") as handle:
        json.dump(index, handle, ensure_ascii=False, indent=2)
    return index


def _rewrite_completed_table_jsons(elements: list[dict[str, Any]]) -> None:
    for element in elements or []:
        if str(element.get("type") or "") != "table":
            continue
        json_path = str(element.get("jsonPath") or "").strip()
        if not json_path:
            continue
        try:
            _write_table_json(Path(json_path), element)
        except Exception:
            continue


def _write_parsed_markdown(output_dir: Path, source: Path, pages: list[dict[str, Any]], elements: list[dict[str, Any]]) -> Path:
    markdown_path = output_dir / "parsed.md"
    parts: list[str] = [f"# {_markdown_escape_heading(source.stem)}", ""]
    elements_by_page: dict[int, list[dict[str, Any]]] = {}
    for element in elements or []:
        elements_by_page.setdefault(int(element.get("page") or 0), []).append(element)

    for page in pages or []:
        page_index = int(page.get("page") or 0)
        parts.append(f"## Page {page_index + 1}")
        parts.append("")
        page_entries: list[dict[str, Any]] = []
        page_elements = _sort_elements(elements_by_page.get(page_index, []))
        occupied = []
        for element in page_elements:
            occupied.append(element.get("bbox") or [])
            if element.get("captionBBox"):
                occupied.append(element.get("captionBBox") or [])
            page_entries.append({"kind": "element", "bbox": element.get("bbox") or [], "element": element})
        for block in page.get("textBlocks") or []:
            bbox = _bbox_from_any(block.get("bbox"))
            text = str(block.get("text") or "").strip()
            if not text or len(bbox) < 4 or _text_block_overlaps_artifact(bbox, occupied):
                continue
            page_entries.append({"kind": "text", "bbox": bbox, "text": text})
        page_entries.sort(key=lambda item: (float((item.get("bbox") or [0, 0, 0, 0])[1]), float((item.get("bbox") or [0, 0, 0, 0])[0])))
        for entry in page_entries:
            if entry["kind"] == "text":
                parts.extend([_markdown_clean_text(str(entry.get("text") or "")), ""])
            else:
                parts.extend(_markdown_for_element(entry.get("element") or {}, output_dir))
                parts.append("")
    markdown_path.write_text("\n".join(parts).rstrip() + "\n", encoding="utf-8")
    return markdown_path


def _markdown_for_element(element: dict[str, Any], output_dir: Path) -> list[str]:
    kind = str(element.get("type") or "")
    if kind == "table":
        return _markdown_for_table(element)
    if kind == "formula":
        return _markdown_for_formula(element)
    if kind in {"figure", "chart"}:
        return _markdown_for_figure(element, output_dir)
    text = str(element.get("text") or element.get("caption") or "").strip()
    return [_markdown_clean_text(text)] if text else []


def _markdown_for_table(element: dict[str, Any]) -> list[str]:
    rows = [[str(cell or "") for cell in row] for row in element.get("table") or []]
    parts: list[str] = []
    caption = str(element.get("caption") or "").strip()
    if caption:
        parts.append(f"**{_markdown_clean_text(caption)}**")
        parts.append("")
    if rows:
        widths = [max((len(row[column]) if column < len(row) else 0 for row in rows), default=0) for column in range(max(len(row) for row in rows))]
        header = rows[0]
        parts.append(_markdown_table_row(header, widths))
        parts.append("| " + " | ".join("-" * max(3, width) for width in widths) + " |")
        for row in rows[1:]:
            parts.append(_markdown_table_row(row, widths))
    elif element.get("text"):
        parts.append(_markdown_clean_text(str(element.get("text") or "")))
    return parts


def _markdown_for_formula(element: dict[str, Any]) -> list[str]:
    latex = str(element.get("latex") or element.get("text") or "").strip()
    number = str((element.get("metadata") or {}).get("formulaNumber") or "").strip()
    if number and latex:
        latex = f"{latex} \\tag{{{number}}}"
    return ["$$", latex, "$$"] if latex else []


def _markdown_for_figure(element: dict[str, Any], output_dir: Path) -> list[str]:
    caption = str(element.get("caption") or element.get("text") or "").strip()
    png_path = str(element.get("pngPath") or "").strip()
    if png_path:
        try:
            image_ref = Path(png_path).resolve().relative_to(output_dir.resolve()).as_posix()
        except Exception:
            image_ref = png_path
        alt = _markdown_clean_text(caption or str(element.get("label") or "Figure"))
        return [f"![{alt}]({image_ref})", "", _markdown_clean_text(caption)] if caption else [f"![{alt}]({image_ref})"]
    return [_markdown_clean_text(caption)] if caption else []


def _markdown_table_row(row: list[str], widths: list[int]) -> str:
    cells = []
    for index, width in enumerate(widths):
        value = row[index] if index < len(row) else ""
        cells.append(_markdown_escape_cell(value).ljust(width))
    return "| " + " | ".join(cells) + " |"


def _markdown_escape_cell(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("|", "\\|")).strip()


def _markdown_clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\n", " ")).strip()


def _markdown_escape_heading(value: str) -> str:
    return _markdown_clean_text(value).replace("#", "").strip() or "Parsed PDF"


def _text_block_overlaps_artifact(bbox: list[float], artifact_bboxes: list[list[float]]) -> bool:
    for artifact_bbox in artifact_bboxes or []:
        artifact = _bbox_from_any(artifact_bbox)
        if len(artifact) < 4:
            continue
        if _bbox_intersection_area(bbox, artifact) <= 0:
            continue
        if _overlap_ratio(_rect_from_bbox(bbox), _rect_from_bbox(artifact)) >= 0.55:
            return True
    return False


# ---------------------------------------------------------------------------
# Text blocks
# ---------------------------------------------------------------------------


def _extract_text_blocks(page: Any) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for line in _text_lines(page):
        text = str(line.get("text") or "").strip()
        bbox = line.get("bbox") or []
        if not text or len(bbox) < 4:
            continue
        blocks.append({"bbox": [float(value) for value in bbox[:4]], "text": text, "blockNo": len(blocks)})
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


def _text_lines(page: Any) -> list[dict[str, Any]]:
    lines: list[dict[str, Any]] = []
    try:
        raw = page.get_text("dict") or {}
    except Exception:
        return lines
    for block_index, block in enumerate(raw.get("blocks", []) or []):
        if not isinstance(block, dict) or block.get("type") != 0:
            continue
        for line_index, line in enumerate(block.get("lines", []) or []):
            if not isinstance(line, dict):
                continue
            spans = line.get("spans", []) or []
            parts: list[str] = []
            sizes: list[float] = []
            for span in spans:
                if not isinstance(span, dict):
                    continue
                parts.append(str(span.get("text") or ""))
                try:
                    sizes.append(float(span.get("size") or 0))
                except Exception:
                    pass
            text = re.sub(r"\s+", " ", "".join(parts)).strip()
            bbox = _bbox_from_any(line.get("bbox"))
            if text and len(bbox) >= 4:
                lines.append(
                    {
                        "text": text,
                        "bbox": bbox,
                        "blockIndex": block_index,
                        "lineIndex": line_index,
                        "fontSize": sum(sizes) / len(sizes) if sizes else 0.0,
                    }
                )
    return lines


def _page_text_blocks_with_lines(page: Any) -> list[dict[str, Any]]:
    """Return line-level text blocks with same-baseline fragments joined.

    PyMuPDF may split a caption into separate blocks (for example ``Fig. 2``
    and the following legend text).  Joining only same-baseline fragments lets
    the caption matcher see the real legend while still preventing paragraph,
    footer, and table-caption leakage.
    """

    return _merge_same_baseline_text_blocks(_text_lines(page))


def _merge_same_baseline_text_blocks(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not lines:
        return []
    ordered = sorted(lines, key=lambda item: (float((item.get("bbox") or [0, 0, 0, 0])[1]), float((item.get("bbox") or [0, 0, 0, 0])[0])))
    rows: list[list[dict[str, Any]]] = []
    for line in ordered:
        bbox = line.get("bbox") or []
        if len(bbox) < 4:
            continue
        placed = False
        cy = (float(bbox[1]) + float(bbox[3])) / 2.0
        height = max(1.0, float(bbox[3]) - float(bbox[1]))
        for row in rows:
            rb = row[0].get("bbox") or []
            rcy = (float(rb[1]) + float(rb[3])) / 2.0
            rheight = max(1.0, float(rb[3]) - float(rb[1]))
            if abs(cy - rcy) <= max(2.6, min(height, rheight) * 0.45):
                row.append(line)
                placed = True
                break
        if not placed:
            rows.append([line])

    merged: list[dict[str, Any]] = []
    for row in rows:
        row = sorted(row, key=lambda item: float((item.get("bbox") or [0, 0, 0, 0])[0]))
        current: list[dict[str, Any]] = []
        last_x1: float | None = None
        for line in row:
            bbox = line.get("bbox") or []
            if last_x1 is None or float(bbox[0]) - last_x1 <= max(22.0, _median_font_size(row) * 3.2):
                current.append(line)
            else:
                merged.append(_merge_text_line_group(current))
                current = [line]
            last_x1 = float(bbox[2])
        if current:
            merged.append(_merge_text_line_group(current))
    return sorted(merged, key=lambda item: (float((item.get("bbox") or [0, 0, 0, 0])[1]), float((item.get("bbox") or [0, 0, 0, 0])[0])))


def _median_font_size(lines: list[dict[str, Any]]) -> float:
    sizes = sorted(float(line.get("fontSize") or 0.0) for line in lines if float(line.get("fontSize") or 0.0) > 0)
    if not sizes:
        return 7.0
    mid = len(sizes) // 2
    return sizes[mid] if len(sizes) % 2 else (sizes[mid - 1] + sizes[mid]) / 2.0


def _merge_text_line_group(group: list[dict[str, Any]]) -> dict[str, Any]:
    text = re.sub(r"\s+", " ", " ".join(str(item.get("text") or "").strip() for item in group)).strip()
    bbox = _union_nonempty_bboxes([item.get("bbox") or [] for item in group])
    return {
        "text": text,
        "bbox": bbox,
        "lines": group,
        "fontSize": _median_font_size(group),
        "blockNo": min((int(item.get("blockIndex") or 0) for item in group), default=0),
    }


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------


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
    strategies: list[tuple[dict[str, Any], dict[str, Any], list[float]]] = [
        ({}, {}, []),
        ({"vertical_strategy": "lines", "horizontal_strategy": "lines"}, {}, []),
        ({"vertical_strategy": "lines", "horizontal_strategy": "lines", "snap_tolerance": 3, "join_tolerance": 3, "intersection_tolerance": 3}, {}, []),
    ]
    text_strategy = {"vertical_strategy": "text", "horizontal_strategy": "text", "snap_tolerance": 4, "join_tolerance": 4, "intersection_tolerance": 4}
    for caption_info, clip_bbox in _caption_table_clips(page, table_captions, page_size, text_blocks):
        strategies.append((dict(text_strategy), caption_info, clip_bbox))
    seen_strategy: set[tuple[Any, ...]] = set()
    table_index = 0
    for params, caption_hint, clip_bbox in strategies:
        key = (tuple(sorted(params.items())), tuple(round(value, 2) for value in clip_bbox))
        if key in seen_strategy:
            continue
        seen_strategy.add(key)
        try:
            result = finder(clip=_rect_from_bbox(clip_bbox), **params) if clip_bbox else finder(**params)
        except TypeError:
            continue
        except Exception:
            continue
        for table in getattr(result, "tables", []) or []:
            bbox = _bbox_from_any(getattr(table, "bbox", None))
            if len(bbox) < 4:
                continue
            raw_rows = _safe_table_extract(table)
            rows, normalization = _normalize_table_rows(raw_rows)
            rows, text_repairs = _repair_table_rows_from_text_blocks(rows, bbox, text_blocks, page_size)
            if text_repairs:
                normalization.extend(text_repairs)
            if not rows:
                continue
            caption_info = caption_hint or _table_caption_for_bbox(bbox, text_blocks, page_size)
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
                    "label": _table_label_from_caption(caption_info.get("text", "") if caption_info else "") or f"Table {table_index}",
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
                        "tableEvidenceScore": round(_table_evidence_score(rows, bbox, page_size, bool(caption_info), params), 3),
                        "rawShape": [len(raw_rows), max((len(row) for row in raw_rows), default=0)],
                        "normalization": normalization,
                    },
                    "raw": {"rows": raw_rows} if normalization else {},
                }
            )

    deduped = dedupe_tables_by_iou(tables)
    used_element_ids: set[str] = set()
    for next_index, table in enumerate(deduped, start=1):
        rows = table.get("table") or []
        label = _safe_file_label(str(table.get("label") or f"table_{next_index}")).lower()
        element_id = f"p{page_index + 1}_table_{next_index}"
        if label and label != f"table_{next_index}":
            element_id = f"p{page_index + 1}_{label}"
        if element_id in used_element_ids:
            base_id = element_id
            suffix = 2
            while f"{base_id}_{suffix}" in used_element_ids:
                suffix += 1
            element_id = f"{base_id}_{suffix}"
        used_element_ids.add(element_id)
        csv_path = output_dir / "tables" / f"{element_id}.csv"
        json_path = output_dir / "tables" / f"{element_id}.json"
        png_path = output_dir / "clips" / f"{element_id}.png"
        table.update({"id": element_id, "csvPath": str(csv_path), "jsonPath": str(json_path), "pngPath": str(png_path)})
        _write_table_csv(csv_path, rows)
        crop_element_png(page, table.get("bbox") or [], png_path, zoom=2.5, padding=6)
        _write_table_json(json_path, table)
    return deduped


def _extract_tables(page: Any, page_index: int, page_size: list[float], output_dir: Path) -> list[dict[str, Any]]:
    return extract_tables_pymupdf_multi_strategy(page, page_index, page_size, output_dir, _extract_text_blocks(page))


def dedupe_tables_by_iou(tables: list[dict[str, Any]], iou_threshold: float = 0.72) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for table in sorted(tables, key=_table_quality_key, reverse=True):
        if any(
            int(existing.get("page") or 0) == int(table.get("page") or 0)
            and (
                _bbox_iou(existing.get("bbox") or [], table.get("bbox") or []) >= iou_threshold
                or _bbox_overlap_ratio(existing.get("bbox") or [], table.get("bbox") or []) >= 0.92
            )
            for existing in result
        ):
            continue
        result.append(table)
    return _sort_elements(result)


def _safe_table_extract(table: Any) -> list[list[str]]:
    try:
        rows = table.extract()
    except Exception:
        return []
    cleaned: list[list[str]] = []
    for row in rows or []:
        if row is None:
            continue
        values = [re.sub(r"\s+", " ", str(cell or "")).strip() for cell in row]
        if any(values):
            cleaned.append(values)
    if not cleaned:
        return []
    return cleaned


def _normalize_table_rows(rows: list[list[str]]) -> tuple[list[list[str]], list[str]]:
    cleaned = [[re.sub(r"\s+", " ", str(cell or "")).strip() for cell in row] for row in rows or []]
    cleaned = [row for row in cleaned if any(row)]
    if not cleaned:
        return [], []
    width = max(len(row) for row in cleaned)
    cleaned = [row + [""] * (width - len(row)) for row in cleaned]
    actions: list[str] = []

    empty_columns = [column for column in range(width) if not any(row[column] for row in cleaned)]
    for column in reversed(empty_columns):
        for row in cleaned:
            del row[column]
    if empty_columns:
        actions.append("drop_empty_columns")

    column = 1
    while cleaned and column < len(cleaned[0]):
        if _looks_like_split_text_column(cleaned, column):
            for row in cleaned:
                row[column - 1] = " ".join(part for part in (row[column - 1], row[column]) if part).strip()
                del row[column]
            actions.append(f"merge_split_column_{column}")
            continue
        column += 1
    if len(cleaned) >= 3 and _row_numeric_ratio(cleaned[0]) == 0 and _row_numeric_ratio(cleaned[1]) == 0 and _row_numeric_ratio(cleaned[2]) >= 0.5:
        cleaned[0] = [" ".join(part for part in cells if part).strip() for cells in zip(cleaned[0], cleaned[1])]
        del cleaned[1]
        actions.append("merge_wrapped_header")
    return cleaned, actions


def _repair_table_rows_from_text_blocks(
    rows: list[list[str]],
    bbox: list[float],
    text_blocks: list[dict[str, Any]],
    page_size: list[float],
) -> tuple[list[list[str]], list[str]]:
    if not rows or len(bbox or []) < 4 or not text_blocks:
        return rows, []
    current_width = max((len(row) for row in rows), default=0)
    if current_width < 2:
        return rows, []
    reconstructed = _table_rows_from_positioned_text(bbox, text_blocks, page_size, current_width)
    if not reconstructed:
        return rows, []
    if not _positioned_table_rows_better(rows, reconstructed):
        return rows, []
    return reconstructed, ["reconstruct_from_positioned_text"]


def _table_rows_from_positioned_text(
    bbox: list[float],
    text_blocks: list[dict[str, Any]],
    page_size: list[float],
    min_columns: int,
) -> list[list[str]]:
    page_width, page_height = _page_dimensions(page_size)
    if page_width <= 0 or page_height <= 0:
        return []
    x0 = max(0.0, float(bbox[0]) - 8.0)
    x1 = min(page_width, float(bbox[2]) + 8.0)
    y0 = max(0.0, float(bbox[1]) - 28.0)
    y1 = min(page_height, float(bbox[3]) + 6.0)
    cells: list[dict[str, Any]] = []
    for block in text_blocks or []:
        block_bbox = _bbox_from_any(block.get("bbox"))
        text = re.sub(r"\s+", " ", str(block.get("text") or "")).strip()
        if len(block_bbox) < 4 or not text or TABLE_CAPTION_PATTERN.search(text):
            continue
        cx = (block_bbox[0] + block_bbox[2]) / 2.0
        cy = (block_bbox[1] + block_bbox[3]) / 2.0
        if cx < x0 or cx > x1 or cy < y0 or cy > y1:
            continue
        cells.append({"text": text, "bbox": block_bbox, "cx": cx, "cy": cy})
    if len(cells) < min_columns * 2:
        return []

    line_groups: list[list[dict[str, Any]]] = []
    for cell in sorted(cells, key=lambda item: (float(item["cy"]), float(item["cx"]))):
        placed = False
        for group in line_groups:
            group_cy = sum(float(item["cy"]) for item in group) / len(group)
            if abs(float(cell["cy"]) - group_cy) <= 4.8:
                group.append(cell)
                placed = True
                break
        if not placed:
            line_groups.append([cell])

    line_groups = [sorted(group, key=lambda item: float(item["cx"])) for group in line_groups if len(group) >= 2]
    if len(line_groups) < 2:
        return []
    target_columns = max(min_columns, max(len(group) for group in line_groups))
    if target_columns < 2:
        return []
    full_rows = [group for group in line_groups if len(group) == target_columns]
    if not full_rows:
        return []
    column_centers: list[float] = []
    for column in range(target_columns):
        values = sorted(float(group[column]["cx"]) for group in full_rows)
        mid = len(values) // 2
        column_centers.append(values[mid] if len(values) % 2 else (values[mid - 1] + values[mid]) / 2.0)

    max_distance = max(24.0, (x1 - x0) / max(1, target_columns) * 0.52)
    rebuilt: list[list[str]] = []
    for group in line_groups:
        row = [""] * target_columns
        for cell in group:
            distances = [abs(float(cell["cx"]) - center) for center in column_centers]
            column = min(range(len(distances)), key=distances.__getitem__)
            if distances[column] > max_distance:
                continue
            row[column] = " ".join(part for part in (row[column], str(cell["text"])) if part).strip()
        if any(row):
            rebuilt.append(row)
    return rebuilt


def _positioned_table_rows_better(current: list[list[str]], rebuilt: list[list[str]]) -> bool:
    if not rebuilt:
        return False
    current_width = max((len(row) for row in current), default=0)
    rebuilt_width = max((len(row) for row in rebuilt), default=0)
    if rebuilt_width < current_width or len(rebuilt) < len(current):
        return False
    current_first = current[0] if current else []
    rebuilt_first = rebuilt[0]
    current_first_numeric = _row_numeric_ratio(current_first)
    rebuilt_first_numeric = _row_numeric_ratio(rebuilt_first)
    current_first_text = " ".join(str(cell or "") for cell in current_first).strip()
    rebuilt_first_text = " ".join(str(cell or "") for cell in rebuilt_first).strip()
    if rebuilt_first_numeric <= 0.25 and current_first_numeric > 0.25:
        return True
    if len(rebuilt) > len(current) and rebuilt_first_numeric <= 0.25:
        return True
    if len(rebuilt_first_text) > len(current_first_text) + 2 and rebuilt_first_numeric <= current_first_numeric:
        return True
    return False


def _looks_like_split_text_column(rows: list[list[str]], column: int) -> bool:
    if not rows or column <= 0 or column >= len(rows[0]):
        return False
    header = rows[0]
    split_word = False
    if header[column] or not header[column - 1]:
        split_word = bool(re.search(r"[A-Za-z]$", header[column - 1]) and re.match(r"^[a-z]{3,}(?:\s|$)", header[column]))
        if not split_word:
            return False
    values = [row[column] for row in rows[1:] if row[column]]
    if len(values) < max(2, int((len(rows) - 1) * 0.4)):
        return False
    numeric = sum(1 for value in values if re.fullmatch(r"[-+−]?\d+(?:[.,]\d+)?%?", value))
    alphabetic = sum(1 for value in values if re.search(r"[A-Za-z]{2,}", value))
    paired = sum(1 for row in rows[1:] if row[column - 1] and row[column])
    looks_textual = numeric / max(1, len(values)) <= 0.2 and alphabetic / max(1, len(values)) >= 0.5
    return (split_word or looks_textual) and paired >= max(2, int((len(rows) - 1) * 0.4))


def _row_numeric_ratio(row: list[str]) -> float:
    values = [value for value in row if value]
    if not values:
        return 0.0
    numeric = sum(1 for value in values if re.search(r"[-+−]?\d", value))
    return numeric / len(values)


def _valid_table_candidate(
    rows: list[list[str]],
    bbox: list[float],
    page_size: list[float],
    caption_info: dict[str, Any] | None,
    params: dict[str, Any],
) -> bool:
    if len(bbox or []) < 4:
        return False
    page_width, page_height = _page_dimensions(page_size)
    width = _bbox_width(bbox)
    height = _bbox_height(bbox)
    if page_width <= 0 or page_height <= 0 or width < 45 or height < 18:
        return False
    if width * height < 1200:
        return False
    row_count = len(rows)
    col_count = max((len(row) for row in rows), default=0)
    nonempty = sum(1 for row in rows for cell in row if str(cell).strip())
    if row_count < 2 or col_count < 2 or nonempty < 4:
        return False
    score = _table_structural_score(rows)
    if caption_info:
        return score >= 0.15
    if _is_text_table_strategy(params):
        if not caption_info:
            return False
        area_ratio = width * height / max(1.0, page_width * page_height)
        return score >= 0.35 and row_count >= 3 and nonempty >= 8 and area_ratio <= 0.58
    return score >= 0.28


def _table_evidence_score(
    rows: list[list[str]], bbox: list[float], page_size: list[float], captioned: bool, params: dict[str, Any]
) -> float:
    score = _table_structural_score(rows) * 0.55
    if captioned:
        score += 0.3
    if not _is_text_table_strategy(params):
        score += 0.12
    page_width, page_height = _page_dimensions(page_size)
    if page_width > 0 and page_height > 0:
        area_ratio = _bbox_area(bbox) / (page_width * page_height)
        if area_ratio > 0.58:
            score -= 0.35
    return max(0.0, min(1.0, score))


def _table_structural_score(rows: list[list[str]]) -> float:
    if not rows:
        return 0.0
    widths = [len(row) for row in rows if row]
    if not widths:
        return 0.0
    dominant = max(set(widths), key=widths.count)
    same_width = widths.count(dominant) / max(1, len(widths))
    nonempty_counts = [sum(1 for cell in row if str(cell).strip()) for row in rows]
    filled_ratio = sum(nonempty_counts) / max(1, len(rows) * dominant)
    numericish = sum(1 for row in rows for cell in row if re.search(r"[-+]?\d", str(cell)))
    numeric_bonus = min(0.25, numericish / max(1, len(rows) * dominant) * 0.5)
    return max(0.0, min(1.0, same_width * 0.45 + filled_ratio * 0.45 + numeric_bonus))


def _table_quality_key(table: dict[str, Any]) -> tuple[float, float, float]:
    metadata = table.get("metadata") or {}
    rows = float(metadata.get("rows") or len(table.get("table") or []))
    cols = float(metadata.get("columns") or max((len(row) for row in table.get("table") or []), default=0))
    score = float(metadata.get("structuralScore") or 0.0)
    area = _bbox_area(table.get("bbox") or [])
    caption_bonus = 0.2 if table.get("caption") else 0.0
    return score + caption_bonus, rows * cols, area


def _is_text_table_strategy(params: dict[str, Any] | None) -> bool:
    params = params or {}
    return params.get("vertical_strategy") == "text" or params.get("horizontal_strategy") == "text"


def _table_text(rows: list[list[str]]) -> str:
    return "\n".join("\t".join(str(cell or "") for cell in row) for row in rows)


def _write_table_csv(path: Path, rows: list[list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerows(rows or [])


def _write_table_json(path: Path, table: dict[str, Any] | list[list[str]]) -> None:
    if isinstance(table, dict):
        rows = [[str(cell or "") for cell in row] for row in table.get("table") or []]
        metadata = dict(table.get("metadata") or {})
        payload = {
            "version": 2,
            "id": str(table.get("id") or ""),
            "page": int(table.get("page") or 0),
            "bbox": _bbox_from_any(table.get("bbox")),
            "pageSize": list(table.get("pageSize") or []),
            "caption": str(table.get("caption") or ""),
            "captionBBox": _bbox_from_any(table.get("captionBBox")),
            "rows": rows,
            "shape": {"rows": len(rows), "columns": max((len(row) for row in rows), default=0)},
            "cells": _table_cells(rows),
            "headerRows": _header_row_indexes(rows),
            "unitRows": _unit_row_indexes(rows),
            "footnoteRows": _footnote_row_indexes(rows),
            "spansPreserved": False,
            "metadata": metadata,
            "quality": {
                "confidence": float(table.get("confidence") or 0.0),
                "needsReview": bool(table.get("needsReview")),
                "qualityFlags": [str(flag) for flag in table.get("qualityFlags") or [] if str(flag or "").strip()],
            },
            "source": {
                "engine": str(table.get("engine") or "pymupdf"),
                "sourceEngines": [str(item) for item in table.get("sourceEngines") or [] if str(item or "").strip()],
                "sourceElementIds": [str(item) for item in table.get("sourceElementIds") or [] if str(item or "").strip()],
            },
            "artifacts": {
                "csvPath": str(table.get("csvPath") or ""),
                "jsonPath": str(table.get("jsonPath") or path),
                "pngPath": str(table.get("pngPath") or ""),
            },
        }
    else:
        rows = [[str(cell or "") for cell in row] for row in table or []]
        payload = {"version": 2, "rows": rows, "shape": {"rows": len(rows), "columns": max((len(row) for row in rows), default=0)}, "cells": _table_cells(rows)}
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def _table_cells(rows: list[list[str]]) -> list[dict[str, Any]]:
    cells: list[dict[str, Any]] = []
    for row_index, row in enumerate(rows or []):
        for column_index, value in enumerate(row or []):
            cells.append(
                {
                    "row": row_index,
                    "column": column_index,
                    "text": str(value or ""),
                    "rowspan": 1,
                    "colspan": 1,
                    "isHeader": row_index in _header_row_indexes(rows),
                }
            )
    return cells


def _header_row_indexes(rows: list[list[str]]) -> list[int]:
    if not rows:
        return []
    if len(rows) == 1:
        return [0]
    first = rows[0]
    second = rows[1] if len(rows) > 1 else []
    first_numeric = _row_numeric_ratio(first)
    second_numeric = _row_numeric_ratio(second)
    if first_numeric <= 0.25 and second_numeric > first_numeric:
        return [0]
    return [0] if any(str(cell or "").strip() for cell in first) else []


def _unit_row_indexes(rows: list[list[str]]) -> list[int]:
    units = re.compile(
        r"^(?:%|(?:mAh|Ah|Wh|mg|g|kg|mm|cm|m|mol|V|A|K|Pa|Hz|s|min|h|°C)"
        r"(?:(?:\s+(?:/|-|·|\*)?\s*[A-Za-z0-9%°-]+)|(?:(?:/|-|·|\*)\s*[A-Za-z0-9%°-]+))*)$",
        re.IGNORECASE,
    )
    result: list[int] = []
    for index, row in enumerate(rows or []):
        values = [str(cell or "").strip() for cell in row if str(cell or "").strip()]
        if values and sum(1 for value in values if units.search(value)) / len(values) >= 0.5:
            result.append(index)
    return result


def _footnote_row_indexes(rows: list[list[str]]) -> list[int]:
    result: list[int] = []
    pattern = re.compile(r"^(?:note|notes|注|备注|[*†‡§]|\([a-z]\))", re.IGNORECASE)
    for index, row in enumerate(rows or []):
        values = [str(cell or "").strip() for cell in row if str(cell or "").strip()]
        if len(values) == 1 and pattern.search(values[0]):
            result.append(index)
    return result


def _table_caption_blocks(text_blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [block for block in text_blocks or [] if TABLE_CAPTION_PATTERN.search(str(block.get("text") or "").strip())]


def _caption_table_clips(
    page: Any,
    captions: list[dict[str, Any]],
    page_size: list[float],
    text_blocks: list[dict[str, Any]],
) -> list[tuple[dict[str, Any], list[float]]]:
    page_width, page_height = _page_dimensions(page_size)
    if page_width <= 0 or page_height <= 0:
        return []
    rules = _horizontal_table_rules(page, page_size)
    result: list[tuple[dict[str, Any], list[float]]] = []
    for caption in captions:
        caption_bbox = _bbox_from_any(caption.get("bbox"))
        caption_text = _clean_caption_text(str(caption.get("text") or ""))
        if len(caption_bbox) < 4 or not caption_text:
            continue
        col_x0, col_x1 = _column_bounds_for_bbox(caption_bbox, page_size)
        if _bbox_width(caption_bbox) >= page_width * 0.55:
            col_x0, col_x1 = 8.0, page_width - 8.0
        nearby_rules = [
            rule
            for rule in rules
            if rule[1] >= caption_bbox[3] - 2.0
            and rule[1] <= caption_bbox[3] + page_height * 0.48
            and _horizontal_overlap_ratio(rule, [col_x0, caption_bbox[1], col_x1, caption_bbox[3]]) >= 0.35
        ]
        nearby_rules.sort(key=lambda rule: rule[1])
        top_rule = nearby_rules[0] if nearby_rules else []
        lower_rules = [rule for rule in nearby_rules[1:] if rule[1] - (top_rule[3] if top_rule else caption_bbox[3]) >= 18.0]
        bottom_rule = lower_rules[-1] if lower_rules else []
        if bottom_rule and _has_table_text_just_below(bottom_rule, col_x0, col_x1, text_blocks):
            bottom_rule = []
        top = float(top_rule[3] + 0.5) if top_rule else float(caption_bbox[3] + 2.0)
        bottom = float(bottom_rule[3] + 1.0) if bottom_rule else _infer_caption_table_bottom(top, col_x0, col_x1, text_blocks, page_height)
        if top_rule:
            col_x0 = max(0.0, top_rule[0] - 2.0)
            col_x1 = min(page_width, top_rule[2] + 2.0)
        if bottom <= top + 18.0:
            continue
        caption_info = {"text": caption_text[:360], "bbox": caption_bbox, "score": 0.95}
        result.append((caption_info, [col_x0, top, col_x1, min(page_height, bottom)]))
    return result


def _horizontal_table_rules(page: Any, page_size: list[float]) -> list[list[float]]:
    page_width, _page_height = _page_dimensions(page_size)
    rules: list[list[float]] = []
    try:
        drawings = page.get_drawings() or []
    except Exception:
        drawings = []
    for drawing in drawings:
        bbox = _bbox_from_any(drawing.get("rect") if isinstance(drawing, dict) else None)
        if len(bbox) < 4:
            continue
        if _bbox_width(bbox) >= max(90.0, page_width * 0.18) and _bbox_height(bbox) <= 4.0:
            rules.append(bbox)
    return sorted(rules, key=lambda bbox: (bbox[1], bbox[0]))


def _infer_caption_table_bottom(top: float, x0: float, x1: float, text_blocks: list[dict[str, Any]], page_height: float) -> float:
    lines = []
    for block in text_blocks or []:
        bbox = _bbox_from_any(block.get("bbox"))
        if len(bbox) < 4 or bbox[1] < top or bbox[1] > top + page_height * 0.42:
            continue
        if _horizontal_overlap_ratio(bbox, [x0, bbox[1], x1, bbox[3]]) >= 0.35:
            lines.append(bbox)
    lines.sort(key=lambda bbox: bbox[1])
    previous_bottom = top
    for bbox in lines:
        if bbox[1] - previous_bottom > 20.0 and previous_bottom > top + 18.0:
            return min(page_height, previous_bottom + 3.0)
        previous_bottom = max(previous_bottom, bbox[3])
    return min(page_height, max(top + 32.0, previous_bottom + 3.0))


def _has_table_text_just_below(rule: list[float], x0: float, x1: float, text_blocks: list[dict[str, Any]]) -> bool:
    for block in text_blocks or []:
        bbox = _bbox_from_any(block.get("bbox"))
        if len(bbox) < 4 or bbox[1] < rule[3] + 1.0 or bbox[1] > rule[3] + 16.0:
            continue
        if _horizontal_overlap_ratio(bbox, [x0, bbox[1], x1, bbox[3]]) >= 0.35:
            return True
    return False


def _table_caption_for_bbox(bbox: list[float], text_blocks: list[dict[str, Any]], page_size: list[float]) -> dict[str, Any]:
    if len(bbox or []) < 4:
        return {}
    max_distance = max(24.0, float(page_size[1] if len(page_size) > 1 else 0.0) * 0.08)
    candidates: list[tuple[float, dict[str, Any]]] = []
    for block in text_blocks or []:
        block_bbox = _bbox_from_any(block.get("bbox"))
        text = _clean_caption_text(str(block.get("text") or ""))
        if len(block_bbox) < 4 or not TABLE_CAPTION_PATTERN.search(text):
            continue
        if _bbox_iou(bbox, block_bbox) > 0.0 or _contains_bbox(bbox, block_bbox):
            continue
        overlap = max(0.0, min(bbox[2], block_bbox[2]) - max(bbox[0], block_bbox[0]))
        if overlap < min(_bbox_width(bbox), _bbox_width(block_bbox)) * 0.16:
            continue
        above = float(bbox[1]) - float(block_bbox[3])
        below = float(block_bbox[1]) - float(bbox[3])
        distance = above if above >= 0 else below if below >= 0 else -1.0
        if distance < 0 or distance > max_distance:
            continue
        direction_penalty = 0.0 if above >= 0 else 8.0
        candidates.append((distance + direction_penalty, {"text": text[:360], "bbox": block_bbox, "score": 0.9}))
    if not candidates:
        return {}
    candidates.sort(key=lambda item: item[0])
    return candidates[0][1]


def _table_label_from_caption(caption: str) -> str:
    m = re.search(r"^\s*(Table|表)\s*([0-9]+[A-Za-z]?)", str(caption or ""), flags=re.IGNORECASE)
    if not m:
        return ""
    prefix = "Table" if m.group(1).lower().startswith("table") else "表"
    return f"{prefix} {m.group(2)}"


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------


def extract_figures_pymupdf_enhanced(page: Any, *args: Any) -> list[dict[str, Any]]:
    """Extract figures using strict figure-caption anchoring.

    Supported call styles:
    - current: ``(page, table_rects, page_index, page_size, output_dir)``
    - legacy:  ``(page, text_blocks, table_rects, page_index, page_size, output_dir)``

    The logic intentionally refuses to use arbitrary nearby text as a legend.
    A legend must start with ``Fig.``, ``Figure`` or ``图``.  This prevents
    footer text like ``RSC Adv., 2026...`` and following ``Table 4...`` captions
    from being attached to graph images.
    """

    if len(args) == 4:
        table_rects, page_index, page_size, output_dir = args
        text_blocks = _page_text_blocks_with_lines(page)
    elif len(args) == 5:
        maybe_text_blocks, table_rects, page_index, page_size, output_dir = args
        # Preserve line/span information whenever possible.  The provided legacy
        # blocks are kept only as a fallback for very old PyMuPDF versions.
        text_blocks = _page_text_blocks_with_lines(page) or list(maybe_text_blocks or [])
    else:
        raise TypeError("extract_figures_pymupdf_enhanced expects 4 or 5 positional arguments after page")

    table_rects = list(table_rects or [])
    page_index = int(page_index)
    page_size = [float(page_size[0]), float(page_size[1])] if len(page_size or []) >= 2 else [0.0, 0.0]
    output_dir = Path(output_dir)

    visual_candidates = _collect_visual_bboxes(page, page_size)
    figure_captions = _figure_caption_candidates(text_blocks, page_size)
    figures: list[dict[str, Any]] = []
    used_caption_numbers: set[str] = set()

    # Primary path: start from real figure captions and find the closest visual
    # content above/near them.  This handles vector-only graphs and split captions.
    for caption_info in figure_captions:
        number = str(caption_info.get("number") or "").strip()
        if number and number in used_caption_numbers:
            continue
        image_bbox = _figure_image_bbox_for_caption(
            caption_info=caption_info,
            visual_candidates=visual_candidates,
            table_rects=table_rects,
            text_blocks=text_blocks,
            page_size=page_size,
        )
        if len(image_bbox) < 4 or not _reasonable_figure_bbox(image_bbox, page_size, allow_small=True):
            continue
        if _is_table_overlap(image_bbox, table_rects, threshold=0.32):
            continue
        caption_bbox = caption_info.get("bbox") or []
        display_bbox = _clip_bbox(_union_nonempty_bboxes([image_bbox, caption_bbox]), page_size)
        if len(display_bbox) < 4:
            continue
        caption_text = _clean_caption_text(str(caption_info.get("text") or ""))
        if not _has_real_figure_caption(caption_text):
            continue
        used_caption_numbers.add(number)
        figures.append(
            _build_figure_element(
                page=page,
                page_index=page_index,
                figure_index=len(figures) + 1,
                page_size=page_size,
                output_dir=output_dir,
                image_bbox=image_bbox,
                display_bbox=display_bbox,
                caption_info={**caption_info, "text": caption_text},
            )
        )

    # Secondary path: retain large caption-free images, but only when they are not
    # decorative headers/footers and do not sit beside an unrelated table caption.
    for bbox in _dedupe_bboxes(visual_candidates):
        if _is_bbox_covered_by_figures(bbox, figures):
            continue
        if not _reasonable_figure_bbox(bbox, page_size):
            continue
        if _is_table_overlap(bbox, table_rects, threshold=0.35):
            continue
        caption_info = _best_caption_for_image_bbox(bbox, figure_captions, page_size, require_real=True)
        caption_text = _clean_caption_text(str(caption_info.get("text") or "")) if caption_info else ""
        skip, _reason = _should_skip_figure_candidate(bbox, page_index, page_size, text_blocks, caption_text)
        if skip:
            continue
        if caption_info and caption_info.get("number") in used_caption_numbers:
            continue
        image_bbox = _refine_figure_image_bbox(bbox, visual_candidates, page_size)
        display_bbox = _clip_bbox(_union_nonempty_bboxes([image_bbox, caption_info.get("bbox", []) if caption_info else []]), page_size)
        if caption_info:
            used_caption_numbers.add(str(caption_info.get("number") or ""))
        figures.append(
            _build_figure_element(
                page=page,
                page_index=page_index,
                figure_index=len(figures) + 1,
                page_size=page_size,
                output_dir=output_dir,
                image_bbox=image_bbox,
                display_bbox=display_bbox,
                caption_info=caption_info or {},
            )
        )

    return _dedupe_figure_elements(figures)


def _extract_figures(
    page: Any,
    page_index: int,
    page_size: list[float],
    output_dir: Path,
    text_blocks: list[dict[str, Any]],
    table_rects: list[Any],
) -> list[dict[str, Any]]:
    return extract_figures_pymupdf_enhanced(page, text_blocks, table_rects, page_index, page_size, output_dir)


def _collect_visual_bboxes(page: Any, page_size: list[float]) -> list[list[float]]:
    candidates: list[list[float]] = []
    try:
        for block in (page.get_text("dict") or {}).get("blocks", []) or []:
            if isinstance(block, dict) and block.get("type") == 1:
                bbox = _bbox_from_any(block.get("bbox"))
                if _reasonable_visual_bbox(bbox, page_size):
                    candidates.append(_clip_bbox(bbox, page_size))
    except Exception:
        pass

    try:
        for info in page.get_image_info(hashes=True, xrefs=True) or []:
            bbox = _bbox_from_any(info.get("bbox"))
            if _reasonable_visual_bbox(bbox, page_size):
                candidates.append(_clip_bbox(bbox, page_size))
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
        if not isinstance(drawing, dict):
            continue
        bbox = _bbox_from_any(drawing.get("rect"))
        if not _reasonable_visual_bbox(bbox, page_size, allow_thin=True):
            continue
        if _is_visual_noise(bbox, page_size):
            continue
        drawing_bboxes.append(_clip_bbox(bbox, page_size))
    candidates.extend(drawing_bboxes)
    candidates.extend(_merge_nearby_bboxes(drawing_bboxes))
    return _dedupe_bboxes([box for box in candidates if len(box) >= 4], iou_threshold=0.88)


def _figure_caption_candidates(text_blocks: list[dict[str, Any]], page_size: list[float]) -> list[dict[str, Any]]:
    blocks = sorted(text_blocks or [], key=lambda item: (float((item.get("bbox") or [0, 0, 0, 0])[1]), float((item.get("bbox") or [0, 0, 0, 0])[0])))
    captions: list[dict[str, Any]] = []
    used_indices: set[int] = set()
    for idx, block in enumerate(blocks):
        if idx in used_indices:
            continue
        bbox = _bbox_from_any(block.get("bbox"))
        text = _clean_caption_text(str(block.get("text") or ""))
        if len(bbox) < 4 or not text:
            continue
        match = FIGURE_CAPTION_PATTERN.search(text)
        if not match:
            continue
        if DECORATIVE_FIGURE_TEXT_PATTERN.search(text) and len(text) < 32:
            continue
        if TABLE_CAPTION_PATTERN.search(text):
            continue
        number = match.group(2)
        caption_text = text
        caption_bbox = bbox
        used_indices.add(idx)
        # Attach only short continuation lines in the same column and just below
        # the figure-caption start.  Stop before table captions, page footers or
        # normal paragraph body.
        continuation_count = 0
        for next_idx in range(idx + 1, len(blocks)):
            candidate = blocks[next_idx]
            candidate_bbox = _bbox_from_any(candidate.get("bbox"))
            candidate_text = _clean_caption_text(str(candidate.get("text") or ""))
            if len(candidate_bbox) < 4 or not candidate_text:
                continue
            if candidate_bbox[1] < caption_bbox[1] - 2:
                continue
            if FIGURE_CAPTION_PATTERN.search(candidate_text) or TABLE_CAPTION_PATTERN.search(candidate_text):
                break
            if not _is_caption_continuation_line(caption_bbox, caption_text, candidate_bbox, candidate_text, page_size):
                # Once we have moved clearly below the caption, stop scanning.
                if candidate_bbox[1] - caption_bbox[3] > max(18.0, _bbox_height(caption_bbox) * 1.8):
                    break
                continue
            caption_text = _clean_caption_text(f"{caption_text} {candidate_text}")
            caption_bbox = _union_nonempty_bboxes([caption_bbox, candidate_bbox])
            used_indices.add(next_idx)
            continuation_count += 1
            if continuation_count >= 4 or len(caption_text) >= 520:
                break
        captions.append(
            {
                "text": caption_text[:620],
                "bbox": caption_bbox,
                "number": number,
                "score": 0.98,
                "source": "caption_regex",
            }
        )
    return _dedupe_caption_candidates(captions)


def _is_caption_continuation_line(
    caption_bbox: list[float],
    caption_text: str,
    line_bbox: list[float],
    line_text: str,
    page_size: list[float],
) -> bool:
    if len(caption_bbox or []) < 4 or len(line_bbox or []) < 4:
        return False
    if DECORATIVE_FIGURE_TEXT_PATTERN.search(line_text):
        return False
    if _is_page_header_or_footer_bbox(line_bbox, page_size):
        return False
    gap = float(line_bbox[1]) - float(caption_bbox[3])
    if gap < -4.0 or gap > max(18.0, _bbox_height(caption_bbox) * 1.9):
        return False
    if not _same_column(caption_bbox, line_bbox, page_size):
        return False
    overlap = _horizontal_overlap_ratio(caption_bbox, line_bbox)
    # Captions may be narrower than continuation lines.  Permit a similar left
    # edge when overlap is modest.
    left_aligned = abs(float(line_bbox[0]) - float(caption_bbox[0])) <= 18.0
    short_caption_line = len(line_text) <= 220 and not re.match(r"^\s*[A-Z][a-z]+\s+[a-z]+\s+", line_text)
    return (overlap >= 0.18 or left_aligned) and short_caption_line


def _dedupe_caption_candidates(captions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for caption in sorted(captions, key=lambda item: (-len(str(item.get("text") or "")), float((item.get("bbox") or [0, 0, 0, 0])[1]))):
        bbox = caption.get("bbox") or []
        number = str(caption.get("number") or "")
        duplicate = False
        for existing in result:
            if number and number == str(existing.get("number") or "") and _bbox_iou(bbox, existing.get("bbox") or []) > 0.08:
                duplicate = True
                break
            if _bbox_iou(bbox, existing.get("bbox") or []) > 0.65:
                duplicate = True
                break
        if not duplicate:
            result.append(caption)
    return sorted(result, key=lambda item: (float((item.get("bbox") or [0, 0, 0, 0])[1]), float((item.get("bbox") or [0, 0, 0, 0])[0])))


def _figure_image_bbox_for_caption(
    caption_info: dict[str, Any],
    visual_candidates: list[list[float]],
    table_rects: list[Any],
    text_blocks: list[dict[str, Any]],
    page_size: list[float],
) -> list[float]:
    caption_bbox = _bbox_from_any(caption_info.get("bbox"))
    if len(caption_bbox) < 4:
        return []
    page_width, page_height = _page_dimensions(page_size)
    if page_width <= 0 or page_height <= 0:
        return []

    scored: list[tuple[float, list[float]]] = []
    col_x0, col_x1 = _column_bounds_for_bbox(caption_bbox, page_size)
    caption_cx = (caption_bbox[0] + caption_bbox[2]) / 2.0
    for candidate in visual_candidates or []:
        bbox = _bbox_from_any(candidate)
        if len(bbox) < 4:
            continue
        if _is_table_overlap(bbox, table_rects, threshold=0.28):
            continue
        if _bbox_inside_column_ratio(bbox, col_x0, col_x1) < 0.50 and _horizontal_overlap_ratio(caption_bbox, bbox) < 0.12:
            continue
        above_distance = caption_bbox[1] - bbox[3]
        below_distance = bbox[1] - caption_bbox[3]
        horizontal_overlap = _horizontal_overlap_ratio(caption_bbox, bbox)
        candidate_cx = (bbox[0] + bbox[2]) / 2.0
        center_penalty = abs(candidate_cx - caption_cx) / max(1.0, page_width) * 45.0
        width_ratio = min(_bbox_width(caption_bbox), _bbox_width(bbox)) / max(1.0, max(_bbox_width(caption_bbox), _bbox_width(bbox)))
        if -8.0 <= above_distance <= max(130.0, page_height * 0.18):
            score = above_distance + center_penalty - horizontal_overlap * 35.0 - width_ratio * 10.0
            scored.append((score, bbox))
        elif -8.0 <= below_distance <= max(70.0, page_height * 0.10):
            # Less common, but some journals place captions above images.
            score = below_distance + 36.0 + center_penalty - horizontal_overlap * 22.0
            scored.append((score, bbox))

    if scored:
        scored.sort(key=lambda item: item[0])
        seed = scored[0][1]
        refined = _refine_figure_image_bbox(seed, [box for _, box in scored] + visual_candidates, page_size)
        # Do not let the visual merge cross down into a following table caption.
        return _trim_bbox_against_unrelated_text(refined, caption_bbox, text_blocks, page_size)

    return _fallback_caption_inferred_bbox(caption_bbox, text_blocks, table_rects, page_size)


def _fallback_caption_inferred_bbox(
    caption_bbox: list[float],
    text_blocks: list[dict[str, Any]],
    table_rects: list[Any],
    page_size: list[float],
) -> list[float]:
    page_width, page_height = _page_dimensions(page_size)
    if page_width <= 0 or page_height <= 0 or len(caption_bbox or []) < 4:
        return []
    col_x0, col_x1 = _column_bounds_for_bbox(caption_bbox, page_size)
    x0 = max(col_x0, caption_bbox[0] - 14.0)
    x1 = min(col_x1, caption_bbox[2] + 14.0)
    y1 = max(0.0, caption_bbox[1] - 4.0)
    search_top = max(0.0, y1 - min(260.0, page_height * 0.34))

    blockers: list[float] = []
    for block in text_blocks or []:
        bbox = _bbox_from_any(block.get("bbox"))
        text = str(block.get("text") or "")
        if len(bbox) < 4 or bbox[3] >= y1 or bbox[1] < search_top:
            continue
        if _bbox_inside_column_ratio(bbox, col_x0, col_x1) < 0.5:
            continue
        if FIGURE_CAPTION_PATTERN.search(text):
            blockers.append(bbox[3])
            continue
        # A long text line right above the figure likely belongs to a paragraph
        # before the graph; use it as the upper boundary, but ignore tiny axis labels.
        if len(text) >= 20 and _bbox_width(bbox) >= (x1 - x0) * 0.35:
            blockers.append(bbox[3])
    if blockers:
        search_top = min(y1 - 28.0, max(blockers) + 5.0)
    bbox = _clip_bbox([x0, search_top, x1, y1], page_size)
    if _is_table_overlap(bbox, table_rects, threshold=0.20):
        return []
    return bbox


def _trim_bbox_against_unrelated_text(
    image_bbox: list[float],
    caption_bbox: list[float],
    text_blocks: list[dict[str, Any]],
    page_size: list[float],
) -> list[float]:
    if len(image_bbox or []) < 4 or len(caption_bbox or []) < 4:
        return image_bbox
    image = [float(v) for v in image_bbox[:4]]
    col_x0, col_x1 = _column_bounds_for_bbox(caption_bbox, page_size)
    for block in text_blocks or []:
        bbox = _bbox_from_any(block.get("bbox"))
        text = str(block.get("text") or "")
        if len(bbox) < 4:
            continue
        if FIGURE_CAPTION_PATTERN.search(text):
            continue
        if _bbox_inside_column_ratio(bbox, col_x0, col_x1) < 0.5:
            continue
        # If an unrelated table caption or footer starts just below the image,
        # make sure the pure image bbox stops above it.
        if TABLE_CAPTION_PATTERN.search(text) and image[1] < bbox[1] < image[3] + 18.0:
            image[3] = min(image[3], bbox[1] - 3.0)
    return _clip_bbox(image, page_size)


def _build_figure_element(
    page: Any,
    page_index: int,
    figure_index: int,
    page_size: list[float],
    output_dir: Path,
    image_bbox: list[float],
    display_bbox: list[float],
    caption_info: dict[str, Any],
) -> dict[str, Any]:
    caption = _clean_caption_text(str(caption_info.get("text") or ""))
    number = _figure_number_from_caption(caption) or str(caption_info.get("number") or "")
    label = f"Figure {number}" if number else f"Figure {figure_index}"
    element_id = f"p{page_index + 1}_figure_{_safe_file_label(number or str(figure_index))}"
    png_path = output_dir / "clips" / f"{element_id}.png"
    image_meta = crop_element_png(page, display_bbox, png_path, zoom=2.5, padding=8)
    return {
        "id": element_id,
        "type": "figure",
        "page": page_index,
        "bbox": display_bbox,
        "pageSize": page_size,
        "label": label,
        "caption": caption,
        "captionBBox": caption_info.get("bbox", []) if caption_info else [],
        "text": caption,
        "table": [],
        "csvPath": "",
        "jsonPath": "",
        "pngPath": str(png_path) if image_meta else "",
        "metadata": {
            "width": round(_bbox_width(display_bbox), 2),
            "height": round(_bbox_height(display_bbox), 2),
            "imageBBox": image_bbox,
            "captionNumber": number,
            "captionSource": caption_info.get("source", "") if caption_info else "",
            "captionScore": caption_info.get("score", 0.0) if caption_info else 0.0,
            **image_meta,
        },
    }


def _best_caption_for_image_bbox(
    bbox: list[float],
    captions: list[dict[str, Any]],
    page_size: list[float],
    require_real: bool = True,
) -> dict[str, Any]:
    if len(bbox or []) < 4:
        return {}
    candidates: list[tuple[float, dict[str, Any]]] = []
    for caption in captions or []:
        caption_bbox = _bbox_from_any(caption.get("bbox"))
        caption_text = str(caption.get("text") or "")
        if len(caption_bbox) < 4:
            continue
        if require_real and not _has_real_figure_caption(caption_text):
            continue
        if not _same_column(bbox, caption_bbox, page_size) and _horizontal_overlap_ratio(bbox, caption_bbox) < 0.12:
            continue
        below = caption_bbox[1] - bbox[3]
        above = bbox[1] - caption_bbox[3]
        if -8.0 <= below <= max(135.0, page_size[1] * 0.18):
            score = below - _horizontal_overlap_ratio(bbox, caption_bbox) * 30.0
            candidates.append((score, caption))
        elif -8.0 <= above <= max(70.0, page_size[1] * 0.10):
            score = above + 35.0 - _horizontal_overlap_ratio(bbox, caption_bbox) * 20.0
            candidates.append((score, caption))
    if not candidates:
        return {}
    candidates.sort(key=lambda item: item[0])
    return candidates[0][1]


def _caption_near_bbox(bbox: list[float], text_blocks: list[dict[str, Any]], page_size: list[float] | None = None) -> str:
    page_size = page_size or [0.0, 0.0]
    captions = _figure_caption_candidates(text_blocks, page_size)
    info = _best_caption_for_image_bbox(bbox, captions, page_size, require_real=True)
    return _clean_caption_text(str(info.get("text") or "")) if info else ""


def _refine_figure_image_bbox(seed_bbox: list[float], visual_candidates: list[list[float]], page_size: list[float]) -> list[float]:
    seed = _bbox_from_any(seed_bbox)
    if len(seed) < 4:
        return []
    refined = [float(v) for v in seed[:4]]
    changed = True
    while changed:
        changed = False
        for candidate in visual_candidates or []:
            box = _bbox_from_any(candidate)
            if len(box) < 4 or box == refined:
                continue
            if not _same_column(refined, box, page_size) and _bbox_gap(refined, box)[0] > 24.0:
                continue
            hgap, vgap = _bbox_gap(refined, box)
            h_overlap = _horizontal_overlap_ratio(refined, box)
            v_overlap = _vertical_overlap_ratio(refined, box)
            should_merge = (
                _bbox_intersection_area(refined, box) > 0
                or (h_overlap > 0.35 and vgap <= 24.0)
                or (v_overlap > 0.30 and hgap <= 24.0)
                or (hgap <= 14.0 and vgap <= 14.0)
            )
            if not should_merge:
                continue
            new_box = _union_nonempty_bboxes([refined, box])
            if len(new_box) < 4:
                continue
            # Prevent accidental cross-column/page-wide merges unless the seed is
            # already clearly a cross-column figure.
            page_width, page_height = _page_dimensions(page_size)
            if page_width > 0 and _bbox_width(new_box) > page_width * 0.82 and _bbox_width(seed) < page_width * 0.58:
                continue
            if page_height > 0 and _bbox_height(new_box) > page_height * 0.55:
                continue
            if new_box != refined:
                refined = new_box
                changed = True
    return _clip_bbox([refined[0] - 6.0, refined[1] - 6.0, refined[2] + 6.0, refined[3] + 6.0], page_size)


def _should_skip_figure_candidate(
    bbox: list[float],
    page_index: int,
    page_size: list[float],
    text_blocks: list[dict[str, Any]],
    caption: str,
) -> tuple[bool, str]:
    if len(bbox or []) < 4:
        return True, "invalid_bbox"
    if _has_real_figure_caption(caption):
        return False, ""
    page_width, page_height = _page_dimensions(page_size)
    if page_width <= 0 or page_height <= 0:
        return False, ""
    width = _bbox_width(bbox)
    height = _bbox_height(bbox)
    if width <= 0 or height <= 0:
        return True, "invalid_bbox_size"
    page_area = max(1.0, page_width * page_height)
    area_ratio = (width * height) / page_area
    aspect = width / max(height, 1.0)
    nearby_text = _text_near_or_inside_bbox(bbox, text_blocks)
    has_decorative_text = bool(DECORATIVE_FIGURE_TEXT_PATTERN.search(nearby_text or ""))
    is_header_or_footer = _is_page_header_or_footer_bbox(bbox, page_size)
    is_first_page_title_band = _is_first_page_title_band_candidate(bbox, page_index, page_size, nearby_text)
    if has_decorative_text and (is_header_or_footer or is_first_page_title_band):
        return True, "decorative_header_or_title_text"
    if is_first_page_title_band:
        return True, "first_page_title_band_without_caption"
    if is_header_or_footer and (has_decorative_text or height <= page_height * 0.16):
        return True, "page_header_or_footer_without_caption"
    if width >= page_width * 0.55 and height <= page_height * 0.16 and aspect >= 3.0 and (has_decorative_text or bbox[1] <= page_height * 0.35):
        return True, "wide_shallow_banner_without_caption"
    if area_ratio <= 0.018 and (is_header_or_footer or has_decorative_text):
        return True, "small_logo_or_icon_without_caption"
    return False, ""


def _is_first_page_title_band_candidate(bbox: list[float], page_index: int, page_size: list[float], nearby_text: str) -> bool:
    if page_index != 0:
        return False
    page_width, page_height = _page_dimensions(page_size)
    if page_width <= 0 or page_height <= 0 or len(bbox or []) < 4:
        return False
    width = _bbox_width(bbox)
    height = _bbox_height(bbox)
    y0 = float(bbox[1])
    if y0 > page_height * 0.35:
        return False
    wide = width >= page_width * 0.42
    shallow = height <= page_height * 0.22
    has_decorative_text = bool(DECORATIVE_FIGURE_TEXT_PATTERN.search(nearby_text or ""))
    return has_decorative_text or (wide and shallow)


def _dedupe_figure_elements(figures: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for fig in sorted(figures, key=_figure_quality_key, reverse=True):
        bbox = fig.get("bbox") or []
        number = str((fig.get("metadata") or {}).get("captionNumber") or "")
        duplicate = False
        for existing in result:
            existing_number = str((existing.get("metadata") or {}).get("captionNumber") or "")
            if number and existing_number and number == existing_number:
                duplicate = True
                break
            if _bbox_iou(bbox, existing.get("bbox") or []) > 0.62:
                duplicate = True
                break
        if not duplicate:
            result.append(fig)
    return _sort_elements(result)


def _figure_quality_key(fig: dict[str, Any]) -> tuple[float, float, float]:
    metadata = fig.get("metadata") or {}
    caption_bonus = 1.0 if fig.get("caption") else 0.0
    number_bonus = 0.4 if metadata.get("captionNumber") else 0.0
    area = _bbox_area(fig.get("bbox") or [])
    return caption_bonus + number_bonus + float(metadata.get("captionScore") or 0.0), area, -float(fig.get("page") or 0)


def _is_bbox_covered_by_figures(bbox: list[float], figures: list[dict[str, Any]]) -> bool:
    for fig in figures or []:
        image_bbox = ((fig.get("metadata") or {}).get("imageBBox") or fig.get("bbox") or [])
        if _bbox_iou(bbox, image_bbox) > 0.38 or _overlap_ratio(_rect_from_bbox(bbox), _rect_from_bbox(image_bbox)) > 0.72:
            return True
    return False


def _has_real_figure_caption(caption: str) -> bool:
    return bool(FIGURE_CAPTION_PATTERN.search(str(caption or "").strip()))


def _figure_number_from_caption(caption: str) -> str:
    match = FIGURE_LABEL_EXTRACT_PATTERN.search(str(caption or "").strip())
    return match.group(1) if match else ""


def _clean_caption_text(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(text or "").replace("\n", " ")).strip()
    cleaned = re.sub(r"^(?:Figure|Fig)\s+", "Fig. ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^Fig\.\s*", "Fig. ", cleaned, flags=re.IGNORECASE)
    return cleaned


# ---------------------------------------------------------------------------
# Formula candidates
# ---------------------------------------------------------------------------


def extract_formula_candidates_pymupdf(
    page: Any, text_blocks: list[dict[str, Any]], page_index: int, page_size: list[float], output_dir: Path
) -> list[dict[str, Any]]:
    formulas: list[dict[str, Any]] = []
    page_width = float(getattr(page.rect, "width", page_size[0] if page_size else 0.0))
    lines = _merge_formula_lines(_text_lines(page), page_width)
    for line_index, line in enumerate(lines, start=1):
        text = str(line.get("text") or "").strip()
        bbox = _bbox_from_any(line.get("bbox"))
        if not _looks_like_formula(text, bbox, page_width):
            continue
        if not _is_isolated_formula_line(line, lines, page.rect):
            continue
        element_id = f"p{page_index + 1}_formula_{line_index}"
        padded = _pad_bbox(bbox, page.rect, 4)
        png_path = output_dir / "clips" / f"{element_id}.png"
        image_meta = crop_element_png(page, padded, png_path, zoom=3.0, padding=4)
        formula_text, formula_number = _split_formula_number(text)
        if not formula_text:
            formula_text = text
        formulas.append(
            {
                "id": element_id,
                "type": "formula",
                "page": page_index,
                "bbox": padded,
                "pageSize": page_size,
                "label": f"Formula {len(formulas) + 1}",
                "caption": "",
                "captionBBox": [],
                "text": text,
                "latex": formula_text,
                "table": [],
                "csvPath": "",
                "jsonPath": "",
                "pngPath": str(png_path) if image_meta else "",
                "metadata": {"lineIndex": line_index, "formulaNumber": formula_number, **image_meta},
            }
        )
    return formulas


def _extract_formulas(page: Any, page_index: int, page_size: list[float], output_dir: Path) -> list[dict[str, Any]]:
    return extract_formula_candidates_pymupdf(page, _extract_text_blocks(page), page_index, page_size, output_dir)


def _merge_formula_lines(lines: list[dict[str, Any]], page_width: float) -> list[dict[str, Any]]:
    if not lines:
        return []
    ordered = sorted(lines, key=lambda line: (float((line.get("bbox") or [0, 0, 0, 0])[1]), float((line.get("bbox") or [0, 0, 0, 0])[0])))
    merged: list[dict[str, Any]] = []
    idx = 0
    while idx < len(ordered):
        line = ordered[idx]
        text = str(line.get("text") or "").strip()
        bbox = _bbox_from_any(line.get("bbox"))
        if len(bbox) < 4:
            idx += 1
            continue
        current = {**line, "text": text, "bbox": bbox}
        current_can_group = _line_has_formula_body(text)
        lookahead = idx + 1
        continuation_count = 0
        while lookahead < len(ordered):
            candidate = ordered[lookahead]
            candidate_text = str(candidate.get("text") or "").strip()
            candidate_bbox = _bbox_from_any(candidate.get("bbox"))
            if len(candidate_bbox) < 4 or not candidate_text:
                lookahead += 1
                continue
            if not current_can_group:
                break
            if _same_line_equation_number(current.get("bbox") or [], candidate_text, candidate_bbox, page_width):
                current["text"] = f"{current.get('text', '')} {candidate_text}".strip()
                current["bbox"] = _union_nonempty_bboxes([current.get("bbox") or [], candidate_bbox])
                lookahead += 1
                continue
            if not _same_formula_group(current, candidate, page_width):
                break
            current["text"] = f"{current.get('text', '')} {candidate_text}".strip()
            current["bbox"] = _union_nonempty_bboxes([current.get("bbox") or [], candidate_bbox])
            continuation_count += 1
            lookahead += 1
            if continuation_count >= 3 or len(str(current.get("text") or "")) > 240:
                break
        merged.append(current)
        idx = lookahead
    return merged


def _looks_like_formula(text: str, bbox: list[float], page_width: float) -> bool:
    compact = re.sub(r"\s+", "", text)
    if len(compact) < 3 or len(compact) > 180:
        return False
    if _is_equation_number_only(text):
        return False
    lowered = text.strip().lower()
    if _looks_like_formula_noise(text):
        return False
    if FIGURE_CAPTION_PATTERN.search(text) or TABLE_CAPTION_PATTERN.search(text):
        return False
    if lowered.startswith(("where ", "when ", "for ", "table ", "figure ", "fig.")):
        return False
    if _looks_like_sentence_formula_noise(text):
        return False
    if not _has_strong_formula_signal(text):
        return False
    width = _bbox_width(bbox)
    if page_width > 0 and width > page_width * 0.85 and len(text.split()) > 12:
        return False
    math_chars = sum(1 for char in text if char in "=≈≠≤≥±∑∫√∞παβγΔλμσθ×÷+-*/^_()[]{}")
    digit_chars = sum(1 for char in text if char.isdigit())
    alpha_words = len(re.findall(r"[A-Za-z]{3,}", text))
    latex_tokens = len(re.findall(r"\\[A-Za-z]+", text))
    return (math_chars + digit_chars + latex_tokens >= 2) and alpha_words <= 10


def _line_has_formula_body(text: str) -> bool:
    value = str(text or "").strip()
    if not value or _is_equation_number_only(value):
        return False
    if value.endswith(":") and len(value.split()) >= 4:
        return False
    if _looks_like_formula_noise(value):
        return False
    if _looks_like_sentence_formula_noise(value):
        return False
    return _has_strong_formula_signal(value)


def _has_strong_formula_signal(text: str) -> bool:
    value = str(text or "")
    if re.search(r"(=|\\frac|\\sum|\\int|\\sqrt|[A-Za-z0-9]\s*[\^_]|[\u2206\u0394\u03b4\u03bc\u03c3\u03b1-\u03c9])", value):
        return True
    if re.search(r"\b(?:sin|cos|tan|log|ln|exp)\s*\(", value):
        return True
    return False


def _looks_like_formula_noise(text: str) -> bool:
    value = re.sub(r"\s+", " ", str(text or "")).strip()
    lowered = value.lower()
    if not value:
        return True
    if re.search(r"(https?://|www\.|crossref|pubmed|creative\s+commons|license|copyright|\bcc\s+by\b)", lowered):
        return True
    if re.search(r"\b(?:adv\.|small|mater\.|chem\.|electrochim\.|journal|doi)\b", lowered) and len(re.findall(r"[A-Za-z]{3,}", value)) >= 3:
        return True
    if re.match(r"^\d+(?:\.\d+)+\.?\s+[A-Z][A-Za-z]", value) and "=" not in value:
        return True
    if value.count(";") >= 2 and "=" not in value:
        return True
    return False


def _is_equation_number_only(text: str) -> bool:
    return bool(re.fullmatch(r"\(?\s*\d+[A-Za-z]?\s*\)?", str(text or "").strip()))


def _split_formula_number(text: str) -> tuple[str, str]:
    value = str(text or "").strip()
    if not value:
        return "", ""
    match = re.search(r"\s*(\(\s*(\d+[A-Za-z]?)\s*\))\s*$", value)
    if not match:
        return value, ""
    body = value[: match.start()].strip()
    number = match.group(2).strip()
    return body, number


def _same_line_equation_number(formula_bbox: list[float], text: str, bbox: list[float], page_width: float) -> bool:
    if len(formula_bbox or []) < 4 or len(bbox or []) < 4:
        return False
    if not EQUATION_NUMBER_PATTERN.search(text):
        return False
    return abs(float(formula_bbox[1]) - float(bbox[1])) <= 9.0 and (page_width <= 0 or float(bbox[0]) > page_width * 0.50)


def _same_formula_group(current: dict[str, Any], candidate: dict[str, Any], page_width: float) -> bool:
    current_bbox = _bbox_from_any(current.get("bbox"))
    candidate_bbox = _bbox_from_any(candidate.get("bbox"))
    if len(current_bbox) < 4 or len(candidate_bbox) < 4:
        return False
    current_text = str(current.get("text") or "")
    candidate_text = str(candidate.get("text") or "")
    if FIGURE_CAPTION_PATTERN.search(candidate_text) or TABLE_CAPTION_PATTERN.search(candidate_text):
        return False
    if _looks_like_sentence_formula_noise(candidate_text):
        return False
    gap = float(candidate_bbox[1]) - float(current_bbox[3])
    if gap < -3.0 or gap > 13.0:
        return False
    if page_width > 0:
        current_center = (current_bbox[0] + current_bbox[2]) / 2.0
        candidate_center = (candidate_bbox[0] + candidate_bbox[2]) / 2.0
        center_close = abs(current_center - candidate_center) <= page_width * 0.16
    else:
        center_close = True
    aligned = abs(float(current_bbox[0]) - float(candidate_bbox[0])) <= 32.0 or _horizontal_overlap_ratio(current_bbox, candidate_bbox) >= 0.20
    combined = f"{current_text} {candidate_text}"
    return (center_close or aligned) and bool(FORMULA_SYMBOL_PATTERN.search(combined))


def _looks_like_sentence_formula_noise(text: str) -> bool:
    value = str(text or "").strip()
    words = [word.lower() for word in re.findall(r"[A-Za-z]{3,}", value)]
    if len(words) < 6:
        return False
    return bool(FORMULA_SENTENCE_WORDS.intersection(words)) or value.endswith((".", "!", "?"))


def _is_isolated_formula_line(line: dict[str, Any], lines: list[dict[str, Any]], page_rect: Any) -> bool:
    bbox = _bbox_from_any(line.get("bbox"))
    if len(bbox) < 4:
        return False
    text = str(line.get("text") or "")
    if EQUATION_NUMBER_PATTERN.search(text):
        return True
    above_gap = below_gap = 999.0
    for other in lines:
        if other is line:
            continue
        other_bbox = _bbox_from_any(other.get("bbox"))
        if len(other_bbox) < 4:
            continue
        if _horizontal_overlap_ratio(bbox, other_bbox) < 0.12:
            continue
        if other_bbox[3] <= bbox[1]:
            above_gap = min(above_gap, bbox[1] - other_bbox[3])
        if other_bbox[1] >= bbox[3]:
            below_gap = min(below_gap, other_bbox[1] - bbox[3])
    return above_gap >= 3.5 and below_gap >= 3.5


# ---------------------------------------------------------------------------
# Image cropping and schema
# ---------------------------------------------------------------------------


def crop_element_png(page: Any, bbox: list[float], output_path: str | Path, zoom: float = 2.5, padding: float = 6.0) -> dict[str, Any]:
    if len(bbox or []) < 4:
        return {}
    try:
        import fitz

        rect = fitz.Rect(float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3]))
        page_rect = page.rect
        rect = rect + (-padding, -padding, padding, padding)
        rect = rect & page_rect
        if rect.is_empty or rect.width <= 1 or rect.height <= 1:
            return {}
        matrix = fitz.Matrix(float(zoom), float(zoom))
        pix = page.get_pixmap(matrix=matrix, clip=rect, alpha=False)
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        pix.save(str(output_path))
        return {
            "pixelWidth": int(pix.width),
            "pixelHeight": int(pix.height),
            "imageWidth": int(pix.width),
            "imageHeight": int(pix.height),
            "clipBBox": _rect_list(rect),
            "zoom": float(zoom),
        }
    except Exception as exc:
        return {"cropError": str(exc)}


def _complete_element_schema(elements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    completed: list[dict[str, Any]] = []
    for index, element in enumerate(elements):
        item = dict(element)
        item.setdefault("id", f"element_{index + 1}")
        item.setdefault("type", "unknown")
        item.setdefault("page", 0)
        item.setdefault("bbox", [])
        item.setdefault("pageSize", [])
        item.setdefault("label", item.get("type", "element"))
        item.setdefault("caption", "")
        item.setdefault("captionBBox", [])
        item.setdefault("text", item.get("caption", ""))
        item.setdefault("table", [])
        item.setdefault("csvPath", "")
        item.setdefault("jsonPath", "")
        item.setdefault("pngPath", "")
        item.setdefault("metadata", {})
        try:
            item = normalize_element(item, "pymupdf")
        except Exception:
            pass
        item = apply_quality(item)
        completed.append(item)
    return completed


def _dedupe_elements(elements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for element in _sort_elements(elements):
        bbox = element.get("bbox") or []
        etype = element.get("type")
        page = int(element.get("page") or 0)
        duplicate = False
        for existing in result:
            if existing.get("type") != etype or int(existing.get("page") or 0) != page:
                continue
            threshold = 0.72 if etype == "table" else 0.68 if etype == "figure" else 0.8
            if _bbox_iou(bbox, existing.get("bbox") or []) >= threshold:
                duplicate = True
                break
        if not duplicate:
            result.append(element)
    return result


def _sort_elements(elements: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    type_order = {"title": 0, "text": 1, "formula": 2, "figure": 3, "table": 4}
    return sorted(
        list(elements),
        key=lambda item: (
            int(item.get("page") or 0),
            float((item.get("bbox") or [0, 0, 0, 0])[1]) if len(item.get("bbox") or []) >= 4 else 0.0,
            float((item.get("bbox") or [0, 0, 0, 0])[0]) if len(item.get("bbox") or []) >= 4 else 0.0,
            type_order.get(str(item.get("type") or ""), 99),
        ),
    )


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------


def _bbox_from_any(value: Any) -> list[float]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)) and len(value) >= 4:
        try:
            return [float(value[0]), float(value[1]), float(value[2]), float(value[3])]
        except Exception:
            return []
    attrs = ("x0", "y0", "x1", "y1")
    if all(hasattr(value, attr) for attr in attrs):
        try:
            return [float(value.x0), float(value.y0), float(value.x1), float(value.y1)]
        except Exception:
            return []
    return []


def _rect_list(rect: Any) -> list[float]:
    return _bbox_from_any(rect)


def _rect_from_bbox(bbox: list[float]) -> Any:
    try:
        import fitz

        if len(bbox or []) >= 4:
            return fitz.Rect(float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3]))
    except Exception:
        pass
    return [float(v) for v in bbox[:4]] if len(bbox or []) >= 4 else []


def _page_dimensions(page_size: list[float]) -> tuple[float, float]:
    try:
        page_width = float(page_size[0])
        page_height = float(page_size[1])
    except Exception:
        return 0.0, 0.0
    return page_width, page_height


def _clip_bbox(bbox: list[float], page_size: list[float]) -> list[float]:
    if len(bbox or []) < 4:
        return []
    page_width, page_height = _page_dimensions(page_size)
    x0 = max(0.0, float(bbox[0]))
    y0 = max(0.0, float(bbox[1]))
    x1 = float(bbox[2])
    y1 = float(bbox[3])
    if page_width > 0:
        x1 = min(page_width, x1)
    if page_height > 0:
        y1 = min(page_height, y1)
    if x1 <= x0 or y1 <= y0:
        return []
    return [x0, y0, x1, y1]


def _bbox_width(bbox: list[float]) -> float:
    if len(bbox or []) < 4:
        return 0.0
    return max(0.0, float(bbox[2]) - float(bbox[0]))


def _bbox_height(bbox: list[float]) -> float:
    if len(bbox or []) < 4:
        return 0.0
    return max(0.0, float(bbox[3]) - float(bbox[1]))


def _bbox_area(bbox: list[float]) -> float:
    return _bbox_width(bbox) * _bbox_height(bbox)


def _bbox_intersection_area(left: list[float], right: list[float]) -> float:
    if len(left or []) < 4 or len(right or []) < 4:
        return 0.0
    x0 = max(float(left[0]), float(right[0]))
    y0 = max(float(left[1]), float(right[1]))
    x1 = min(float(left[2]), float(right[2]))
    y1 = min(float(left[3]), float(right[3]))
    if x1 <= x0 or y1 <= y0:
        return 0.0
    return (x1 - x0) * (y1 - y0)


def _bbox_iou(left: list[float], right: list[float]) -> float:
    inter = _bbox_intersection_area(left, right)
    if inter <= 0:
        return 0.0
    union = _bbox_area(left) + _bbox_area(right) - inter
    return inter / union if union > 0 else 0.0


def _bbox_overlap_ratio(left: list[float], right: list[float]) -> float:
    inter = _bbox_intersection_area(left, right)
    if inter <= 0:
        return 0.0
    denom = min(_bbox_area(left), _bbox_area(right))
    return inter / denom if denom > 0 else 0.0


def _overlap_ratio(left_rect: Any, right_rect: Any) -> float:
    left = _bbox_from_any(left_rect)
    right = _bbox_from_any(right_rect)
    inter = _bbox_intersection_area(left, right)
    denom = min(_bbox_area(left), _bbox_area(right))
    return inter / denom if denom > 0 else 0.0


def _contains_bbox(outer: list[float], inner: list[float], tolerance: float = 1.0) -> bool:
    if len(outer or []) < 4 or len(inner or []) < 4:
        return False
    return (
        float(outer[0]) - tolerance <= float(inner[0])
        and float(outer[1]) - tolerance <= float(inner[1])
        and float(outer[2]) + tolerance >= float(inner[2])
        and float(outer[3]) + tolerance >= float(inner[3])
    )


def _horizontal_overlap_ratio(left: list[float], right: list[float]) -> float:
    if len(left or []) < 4 or len(right or []) < 4:
        return 0.0
    overlap = max(0.0, min(float(left[2]), float(right[2])) - max(float(left[0]), float(right[0])))
    return overlap / max(1.0, min(_bbox_width(left), _bbox_width(right)))


def _vertical_overlap_ratio(left: list[float], right: list[float]) -> float:
    if len(left or []) < 4 or len(right or []) < 4:
        return 0.0
    overlap = max(0.0, min(float(left[3]), float(right[3])) - max(float(left[1]), float(right[1])))
    return overlap / max(1.0, min(_bbox_height(left), _bbox_height(right)))


def _bbox_gap(a: list[float], b: list[float]) -> tuple[float, float]:
    if len(a or []) < 4 or len(b or []) < 4:
        return 10**9, 10**9
    hgap = max(0.0, max(float(a[0]), float(b[0])) - min(float(a[2]), float(b[2])))
    vgap = max(0.0, max(float(a[1]), float(b[1])) - min(float(a[3]), float(b[3])))
    return hgap, vgap


def _union_nonempty_bboxes(bboxes: Iterable[list[float]]) -> list[float]:
    boxes = [list(map(float, box[:4])) for box in bboxes if len(box or []) >= 4 and _bbox_width(box) > 0 and _bbox_height(box) > 0]
    if not boxes:
        return []
    return [min(box[0] for box in boxes), min(box[1] for box in boxes), max(box[2] for box in boxes), max(box[3] for box in boxes)]


def _union_bboxes(bboxes: Iterable[list[float]]) -> list[float]:
    return _union_nonempty_bboxes(bboxes)


def _expanded_bbox(bbox: list[float], margin: float) -> list[float]:
    if len(bbox or []) < 4:
        return []
    return [float(bbox[0]) - margin, float(bbox[1]) - margin, float(bbox[2]) + margin, float(bbox[3]) + margin]


def _pad_bbox(bbox: list[float], page_rect: Any, padding: float) -> list[float]:
    if len(bbox or []) < 4:
        return []
    page_bbox = _bbox_from_any(page_rect)
    x0 = float(bbox[0]) - padding
    y0 = float(bbox[1]) - padding
    x1 = float(bbox[2]) + padding
    y1 = float(bbox[3]) + padding
    if len(page_bbox) >= 4:
        x0 = max(page_bbox[0], x0)
        y0 = max(page_bbox[1], y0)
        x1 = min(page_bbox[2], x1)
        y1 = min(page_bbox[3], y1)
    return [x0, y0, x1, y1] if x1 > x0 and y1 > y0 else []


def _merge_nearby_bboxes(bboxes: list[list[float]], gap: float = 18.0) -> list[list[float]]:
    result: list[list[float]] = []
    for bbox in sorted([_bbox_from_any(box) for box in bboxes if len(_bbox_from_any(box)) >= 4], key=lambda box: (box[1], box[0])):
        merged = False
        for idx, existing in enumerate(result):
            hgap, vgap = _bbox_gap(existing, bbox)
            if _bbox_intersection_area(existing, bbox) > 0 or (hgap <= gap and _vertical_overlap_ratio(existing, bbox) > 0.22) or (vgap <= gap and _horizontal_overlap_ratio(existing, bbox) > 0.22):
                result[idx] = _union_nonempty_bboxes([existing, bbox])
                merged = True
                break
        if not merged:
            result.append(bbox)
    changed = True
    while changed:
        changed = False
        compact: list[list[float]] = []
        for bbox in result:
            for idx, existing in enumerate(compact):
                hgap, vgap = _bbox_gap(existing, bbox)
                if _bbox_intersection_area(existing, bbox) > 0 or (hgap <= gap and _vertical_overlap_ratio(existing, bbox) > 0.22) or (vgap <= gap and _horizontal_overlap_ratio(existing, bbox) > 0.22):
                    compact[idx] = _union_nonempty_bboxes([existing, bbox])
                    changed = True
                    break
            else:
                compact.append(bbox)
        result = compact
    return result


def _dedupe_bboxes(bboxes: list[list[float]], iou_threshold: float = 0.72) -> list[list[float]]:
    result: list[list[float]] = []
    for bbox in sorted([_bbox_from_any(box) for box in bboxes if len(_bbox_from_any(box)) >= 4], key=_bbox_area, reverse=True):
        if any(_bbox_iou(bbox, existing) >= iou_threshold or _overlap_ratio(_rect_from_bbox(bbox), _rect_from_bbox(existing)) >= 0.92 for existing in result):
            continue
        result.append(bbox)
    return sorted(result, key=lambda box: (box[1], box[0]))


def _column_bounds_for_bbox(bbox: list[float], page_size: list[float]) -> tuple[float, float]:
    if len(bbox or []) < 4 or len(page_size or []) < 2:
        return 0.0, 0.0
    page_width = float(page_size[0] or 0)
    if page_width <= 0:
        return 0.0, 0.0
    x0, x1 = float(bbox[0]), float(bbox[2])
    cx = (x0 + x1) / 2.0
    if _bbox_width(bbox) >= page_width * 0.62:
        return 0.0, page_width
    center = page_width / 2.0
    gutter_half = max(12.0, page_width * 0.025)
    margin = 8.0
    if cx < center and x1 <= center + gutter_half:
        return margin, center - gutter_half
    if cx >= center and x0 >= center - gutter_half:
        return center + gutter_half, page_width - margin
    return margin, page_width - margin


def _bbox_inside_column_ratio(bbox: list[float], col_x0: float, col_x1: float) -> float:
    if len(bbox or []) < 4:
        return 0.0
    overlap = max(0.0, min(float(bbox[2]), col_x1) - max(float(bbox[0]), col_x0))
    return overlap / max(1.0, _bbox_width(bbox))


def _same_column(a: list[float], b: list[float], page_size: list[float]) -> bool:
    ax0, ax1 = _column_bounds_for_bbox(a, page_size)
    bx0, bx1 = _column_bounds_for_bbox(b, page_size)
    if abs(ax0 - bx0) <= 10.0 and abs(ax1 - bx1) <= 10.0:
        return True
    return _horizontal_overlap_ratio(a, b) >= 0.32


def _reasonable_visual_bbox(bbox: list[float], page_size: list[float], allow_thin: bool = False) -> bool:
    bbox = _bbox_from_any(bbox)
    if len(bbox) < 4:
        return False
    width = _bbox_width(bbox)
    height = _bbox_height(bbox)
    page_width, page_height = _page_dimensions(page_size)
    if width <= 0 or height <= 0:
        return False
    if allow_thin:
        if width < 8 or height < 8 or width * height < 120:
            return False
    elif width < 28 or height < 20 or width * height < 900:
        return False
    if page_width > 0 and width > page_width * 0.98:
        return False
    if page_height > 0 and height > page_height * 0.85:
        return False
    return True


def _reasonable_figure_bbox(bbox: list[float], page_size: list[float], allow_small: bool = False) -> bool:
    bbox = _bbox_from_any(bbox)
    if len(bbox) < 4:
        return False
    page_width, page_height = _page_dimensions(page_size)
    width = _bbox_width(bbox)
    height = _bbox_height(bbox)
    area = width * height
    if width <= 0 or height <= 0:
        return False
    min_area = 1000.0 if allow_small else 1800.0
    min_width = 24.0 if allow_small else 35.0
    min_height = 18.0 if allow_small else 25.0
    if width < min_width or height < min_height or area < min_area:
        return False
    if page_width > 0 and width > page_width * 0.98:
        return False
    if page_height > 0 and height > page_height * 0.75:
        return False
    aspect = width / max(height, 1.0)
    if aspect > 9.5 or aspect < 0.08:
        return False
    return True


def _is_visual_noise(bbox: list[float], page_size: list[float]) -> bool:
    if len(bbox or []) < 4:
        return True
    page_width, page_height = _page_dimensions(page_size)
    width = _bbox_width(bbox)
    height = _bbox_height(bbox)
    if width <= 1 or height <= 1:
        return True
    # Page rules, headers and footers are often long shallow vector rectangles.
    if page_width > 0 and width > page_width * 0.55 and height < 4.0:
        return True
    if page_height > 0 and height > page_height * 0.50 and width < 4.0:
        return True
    return False


def _is_table_overlap(bbox: list[float], table_rects: list[Any], threshold: float = 0.35) -> bool:
    if len(bbox or []) < 4:
        return False
    for table_rect in table_rects or []:
        table_bbox = _bbox_from_any(table_rect)
        if len(table_bbox) < 4:
            continue
        if _overlap_ratio(_rect_from_bbox(bbox), _rect_from_bbox(table_bbox)) > threshold:
            return True
    return False


def _is_page_header_or_footer_bbox(bbox: list[float], page_size: list[float]) -> bool:
    page_width, page_height = _page_dimensions(page_size)
    if page_width <= 0 or page_height <= 0 or len(bbox or []) < 4:
        return False
    y0 = float(bbox[1])
    y1 = float(bbox[3])
    return y1 <= page_height * 0.12 or y0 >= page_height * 0.90


def _text_near_or_inside_bbox(bbox: list[float], text_blocks: list[dict[str, Any]], margin: float = 28.0) -> str:
    if len(bbox or []) < 4:
        return ""
    expanded = _expanded_bbox(bbox, margin)
    collected: list[str] = []
    for block in text_blocks or []:
        block_bbox = _bbox_from_any(block.get("bbox"))
        if len(block_bbox) < 4:
            continue
        text = str(block.get("text") or "").strip().replace("\n", " ")
        if not text:
            continue
        if _bbox_intersection_area(expanded, block_bbox) > 0:
            collected.append(text)
    return " ".join(collected)[:1200]


def _safe_file_label(label: str) -> str:
    label = re.sub(r"\s+", "_", str(label or "").strip().lower())
    label = re.sub(r"[^a-z0-9_\-\.\u4e00-\u9fff]+", "", label)
    return label[:48] or "item"
