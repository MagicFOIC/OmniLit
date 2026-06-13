from __future__ import annotations

import re
from typing import Any

from .pdf_extraction_schema import normalize_bbox


CAPTION_PATTERNS = {
    "figure": re.compile(r"^\s*(fig(?:ure)?\.?\s*\d+[A-Za-z]?|图\s*\d+)", re.IGNORECASE),
    "chart": re.compile(r"^\s*(fig(?:ure)?\.?\s*\d+[A-Za-z]?|图\s*\d+)", re.IGNORECASE),
    "table": re.compile(r"^\s*(table\s*\d+[A-Za-z]?|表\s*\d+)", re.IGNORECASE),
    "formula": re.compile(r"^\s*(eq(?:uation)?\.?\s*\d+[A-Za-z]?|公式\s*\d+)", re.IGNORECASE),
}


def find_nearby_caption(
    element_bbox: list[float],
    text_blocks: list[dict[str, Any]],
    page_size: list[float],
    element_type: str,
) -> dict[str, Any]:
    bbox = normalize_bbox(element_bbox)
    if len(bbox) < 4 or bbox == [0.0, 0.0, 0.0, 0.0]:
        return {}
    page_height = float(page_size[1] if len(page_size) > 1 else 0.0) or 1.0
    max_distance = page_height * 0.12
    preferred_below = element_type in {"figure", "chart"}
    pattern = CAPTION_PATTERNS.get(element_type, CAPTION_PATTERNS["figure"])
    candidates: list[tuple[float, float, dict[str, Any]]] = []

    for block in text_blocks or []:
        block_bbox = normalize_bbox(block.get("bbox"))
        text = str(block.get("text") or "").strip().replace("\n", " ")
        if not text or len(block_bbox) < 4:
            continue
        overlap = _horizontal_overlap_ratio(bbox, block_bbox)
        if overlap < 0.25:
            continue
        below = block_bbox[1] - bbox[3]
        above = bbox[1] - block_bbox[3]
        distance = below if below >= 0 else above if above >= 0 else -1.0
        if distance < 0 or distance > max_distance:
            continue
        matched = bool(pattern.search(text))
        if not matched and len(text) > 180:
            continue
        direction_bonus = 0.0
        if preferred_below and below >= 0:
            direction_bonus = 0.2
        elif not preferred_below and above >= 0:
            direction_bonus = 0.2
        match_bonus = 0.5 if matched else 0.15
        score = match_bonus + direction_bonus + min(0.25, overlap * 0.25) + max(0.0, 0.2 - distance / max_distance * 0.2)
        candidates.append((distance, -score, {"text": text[:300], "bbox": block_bbox, "score": round(score, 3)}))

    if not candidates:
        return {}
    candidates.sort(key=lambda item: (item[1], item[0]))
    return candidates[0][2]


def _horizontal_overlap_ratio(left: list[float], right: list[float]) -> float:
    overlap = max(0.0, min(left[2], right[2]) - max(left[0], right[0]))
    width = max(1.0, min(left[2] - left[0], right[2] - right[0]))
    return overlap / width
