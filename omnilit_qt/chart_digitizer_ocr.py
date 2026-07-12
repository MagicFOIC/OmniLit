from __future__ import annotations

import math
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

try:
    import cv2
    import numpy as np
except Exception:  # pragma: no cover - optional accuracy enhancement.
    cv2 = None
    np = None

try:
    from PIL import Image, ImageDraw, ImageFont
except Exception:  # pragma: no cover
    Image = ImageDraw = ImageFont = None

try:
    from rapidocr import RapidOCR
except Exception:  # pragma: no cover - optional offline OCR backend.
    RapidOCR = None


CHARACTERS = "0123456789"


def image_axis_calibration(
    image: Any, plot_area: list[int], region: list[int], *, allow_empty_enlargement: bool = True
) -> dict[str, Any]:
    if cv2 is None or np is None:
        return {}
    array = _image_array(image)
    if array is None:
        return {}
    height, width = array.shape[:2]
    x0, y0, x1, y1 = [int(round(value)) for value in plot_area]
    rx0, ry0, rx1, ry1 = [int(round(value)) for value in region]
    plot_width = max(1, x1 - x0)
    plot_height = max(1, y1 - y0)
    x_box = [max(0, x0 - 8), max(0, y1 + 2), min(width, x1 + 8), min(height, ry1, y1 + max(56, int(plot_height * 0.55)))]
    y_box = [max(0, rx0, x0 - max(38, int(plot_width * 0.25))), max(0, y0 - 5), max(1, x0 - 2), min(height, y1 + 5)]
    result: dict[str, Any] = {}
    rapid_items = _rapidocr_items(image, array)
    x_ticks = _rapid_ticks(rapid_items, plot_area, region, axis="x")
    y_ticks = _rapid_ticks(rapid_items, plot_area, region, axis="y")
    x_axis = _axis_from_ticks(x_ticks, axis="x", source="rapidocr")
    y_axis = _axis_from_ticks(y_ticks, axis="y", source="rapidocr")
    has_full_numeric_candidates = bool(x_ticks or y_ticks)
    if x_axis is None and (has_full_numeric_candidates or allow_empty_enlargement):
        enlarged_x_ticks = _rapid_band_ticks(image, array, x_box, axis="x")
        enlarged_x_axis = _axis_from_ticks(enlarged_x_ticks, axis="x", source="rapidocr_enlarged")
        if enlarged_x_axis:
            x_ticks, x_axis = enlarged_x_ticks, enlarged_x_axis
    if y_axis is None and (has_full_numeric_candidates or allow_empty_enlargement):
        enlarged_y_ticks = _rapid_band_ticks(image, array, y_box, axis="y")
        enlarged_y_axis = _axis_from_ticks(enlarged_y_ticks, axis="y", source="rapidocr_enlarged")
        if enlarged_y_axis:
            y_ticks, y_axis = enlarged_y_ticks, enlarged_y_axis
    if x_axis is None and (has_full_numeric_candidates or allow_empty_enlargement):
        template_x_ticks = _recognize_tick_band(array, x_box, axis="x")
        x_axis = _axis_from_ticks(template_x_ticks, axis="x", source="image_template_ocr")
        if x_axis:
            x_ticks = template_x_ticks
    if y_axis is None and (has_full_numeric_candidates or allow_empty_enlargement):
        template_y_ticks = _recognize_tick_band(array, y_box, axis="y")
        y_axis = _axis_from_ticks(template_y_ticks, axis="y", source="image_template_ocr")
        if y_axis:
            y_ticks = template_y_ticks
    if y_axis is None:
        arbitrary_label = _arbitrary_unit_axis_label(rapid_items, plot_area, region)
        if arbitrary_label:
            y_axis = {
                "label": arbitrary_label,
                "scale": "linear",
                "source": "normalized_arbitrary_units",
                "confidence": 0.82,
                "calibration": [
                    {"pixel": [float(x0), float(y1)], "value": 0.0, "text": "normalized minimum"},
                    {"pixel": [float(x0), float(y0)], "value": 1.0, "text": "normalized maximum"},
                ],
                "tickCount": 0,
            }
    if x_axis:
        result["xAxis"] = x_axis
    if y_axis:
        result["yAxis"] = y_axis
    if x_ticks or y_ticks:
        result["ocrCandidates"] = {"x": x_ticks, "y": y_ticks}
    return result


def _arbitrary_unit_axis_label(items: list[dict[str, Any]], plot_area: list[int], region: list[int]) -> str:
    x0, y0, x1, y1 = [float(value) for value in plot_area]
    rx0, ry0, rx1, ry1 = [float(value) for value in region]
    for item in items:
        text = str(item.get("text") or "").strip()
        lower = text.lower().replace(" ", "")
        if not any(token in lower for token in ("a.u.", "a.u", "arb.unit", "arbitraryunit")):
            continue
        bx0, by0, bx1, by1 = item["bbox"]
        center_x = (bx0 + bx1) / 2.0
        center_y = (by0 + by1) / 2.0
        if rx0 <= center_x <= x0 + (x1 - x0) * 0.08 and y0 - 20 <= center_y <= y1 + 20:
            return text
    return ""


def image_marker_series(image: Any, plot_area: list[int]) -> list[dict[str, Any]]:
    if cv2 is None or np is None:
        return []
    array = _image_array(image)
    if array is None:
        return []
    x0, y0, x1, y1 = [int(round(value)) for value in plot_area]
    inner = array[max(0, y0 + 3) : max(y0 + 4, y1 - 3), max(0, x0 + 3) : max(x0 + 4, x1 - 3)]
    if inner.size == 0:
        return []
    gray = cv2.cvtColor(inner, cv2.COLOR_RGB2GRAY)
    mask = (gray < 125).astype(np.uint8)
    count, labels, stats, centroids = cv2.connectedComponentsWithStats(mask, connectivity=8)
    plot_width = max(1.0, x1 - x0)
    for label in range(1, count):
        left, top, width, height, area = [int(value) for value in stats[label]]
        if width < plot_width * 0.20 or width > plot_width * 0.96 or height < 2 or height > 32:
            continue
        if area / max(1.0, width * height) > 0.88:
            continue
        ys, xs = np.where(labels == label)
        by_x: dict[int, list[int]] = {}
        for px, py in zip(xs, ys):
            by_x.setdefault(int(px), []).append(int(py))
        pixels = [(x0 + 3 + px, y0 + 3 + round(float(np.median(py_values)))) for px, py_values in sorted(by_x.items())]
        if len(pixels) >= max(10, int(plot_width * 0.15)):
            return [{
                "pixels": pixels,
                "domainPx": [float(pixels[0][0]), float(pixels[-1][0])],
                "domainCoverage": (pixels[-1][0] - pixels[0][0]) / plot_width,
                "color": "#333333",
                "confidence": 0.88,
                "markerSeries": False,
            }]
    markers: list[tuple[float, float, int]] = []
    for label in range(1, count):
        left, top, width, height, area = [int(value) for value in stats[label]]
        if not (2 <= width <= 18 and 2 <= height <= 18 and 5 <= area <= 240):
            continue
        aspect = width / max(1.0, height)
        fill = area / max(1.0, width * height)
        if not (0.35 <= aspect <= 2.8 and 0.18 <= fill <= 0.95):
            continue
        center_x, center_y = centroids[label]
        markers.append((float(x0 + 3 + center_x), float(y0 + 3 + center_y), area))
    if len(markers) < 4:
        return []
    markers.sort(key=lambda item: item[0])
    if markers[-1][0] - markers[0][0] < plot_width * 0.20:
        return []
    median_area = float(np.median([item[2] for item in markers]))
    stable = [item for item in markers if 0.35 * median_area <= item[2] <= 2.8 * median_area]
    if len(stable) < 4:
        return []
    return [{
        "pixels": [(round(item[0]), round(item[1])) for item in stable],
        "domainPx": [stable[0][0], stable[-1][0]],
        "domainCoverage": (stable[-1][0] - stable[0][0]) / plot_width,
        "color": "#333333",
        "confidence": min(0.94, 0.72 + len(stable) * 0.012),
        "markerSeries": True,
    }]


@lru_cache(maxsize=1)
def _rapidocr_engine() -> Any:
    return RapidOCR() if RapidOCR is not None else None


def _rapidocr_items(image: Any, array: Any) -> list[dict[str, Any]]:
    cached = getattr(image, "_omnilit_rapidocr_items", None)
    if isinstance(cached, list):
        return cached
    engine = _rapidocr_engine()
    if engine is None:
        return []
    try:
        output = engine(array)
        boxes = output.boxes if output is not None and output.boxes is not None else []
        texts = output.txts if output is not None and output.txts is not None else []
        scores = output.scores if output is not None and output.scores is not None else []
        items: list[dict[str, Any]] = []
        for box, text, score in zip(boxes, texts, scores):
            xs = [float(point[0]) for point in box]
            ys = [float(point[1]) for point in box]
            items.append({"text": str(text or ""), "score": float(score), "bbox": [min(xs), min(ys), max(xs), max(ys)]})
        image._omnilit_rapidocr_items = items
        return items
    except Exception:
        image._omnilit_rapidocr_items = []
        return []


def _rapid_ticks(items: list[dict[str, Any]], plot_area: list[int], region: list[int], *, axis: str) -> list[dict[str, Any]]:
    x0, y0, x1, y1 = [float(value) for value in plot_area]
    rx0, ry0, rx1, ry1 = [float(value) for value in region]
    plot_width = max(1.0, x1 - x0)
    plot_height = max(1.0, y1 - y0)
    ticks: list[dict[str, Any]] = []
    for item in items:
        if float(item.get("score") or 0.0) < 0.72:
            continue
        value = _parse_ocr_number(str(item.get("text") or ""))
        if value is None:
            continue
        bx0, by0, bx1, by1 = item["bbox"]
        center_x = (bx0 + bx1) / 2.0
        center_y = (by0 + by1) / 2.0
        if axis == "x":
            near_axis = y1 - 2 <= center_y <= min(ry1, y1 + max(60.0, plot_height * 0.58))
            within_span = x0 - plot_width * 0.06 <= center_x <= x1 + plot_width * 0.06
            if not (near_axis and within_span):
                continue
            pixel = [center_x, y1]
        else:
            near_axis = max(rx0, x0 - max(45.0, plot_width * 0.25)) <= center_x <= x0 + plot_width * 0.035
            within_span = y0 - plot_height * 0.06 <= center_y <= y1 + plot_height * 0.06
            if not (near_axis and within_span):
                continue
            pixel = [x0, center_y]
        ticks.append({"text": str(item["text"]), "value": value, "pixel": pixel, "confidence": float(item["score"])})
    coordinate_index = 0 if axis == "x" else 1
    return sorted(ticks, key=lambda item: item["pixel"][coordinate_index])


def _rapid_band_ticks(image: Any, array: Any, box: list[int], *, axis: str) -> list[dict[str, Any]]:
    cache = getattr(image, "_omnilit_rapidocr_band_cache", None)
    if not isinstance(cache, dict):
        cache = {}
        image._omnilit_rapidocr_band_cache = cache
    key = (axis, *box)
    if key in cache:
        return cache[key]
    engine = _rapidocr_engine()
    x0, y0, x1, y1 = box
    if engine is None or x1 - x0 < 8 or y1 - y0 < 5:
        return []
    crop = array[y0:y1, x0:x1]
    scale = 4.0
    enlarged = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    try:
        output = engine(enlarged)
    except Exception:
        cache[key] = []
        return []
    ticks: list[dict[str, Any]] = []
    boxes = output.boxes if output is not None and output.boxes is not None else []
    texts = output.txts if output is not None and output.txts is not None else []
    scores = output.scores if output is not None and output.scores is not None else []
    for detected_box, text, score in zip(boxes, texts, scores):
        if float(score) < 0.68:
            continue
        value = _parse_ocr_number(str(text or ""))
        if value is None:
            continue
        xs = [float(point[0]) / scale + x0 for point in detected_box]
        ys = [float(point[1]) / scale + y0 for point in detected_box]
        center_x = (min(xs) + max(xs)) / 2.0
        center_y = (min(ys) + max(ys)) / 2.0
        ticks.append({"text": str(text), "value": value, "pixel": [center_x, center_y], "confidence": float(score)})
    coordinate_index = 0 if axis == "x" else 1
    ticks.sort(key=lambda item: item["pixel"][coordinate_index])
    cache[key] = ticks
    return ticks


def _parse_ocr_number(text: str) -> float | None:
    clean = str(text or "").strip().replace("−", "-").replace("—", "-").replace("O", "0").replace("o", "0")
    clean = clean.strip("+|,:;[]() ")
    clean = re.sub(r"(?<=\d)-$", "", clean)
    clean = re.sub(r"^[AB](?=\d)", "", clean, flags=re.IGNORECASE)
    if re.fullmatch(r"4\.0+\d+", clean):
        clean = "-0." + clean.split(".", 1)[1]
    if not re.fullmatch(r"[-+]?\d+(?:\.\d+)?", clean):
        return None
    try:
        return float(clean)
    except ValueError:
        return None


def _image_array(image: Any) -> Any:
    try:
        if hasattr(image, "getpixel"):
            return np.asarray(image.convert("RGB"))
        if hasattr(image, "constBits") and hasattr(image, "bytesPerLine"):
            height = int(image.height())
            width = int(image.width())
            stride = int(image.bytesPerLine())
            raw = np.frombuffer(image.constBits(), dtype=np.uint8, count=height * stride).reshape(height, stride)
            bgra = raw[:, : width * 4].reshape(height, width, 4)
            return bgra[:, :, [2, 1, 0]]
    except Exception:
        return None
    return None


def _recognize_tick_band(array: Any, box: list[int], *, axis: str) -> list[dict[str, Any]]:
    x0, y0, x1, y1 = box
    if x1 - x0 < 8 or y1 - y0 < 5:
        return []
    crop = array[y0:y1, x0:x1]
    gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    components: list[dict[str, Any]] = []
    for contour in contours:
        x, y, width, height = cv2.boundingRect(contour)
        if width < 1 or height < 2 or width > 24 or height > 26 or width * height < 3:
            continue
        glyph = binary[y : y + height, x : x + width]
        for offset, piece in _split_glyph(glyph):
            character, confidence = _recognize_glyph(piece)
            if not character or confidence < 0.55:
                continue
            components.append({"char": character, "confidence": confidence, "x": x + offset, "y": y, "w": piece.shape[1], "h": height})
    if axis == "x":
        labels = _group_x_labels(components)
    else:
        labels = _group_y_labels(components)
    ticks: list[dict[str, Any]] = []
    for label in labels:
        text = "".join(item["char"] for item in label)
        value = _parse_number(text)
        if value is None:
            continue
        center_x = x0 + (min(item["x"] for item in label) + max(item["x"] + item["w"] for item in label)) / 2.0
        center_y = y0 + (min(item["y"] for item in label) + max(item["y"] + item["h"] for item in label)) / 2.0
        ticks.append({"text": text, "value": value, "pixel": [center_x, center_y], "confidence": sum(item["confidence"] for item in label) / len(label)})
    coordinate = (lambda item: item["pixel"][0]) if axis == "x" else (lambda item: item["pixel"][1])
    return sorted(ticks, key=coordinate)


def _group_x_labels(components: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    if not components:
        return []
    heights = [item["h"] for item in components]
    median_height = float(np.median(heights))
    rows: list[list[dict[str, Any]]] = []
    for item in sorted(components, key=lambda entry: entry["y"] + entry["h"]):
        baseline = item["y"] + item["h"]
        target = next((row for row in rows if abs(baseline - np.median([entry["y"] + entry["h"] for entry in row])) <= max(2.5, median_height * 0.30)), None)
        if target is None:
            rows.append([item])
        else:
            target.append(item)
    if not rows:
        return []
    row = max(rows, key=lambda entries: (len(entries), -np.median([item["y"] for item in entries])))
    return _split_by_gap(sorted(row, key=lambda item: item["x"]), max(3.0, median_height * 0.48))


def _group_y_labels(components: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    if not components:
        return []
    median_height = float(np.median([item["h"] for item in components]))
    groups: list[list[dict[str, Any]]] = []
    for item in sorted(components, key=lambda entry: entry["y"] + entry["h"]):
        baseline = item["y"] + item["h"]
        target = next((group for group in groups if abs(baseline - np.median([entry["y"] + entry["h"] for entry in group])) <= max(3.0, median_height * 0.42)), None)
        if target is None:
            groups.append([item])
        else:
            target.append(item)
    return [sorted(group, key=lambda item: item["x"]) for group in groups]


def _split_by_gap(items: list[dict[str, Any]], threshold: float) -> list[list[dict[str, Any]]]:
    groups: list[list[dict[str, Any]]] = []
    for item in items:
        if not groups or item["x"] - (groups[-1][-1]["x"] + groups[-1][-1]["w"]) > threshold:
            groups.append([item])
        else:
            groups[-1].append(item)
    return groups


def _parse_number(text: str) -> float | None:
    clean = str(text or "").strip(".")
    if not clean or clean in {"-", ".", "-."} or clean.count(".") > 1 or "-" in clean[1:]:
        return None
    try:
        return float(clean)
    except ValueError:
        return None


def _axis_from_ticks(ticks: list[dict[str, Any]], *, axis: str, source: str) -> dict[str, Any] | None:
    if len(ticks) < 2:
        return None
    coordinate_index = 0 if axis == "x" else 1
    coordinates = np.asarray([item["pixel"][coordinate_index] for item in ticks], dtype=np.float64)
    values = np.asarray([item["value"] for item in ticks], dtype=np.float64)
    if float(np.ptp(coordinates)) < 18 or float(np.ptp(values)) <= 1e-12:
        return None
    if len(ticks) == 2:
        if not source.startswith("rapidocr") or min(float(item.get("confidence") or 0.0) for item in ticks) < 0.92:
            return None
        slope = float((values[1] - values[0]) / (coordinates[1] - coordinates[0]))
        intercept = float(values[0] - slope * coordinates[0])
        inliers = np.asarray([0, 1], dtype=np.int64)
    else:
        model = _robust_linear_model(coordinates, values)
        if model is None and source.startswith("rapidocr"):
            model = _high_confidence_pair_model(ticks, coordinates, values)
        if model is None:
            return None
        slope, intercept, inliers = model
    fit_coordinates = coordinates[inliers]
    fit_values = values[inliers]
    predicted = fit_coordinates * slope + intercept
    residual = float(np.sum((fit_values - predicted) ** 2))
    total = float(np.sum((fit_values - np.mean(fit_values)) ** 2))
    r_squared = 1.0 - residual / total if total > 1e-12 else 0.0
    if not math.isfinite(r_squared) or r_squared < 0.999:
        fallback = _high_confidence_pair_model(ticks, coordinates, values) if source.startswith("rapidocr") else None
        if fallback is None:
            return None
        slope, intercept, inliers = fallback
        fit_coordinates = coordinates[inliers]
        fit_values = values[inliers]
        predicted = fit_coordinates * slope + intercept
        residual = float(np.sum((fit_values - predicted) ** 2))
        total = float(np.sum((fit_values - np.mean(fit_values)) ** 2))
        r_squared = 1.0 - residual / total if total > 1e-12 else 1.0
    first_index = int(inliers[0])
    last_index = int(inliers[-1])
    first = ticks[first_index]
    last = ticks[last_index]
    first_value = float(first["pixel"][coordinate_index] * slope + intercept)
    last_value = float(last["pixel"][coordinate_index] * slope + intercept)
    confidence = min(0.88, 0.60 + max(0.0, r_squared) * 0.18 + min(0.10, len(inliers) * 0.018))
    return {
        "scale": "linear",
        "source": source,
        "confidence": confidence,
        "calibration": [
            {"pixel": first["pixel"], "value": first_value, "text": first["text"]},
            {"pixel": last["pixel"], "value": last_value, "text": last["text"]},
        ],
        "tickCount": len(inliers),
        "fitR2": r_squared,
    }


def _robust_linear_model(coordinates: Any, values: Any) -> tuple[float, float, Any] | None:
    count = len(coordinates)
    if count < 3:
        return None
    spacing = float(np.median(np.diff(np.sort(coordinates)))) if count >= 2 else 1.0
    best: tuple[int, float, float, float, Any] | None = None
    for first in range(count - 1):
        for second in range(first + 1, count):
            delta = float(coordinates[second] - coordinates[first])
            if abs(delta) < max(4.0, spacing * 0.60):
                continue
            slope = float((values[second] - values[first]) / delta)
            if abs(slope) < 1e-12:
                continue
            intercept = float(values[first] - slope * coordinates[first])
            tolerance = max(0.18, abs(slope) * spacing * 0.18)
            errors = np.abs(values - (coordinates * slope + intercept))
            inliers = np.where(errors <= tolerance)[0]
            if len(inliers) < max(3, math.ceil(count * 0.45)):
                continue
            score = (len(inliers), -float(np.mean(errors[inliers])), -abs(slope), slope, inliers)
            if best is None or score[:3] > best[:3]:
                best = score
    if best is None:
        return None
    inliers = best[4]
    slope, intercept = np.polyfit(coordinates[inliers], values[inliers], 1)
    return float(slope), float(intercept), inliers


def _high_confidence_pair_model(ticks: list[dict[str, Any]], coordinates: Any, values: Any) -> tuple[float, float, Any] | None:
    if len(ticks) < 2:
        return None
    spacing = float(np.median(np.diff(np.sort(coordinates)))) if len(ticks) >= 2 else 1.0
    candidates: list[tuple[float, int, int]] = []
    for first in range(len(ticks) - 1):
        for second in range(first + 1, len(ticks)):
            delta = float(coordinates[second] - coordinates[first])
            if not (spacing * 0.55 <= abs(delta) <= spacing * 1.65):
                continue
            confidence = min(float(ticks[first].get("confidence") or 0.0), float(ticks[second].get("confidence") or 0.0))
            if confidence < 0.88 or abs(float(values[second] - values[first])) < 1e-12:
                continue
            candidates.append((confidence, first, second))
    if not candidates:
        return None
    _, first, second = max(candidates)
    slope = float((values[second] - values[first]) / (coordinates[second] - coordinates[first]))
    intercept = float(values[first] - slope * coordinates[first])
    return slope, intercept, np.asarray([first, second], dtype=np.int64)


def _recognize_glyph(glyph: Any) -> tuple[str, float]:
    height, width = glyph.shape[:2]
    if height <= 3 and width >= max(2, height * 1.7):
        return "-", 0.92
    if height <= 3 and width <= 4:
        return ".", 0.90
    normalized = _normalize_glyph(glyph)
    templates, labels = _templates()
    if templates is None or len(templates) == 0:
        return "", 0.0
    distances = np.mean(np.abs(templates - normalized[None, :, :]), axis=(1, 2))
    index = int(np.argmin(distances))
    distance = float(distances[index])
    return labels[index], max(0.0, 1.0 - distance * 1.85)


def _split_glyph(glyph: Any) -> list[tuple[int, Any]]:
    height, width = glyph.shape[:2]
    if height < 5 or width <= height * 0.92:
        return [(0, glyph)]
    count = max(2, min(4, int(round(width / max(1.0, height * 0.68)))))
    edges = [round(index * width / count) for index in range(count + 1)]
    pieces: list[tuple[int, Any]] = []
    for start, end in zip(edges, edges[1:]):
        piece = glyph[:, start:end]
        columns = np.where(np.any(piece > 0, axis=0))[0]
        if len(columns) == 0:
            continue
        clean_start = int(columns[0])
        clean_end = int(columns[-1]) + 1
        pieces.append((start + clean_start, piece[:, clean_start:clean_end]))
    return pieces or [(0, glyph)]


def _normalize_glyph(glyph: Any) -> Any:
    ys, xs = np.where(glyph > 0)
    canvas = np.zeros((30, 22), dtype=np.float32)
    if len(xs) == 0:
        return canvas
    crop = glyph[min(ys) : max(ys) + 1, min(xs) : max(xs) + 1]
    scale = min(18 / max(1, crop.shape[1]), 26 / max(1, crop.shape[0]))
    width = max(1, int(round(crop.shape[1] * scale)))
    height = max(1, int(round(crop.shape[0] * scale)))
    resized = cv2.resize(crop, (width, height), interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0
    x0 = (22 - width) // 2
    y0 = (30 - height) // 2
    canvas[y0 : y0 + height, x0 : x0 + width] = resized
    return canvas


@lru_cache(maxsize=1)
def _templates() -> tuple[Any, list[str]]:
    values: list[Any] = []
    labels: list[str] = []
    for character in CHARACTERS:
        for font in (cv2.FONT_HERSHEY_SIMPLEX, cv2.FONT_HERSHEY_DUPLEX, cv2.FONT_HERSHEY_COMPLEX, cv2.FONT_HERSHEY_TRIPLEX):
            for scale in (0.32, 0.40, 0.50, 0.62, 0.76):
                for thickness in (1, 2):
                    canvas = np.zeros((40, 32), dtype=np.uint8)
                    cv2.putText(canvas, character, (2, 31), font, scale, 255, thickness, cv2.LINE_AA)
                    values.append(_normalize_glyph(canvas))
                    labels.append(character)
        if Image is not None:
            font_paths = [
                Path("C:/Windows/Fonts/times.ttf"),
                Path("C:/Windows/Fonts/timesbd.ttf"),
                Path("C:/Windows/Fonts/arial.ttf"),
                Path("C:/Windows/Fonts/calibri.ttf"),
                Path("C:/Windows/Fonts/cambria.ttc"),
            ]
            for font_path in font_paths:
                if not font_path.exists():
                    continue
                for size in (9, 11, 13, 16, 20, 24):
                    try:
                        font = ImageFont.truetype(str(font_path), size)
                        canvas_image = Image.new("L", (40, 40), 0)
                        draw = ImageDraw.Draw(canvas_image)
                        draw.text((3, 1), character, fill=255, font=font, stroke_width=0)
                        values.append(_normalize_glyph(np.asarray(canvas_image)))
                        labels.append(character)
                    except Exception:
                        continue
    return np.asarray(values, dtype=np.float32), labels
