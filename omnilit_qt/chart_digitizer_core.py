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

try:
    from PIL import Image as PillowImage
except Exception:  # pragma: no cover - Pillow is an optional headless fallback.
    PillowImage = None

from .chart_digitizer_schema import (
    CALIBRATED_AXIS_SOURCES,
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

try:
    from .chart_digitizer_ocr import image_axis_calibration, image_marker_series
except Exception:  # pragma: no cover - OpenCV OCR is optional.
    image_axis_calibration = None
    image_marker_series = None


LINE_CHART_HINTS = re.compile(
    r"\b(line|curve|trend|spectrum|spectra|rate|time|temperature|voltage|current|"
    r"intensity|profile|response|kinetic)\b",
    re.IGNORECASE,
)
NON_LINE_HINTS = re.compile(
    r"\b(photo|photograph(?:s|ic)?|microscopy|sem|tem|schematic|table|workflow|flowchart|structure|boxplot|"
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
    calibration = calibration if isinstance(calibration, dict) else {}
    chart_type, type_confidence, type_warnings = classify_chart_candidate(element, image, index)
    if chart_type != "line_chart" and image is not None and _manual_axis_gate(calibration):
        chart_type = "line_chart"
        type_confidence = max(type_confidence, 0.86)
        type_warnings = ["使用人工确认的子图/绘图区通过坐标轴门控。"]
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

    manual_regions = _manual_subplot_regions(calibration)
    subplot_regions = manual_regions or _detect_subplot_regions(image)
    subplots: list[dict[str, Any]] = []
    warnings = list(type_warnings)
    confidences = [type_confidence]
    for subplot_index, region in enumerate(subplot_regions):
        subplot_calibration = _calibration_for_subplot(calibration, subplot_index)
        subplot = _analyze_subplot(image, region, subplot_index, count, subplot_calibration, element, index)
        subplots.append(subplot)
        confidences.append(float(subplot.get("confidence") or 0.0))
        warnings.extend(str(item) for item in subplot.get("warnings") or [])

    subplots = _propagate_shared_axes(subplots)
    subplots = _propagate_shared_axes(subplots)
    warnings = list(type_warnings)
    for item in subplots:
        warnings.extend(str(warning) for warning in item.get("warnings") or [])

    confidence = _clamp(sum(confidences) / len(confidences) if confidences else 0.0)
    needs_review = confidence < 0.62 or any(_subplot_needs_review(item) for item in subplots)
    if needs_review and not any("手动校准" in item for item in warnings):
        warnings.append("需要手动校准。")

    return {
        "schemaVersion": SCHEMA_VERSION,
        "source": build_source_metadata(element, index, record_id),
        "analysis": {
            "chartType": "line_chart",
            "eligible": True,
            "createdAt": utc_now_iso(),
            "engine": ENGINE_NAME,
            "sampleCount": count,
            "confidence": confidence,
            "needsReview": bool(needs_review),
            "status": "需要手动校准" if needs_review else "自动结果",
            "warnings": _dedupe_strings(warnings),
            "pipeline": [
                {"stage": "axis_gate", "status": "passed", "confidence": type_confidence},
                {"stage": "subplot_split", "status": "manual" if manual_regions else "automatic", "count": len(subplots)},
                {"stage": "axis_calibration", "status": "review" if any(_subplot_needs_review(item) for item in subplots) else "passed"},
                {"stage": "curve_sampling", "status": "review" if needs_review else "passed"},
                {"stage": "data_export", "status": "ready"},
            ],
        },
        "subplots": subplots,
    }


def classify_chart_candidate(
    element: dict[str, Any], image: Any = None, index: dict[str, Any] | None = None
) -> tuple[str, float, list[str]]:
    caption = str(element.get("caption") or element.get("text") or "")
    lower = caption.lower()
    warnings: list[str] = []
    if image is None:
        return "unknown", 0.0, ["图像文件不可读取，无法执行坐标轴门控。"]
    if _is_degenerate_image(image):
        return "unsupported", 0.98, ["图像内容接近全黑/空白，无法形成有效坐标图，已跳过。"]
    if _looks_like_table_grid(image):
        return "unsupported", 0.90, ["检测到表格网格拓扑而不是坐标轴，已跳过图数据分析。"]

    # Geometry is the hard gate. Caption text is supporting evidence only.
    axes = _detect_axes(image, [0, 0, _image_width(image), _image_height(image)])
    axis_confidence = float(axes.get("confidence") or 0.0)
    if axis_confidence < 0.43:
        return "unsupported", _clamp(axis_confidence), ["未检测到成对且连续的坐标轴，已跳过图数据分析。"]
    tick_score = float((axes.get("geometry") or {}).get("tickScore") or 0.0)
    x_tick_count = int((axes.get("geometry") or {}).get("xTickCount") or 0)
    y_tick_count = int((axes.get("geometry") or {}).get("yTickCount") or 0)
    horizontal_continuity = float((axes.get("geometry") or {}).get("horizontalContinuity") or 0.0)
    vertical_continuity = float((axes.get("geometry") or {}).get("verticalContinuity") or 0.0)
    intersection = bool((axes.get("geometry") or {}).get("intersection"))
    text_axes = _pdf_text_calibration(element, index or {}, axes.get("plot_area") or [])
    text_axis_pair = bool(text_axes.get("xAxis") and text_axes.get("yAxis"))
    strong_axis_pair = intersection and min(horizontal_continuity, vertical_continuity) >= 0.68
    geometry_axis_pair = (x_tick_count >= 1 and y_tick_count >= 1) or strong_axis_pair
    if not geometry_axis_pair:
        return "unsupported", _clamp(axis_confidence * 0.72), ["检测到边框或比例尺，但没有同时检测到 x、y 轴刻度，已跳过。"]
    if min(horizontal_continuity, vertical_continuity) < 0.22:
        return "unsupported", _clamp(axis_confidence * 0.75), ["坐标轴连续长度不足，疑似正文边界、比例尺或残缺图，已跳过。"]
    if tick_score < 0.24 and not text_axis_pair:
        return "unsupported", _clamp(axis_confidence * 0.72), ["检测到边框状直线，但缺少坐标轴刻度证据，已跳过。"]
    if not _has_curve_pixels(image, axes.get("plot_area") or []):
        return "unsupported", _clamp(axis_confidence * 0.75), ["检测到坐标轴，但未检测到可采样的连续曲线，已跳过。"]
    if NON_LINE_HINTS.search(lower):
        if not LINE_CHART_HINTS.search(lower):
            return "unsupported", _clamp(axis_confidence * 0.82), ["caption 明确描述照片、显微图或示意图，且没有曲线证据，已跳过。"]
        if tick_score < 0.48:
            return "unsupported", _clamp(axis_confidence * 0.75), ["caption 与刻度证据均表明该图不是曲线图，已跳过。"]
        warnings.append("caption 包含照片/显微图描述，后续仅保留具有可标定坐标轴的曲线面板。")
    caption_bonus = 0.08 if LINE_CHART_HINTS.search(lower) else 0.0
    return "line_chart", _clamp(axis_confidence * 0.82 + 0.10 + caption_bonus), warnings


def _manual_axis_gate(calibration: dict[str, Any]) -> bool:
    if not isinstance(calibration, dict):
        return False
    if _bbox_int(calibration.get("plotAreaPx") or calibration.get("plotArea")):
        return True
    subplots = calibration.get("subplots")
    if not isinstance(subplots, list):
        return False
    return any(
        isinstance(item, dict)
        and bool(_bbox_int(item.get("plotAreaPx") or item.get("plotArea") or item.get("bboxPx") or item.get("bbox")))
        for item in subplots
    )


def _looks_like_table_grid(image: Any) -> bool:
    width = _image_width(image)
    height = _image_height(image)
    horizontal = 0
    last_y = -10
    for y in range(3, height - 3):
        start, end = _longest_dark_run(image, y, 2, width - 2, horizontal=True)
        if end - start >= width * 0.60 and y - last_y > 4:
            horizontal += 1
            last_y = y
    vertical = 0
    last_x = -10
    for x in range(3, width - 3):
        start, end = _longest_dark_run(image, x, 2, height - 2, horizontal=False)
        if end - start >= height * 0.20 and x - last_x > 4:
            vertical += 1
            last_x = x
    return horizontal >= 3 and vertical >= 3


def _is_degenerate_image(image: Any) -> bool:
    width = _image_width(image)
    height = _image_height(image)
    dark = 0
    light = 0
    total = 0
    step = max(2, min(width, height) // 120)
    for y in range(0, height, step):
        for x in range(0, width, step):
            r, g, b = _rgb(image, x, y)
            luminance = 0.299 * r + 0.587 * g + 0.114 * b
            dark += int(luminance < 12)
            light += int(luminance > 252)
            total += 1
    return total > 0 and (dark / total >= 0.88 or light / total >= 0.997)


def _subplot_has_calibrated_axis(subplot: dict[str, Any]) -> bool:
    axes = subplot.get("axes") if isinstance(subplot, dict) else {}
    return all(str((axes.get(axis) or {}).get("source") or "") in CALIBRATED_AXIS_SOURCES for axis in ("x", "y"))


def _reindex_subplots(subplots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for index, subplot in enumerate(subplots):
        item = dict(subplot)
        coordinate_id = f"axes_{index + 1}"
        item["subplotId"] = f"subplot_{index + 1}"
        item["coordinateSystemId"] = coordinate_id
        item["label"] = chr(ord("a") + index) if index < 26 else str(index + 1)
        series: list[dict[str, Any]] = []
        for series_index, entry in enumerate(item.get("series") or []):
            series_item = dict(entry)
            series_item["seriesId"] = f"series_{series_index + 1}"
            series_item["coordinateSystemId"] = coordinate_id
            series.append(series_item)
        item["series"] = series
        result.append(item)
    return result


def _propagate_shared_axes(subplots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = [dict(item) for item in subplots]
    for item in result:
        axes = dict(item.get("axes") or {})
        y_axis = dict(axes.get("y") or {})
        series_text = " ".join(str(series.get("name") or "") for series in item.get("series") or []).lower().replace(" ", "")
        if str(y_axis.get("source") or "") not in CALIBRATED_AXIS_SOURCES and "a.u" in series_text:
            area = item.get("plotAreaPx") or []
            if len(area) >= 4:
                x0, y0, x1, y1 = [float(value) for value in area]
                axes["y"] = make_axis(
                    label="Intensity (a.u.)",
                    scale="linear",
                    minimum=0.0,
                    maximum=1.0,
                    calibration=[{"pixel": [x0, y1], "value": 0.0}, {"pixel": [x0, y0], "value": 1.0}],
                    source="normalized_arbitrary_units",
                    confidence=0.80,
                )
                item["axes"] = axes
    for axis_name in ("x", "y"):
        donors = [
            item for item in result
            if str((((item.get("axes") or {}).get(axis_name) or {}).get("source") or "")) in CALIBRATED_AXIS_SOURCES
        ]
        for item in result:
            axes = dict(item.get("axes") or {})
            current = dict(axes.get(axis_name) or {})
            if str(current.get("source") or "") in CALIBRATED_AXIS_SOURCES:
                continue
            area = item.get("plotAreaPx") or []
            if len(area) < 4:
                continue
            same_dimension = []
            for donor in donors:
                donor_area = donor.get("plotAreaPx") or []
                if len(donor_area) < 4:
                    continue
                if axis_name == "x":
                    center_delta = abs((area[0] + area[2]) - (donor_area[0] + donor_area[2])) / 2.0
                    span = max(1.0, area[2] - area[0], donor_area[2] - donor_area[0])
                else:
                    center_delta = abs((area[1] + area[3]) - (donor_area[1] + donor_area[3])) / 2.0
                    span = max(1.0, area[3] - area[1], donor_area[3] - donor_area[1])
                if center_delta <= span * 0.16:
                    same_dimension.append((center_delta, donor))
            if not same_dimension:
                continue
            donor = min(same_dimension, key=lambda value: value[0])[1]
            shared = dict(((donor.get("axes") or {}).get(axis_name) or {}))
            shared["source"] = "shared_subplot_axis"
            shared["confidence"] = min(0.90, float(shared.get("confidence") or 0.0) * 0.96)
            axes[axis_name] = shared
            item["axes"] = axes
            for series in item.get("series") or []:
                for point in series.get("points") or []:
                    pixel = point.get("pixel") or []
                    if len(pixel) >= 2:
                        coordinate = float(pixel[0] if axis_name == "x" else pixel[1])
                        point[axis_name] = _map_axis_value(shared, coordinate)
            item["warnings"] = [
                warning for warning in item.get("warnings") or []
                if "坐标轴" not in str(warning) and "手动校准" not in str(warning)
            ]
            item["needsReview"] = (
                float(item.get("confidence") or 0.0) < 0.62
                or any(bool(series.get("needsReview")) for series in item.get("series") or [])
                or any(str((axes.get(axis) or {}).get("source") or "") == "auto_geometry_preview" for axis in ("x", "y"))
            )
    for item in result:
        axes = item.get("axes") or {}
        if not all(str((axes.get(axis) or {}).get("source") or "") in CALIBRATED_AXIS_SOURCES for axis in ("x", "y")):
            continue
        series_items = list(item.get("series") or [])
        for series in series_items:
            missing = sum(1 for point in series.get("points") or [] if point.get("missing"))
            confidence = float(series.get("confidence") or 0.0)
            domain = float(series.get("domainCoverage") or 0.0)
            series["needsReview"] = confidence < 0.55 or missing > 0 or domain < 0.18
            if not series["needsReview"]:
                series["warnings"] = []
        strong = [series for series in series_items if not series.get("needsReview")]
        if len(strong) >= 2:
            series_items = [series for series in series_items if not series.get("needsReview") or series.get("seedPixel")]
            for series_index, series in enumerate(series_items):
                series["seriesId"] = f"series_{series_index + 1}"
        item["series"] = series_items
        item["needsReview"] = float(item.get("confidence") or 0.0) < 0.62 or any(series.get("needsReview") for series in series_items)
        if not item["needsReview"]:
            item["warnings"] = [warning for warning in item.get("warnings") or [] if "手动校准" not in str(warning)]
    return result


def _repair_sparse_series_points(series: dict[str, Any], axes: dict[str, Any]) -> None:
    points = list(series.get("points") or [])
    missing_indices = [index for index, point in enumerate(points) if point.get("missing")]
    if not points or len(missing_indices) > max(2, int(len(points) * 0.20)):
        return
    for index in missing_indices:
        left = next((points[position] for position in range(index - 1, -1, -1) if not points[position].get("missing") and points[position].get("pixel")), None)
        right = next((points[position] for position in range(index + 1, len(points)) if not points[position].get("missing") and points[position].get("pixel")), None)
        neighbors = [point for point in (left, right) if point is not None]
        if not neighbors:
            continue
        pixel_x = sum(float(point["pixel"][0]) for point in neighbors) / len(neighbors)
        pixel_y = sum(float(point["pixel"][1]) for point in neighbors) / len(neighbors)
        if points[index].get("x") is not None:
            pixel_x = float(points[index]["pixel"][0]) if points[index].get("pixel") else pixel_x
        points[index] = make_point(
            index,
            _map_axis_value(axes["x"], pixel_x),
            _map_axis_value(axes["y"], pixel_y),
            [pixel_x, pixel_y],
            confidence=0.42,
            missing=False,
        )
    series["points"] = points


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
    caption = str((element or {}).get("caption") or (element or {}).get("text") or "")
    image_calibration = (
        image_axis_calibration(image, plot_area, region, allow_empty_enlargement=not bool(NON_LINE_HINTS.search(caption)))
        if image_axis_calibration is not None
        else {}
    )
    if not image_calibration.get("yAxis"):
        arbitrary_label = next(
            (str(item.get("text") or "") for item in legend_candidates if "a.u" in str(item.get("text") or "").lower().replace(" ", "")),
            "",
        )
        if arbitrary_label:
            x0, y0, x1, y1 = [float(value) for value in plot_area]
            image_calibration["yAxis"] = {
                "label": arbitrary_label,
                "scale": "linear",
                "source": "normalized_arbitrary_units",
                "confidence": 0.80,
                "calibration": [
                    {"pixel": [x0, y1], "value": 0.0, "text": "normalized minimum"},
                    {"pixel": [x0, y0], "value": 1.0, "text": "normalized maximum"},
                ],
            }
    if text_calibration.get("warnings"):
        axes_info.setdefault("warnings", []).extend(text_calibration.get("warnings") or [])
    if _axis_from_payload(effective_calibration.get("xAxis") or effective_calibration.get("x"), plot_area, "x") is None:
        if text_calibration.get("xAxis"):
            effective_calibration["xAxis"] = text_calibration["xAxis"]
        elif image_calibration.get("xAxis"):
            effective_calibration["xAxis"] = image_calibration["xAxis"]
    if _axis_from_payload(effective_calibration.get("yAxis") or effective_calibration.get("y"), plot_area, "y") is None:
        if text_calibration.get("yAxis"):
            effective_calibration["yAxis"] = text_calibration["yAxis"]
        elif image_calibration.get("yAxis"):
            effective_calibration["yAxis"] = image_calibration["yAxis"]
    series_seeds = _series_seeds_from_calibration(calibration)
    curves = _extract_series(image, plot_area, series_seeds)
    if not curves and not series_seeds and image_marker_series is not None:
        curves = image_marker_series(image, plot_area)
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
        points = (
            _points_from_markers(curve["pixels"], axes)
            if curve.get("markerSeries")
            else _sample_curve(curve["pixels"], plot_area, axes, sample_count)
        )
        missing_count = sum(1 for point in points if point.get("missing"))
        missing_ratio = missing_count / max(1, len(points))
        domain_coverage = float(curve.get("domainCoverage") or 0.0)
        series_warnings: list[str] = []
        if missing_count:
            series_warnings.append("曲线在部分 x 位置断裂或没有可靠交点，缺失点已标记为 missing。")
        if domain_coverage < 0.18:
            series_warnings.append("曲线有效 x 范围过短，可能只是标注、误差棒或局部残片。")
        coverage_quality = 0.58 if domain_coverage < 0.18 else 1.0
        series_confidence = _clamp(curve.get("confidence", 0.0) * axis_quality * coverage_quality * max(0.35, 1.0 - missing_ratio * 0.9))
        series_confidences.append(series_confidence)
        series_entries.append(
            {
                "seriesId": f"series_{series_index + 1}",
                "coordinateSystemId": f"axes_{subplot_index + 1}",
                "name": curve.get("name") or f"Series {series_index + 1}",
                "nameSource": curve.get("nameSource") or ("manual_seed" if curve.get("name") else "default"),
                "color": curve.get("color") or "#444444",
                "confidence": series_confidence,
                "needsReview": series_confidence < 0.62 or missing_count > 0 or domain_coverage < 0.18,
                "warnings": series_warnings,
                "seedPixel": curve.get("seedPixel") or [],
                "legendCandidate": curve.get("legendCandidate") or {},
                "domainCoverage": domain_coverage,
                "markerSeries": bool(curve.get("markerSeries")),
                "points": points,
            }
        )
    strong_series = [item for item in series_entries if not item.get("needsReview")]
    if len(strong_series) >= 2:
        series_entries = [
            item for item in series_entries
            if float(item.get("domainCoverage") or 0.0) >= 0.18 or item.get("seedPixel")
        ]
        for series_index, item in enumerate(series_entries):
            item["seriesId"] = f"series_{series_index + 1}"
        series_confidences = [float(item.get("confidence") or 0.0) for item in series_entries]
    if series_confidences:
        confidence = _clamp((axis_quality * 0.45) + (sum(series_confidences) / len(series_confidences) * 0.55))
    else:
        confidence = _clamp(axis_quality * 0.45)
    return {
        "subplotId": f"subplot_{subplot_index + 1}",
        "coordinateSystemId": f"axes_{subplot_index + 1}",
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
    if all(source in CALIBRATED_AXIS_SOURCES for source in sources):
        confidences = [float((axes.get(axis) or {}).get("confidence") or 0.0) for axis in ("x", "y")]
        return _clamp(max(float(axes_info.get("confidence") or 0.0), min(confidences or [0.0])))
    return _clamp(float(axes_info.get("confidence") or 0.0))


def _axis_warnings_for_effective_axes(axes: dict[str, Any], warnings: list[str]) -> list[str]:
    sources = [str((axes.get(axis) or {}).get("source") or "") for axis in ("x", "y")]
    if all(source in CALIBRATED_AXIS_SOURCES for source in sources):
        return [warning for warning in warnings if "坐标轴" not in warning and "手动校准" not in warning]
    return warnings


def _load_image(path: Path) -> Any:
    if not path.exists():
        return None
    if QImage is not None:
        image = QImage(str(path))
        if not image.isNull():
            return image.convertToFormat(QImage.Format_RGB32)
    if PillowImage is not None:
        try:
            return PillowImage.open(path).convert("RGB")
        except Exception:
            return None
    return None


def _image_width(image: Any) -> int:
    value = getattr(image, "width", 0)
    return int(value() if callable(value) else value)


def _image_height(image: Any) -> int:
    value = getattr(image, "height", 0)
    return int(value() if callable(value) else value)


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
    axis_frames = _detect_axis_frame_regions(image)
    candidate_sets: list[list[list[int]]] = []
    completed_axis_frames: list[list[int]] = []
    if len(axis_frames) >= 2:
        completed_axis_frames = _complete_axis_frame_grid(image, axis_frames)
        candidate_sets.append(completed_axis_frames)
    for columns, rows in ((2, 2), (3, 1), (1, 3), (3, 2), (2, 3), (3, 3), (4, 2), (4, 3)):
        regions = _grid_regions(width, height, columns, rows)
        valid = [region for region in regions if _looks_like_subplot_region(image, region)]
        if len(valid) >= 2:
            candidate_sets.append(valid)
    if candidate_sets:
        max_count = max(len(items) for items in candidate_sets)
        if completed_axis_frames and len(completed_axis_frames) == max_count:
            return completed_axis_frames
        candidate_sets.sort(
            key=lambda items: (
                len(items),
                sum((item[2] - item[0]) * (item[3] - item[1]) for item in items),
            ),
            reverse=True,
        )
        return candidate_sets[0]
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


def _detect_axis_frame_regions(image: Any) -> list[list[int]]:
    """Find subplot frames from bottom/left axis intersections at arbitrary positions."""
    width = _image_width(image)
    height = _image_height(image)
    min_horizontal = max(70, int(width * 0.09))
    min_vertical = max(60, int(height * 0.08))
    horizontal: list[tuple[int, int, int]] = []
    for y in range(4, height - 4):
        for start, end in _dark_runs(image, y, 2, width - 2, horizontal=True):
            if end - start >= min_horizontal:
                horizontal.append((y, start, end))
    vertical: list[tuple[int, int, int]] = []
    for x in range(4, width - 4):
        for start, end in _dark_runs(image, x, 2, height - 2, horizontal=False):
            if end - start >= min_vertical:
                vertical.append((x, start, end))
    horizontal = _suppress_parallel_lines(horizontal, coordinate_index=0)
    vertical = _suppress_parallel_lines(vertical, coordinate_index=0)
    frames: list[list[int]] = []
    for y, hx0, hx1 in horizontal:
        for x, vy0, vy1 in vertical:
            tolerance = max(7, int(min(hx1 - hx0, vy1 - vy0) * 0.05))
            if abs(x - hx0) > tolerance or y < vy0 + 55 or y > vy1 + tolerance:
                continue
            previous_axes = [
                other_y
                for other_y, other_x0, other_x1 in horizontal
                if vy0 <= other_y < y - 12
                and abs(other_x0 - x) <= tolerance
                and _interval_overlap_ratio(hx0, hx1, other_x0, other_x1) >= 0.60
            ]
            plot_top = max(previous_axes) + 5 if previous_axes else vy0
            plot_width = hx1 - x
            plot_height = y - plot_top
            if plot_width < 70 or plot_height < 55:
                continue
            region = [
                max(0, x - int(plot_width * 0.18)),
                max(0, plot_top - int(plot_height * 0.12)),
                min(width, hx1 + int(plot_width * 0.08)),
                min(height, y + int(plot_height * 0.24)),
            ]
            if _looks_like_subplot_region(image, region):
                frames.append(region)
    return _dedupe_regions(frames)


def _longest_dark_run(
    image: Any, fixed: int, start: int, end: int, *, horizontal: bool, max_gap: int = 2
) -> tuple[int, int]:
    runs = _dark_runs(image, fixed, start, end, horizontal=horizontal, max_gap=max_gap)
    return max(runs, key=lambda item: item[1] - item[0], default=(start, start))


def _dark_runs(
    image: Any, fixed: int, start: int, end: int, *, horizontal: bool, max_gap: int = 2
) -> list[tuple[int, int]]:
    runs: list[tuple[int, int]] = []
    run_start: int | None = None
    last_dark: int | None = None
    for position in range(start, end):
        dark = _is_dark(image, position, fixed) if horizontal else _is_dark(image, fixed, position)
        if dark:
            if run_start is None:
                run_start = position
            last_dark = position
        elif last_dark is not None and position - last_dark > max_gap:
            if run_start is not None:
                runs.append((run_start, last_dark + 1))
            run_start = None
            last_dark = None
    if run_start is not None and last_dark is not None:
        runs.append((run_start, last_dark + 1))
    return runs


def _suppress_parallel_lines(lines: list[tuple[int, int, int]], *, coordinate_index: int) -> list[tuple[int, int, int]]:
    selected: list[tuple[int, int, int]] = []
    for line in sorted(lines, key=lambda item: item[2] - item[1], reverse=True):
        coordinate = line[coordinate_index]
        if any(
            abs(coordinate - existing[coordinate_index]) <= 4
            and _interval_overlap_ratio(line[1], line[2], existing[1], existing[2]) >= 0.55
            and min(line[2] - line[1], existing[2] - existing[1]) / max(1, max(line[2] - line[1], existing[2] - existing[1])) >= 0.65
            for existing in selected
        ):
            continue
        selected.append(line)
    return selected


def _interval_overlap_ratio(a0: int, a1: int, b0: int, b1: int) -> float:
    overlap = max(0, min(a1, b1) - max(a0, b0))
    return overlap / max(1, min(a1 - a0, b1 - b0))


def _dedupe_regions(regions: list[list[int]]) -> list[list[int]]:
    selected: list[list[int]] = []
    for region in sorted(regions, key=lambda item: (item[1], item[0])):
        if any(_region_iou(region, existing) >= 0.58 for existing in selected):
            continue
        selected.append(region)
    return selected


def _region_iou(first: list[int], second: list[int]) -> float:
    ix0 = max(first[0], second[0])
    iy0 = max(first[1], second[1])
    ix1 = min(first[2], second[2])
    iy1 = min(first[3], second[3])
    intersection = max(0, ix1 - ix0) * max(0, iy1 - iy0)
    first_area = max(1, (first[2] - first[0]) * (first[3] - first[1]))
    second_area = max(1, (second[2] - second[0]) * (second[3] - second[1]))
    return intersection / max(1, first_area + second_area - intersection)


def _complete_axis_frame_grid(image: Any, frames: list[list[int]]) -> list[list[int]]:
    if len(frames) < 3:
        return frames
    widths = [item[2] - item[0] for item in frames]
    heights = [item[3] - item[1] for item in frames]
    x_groups = _cluster_regions(frames, horizontal=True, tolerance=max(20, int(statistics.median(widths) * 0.42)))
    y_groups = _cluster_regions(frames, horizontal=False, tolerance=max(20, int(statistics.median(heights) * 0.42)))
    if len(x_groups) < 2 or len(y_groups) < 2 or len(x_groups) * len(y_groups) > 12:
        return frames
    completed = list(frames)
    for x_group in x_groups:
        for y_group in y_groups:
            candidate = [
                round(statistics.mean(item[0] for item in x_group)),
                round(statistics.mean(item[1] for item in y_group)),
                round(statistics.mean(item[2] for item in x_group)),
                round(statistics.mean(item[3] for item in y_group)),
            ]
            if any(_region_iou(candidate, existing) >= 0.58 for existing in completed):
                continue
            if _looks_like_subplot_region(image, candidate):
                completed.append(candidate)
    return _sort_regions_row_major(_dedupe_regions(completed))


def _cluster_regions(frames: list[list[int]], *, horizontal: bool, tolerance: int) -> list[list[list[int]]]:
    groups: list[list[list[int]]] = []
    coordinate = (lambda item: (item[0] + item[2]) / 2.0) if horizontal else (lambda item: (item[1] + item[3]) / 2.0)
    for frame in sorted(frames, key=coordinate):
        if groups and abs(coordinate(frame) - statistics.mean(coordinate(item) for item in groups[-1])) <= tolerance:
            groups[-1].append(frame)
        else:
            groups.append([frame])
    return groups


def _sort_regions_row_major(frames: list[list[int]]) -> list[list[int]]:
    if not frames:
        return []
    heights = [item[3] - item[1] for item in frames]
    rows = _cluster_regions(frames, horizontal=False, tolerance=max(12, int(statistics.median(heights) * 0.38)))
    result: list[list[int]] = []
    for row in rows:
        result.extend(sorted(row, key=lambda item: item[0]))
    return result


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
    geometry = axes.get("geometry") or {}
    strong_axis_pair = bool(geometry.get("intersection")) and min(
        float(geometry.get("horizontalContinuity") or 0.0),
        float(geometry.get("verticalContinuity") or 0.0),
    ) >= 0.68
    has_axis_pair = (
        int(geometry.get("xTickCount") or 0) >= 1
        and int(geometry.get("yTickCount") or 0) >= 1
    ) or strong_axis_pair
    has_continuity = min(
        float(geometry.get("horizontalContinuity") or 0.0),
        float(geometry.get("verticalContinuity") or 0.0),
    ) >= 0.20
    confidence_threshold = 0.40 if int(geometry.get("xTickCount") or 0) >= 2 and int(geometry.get("yTickCount") or 0) >= 2 else 0.43
    return (
        float(axes.get("confidence") or 0.0) >= confidence_threshold
        and has_axis_pair
        and has_continuity
        and _has_curve_pixels(image, axes.get("plot_area") or [x0, y0, x1, y1])
    )


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

    row_candidates: list[tuple[float, int, float]] = []
    for y in range(max(y0, row_start), max(row_start + 1, row_end)):
        score, continuity = _axis_line_score(
            image,
            x0 + int(width * 0.05),
            x1 - int(width * 0.04),
            y,
            horizontal=True,
        )
        row_candidates.append((score, y, continuity))
    max_row_score = max((item[0] for item in row_candidates), default=0.0)
    eligible_rows = [item for item in row_candidates if item[0] >= max(0.25, max_row_score * 0.72)]
    best_row = max(eligible_rows, key=lambda item: item[1], default=max(row_candidates, default=(0.0, row_end - 1, 0.0)))

    col_candidates: list[tuple[float, int, float]] = []
    for x in range(max(x0, col_start), max(col_start + 1, col_end)):
        score, continuity = _axis_line_score(
            image,
            y0 + int(height * 0.05),
            y1 - int(height * 0.08),
            x,
            horizontal=False,
        )
        col_candidates.append((score, x, continuity))
    max_col_score = max((item[0] for item in col_candidates), default=0.0)
    eligible_cols = [item for item in col_candidates if item[0] >= max(0.25, max_col_score * 0.72)]
    best_col = min(eligible_cols, key=lambda item: item[1], default=max(col_candidates, default=(0.0, col_start, 0.0)))

    pair_candidates: list[tuple[float, tuple[float, int, float], tuple[float, int, float]]] = []
    for row in [item for item in row_candidates if item[0] >= max(0.16, max_row_score * 0.45)]:
        for column in [item for item in col_candidates if item[0] >= max(0.16, max_col_score * 0.45)]:
            intersects = _dark_near(image, int(column[1]), int(row[1]), 2)
            pair_score = math.sqrt(max(0.0, row[0] * column[0])) * (1.0 if intersects else 0.52)
            pair_score += ((row[1] - row_start) / max(1.0, row_end - row_start)) * 0.015
            pair_candidates.append((pair_score, row, column))
    if pair_candidates:
        _, best_row, best_col = max(pair_candidates, key=lambda item: item[0])

    row_score = float(best_row[0])
    col_score = float(best_col[0])
    intersection = _dark_near(image, int(best_col[1]), int(best_row[1]), 2)
    confidence = _clamp(math.sqrt(max(0.0, row_score * col_score)) * (1.0 if intersection else 0.72))
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
    tick_geometry = _axis_tick_evidence(image, plot_area)
    warnings = []
    if confidence < 0.55:
        warnings.append("坐标轴识别置信度低，需要手动校准。")
    return {
        "plot_area": plot_area,
        "confidence": confidence,
        "source": "auto_geometry",
        "warnings": warnings,
        "geometry": {
            "horizontalContinuity": float(best_row[2]),
            "verticalContinuity": float(best_col[2]),
            "intersection": bool(intersection),
            **tick_geometry,
        },
    }


def _axis_line_score(image: Any, start: int, end: int, fixed: int, *, horizontal: bool) -> tuple[float, float]:
    """Score a genuinely continuous axis line, not a dense row of text glyphs."""
    if end <= start:
        return 0.0, 0.0
    flags: list[bool] = []
    for position in range(start, end):
        if horizontal:
            flags.append(any(_is_dark(image, position, fixed + offset) for offset in (-1, 0, 1)))
        else:
            flags.append(any(_is_dark(image, fixed + offset, position) for offset in (-1, 0, 1)))
    dark_count = sum(1 for value in flags if value)
    longest = 0
    run = 0
    gap = 0
    for value in flags:
        if value:
            run += gap + 1
            gap = 0
            longest = max(longest, run)
        elif run and gap < 2:
            gap += 1
        else:
            run = 0
            gap = 0
    length = max(1, len(flags))
    continuity = longest / length
    occupancy = dark_count / length
    score = 0.76 * min(1.0, continuity / 0.68) + 0.24 * min(1.0, occupancy / 0.52)
    return _clamp(score), continuity


def _dark_near(image: Any, x: int, y: int, radius: int) -> bool:
    width = _image_width(image)
    height = _image_height(image)
    for py in range(max(0, y - radius), min(height, y + radius + 1)):
        for px in range(max(0, x - radius), min(width, x + radius + 1)):
            if _is_dark(image, px, py):
                return True
    return False


def _axis_tick_evidence(image: Any, plot_area: list[int]) -> dict[str, Any]:
    x0, y0, x1, y1 = _clip_region(plot_area, _image_width(image), _image_height(image))
    x_positions: list[int] = []
    for x in range(x0 + 3, x1 - 2):
        outside = sum(1 for y in range(max(0, y1 - 5), min(_image_height(image), y1 + 7)) if abs(y - y1) > 1 and _is_dark(image, x, y))
        if outside >= 3:
            x_positions.append(x)
    y_positions: list[int] = []
    for y in range(y0 + 2, y1 - 3):
        outside = sum(1 for x in range(max(0, x0 - 7), min(_image_width(image), x0 + 6)) if abs(x - x0) > 1 and _is_dark(image, x, y))
        if outside >= 3:
            y_positions.append(y)
    x_ticks = _group_centers(x_positions, max_width=5)
    y_ticks = _group_centers(y_positions, max_width=5)
    score = min(1.0, (min(4, len(x_ticks)) + min(4, len(y_ticks))) / 6.0)
    return {"xTickCount": len(x_ticks), "yTickCount": len(y_ticks), "tickScore": score}


def _group_centers(values: list[int], *, max_width: int) -> list[int]:
    if not values:
        return []
    groups: list[list[int]] = [[values[0]]]
    for value in values[1:]:
        if value <= groups[-1][-1] + 1:
            groups[-1].append(value)
        else:
            groups.append([value])
    return [round(statistics.mean(group)) for group in groups if len(group) <= max_width]


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
        domain_width = max(1, compact[-1][0] - compact[0][0] + 1)
        path_density = len(compact) / domain_width
        domain_ratio = domain_width / max(1.0, x1 - x0)
        filtered_colors = [_rgb(image, x, y) for x, y in pixels[:: max(1, len(pixels) // 1200)]]
        candidates.append(
            {
                "pixels": compact,
                "domainPx": [float(compact[0][0]), float(compact[-1][0])],
                "domainCoverage": domain_ratio,
                "colorBucket": key,
                "color": _average_color_hex(filtered_colors or color_values.get(key) or []),
                "confidence": min(0.94, 0.52 + path_density * 0.34 + min(0.08, domain_ratio * 0.10)),
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
    grid_rows = {row for row, count in row_counts.items() if count >= width * 0.76}
    grid_cols = {col for col, count in col_counts.items() if count >= height * 0.76}
    if not grid_rows and not grid_cols:
        return pixels
    return [(x, y) for x, y in pixels if y not in grid_rows and x not in grid_cols]


def _sample_curve(pixels: list[tuple[int, int]], plot_area: list[int], axes: dict[str, Any], sample_count: int) -> list[dict[str, Any]]:
    if not pixels:
        return [make_point(i, None, None, [], confidence=0.0, missing=True) for i in range(sample_count)]
    by_x = {int(x): int(y) for x, y in pixels}
    xs = sorted(by_x)
    plot_min_x = float(plot_area[0])
    plot_max_x = float(plot_area[2])
    plot_width = max(1.0, plot_max_x - plot_min_x)
    min_x = plot_min_x if float(xs[0]) - plot_min_x <= plot_width * 0.05 else float(xs[0])
    max_x = plot_max_x if plot_max_x - float(xs[-1]) <= plot_width * 0.05 else float(xs[-1])
    points: list[dict[str, Any]] = []
    window = max(2, int((max_x - min_x) / max(12, sample_count * 2)))
    for index in range(sample_count):
        target_x = min_x if sample_count == 1 else min_x + (max_x - min_x) * index / max(1, sample_count - 1)
        pixel_y, missing, pixel_conf = _interpolate_y(xs, by_x, target_x, window)
        pixel = [target_x, pixel_y] if pixel_y is not None else []
        data_x = _map_axis_value(axes["x"], target_x)
        data_y = _map_axis_value(axes["y"], pixel_y) if pixel_y is not None else None
        points.append(make_point(index, data_x, data_y, pixel, confidence=pixel_conf, missing=missing))
    missing_indices = [index for index, point in enumerate(points) if point.get("missing")]
    if len(missing_indices) == 1 and len(points) >= 5:
        missing_index = missing_indices[0]
        if missing_index == 0:
            neighbors = [points[1]]
        elif missing_index == len(points) - 1:
            neighbors = [points[-2]]
        else:
            neighbors = [points[missing_index - 1], points[missing_index + 1]]
        if all(not neighbor.get("missing") and neighbor.get("pixel") for neighbor in neighbors):
            target_x = float(points[missing_index].get("x")) if points[missing_index].get("x") is not None else None
            pixel_x = min_x + (max_x - min_x) * missing_index / max(1, len(points) - 1)
            pixel_y = sum(float(neighbor["pixel"][1]) for neighbor in neighbors) / len(neighbors)
            points[missing_index] = make_point(
                missing_index,
                target_x,
                _map_axis_value(axes["y"], pixel_y),
                [pixel_x, pixel_y],
                confidence=0.46,
                missing=False,
            )
    return points


def _points_from_markers(pixels: list[tuple[int, int]], axes: dict[str, Any]) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    for index, (pixel_x, pixel_y) in enumerate(sorted(pixels, key=lambda item: item[0])):
        points.append(
            make_point(
                index,
                _map_axis_value(axes["x"], float(pixel_x)),
                _map_axis_value(axes["y"], float(pixel_y)),
                [float(pixel_x), float(pixel_y)],
                confidence=0.90,
                missing=False,
            )
        )
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
    if gap > window * 4:
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
    if hasattr(image, "getpixel"):
        pixels = getattr(image, "_omnilit_dark_pixels", None)
        if pixels is None:
            mask = image.convert("L").point([255 if value < 92 else 0 for value in range(256)], mode="1")
            pixels = mask.load()
            image._omnilit_dark_mask = mask
            image._omnilit_dark_pixels = pixels
        return bool(pixels[int(x), int(y)])
    r, g, b = _rgb(image, x, y)
    return 0.299 * r + 0.587 * g + 0.114 * b < 92


def _rgb(image: Any, x: int, y: int) -> tuple[int, int, int]:
    if QColor is not None and hasattr(image, "pixel"):
        color = QColor(image.pixel(int(x), int(y)))
        return int(color.red()), int(color.green()), int(color.blue())
    if hasattr(image, "getpixel"):
        pixels = getattr(image, "_omnilit_rgb_pixels", None)
        if pixels is None:
            pixels = image.load()
            image._omnilit_rgb_pixels = pixels
        value = pixels[int(x), int(y)]
        if isinstance(value, int):
            return value, value, value
        if isinstance(value, (list, tuple)) and len(value) >= 3:
            return int(value[0]), int(value[1]), int(value[2])
    return 255, 255, 255


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
