from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
ENGINE_NAME = "omnilit_chart_digitizer"
DEFAULT_SAMPLE_COUNT = 10
SUPPORTED_SAMPLE_COUNTS = (5, 10, 15, 20)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize_sample_count(value: Any, default: int = DEFAULT_SAMPLE_COUNT) -> int:
    try:
        count = int(value)
    except (TypeError, ValueError):
        count = int(default)
    return max(2, min(500, count))


def build_source_metadata(
    element: dict[str, Any],
    index: dict[str, Any] | None = None,
    record_id: str = "",
) -> dict[str, Any]:
    source_index = index if isinstance(index, dict) else {}
    return {
        "recordId": str(record_id or ""),
        "elementId": str(element.get("id") or ""),
        "pdfPath": str(source_index.get("sourcePath") or ""),
        "sourceSha256": str(source_index.get("sourceSha256") or ""),
        "page": int(element.get("page") or 0),
        "figureImagePath": str(element.get("pngPath") or ""),
        "caption": str(element.get("caption") or element.get("text") or ""),
    }


def make_empty_result(
    element: dict[str, Any],
    index: dict[str, Any] | None = None,
    *,
    record_id: str = "",
    sample_count: Any = DEFAULT_SAMPLE_COUNT,
    warnings: list[str] | None = None,
    chart_type: str = "unknown",
) -> dict[str, Any]:
    warning_list = [str(item) for item in (warnings or []) if str(item or "").strip()]
    if not warning_list:
        warning_list = ["需要手动校准。"]
    return {
        "schemaVersion": SCHEMA_VERSION,
        "source": build_source_metadata(element, index, record_id),
        "analysis": {
            "chartType": str(chart_type or "unknown"),
            "createdAt": utc_now_iso(),
            "engine": ENGINE_NAME,
            "sampleCount": normalize_sample_count(sample_count),
            "confidence": 0.0,
            "needsReview": True,
            "status": "需要手动校准",
            "warnings": warning_list,
        },
        "subplots": [],
    }


def make_axis(
    *,
    label: str = "",
    scale: str = "linear",
    minimum: float | None = None,
    maximum: float | None = None,
    calibration: list[dict[str, Any]] | None = None,
    source: str = "unknown",
    confidence: float = 0.0,
) -> dict[str, Any]:
    return {
        "label": str(label or ""),
        "scale": str(scale or "unknown"),
        "min": minimum,
        "max": maximum,
        "calibration": calibration or [],
        "source": str(source or "unknown"),
        "confidence": _clean_confidence(confidence),
    }


def make_point(
    index: int,
    x: float | None,
    y: float | None,
    pixel: list[float] | tuple[float, float] | None,
    *,
    confidence: float = 0.0,
    missing: bool = False,
) -> dict[str, Any]:
    px: list[float] = []
    if isinstance(pixel, (list, tuple)) and len(pixel) >= 2:
        px = [float(pixel[0]), float(pixel[1])]
    return {
        "index": int(index),
        "x": None if x is None else float(x),
        "y": None if y is None else float(y),
        "pixel": px,
        "confidence": _clean_confidence(confidence),
        "missing": bool(missing),
    }


def validate_chart_result(result: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(result, dict):
        return ["chart result must be a dictionary"]
    if result.get("schemaVersion") != SCHEMA_VERSION:
        errors.append("schemaVersion must be 1")
    if not isinstance(result.get("source"), dict):
        errors.append("source must be a dictionary")
    analysis = result.get("analysis")
    if not isinstance(analysis, dict):
        errors.append("analysis must be a dictionary")
    else:
        for field in ("chartType", "createdAt", "engine", "sampleCount", "confidence", "needsReview", "warnings"):
            if field not in analysis:
                errors.append(f"analysis missing field: {field}")
        if not isinstance(analysis.get("warnings", []), list):
            errors.append("analysis.warnings must be a list")
    subplots = result.get("subplots")
    if not isinstance(subplots, list):
        errors.append("subplots must be a list")
        return errors
    for subplot_index, subplot in enumerate(subplots):
        if not isinstance(subplot, dict):
            errors.append(f"subplot {subplot_index} must be a dictionary")
            continue
        for field in ("subplotId", "bboxPx", "plotAreaPx", "axes", "series"):
            if field not in subplot:
                errors.append(f"subplot {subplot_index} missing field: {field}")
        axes = subplot.get("axes") or {}
        if not isinstance(axes, dict) or "x" not in axes or "y" not in axes:
            errors.append(f"subplot {subplot_index} must contain x and y axes")
        series = subplot.get("series")
        if not isinstance(series, list):
            errors.append(f"subplot {subplot_index}.series must be a list")
            continue
        for series_index, entry in enumerate(series):
            if not isinstance(entry, dict):
                errors.append(f"subplot {subplot_index} series {series_index} must be a dictionary")
                continue
            for field in ("seriesId", "name", "confidence", "points"):
                if field not in entry:
                    errors.append(f"subplot {subplot_index} series {series_index} missing field: {field}")
            if not isinstance(entry.get("points"), list):
                errors.append(f"subplot {subplot_index} series {series_index}.points must be a list")
    return errors


def chart_result_to_json(result: dict[str, Any]) -> str:
    stable = deepcopy(result) if isinstance(result, dict) else {}
    return json.dumps(stable, ensure_ascii=False, indent=2, sort_keys=False)


def write_chart_result(path: str | Path, result: dict[str, Any]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(chart_result_to_json(result) + "\n", encoding="utf-8")
    return target


def _clean_confidence(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0
