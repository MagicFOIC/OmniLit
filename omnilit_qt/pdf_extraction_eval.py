from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .pdf_extraction_schema import normalize_bbox, normalize_element
from .pdf_extraction_table_utils import table_shape


DEFAULT_THRESHOLDS = {
    "bbox_iou": 0.50,
    "caption_similarity": 0.55,
    "latex_similarity": 0.65,
    "text_similarity": 0.45,
}

EVALUATED_TYPES = {"table", "figure", "chart", "formula"}


def evaluate_extraction_index(
    actual_index: dict[str, Any],
    golden_index: dict[str, Any],
    thresholds: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Compare an extraction index with a golden index.

    The golden index can be a normal extraction_index-like dictionary or a
    compact fixture with an ``expectedElements`` list.  The report is designed
    to be stable enough for regression tests and detailed enough for later UI
    review tooling.
    """

    limits = dict(DEFAULT_THRESHOLDS)
    limits.update({str(key): float(value) for key, value in (thresholds or {}).items()})
    actual_elements = _evaluated_elements(actual_index.get("elements") or [], str(actual_index.get("engine") or ""))
    expected_elements = _evaluated_elements(
        golden_index.get("expectedElements") or golden_index.get("elements") or [],
        str(golden_index.get("engine") or "golden"),
    )

    matches: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    used_actual: set[int] = set()

    for expected_position, expected in enumerate(expected_elements):
        actual_position, actual, score = _best_match(expected, actual_elements, used_actual, limits)
        if actual is None:
            issues.append(_issue("missing_element", "error", expected, None, "Expected element was not extracted."))
            continue
        used_actual.add(actual_position)
        match = {
            "expectedId": str(expected.get("id") or ""),
            "actualId": str(actual.get("id") or ""),
            "type": str(expected.get("type") or ""),
            "expectedPosition": expected_position,
            "actualPosition": actual_position,
            "matchScore": round(score, 3),
            "bboxIoU": round(_bbox_iou(expected.get("bbox") or [], actual.get("bbox") or []), 3),
        }
        matches.append(match)
        issues.extend(_compare_matched_element(expected, actual, limits))

    for position, actual in enumerate(actual_elements):
        if position not in used_actual:
            issues.append(_issue("unexpected_element", "warning", None, actual, "Extracted element is not in golden set."))

    issues.extend(_count_issues(expected_elements, actual_elements))
    issues.extend(_reading_order_issues(matches))

    summary = {
        "passed": not any(item.get("severity") == "error" for item in issues),
        "expectedCount": len(expected_elements),
        "actualCount": len(actual_elements),
        "matchedCount": len(matches),
        "missingCount": sum(1 for item in issues if item.get("code") == "missing_element"),
        "unexpectedCount": sum(1 for item in issues if item.get("code") == "unexpected_element"),
        "errorCount": sum(1 for item in issues if item.get("severity") == "error"),
        "warningCount": sum(1 for item in issues if item.get("severity") == "warning"),
        "byType": _type_summary(expected_elements, actual_elements, matches),
    }
    if matches:
        summary["meanBBoxIoU"] = round(sum(float(item.get("bboxIoU") or 0.0) for item in matches) / len(matches), 3)

    return {
        "version": 1,
        "sourcePath": str(actual_index.get("sourcePath") or ""),
        "goldenName": str(golden_index.get("name") or golden_index.get("sourcePath") or ""),
        "thresholds": limits,
        "summary": summary,
        "matches": matches,
        "issues": issues,
    }


def evaluate_extraction_files(
    actual_index_path: str | Path,
    golden_index_path: str | Path,
    report_path: str | Path | None = None,
    thresholds: dict[str, float] | None = None,
) -> dict[str, Any]:
    actual = json.loads(Path(actual_index_path).read_text(encoding="utf-8"))
    golden = json.loads(Path(golden_index_path).read_text(encoding="utf-8"))
    report = evaluate_extraction_index(actual, golden, thresholds)
    if report_path is not None:
        target = Path(report_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def _evaluated_elements(elements: list[Any], fallback_engine: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for element in elements or []:
        if not isinstance(element, dict):
            continue
        item = normalize_element(element, fallback_engine)
        if str(item.get("type") or "") in EVALUATED_TYPES:
            result.append(item)
    return result


def _best_match(
    expected: dict[str, Any],
    actual_elements: list[dict[str, Any]],
    used_actual: set[int],
    thresholds: dict[str, float],
) -> tuple[int, dict[str, Any] | None, float]:
    best: tuple[float, int, dict[str, Any]] | None = None
    for position, actual in enumerate(actual_elements):
        if position in used_actual:
            continue
        if str(actual.get("type") or "") != str(expected.get("type") or ""):
            continue
        if int(actual.get("page") or 0) != int(expected.get("page") or 0):
            continue
        score = _match_score(expected, actual)
        if score <= 0:
            continue
        if best is None or score > best[0]:
            best = (score, position, actual)
    if best is None:
        return -1, None, 0.0
    score, position, actual = best
    kind = str(expected.get("type") or "")
    minimum = thresholds["latex_similarity"] if kind == "formula" and not _has_bbox(expected) else thresholds["bbox_iou"]
    if score < minimum:
        return -1, None, score
    return position, actual, score


def _match_score(expected: dict[str, Any], actual: dict[str, Any]) -> float:
    expected_id = str(expected.get("id") or "").strip()
    actual_id = str(actual.get("id") or "").strip()
    id_score = 1.0 if expected_id and expected_id == actual_id else 0.0
    bbox_score = _bbox_iou(expected.get("bbox") or [], actual.get("bbox") or [])
    if str(expected.get("type") or "") == "formula":
        text_score = _text_similarity(
            expected.get("latex") or expected.get("text") or "",
            actual.get("latex") or actual.get("text") or "",
        )
    else:
        text_score = max(
            _text_similarity(expected.get("caption") or "", actual.get("caption") or ""),
            _text_similarity(expected.get("text") or "", actual.get("text") or ""),
        )
    return max(id_score, bbox_score, text_score * 0.92)


def _compare_matched_element(
    expected: dict[str, Any],
    actual: dict[str, Any],
    thresholds: dict[str, float],
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    bbox_iou = _bbox_iou(expected.get("bbox") or [], actual.get("bbox") or [])
    if _has_bbox(expected) and bbox_iou < thresholds["bbox_iou"]:
        issues.append(_issue("bbox_mismatch", "error", expected, actual, f"bbox IoU {bbox_iou:.3f} is below threshold."))

    if "needsReview" in expected and bool(expected.get("needsReview")) != bool(actual.get("needsReview")):
        issues.append(_issue("needs_review_mismatch", "error", expected, actual, "needsReview does not match golden expectation."))

    caption = str(expected.get("caption") or "").strip()
    if caption:
        similarity = _text_similarity(caption, actual.get("caption") or "")
        if similarity < thresholds["caption_similarity"]:
            issues.append(_issue("caption_mismatch", "error", expected, actual, f"caption similarity {similarity:.3f} is below threshold."))

    kind = str(expected.get("type") or "")
    if kind == "table":
        expected_shape = _expected_table_shape(expected)
        actual_shape = table_shape(actual.get("table") or [])
        if expected_shape != (0, 0) and expected_shape != actual_shape:
            issues.append(_issue("table_shape_mismatch", "error", expected, actual, f"table shape {actual_shape} does not match {expected_shape}."))
    elif kind == "formula":
        expected_latex = str(expected.get("latex") or expected.get("text") or "").strip()
        if expected_latex:
            similarity = _text_similarity(expected_latex, actual.get("latex") or actual.get("text") or "")
            if similarity < thresholds["latex_similarity"]:
                issues.append(_issue("latex_mismatch", "error", expected, actual, f"LaTeX similarity {similarity:.3f} is below threshold."))
        expected_number = _formula_number(expected)
        if expected_number and expected_number != _formula_number(actual):
            issues.append(_issue("formula_number_mismatch", "error", expected, actual, "formula number does not match golden expectation."))
        for field in ("text", "latex", "pngPath", "bbox", "confidence", "qualityFlags"):
            if field not in actual:
                issues.append(_issue("formula_schema_missing", "error", expected, actual, f"formula is missing field {field}."))
    return issues


def _count_issues(expected_elements: list[dict[str, Any]], actual_elements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for kind in sorted(EVALUATED_TYPES):
        expected_count = sum(1 for item in expected_elements if str(item.get("type") or "") == kind)
        actual_count = sum(1 for item in actual_elements if str(item.get("type") or "") == kind)
        if expected_count != actual_count:
            issues.append(
                {
                    "code": "count_mismatch",
                    "severity": "error",
                    "type": kind,
                    "expectedCount": expected_count,
                    "actualCount": actual_count,
                    "message": f"{kind} count {actual_count} does not match expected {expected_count}.",
                }
            )
    return issues


def _reading_order_issues(matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(matches, key=lambda item: int(item.get("expectedPosition") or 0))
    positions = [int(item.get("actualPosition") or 0) for item in ordered]
    if positions == sorted(positions):
        return []
    return [
        {
            "code": "reading_order_mismatch",
            "severity": "error",
            "message": "Matched elements are not in the same reading order as the golden set.",
            "actualPositions": positions,
        }
    ]


def _type_summary(
    expected_elements: list[dict[str, Any]],
    actual_elements: list[dict[str, Any]],
    matches: list[dict[str, Any]],
) -> dict[str, dict[str, int]]:
    result: dict[str, dict[str, int]] = {}
    for kind in sorted(EVALUATED_TYPES):
        result[kind] = {
            "expected": sum(1 for item in expected_elements if str(item.get("type") or "") == kind),
            "actual": sum(1 for item in actual_elements if str(item.get("type") or "") == kind),
            "matched": sum(1 for item in matches if str(item.get("type") or "") == kind),
        }
    return result


def _expected_table_shape(element: dict[str, Any]) -> tuple[int, int]:
    shape = element.get("tableShape")
    if isinstance(shape, (list, tuple)) and len(shape) >= 2:
        try:
            return int(shape[0]), int(shape[1])
        except (TypeError, ValueError):
            return (0, 0)
    return table_shape(element.get("table") or [])


def _formula_number(element: dict[str, Any]) -> str:
    metadata = element.get("metadata") if isinstance(element.get("metadata"), dict) else {}
    return str(element.get("formulaNumber") or metadata.get("formulaNumber") or "").strip()


def _issue(
    code: str,
    severity: str,
    expected: dict[str, Any] | None,
    actual: dict[str, Any] | None,
    message: str,
) -> dict[str, Any]:
    issue = {"code": code, "severity": severity, "message": message}
    if expected is not None:
        issue.update(
            {
                "expectedId": str(expected.get("id") or ""),
                "type": str(expected.get("type") or ""),
                "page": int(expected.get("page") or 0),
            }
        )
    if actual is not None:
        issue.update({"actualId": str(actual.get("id") or ""), "actualType": str(actual.get("type") or "")})
        if "type" not in issue:
            issue["type"] = str(actual.get("type") or "")
            issue["page"] = int(actual.get("page") or 0)
    return issue


def _bbox_iou(left_value: Any, right_value: Any) -> float:
    left = normalize_bbox(left_value)
    right = normalize_bbox(right_value)
    if not _valid_bbox(left) or not _valid_bbox(right):
        return 0.0
    x0 = max(left[0], right[0])
    y0 = max(left[1], right[1])
    x1 = min(left[2], right[2])
    y1 = min(left[3], right[3])
    intersection = max(0.0, x1 - x0) * max(0.0, y1 - y0)
    union = _bbox_area(left) + _bbox_area(right) - intersection
    return intersection / union if union > 0 else 0.0


def _has_bbox(element: dict[str, Any]) -> bool:
    return _valid_bbox(normalize_bbox(element.get("bbox")))


def _valid_bbox(bbox: list[float]) -> bool:
    return len(bbox) >= 4 and bbox != [0.0, 0.0, 0.0, 0.0] and bbox[2] > bbox[0] and bbox[3] > bbox[1]


def _bbox_area(bbox: list[float]) -> float:
    return max(0.0, bbox[2] - bbox[0]) * max(0.0, bbox[3] - bbox[1])


def _text_similarity(left: Any, right: Any) -> float:
    left_tokens = _tokens(str(left or ""))
    right_tokens = _tokens(str(right or ""))
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / max(len(left_tokens), len(right_tokens))


def _tokens(value: str) -> set[str]:
    return {
        token.lower()
        for token in re.findall(r"\\[A-Za-z]+|[A-Za-z0-9]+|[\u0370-\u03ff]+|[=+\-*/^_()]", str(value or ""))
        if token.strip()
    }
