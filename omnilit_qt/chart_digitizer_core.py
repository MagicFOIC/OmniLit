from __future__ import annotations

import math
import re
import statistics
from collections import Counter
from pathlib import Path
from typing import Any

try:
    from PySide6.QtGui import QColor, QImage
except Exception:  # pragma: no cover - PySide6 is optional for non-Qt test environments.
    QColor = None
    QImage = None

from .chart_digitizer_schema import (
    DEFAULT_SAMPLE_COUNT,
    build_source_metadata,
    make_axis,
    make_empty_result,
    make_point,
    normalize_sample_count,
    utc_now_iso,
    ENGINE_NAME,
    SCHEMA_VERSION,
)


LINE_CHART_HINTS = re.compile(
    r"\b(line|curve|trend|spectrum|spectra|rate|time|temperature|voltage|current|"
    r"intensity|profile|response|kinetic|fig(?:ure)?\.?)\b",
    re.IGNORECASE,
)
NON_LINE_HINTS = re.compile(
    r"\b(photo|microscopy|sem|tem|schematic|workflow|flowchart|structure|boxplot|"
    r"box plot|bar chart|histogram|heatmap|3d|surface|map)\b",
    re.IGNORECASE,
)
NUMERIC_TEXT_PATTERN = re.compile(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?")


def analyze_chart_element(
    element: dict[str, Any],
    index: dict[str, Any] | None = None,
    *,
    record_id: str = "",
    sample_count: Any = DEFAULT_SAMPLE_COUNT,
    calibration: dict[str, Any] | None = None,
) -> dict[str, Any]:
    count = normalize_sample_count(sample_count)
    if not isinstance(element, dict) or str(element.get("type") or "") != "figure":
        return make_empty_result(
            element if isinstance(element, dict) else {},
            index,
            record_id=record_id,
            sample_count=count,
            warnings=["当前元素不是 figure，无法分析图数据。"],
            chart_type="unsupported",
        )

    png_path = Path(str(element.get("pngPath") or "")).expanduser()
    image = _load_image(png_path)
    chart_type, type_confidence, type_warnings = classify_chart_candidate(element, image)
    if chart_type != "line_chart":
        return make_empty_result(
            element,
            index,
            record_id=record_id,
            sample_count=count,
            warnings=type_warnings or ["未识别为折线图/曲线图，需要手动确认。"],
            chart_type=chart_type,
        )
    if image is None:
        return make_empty_result(
            element,
            index,
            record_id=record_id,
            sample_count=count,
            warnings=["图像文件不可读取，需要手动校准。"],
            chart_type=chart_type,
        )

    calibration = calibration if isinstance(calibration, dict) else {}
    subplot_regions = _manual_subplot_regions(calibration) or _detect_subplot_regions(image)
    subplots: list[dict[str, Any]] = []
    warnings = list(type_warnings)
    confidences = [type_confidence]
    for subplot_index, region in enumerate(subplot_regions):
        subplot_calibration = _calibration_for_subplot(calibration, subplot_index)
        subplot = _analyze_subplot(image, region, subplot_index, count, subplot_calibration, element, index)
        subplots.append(subplot)
        confidences.append(float(subplot.get("confidence") or 0.0))
        warnings.extend(str(item) for item in subplot.get("warnings") or [])

    confidence = _clamp(sum(confidences) / len(confidences) if confidences else 0.0)
    needs_review = confidence < 0.62 or any(_subplot_needs_review(item) for item in subplots)
    if needs_review and not any("手动校准" in item for item in warnings):
        warnings.append("需要手动校准。")

    return {
        "schemaVersion": SCHEMA_VERSION,
        "source": build_source_metadata(element, index, record_id),
        "analysis": {
            "chartType": "line_chart",
            "createdAt": utc_now_iso(),
            "engine": ENGINE_NAME,
            "sampleCount": count,
            "confidence": confidence,
            "needsReview": bool(needs_review),
            "status": "需要手动校准" if needs_review else "自动结果",
            "warnings": _dedupe_strings(warnings),
        },
        "subplots": subplots,
    }


def classify_chart_candidate(element: dict[str, Any], image: Any = None) -> tuple[str, float, list[str]]:
    caption = str(element.get("caption") or element.get("text") or "")
    lower = caption.lower()
    if NON_LINE_HINTS.search(lower):
        return "unsupported", 0.18, ["caption 提示该图可能不是折线图/曲线图，暂不自动输出数值。"]
    score = 0.0
    warnings: list[str] = []
    if LINE_CHART_HINTS.search(lower):
        score += 0.32
    if image is not None:
        axes = _detect_axes(image, [0, 0, _image_width(image), _image_height(image)])
        score += axes["confidence"] * 0.55
        if axes["confidence"] < 0.45:
            warnings.append("坐标轴自动识别置信度较低。")
        if _has_curve_pixels(image, axes["plot_area"]):
            score += 0.20
        else:
            warnings.append("未检测到足够连续的曲线像素。")
    else:
        warnings.append("图像文件不可读取。")
    if score >= 0.40:
        return "line_chart", _clamp(score), warnings
    return "unknown", _clamp(score), warnings or ["未达到折线图自动识别阈值。"]


def _analyze_subplot(
    image: Any,
    region: list[int],
    subplot_index: int,
    sample_count: int,
    calibration: dict[str, Any],
    element: dict[str, Any] | None = None,
    index: dict[str, Any] | None = None,
) -> dict[str, Any]:
    axes_info = _detect_axes(image, region, calibration)
    plot_area = axes_info["plot_area"]
    effective_calibration = dict(calibration or {})
    text_calibration = _pdf_text_calibration(element or {}, index or {}, plot_area)
    legend_candidates = _pdf_text_legend_candidates(element or {}, index or {}, plot_area)
    if text_calibration.get("warnings"):
        axes_info.setdefault("warnings", []).extend(text_calibration.get("warnings") or [])
    if _axis_from_payload(effective_calibration.get("xAxis") or effective_calibration.get("x"), plot_area, "x") is None and text_calibration.get("xAxis"):
        effective_calibration["xAxis"] = text_calibration["xAxis"]
    if _axis_from_payload(effective_calibration.get("yAxis") or effective_calibration.get("y"), plot_area, "y") is None and text_calibration.get("yAxis"):
        effective_calibration["yAxis"] = text_calibration["yAxis"]
    series_seeds = _series_seeds_from_calibration(calibration)
    curves = _extract_series(image, plot_area, series_seeds)
    if legend_candidates and not series_seeds:
        curves = _apply_legend_candidates_to_curves(image, plot_area, curves, legend_candidates)
    axes = _axes_from_calibration(plot_area, axes_info, effective_calibration)
    axis_quality = _effective_axis_quality(axes, axes_info)
    warnings = _axis_warnings_for_effective_axes(axes, list(axes_info.get("warnings") or []))
    if series_seeds and not curves:
        warnings.append("手动选择的曲线颜色未能可靠提取，请重新点选曲线主体。")
    if not curves:
        warnings.append("未能可靠分离曲线，需要手动选择曲线或颜色。")
    series_entries: list[dict[str, Any]] = []
    series_confidences: list[float] = []
    for series_index, curve in enumerate(curves):
        points = _sample_curve(curve["pixels"], plot_area, axes, sample_count)
        missing_count = sum(1 for point in points if point.get("missing"))
        missing_ratio = missing_count / max(1, len(points))
        series_warnings: list[str] = []
        if missing_count:
            series_warnings.append("曲线在部分 x 位置断裂或没有可靠交点，缺失点已标记为 missing。")
        series_confidence = _clamp(curve.get("confidence", 0.0) * axis_quality * max(0.35, 1.0 - missing_ratio * 0.9))
        series_confidences.append(series_confidence)
        series_entries.append(
            {
                "seriesId": f"series_{series_index + 1}",
                "name": curve.get("name") or f"Series {series_index + 1}",
                "nameSource": curve.get("nameSource") or ("manual_seed" if curve.get("name") else "default"),
                "color": curve.get("color") or "#444444",
                "confidence": series_confidence,
                "needsReview": series_confidence < 0.62 or missing_count > 0,
                "warnings": series_warnings,
                "seedPixel": curve.get("seedPixel") or [],
                "legendCandidate": curve.get("legendCandidate") or {},
                "points": points,
            }
        )
    if series_confidences:
        confidence = _clamp((axis_quality * 0.45) + (sum(series_confidences) / len(series_confidences) * 0.55))
    else:
        confidence = _clamp(axis_quality * 0.45)
    return {
        "subplotId": f"subplot_{subplot_index + 1}",
        "label": chr(ord("a") + subplot_index) if subplot_index < 26 else str(subplot_index + 1),
        "bboxPx": [float(v) for v in region],
        "plotAreaPx": [float(v) for v in plot_area],
        "axes": axes,
        "legendCandidates": legend_candidates,
        "series": series_entries,
        "confidence": confidence,
        "needsReview": confidence < 0.62
        or axes["x"]["source"] == "auto_geometry_preview"
        or axes["y"]["source"] == "auto_geometry_preview"
        or any(item.get("needsReview") for item in series_entries),
        "warnings": _dedupe_strings(warnings),
    }


def _effective_axis_quality(axes: dict[str, Any], axes_info: dict[str, Any]) -> float:
    sources = [str((axes.get(axis) or {}).get("source") or "") for axis in ("x", "y")]
    if all(source in {"manual_calibration", "pdf_text"} for source in sources):
        confidences = [float((axes.get(axis) or {}).get("confidence") or 0.0) for axis in ("x", "y")]
        return _clamp(max(float(axes_info.get("confidence") or 0.0), min(confidences or [0.0])))
    return _clamp(float(axes_info.get("confidence") or 0.0))


def _axis_warnings_for_effective_axes(axes: dict[str, Any], warnings: list[str]) -> list[str]:
    sources = [str((axes.get(axis) or {}).get("source") or "") for axis in ("x", "y")]
    if all(source in {"manual_calibration", "pdf_text"} for source in sources):
        return [warning for warning in warnings if "坐标轴" not in warning and "手动校准" not in warning]
    return warnings


def _load_image(path: Path) -> Any:
    if QImage is None or not path.exists():
        return None
    image = QImage(str(path))
    if image.isNull():
        return None
    return image.convertToFormat(QImage.Format_RGB32)


def _image_width(image: Any) -> int:
    return int(image.width())


def _image_height(image: Any) -> int:
    return int(image.height())


def _manual_subplot_regions(calibration: dict[str, Any]) -> list[list[int]]:
    regions: list[list[int]] = []
    raw = calibration.get("subplots") if isinstance(calibration, dict) else None
    if isinstance(raw, list):
        for entry in raw:
            if not isinstance(entry, dict):
                continue
            bbox = _bbox_int(entry.get("bboxPx") or entry.get("bbox"))
            if bbox:
                regions.append(bbox)
    return regions


def _calibration_for_subplot(calibration: dict[str, Any], subplot_index: int) -> dict[str, Any]:
    if not isinstance(calibration, dict):
        return {}
    subplots = calibration.get("subplots")
    if isinstance(subplots, list) and subplot_index < len(subplots) and isinstance(subplots[subplot_index], dict):
        return subplots[subplot_index]
    if subplot_index > 0 and any(key in calibration for key in ("plotAreaPx", "plotArea", "xAxis", "yAxis", "x", "y")):
        return {}
    return calibration


def _detect_subplot_regions(image: Any) -> list[list[int]]:
    width = _image_width(image)
    height = _image_height(image)
    whole = [0, 0, width, height]
    for columns, rows in ((2, 2), (3, 1), (1, 3), (3, 2), (2, 3)):
        regions = _grid_regions(width, height, columns, rows)
        if regions and all(_looks_like_subplot_region(image, region) for region in regions):
            return regions
    if width >= 360 and width / max(1, height) >= 1.65:
        left = [0, 0, width // 2, height]
        right = [width // 2, 0, width, height]
        if _looks_like_subplot_region(image, left) and _looks_like_subplot_region(image, right):
            return [left, right]
    if height >= 360 and height / max(1, width) >= 1.55:
        top = [0, 0, width, height // 2]
        bottom = [0, height // 2, width, height]
        if _looks_like_subplot_region(image, top) and _looks_like_subplot_region(image, bottom):
            return [top, bottom]
    return [whole]


def _grid_regions(width: int, height: int, columns: int, rows: int) -> list[list[int]]:
    if columns < 1 or rows < 1:
        return []
    if width // columns < 120 or height // rows < 110:
        return []
    x_edges = [round(width * index / columns) for index in range(columns + 1)]
    y_edges = [round(height * index / rows) for index in range(rows + 1)]
    regions: list[list[int]] = []
    for row in range(rows):
        for column in range(columns):
            regions.append([x_edges[column], y_edges[row], x_edges[column + 1], y_edges[row + 1]])
    return regions


def _looks_like_subplot_region(image: Any, region: list[int]) -> bool:
    x0, y0, x1, y1 = _clip_region(region, _image_width(image), _image_height(image))
    if x1 - x0 < 120 or y1 - y0 < 110:
        return False
    axes = _detect_axes(image, [x0, y0, x1, y1])
    return float(axes.get("confidence") or 0.0) >= 0.43 and _has_curve_pixels(image, axes.get("plot_area") or [x0, y0, x1, y1])


def _detect_axes(image: Any, region: list[int], calibration: dict[str, Any] | None = None) -> dict[str, Any]:
    manual_area = _bbox_int((calibration or {}).get("plotAreaPx") or (calibration or {}).get("plotArea"))
    if manual_area:
        return {
            "plot_area": manual_area,
            "confidence": 0.95,
            "source": "manual_calibration",
            "warnings": [],
        }
    x0, y0, x1, y1 = _clip_region(region, _image_width(image), _image_height(image))
    width = max(1, x1 - x0)
    height = max(1, y1 - y0)
    row_start = y0 + int(height * 0.50)
    row_end = y1 - max(2, int(height * 0.04))
    col_start = x0 + max(2, int(width * 0.04))
    col_end = x0 + int(width * 0.45)

    best_row = (0, row_end - 1)
    for y in range(max(y0, row_start), max(row_start + 1, row_end)):
        count = 0
        for x in range(x0 + int(width * 0.08), x1 - int(width * 0.04), 2):
            if _is_dark(image, x, y):
                count += 1
        if count > best_row[0]:
            best_row = (count, y)

    best_col = (0, col_start)
    for x in range(max(x0, col_start), max(col_start + 1, col_end)):
        count = 0
        for y in range(y0 + int(height * 0.05), y1 - int(height * 0.10), 2):
            if _is_dark(image, x, y):
                count += 1
        if count > best_col[0]:
            best_col = (count, x)

    row_score = min(1.0, best_row[0] / max(1.0, width * 0.38))
    col_score = min(1.0, best_col[0] / max(1.0, height * 0.30))
    confidence = _clamp((row_score + col_score) / 2.0)
    if confidence >= 0.35:
        left = best_col[1]
        bottom = best_row[1]
        top = y0 + max(5, int(height * 0.06))
        right = x1 - max(5, int(width * 0.05))
    else:
        left = x0 + int(width * 0.12)
        bottom = y1 - int(height * 0.12)
        top = y0 + int(height * 0.08)
        right = x1 - int(width * 0.08)

    plot_area = [left, top, max(left + 2, right), max(top + 2, bottom)]
    warnings = []
    if confidence < 0.55:
        warnings.append("坐标轴识别置信度低，需要手动校准。")
    return {
        "plot_area": plot_area,
        "confidence": confidence,
        "source": "auto_geometry",
        "warnings": warnings,
    }


def _axes_from_calibration(plot_area: list[int], axes_info: dict[str, Any], calibration: dict[str, Any]) -> dict[str, Any]:
    x_axis = _axis_from_payload(calibration.get("xAxis") or calibration.get("x"), plot_area, "x")
    y_axis = _axis_from_payload(calibration.get("yAxis") or calibration.get("y"), plot_area, "y")
    if x_axis and y_axis:
        return {"x": x_axis, "y": y_axis}
    x0, y0, x1, y1 = [float(v) for v in plot_area]
    source = "auto_geometry_preview"
    confidence = min(0.48, float(axes_info.get("confidence") or 0.0))
    return {
        "x": make_axis(
            scale="linear",
            minimum=0.0,
            maximum=1.0,
            calibration=[{"pixel": [x0, y1], "value": 0.0}, {"pixel": [x1, y1], "value": 1.0}],
            source=source,
            confidence=confidence,
        ),
        "y": make_axis(
            scale="linear",
            minimum=0.0,
            maximum=1.0,
            calibration=[{"pixel": [x0, y1], "value": 0.0}, {"pixel": [x0, y0], "value": 1.0}],
            source=source,
            confidence=confidence,
        ),
    }


def _axis_from_payload(axis_payload: Any, plot_area: list[int], axis_name: str) -> dict[str, Any] | None:
    if not isinstance(axis_payload, dict):
        return None
    calibration = axis_payload.get("calibration")
    if not isinstance(calibration, list) or len(calibration) < 2:
        return None
    clean: list[dict[str, Any]] = []
    values: list[float] = []
    for item in calibration[:2]:
        if not isinstance(item, dict):
            continue
        pixel = item.get("pixel")
        if not isinstance(pixel, (list, tuple)) or len(pixel) < 2:
            continue
        try:
            value = float(item.get("value"))
            clean.append({"pixel": [float(pixel[0]), float(pixel[1])], "value": value})
            values.append(value)
        except (TypeError, ValueError):
            continue
    if len(clean) < 2:
        return None
    return make_axis(
        label=str(axis_payload.get("label") or ""),
        scale=str(axis_payload.get("scale") or "linear"),
        minimum=min(values),
        maximum=max(values),
        calibration=clean,
        source=str(axis_payload.get("source") or "manual_calibration"),
        confidence=float(axis_payload.get("confidence") or 0.95),
    )


def _pdf_text_calibration(element: dict[str, Any], index: dict[str, Any], plot_area: list[int]) -> dict[str, Any]:
    tick_candidates: list[dict[str, Any]] = []
    for block in _pdf_text_blocks_with_pixels(element, index):
        tick_candidates.extend(_tick_candidates_from_text_block(block))

    x_ticks = _select_axis_ticks(tick_candidates, plot_area, "x")
    y_ticks = _select_axis_ticks(tick_candidates, plot_area, "y")
    warnings: list[str] = []
    result: dict[str, Any] = {}
    if len(x_ticks) >= 2:
        result["xAxis"] = _axis_from_ticks(x_ticks, "x")
    elif tick_candidates:
        warnings.append("PDF 文本层未能可靠匹配 x 轴两个刻度。")
    if len(y_ticks) >= 2:
        result["yAxis"] = _axis_from_ticks(y_ticks, "y")
    elif tick_candidates:
        warnings.append("PDF 文本层未能可靠匹配 y 轴两个刻度。")
    if result:
        result["warnings"] = warnings
    return result


def _pdf_text_blocks_with_pixels(element: dict[str, Any], index: dict[str, Any]) -> list[dict[str, Any]]:
    page_blocks = _page_text_blocks(index, int(element.get("page") or 0))
    if not page_blocks:
        return []
    metadata = element.get("metadata") if isinstance(element.get("metadata"), dict) else {}
    clip_bbox = _bbox_float(metadata.get("clipBBox"))
    try:
        zoom = float(metadata.get("zoom") or 0.0)
    except (TypeError, ValueError):
        zoom = 0.0
    if not clip_bbox or zoom <= 0:
        clip_bbox = _bbox_float(element.get("bbox"))
        try:
            image_width = float(metadata.get("imageWidth") or metadata.get("pixelWidth") or 0.0)
        except (TypeError, ValueError):
            image_width = 0.0
        if not clip_bbox or image_width <= 0:
            return []
        zoom = image_width / max(1.0, clip_bbox[2] - clip_bbox[0])
    result: list[dict[str, Any]] = []
    for block in page_blocks:
        bbox = _bbox_float(block.get("bbox"))
        if not bbox:
            continue
        cx = (bbox[0] + bbox[2]) / 2.0
        cy = (bbox[1] + bbox[3]) / 2.0
        item = dict(block)
        item["pixel"] = [(cx - clip_bbox[0]) * zoom, (cy - clip_bbox[1]) * zoom]
        item["bboxPx"] = [(bbox[0] - clip_bbox[0]) * zoom, (bbox[1] - clip_bbox[1]) * zoom, (bbox[2] - clip_bbox[0]) * zoom, (bbox[3] - clip_bbox[1]) * zoom]
        result.append(item)
    return result


def _tick_candidates_from_text_block(block: dict[str, Any]) -> list[dict[str, Any]]:
    text = str(block.get("text") or "").strip()
    matches = list(NUMERIC_TEXT_PATTERN.finditer(text.replace("−", "-")))
    if len(matches) >= 2:
        return _split_numeric_tick_block(block, matches)
    parsed = _parse_tick_value(text)
    if parsed is not None:
        return [{"text": text, "value": parsed, "pixel": block.get("pixel") or []}]
    if re.search(r"[A-Za-z\u4e00-\u9fff]{2,}", text):
        return []
    return []


def _split_numeric_tick_block(block: dict[str, Any], matches: list[Any]) -> list[dict[str, Any]]:
    text = str(block.get("text") or "").strip()
    if re.search(r"[A-Za-z\u4e00-\u9fff]{2,}", text):
        return []
    if len(matches) > 12:
        return []
    bbox = _bbox_float(block.get("bboxPx"))
    if not bbox:
        return []
    horizontal = (bbox[2] - bbox[0]) >= (bbox[3] - bbox[1]) * 1.8
    result: list[dict[str, Any]] = []
    for index, match in enumerate(matches):
        try:
            value = float(match.group(0))
        except (TypeError, ValueError):
            continue
        fraction = index / max(1, len(matches) - 1)
        if horizontal:
            pixel = [bbox[0] + (bbox[2] - bbox[0]) * fraction, (bbox[1] + bbox[3]) / 2.0]
        else:
            pixel = [(bbox[0] + bbox[2]) / 2.0, bbox[1] + (bbox[3] - bbox[1]) * fraction]
        result.append({"text": match.group(0), "value": value, "pixel": pixel})
    return result


def _pdf_text_legend_candidates(element: dict[str, Any], index: dict[str, Any], plot_area: list[int]) -> list[dict[str, Any]]:
    x0, y0, x1, y1 = [float(v) for v in plot_area]
    width = max(1.0, x1 - x0)
    height = max(1.0, y1 - y0)
    candidates: list[dict[str, Any]] = []
    for block in _pdf_text_blocks_with_pixels(element, index):
        text = _clean_legend_text(str(block.get("text") or ""))
        if not text:
            continue
        px, py = block.get("pixel") or [0.0, 0.0]
        px = float(px)
        py = float(py)
        right_side = x1 - width * 0.05 <= px <= x1 + max(90.0, width * 0.45) and y0 - height * 0.08 <= py <= y1 + height * 0.08
        inside_corner = x0 + width * 0.52 <= px <= x1 and y0 <= py <= y0 + height * 0.42
        if right_side or inside_corner:
            candidates.append(
                {
                    "text": text,
                    "pixel": [px, py],
                    "source": "pdf_text",
                    "confidence": 0.58 if right_side else 0.50,
                }
            )
    unique: list[dict[str, Any]] = []
    for item in candidates:
        if item["text"] not in {existing["text"] for existing in unique}:
            unique.append(item)
    return unique[:8]


def _clean_legend_text(text: str) -> str:
    value = re.sub(r"\s+", " ", str(text or "")).strip()
    if not value or len(value) > 64:
        return ""
    if _parse_tick_value(value) is not None and re.fullmatch(r"\s*[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?\s*", value):
        return ""
    if re.match(r"^(fig(?:ure)?|table)\b", value, re.IGNORECASE):
        return ""
    if len(re.findall(r"[A-Za-z\u4e00-\u9fff]", value)) < 2:
        return ""
    return value


def _page_text_blocks(index: dict[str, Any], page: int) -> list[dict[str, Any]]:
    pages = index.get("pages") if isinstance(index, dict) else None
    if not isinstance(pages, list):
        return []
    for entry in pages:
        if isinstance(entry, dict) and int(entry.get("page") or 0) == int(page):
            blocks = entry.get("textBlocks")
            return [dict(item) for item in blocks or [] if isinstance(item, dict)] if isinstance(blocks, list) else []
    return []


def _parse_tick_value(text: str) -> float | None:
    value = str(text or "").strip()
    if not value or len(value) > 24:
        return None
    if re.search(r"[A-Za-z]{2,}", value):
        return None
    match = NUMERIC_TEXT_PATTERN.search(value.replace("−", "-"))
    if not match:
        return None
    try:
        return float(match.group(0))
    except (TypeError, ValueError):
        return None


def _select_axis_ticks(candidates: list[dict[str, Any]], plot_area: list[int], axis_name: str) -> list[dict[str, Any]]:
    x0, y0, x1, y1 = [float(v) for v in plot_area]
    width = max(1.0, x1 - x0)
    height = max(1.0, y1 - y0)
    selected: list[dict[str, Any]] = []
    for item in candidates:
        px, py = item.get("pixel") or [0.0, 0.0]
        px = float(px)
        py = float(py)
        if axis_name == "x":
            near_bottom = y1 - height * 0.03 <= py <= y1 + max(28.0, height * 0.22)
            inside_x = x0 - width * 0.08 <= px <= x1 + width * 0.08
            if near_bottom and inside_x:
                selected.append(item)
        else:
            near_left = x0 - max(42.0, width * 0.24) <= px <= x0 + width * 0.08
            inside_y = y0 - height * 0.08 <= py <= y1 + height * 0.08
            if near_left and inside_y:
                selected.append(item)
    coord = (lambda item: float((item.get("pixel") or [0, 0])[0])) if axis_name == "x" else (lambda item: float((item.get("pixel") or [0, 0])[1]))
    ordered = sorted(selected, key=coord)
    unique: list[dict[str, Any]] = []
    for item in ordered:
        if any(abs(coord(item) - coord(existing)) <= 2.0 or abs(float(item.get("value")) - float(existing.get("value"))) <= 1e-12 for existing in unique):
            continue
        unique.append(item)
    if len(unique) < 2:
        return []
    return [unique[0], unique[-1]]


def _axis_from_ticks(ticks: list[dict[str, Any]], axis_name: str) -> dict[str, Any]:
    first, second = ticks[0], ticks[-1]
    return {
        "scale": "linear",
        "source": "pdf_text",
        "confidence": 0.78,
        "calibration": [
            {"pixel": [float(first["pixel"][0]), float(first["pixel"][1])], "value": float(first["value"]), "text": str(first.get("text") or "")},
            {"pixel": [float(second["pixel"][0]), float(second["pixel"][1])], "value": float(second["value"]), "text": str(second.get("text") or "")},
        ],
    }


def _series_seeds_from_calibration(calibration: dict[str, Any]) -> list[dict[str, Any]]:
    seeds = calibration.get("seriesSeeds") if isinstance(calibration, dict) else None
    if not isinstance(seeds, list):
        return []
    result: list[dict[str, Any]] = []
    for index, seed in enumerate(seeds):
        if not isinstance(seed, dict):
            continue
        pixel = seed.get("pixel")
        if not isinstance(pixel, (list, tuple)) or len(pixel) < 2:
            continue
        try:
            result.append(
                {
                    "pixel": [float(pixel[0]), float(pixel[1])],
                    "name": str(seed.get("name") or f"Series {index + 1}"),
                }
            )
        except (TypeError, ValueError):
            continue
    return result


def _extract_series(image: Any, plot_area: list[int], series_seeds: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    x0, y0, x1, y1 = _clip_region(plot_area, _image_width(image), _image_height(image))
    buckets: dict[str, list[tuple[int, int]]] = {}
    color_values: dict[str, list[tuple[int, int, int]]] = {}
    for y in range(y0, y1):
        for x in range(x0, x1):
            if x <= x0 + 2 or y >= y1 - 2:
                continue
            rgb = _rgb(image, x, y)
            if not _looks_like_curve_pixel(rgb):
                continue
            key = _color_bucket(rgb)
            buckets.setdefault(key, []).append((x, y))
            color_values.setdefault(key, []).append(rgb)

    seed_by_bucket: dict[str, dict[str, Any]] = {}
    for seed in series_seeds or []:
        pixel = seed.get("pixel") or []
        if len(pixel) < 2:
            continue
        sx = int(round(float(pixel[0])))
        sy = int(round(float(pixel[1])))
        if sx < x0 or sx >= x1 or sy < y0 or sy >= y1:
            continue
        seed_key = _color_bucket(_rgb(image, sx, sy))
        if seed_key not in buckets:
            seed_key = _nearest_bucket_for_seed(image, sx, sy, buckets)
        if seed_key and seed_key in buckets and seed_key not in seed_by_bucket:
            seed_by_bucket[seed_key] = {"name": seed.get("name") or "", "pixel": [float(pixel[0]), float(pixel[1])]}

    candidates: list[dict[str, Any]] = []
    min_coverage = max(8, int((x1 - x0) * 0.12))
    for key, pixels in buckets.items():
        if series_seeds and key not in seed_by_bucket:
            continue
        pixels = _remove_grid_like_pixels(pixels, plot_area)
        columns = {x for x, _ in pixels}
        if len(columns) < min_coverage or len(pixels) < min_coverage * 2:
            continue
        compact = _curve_by_column(pixels)
        if len(compact) < min_coverage:
            continue
        filtered_colors = [_rgb(image, x, y) for x, y in pixels[:: max(1, len(pixels) // 1200)]]
        candidates.append(
            {
                "pixels": compact,
                "colorBucket": key,
                "color": _average_color_hex(filtered_colors or color_values.get(key) or []),
                "confidence": min(0.92, 0.42 + len(compact) / max(1.0, (x1 - x0)) * 0.55),
                "name": (seed_by_bucket.get(key) or {}).get("name") or "",
                "seedPixel": (seed_by_bucket.get(key) or {}).get("pixel") or [],
            }
        )
    candidates.sort(key=lambda item: len(item["pixels"]), reverse=True)
    return candidates[:6]


def _apply_legend_candidates_to_curves(
    image: Any,
    plot_area: list[int],
    curves: list[dict[str, Any]],
    legend_candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not curves or not legend_candidates:
        return curves
    bucket_to_indices: dict[str, list[int]] = {}
    for index, curve in enumerate(curves):
        key = str(curve.get("colorBucket") or "")
        if key:
            bucket_to_indices.setdefault(key, []).append(index)
    assigned: set[int] = set()
    for candidate in sorted(legend_candidates, key=lambda item: float(item.get("confidence") or 0.0), reverse=True):
        text = str(candidate.get("text") or "").strip()
        if not text:
            continue
        key = _legend_candidate_color_bucket(image, candidate, plot_area)
        indices = bucket_to_indices.get(key or "", [])
        if len(indices) != 1 or indices[0] in assigned:
            continue
        curve = curves[indices[0]]
        if curve.get("name"):
            continue
        curve["name"] = text
        curve["nameSource"] = "pdf_text_legend"
        curve["legendCandidate"] = {
            "text": text,
            "pixel": candidate.get("pixel") or [],
            "source": candidate.get("source") or "pdf_text",
            "confidence": candidate.get("confidence") or 0.0,
        }
        curve["confidence"] = _clamp(float(curve.get("confidence") or 0.0) + 0.03)
        assigned.add(indices[0])
    return curves


def _legend_candidate_color_bucket(image: Any, candidate: dict[str, Any], plot_area: list[int]) -> str:
    pixel = candidate.get("pixel") if isinstance(candidate, dict) else None
    if not isinstance(pixel, (list, tuple)) or len(pixel) < 2:
        return ""
    width = _image_width(image)
    height = _image_height(image)
    try:
        px = int(round(float(pixel[0])))
        py = int(round(float(pixel[1])))
    except (TypeError, ValueError):
        return ""
    x0 = max(0, px - 58)
    x1 = min(width, px - 3)
    y0 = max(0, py - 14)
    y1 = min(height, py + 15)
    if x1 <= x0 or y1 <= y0:
        return ""
    counts: Counter[str] = Counter()
    for y in range(y0, y1):
        for x in range(x0, x1):
            if _is_near_plot_axis(x, y, plot_area):
                continue
            rgb = _rgb(image, x, y)
            if _looks_like_curve_pixel(rgb):
                counts[_color_bucket(rgb)] += 1
    if not counts:
        return ""
    top_key, top_count = counts.most_common(1)[0]
    second_count = counts.most_common(2)[1][1] if len(counts) > 1 else 0
    if top_count < 3 or top_count < max(3, second_count * 1.4):
        return ""
    return top_key


def _is_near_plot_axis(x: int, y: int, plot_area: list[int]) -> bool:
    x0, _y0, _x1, y1 = [int(v) for v in plot_area]
    return abs(int(x) - x0) <= 2 or abs(int(y) - y1) <= 2


def _nearest_bucket_for_seed(image: Any, sx: int, sy: int, buckets: dict[str, list[tuple[int, int]]]) -> str:
    best_key = ""
    best_distance = 999999.0
    for key, pixels in buckets.items():
        for x, y in pixels[:2000]:
            distance = (float(x) - sx) ** 2 + (float(y) - sy) ** 2
            if distance < best_distance:
                best_distance = distance
                best_key = key
    return best_key if best_distance <= 36.0 else ""


def _curve_by_column(pixels: list[tuple[int, int]]) -> list[tuple[int, int]]:
    columns: dict[int, list[int]] = {}
    for x, y in pixels:
        columns.setdefault(int(x), []).append(int(y))
    compact: list[tuple[int, int]] = []
    for x in sorted(columns):
        ys = columns[x]
        if not ys:
            continue
        compact.append((x, int(statistics.median(ys))))
    return compact


def _remove_grid_like_pixels(pixels: list[tuple[int, int]], plot_area: list[int]) -> list[tuple[int, int]]:
    if not pixels:
        return []
    x0, y0, x1, y1 = [int(v) for v in plot_area]
    width = max(1, x1 - x0)
    height = max(1, y1 - y0)
    row_counts: dict[int, int] = {}
    col_counts: dict[int, int] = {}
    for x, y in pixels:
        row_counts[y] = row_counts.get(y, 0) + 1
        col_counts[x] = col_counts.get(x, 0) + 1
    grid_rows = {row for row, count in row_counts.items() if count >= width * 0.46}
    grid_cols = {col for col, count in col_counts.items() if count >= height * 0.46}
    if not grid_rows and not grid_cols:
        return pixels
    return [(x, y) for x, y in pixels if y not in grid_rows and x not in grid_cols]


def _sample_curve(pixels: list[tuple[int, int]], plot_area: list[int], axes: dict[str, Any], sample_count: int) -> list[dict[str, Any]]:
    if not pixels:
        return [make_point(i, None, None, [], confidence=0.0, missing=True) for i in range(sample_count)]
    by_x = {int(x): int(y) for x, y in pixels}
    xs = sorted(by_x)
    min_x, max_x = float(plot_area[0]), float(plot_area[2])
    points: list[dict[str, Any]] = []
    window = max(2, int((max_x - min_x) / max(12, sample_count * 2)))
    for index in range(sample_count):
        target_x = min_x if sample_count == 1 else min_x + (max_x - min_x) * index / max(1, sample_count - 1)
        pixel_y, missing, pixel_conf = _interpolate_y(xs, by_x, target_x, window)
        pixel = [target_x, pixel_y] if pixel_y is not None else []
        data_x = _map_axis_value(axes["x"], target_x)
        data_y = _map_axis_value(axes["y"], pixel_y) if pixel_y is not None else None
        points.append(make_point(index, data_x, data_y, pixel, confidence=pixel_conf, missing=missing))
    return points


def _interpolate_y(xs: list[int], by_x: dict[int, int], target_x: float, window: int) -> tuple[float | None, bool, float]:
    nearby = [by_x[x] for x in xs if abs(float(x) - target_x) <= window]
    if nearby:
        return float(statistics.median(nearby)), False, 0.88
    left = max((x for x in xs if x < target_x), default=None)
    right = min((x for x in xs if x > target_x), default=None)
    if left is None or right is None:
        return None, True, 0.0
    gap = right - left
    if gap > window * 8:
        return None, True, 0.20
    ratio = (target_x - left) / max(1.0, gap)
    return float(by_x[left] + (by_x[right] - by_x[left]) * ratio), False, 0.68


def _map_axis_value(axis: dict[str, Any], pixel_coord: float | None) -> float | None:
    if pixel_coord is None:
        return None
    calibration = axis.get("calibration") if isinstance(axis, dict) else None
    if not isinstance(calibration, list) or len(calibration) < 2:
        return None
    first, second = calibration[0], calibration[1]
    p1 = first.get("pixel") if isinstance(first, dict) else None
    p2 = second.get("pixel") if isinstance(second, dict) else None
    if not isinstance(p1, (list, tuple)) or not isinstance(p2, (list, tuple)) or len(p1) < 2 or len(p2) < 2:
        return None
    v1 = float(first.get("value"))
    v2 = float(second.get("value"))
    if abs(float(p2[0]) - float(p1[0])) >= abs(float(p2[1]) - float(p1[1])):
        denom = float(p2[0]) - float(p1[0])
        pixel_start = float(p1[0])
    else:
        denom = float(p2[1]) - float(p1[1])
        pixel_start = float(p1[1])
    if abs(denom) < 1e-9:
        return None
    return v1 + (float(pixel_coord) - pixel_start) / denom * (v2 - v1)


def _has_curve_pixels(image: Any, plot_area: list[int]) -> bool:
    x0, y0, x1, y1 = _clip_region(plot_area, _image_width(image), _image_height(image))
    total = 0
    for y in range(y0, y1, 2):
        for x in range(x0, x1, 2):
            if _looks_like_curve_pixel(_rgb(image, x, y)):
                total += 1
    return total >= max(8, int((x1 - x0) * 0.06))


def _looks_like_curve_pixel(rgb: tuple[int, int, int]) -> bool:
    r, g, b = rgb
    lum = 0.299 * r + 0.587 * g + 0.114 * b
    maxc = max(r, g, b)
    minc = min(r, g, b)
    saturation = maxc - minc
    if lum > 246:
        return False
    if saturation >= 40 and lum < 235:
        return True
    if saturation < 28 and lum < 190:
        return True
    return lum < 95


def _is_dark(image: Any, x: int, y: int) -> bool:
    r, g, b = _rgb(image, x, y)
    return 0.299 * r + 0.587 * g + 0.114 * b < 92


def _rgb(image: Any, x: int, y: int) -> tuple[int, int, int]:
    if QColor is None:
        return 255, 255, 255
    color = QColor(image.pixel(int(x), int(y)))
    return int(color.red()), int(color.green()), int(color.blue())


def _color_bucket(rgb: tuple[int, int, int]) -> str:
    r, g, b = rgb
    lum = 0.299 * r + 0.587 * g + 0.114 * b
    if max(rgb) - min(rgb) < 34 or lum < 95:
        return "gray"
    return f"{round(r / 48)},{round(g / 48)},{round(b / 48)}"


def _average_color_hex(values: list[tuple[int, int, int]]) -> str:
    if not values:
        return "#444444"
    r = int(sum(item[0] for item in values) / len(values))
    g = int(sum(item[1] for item in values) / len(values))
    b = int(sum(item[2] for item in values) / len(values))
    return f"#{r:02x}{g:02x}{b:02x}"


def _clip_region(region: list[int] | tuple[int, ...], width: int, height: int) -> list[int]:
    bbox = _bbox_int(region) or [0, 0, width, height]
    x0 = max(0, min(width - 1, bbox[0]))
    y0 = max(0, min(height - 1, bbox[1]))
    x1 = max(x0 + 1, min(width, bbox[2]))
    y1 = max(y0 + 1, min(height, bbox[3]))
    return [x0, y0, x1, y1]


def _bbox_int(value: Any) -> list[int]:
    if not isinstance(value, (list, tuple)) or len(value) < 4:
        return []
    try:
        x0, y0, x1, y1 = [int(round(float(item))) for item in value[:4]]
    except (TypeError, ValueError):
        return []
    if x1 <= x0 or y1 <= y0:
        return []
    return [x0, y0, x1, y1]


def _bbox_float(value: Any) -> list[float]:
    if not isinstance(value, (list, tuple)) or len(value) < 4:
        return []
    try:
        x0, y0, x1, y1 = [float(item) for item in value[:4]]
    except (TypeError, ValueError):
        return []
    if x1 <= x0 or y1 <= y0:
        return []
    return [x0, y0, x1, y1]


def _subplot_needs_review(subplot: dict[str, Any]) -> bool:
    return bool(subplot.get("needsReview")) or not subplot.get("series")


def _dedupe_strings(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def _clamp(value: Any) -> float:
    try:
        if math.isnan(float(value)):
            return 0.0
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0
