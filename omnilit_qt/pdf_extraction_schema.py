from __future__ import annotations

import hashlib
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 3
RAW_OUTPUT_ENGINES = ("pymupdf", "paddleocr_vl", "mineru")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_bbox(value: Any) -> list[float]:
    try:
        if isinstance(value, (list, tuple)) and len(value) == 0:
            return []
        if value is None:
            return [0.0, 0.0, 0.0, 0.0]
        if hasattr(value, "x0"):
            return [float(value.x0), float(value.y0), float(value.x1), float(value.y1)]
        if isinstance(value, dict):
            keys = ("x0", "y0", "x1", "y1")
            if all(key in value for key in keys):
                return [float(value[key]) for key in keys]
        if isinstance(value, (list, tuple)) and len(value) >= 4:
            return [float(value[0]), float(value[1]), float(value[2]), float(value[3])]
    except (TypeError, ValueError):
        return [0.0, 0.0, 0.0, 0.0]
    return [0.0, 0.0, 0.0, 0.0]


def make_base_index(source: Path, output_dir: Path, engine: str, page_count: int = 0) -> dict[str, Any]:
    source_path = Path(source).expanduser()
    resolved_source = source_path.resolve() if source_path.exists() else source_path
    output_dir.mkdir(parents=True, exist_ok=True)
    return {
        "version": SCHEMA_VERSION,
        "sourcePath": str(resolved_source),
        "sourceSha256": _sha256_file(resolved_source) if resolved_source.exists() else "",
        "analyzedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "engine": str(engine or ""),
        "engineChain": [str(engine)] if engine else [],
        "pageCount": int(page_count or 0),
        "pages": [],
        "elements": [],
        "markdownPath": "",
        "rawOutputs": {name: "" for name in RAW_OUTPUT_ENGINES},
        "qualitySummary": {
            "tables": {"count": 0, "needsReview": 0},
            "figures": {"count": 0, "needsReview": 0},
            "formulas": {"count": 0, "needsReview": 0},
        },
        "debugFiles": {"mineruLayoutPdf": "", "fusionReportJson": ""},
    }


def make_element(
    element_id: str,
    element_type: str,
    page: int,
    bbox: Any,
    page_size: Any,
    *,
    engine: str = "",
    confidence: float = 0.0,
    needs_review: bool = False,
    text: str = "",
    table: list[Any] | None = None,
    csv_path: str = "",
    json_path: str = "",
    png_path: str = "",
    latex: str = "",
    html: str = "",
    markdown: str = "",
    caption: str = "",
    caption_bbox: Any = None,
    raw: Any = None,
    source_element_id: str = "",
    source_element_ids: list[str] | None = None,
    source_engines: list[str] | None = None,
    quality_flags: list[str] | None = None,
    structure_type: str = "",
    **extra: Any,
) -> dict[str, Any]:
    if isinstance(page_size, dict) and "width" in page_size and "height" in page_size:
        page_size_value = [page_size.get("width"), page_size.get("height")]
    else:
        page_size_value = normalize_bbox(page_size)[:2] if isinstance(page_size, dict) else page_size
    if not isinstance(page_size_value, (list, tuple)) or len(page_size_value) < 2:
        page_size_value = [0.0, 0.0]
    element = {
        "id": str(element_id),
        "type": str(element_type),
        "page": int(page or 0),
        "bbox": normalize_bbox(bbox),
        "pageSize": [float(page_size_value[0]), float(page_size_value[1])],
        "text": str(text or ""),
        "table": table if table is not None else [],
        "csvPath": str(csv_path or ""),
        "jsonPath": str(json_path or ""),
        "pngPath": str(png_path or ""),
        "engine": str(engine or ""),
        "confidence": float(confidence or 0.0),
        "needsReview": bool(needs_review),
        "latex": str(latex or ""),
        "html": str(html or ""),
        "markdown": str(markdown or ""),
        "caption": str(caption or ""),
        "captionBBox": normalize_bbox(caption_bbox) if caption_bbox is not None else [],
        "raw": raw if raw is not None else {},
        "sourceElementId": str(source_element_id or ""),
        "sourceElementIds": [str(item) for item in (source_element_ids or ([source_element_id] if source_element_id else [])) if str(item or "").strip()],
        "sourceEngines": [str(item) for item in (source_engines or ([engine] if engine else [])) if str(item or "").strip()],
        "qualityFlags": [str(item) for item in (quality_flags or []) if str(item or "").strip()],
        "structureType": str(structure_type or ""),
    }
    element.update(extra)
    return element


def ensure_version_3(index: dict[str, Any], engine: str = "") -> dict[str, Any]:
    result = deepcopy(index) if isinstance(index, dict) else {}
    result["version"] = SCHEMA_VERSION
    selected_engine = str(result.get("engine") or engine or "")
    result["engine"] = selected_engine
    chain = result.get("engineChain")
    if not isinstance(chain, list):
        chain = [selected_engine] if selected_engine else []
    result["engineChain"] = [str(item) for item in chain if str(item or "").strip()]
    result.setdefault("sourcePath", "")
    result.setdefault("sourceSha256", "")
    result.setdefault("analyzedAt", datetime.now(timezone.utc).isoformat(timespec="seconds"))
    result.setdefault("pageCount", len(result.get("pages") or []))
    result.setdefault("pages", [])
    result.setdefault("elements", [])
    result.setdefault("markdownPath", "")
    raw_outputs = result.get("rawOutputs")
    if not isinstance(raw_outputs, dict):
        raw_outputs = {}
    result["rawOutputs"] = {name: str(raw_outputs.get(name) or "") for name in RAW_OUTPUT_ENGINES}
    quality = result.get("qualitySummary")
    if not isinstance(quality, dict):
        quality = {}
    result["qualitySummary"] = {
        "tables": _summary_bucket(quality.get("tables")),
        "figures": _summary_bucket(quality.get("figures")),
        "formulas": _summary_bucket(quality.get("formulas")),
    }
    debug_files = result.get("debugFiles")
    if not isinstance(debug_files, dict):
        debug_files = {}
    result["debugFiles"] = {
        "mineruLayoutPdf": str(debug_files.get("mineruLayoutPdf") or ""),
        "fusionReportJson": str(debug_files.get("fusionReportJson") or ""),
    }
    normalized_elements = []
    for element in result.get("elements") or []:
        if isinstance(element, dict):
            normalized_elements.append(normalize_element(element, selected_engine))
    result["elements"] = normalized_elements
    return result


def ensure_version_2(index: dict[str, Any], engine: str = "") -> dict[str, Any]:
    return ensure_version_3(index, engine)


def normalize_element(element: dict[str, Any], fallback_engine: str = "") -> dict[str, Any]:
    item = dict(element)
    item.setdefault("id", "")
    item.setdefault("type", "")
    item["page"] = int(item.get("page") or 0)
    item["bbox"] = normalize_bbox(item.get("bbox"))
    page_size = item.get("pageSize")
    if not isinstance(page_size, (list, tuple)) or len(page_size) < 2:
        page_size = [0.0, 0.0]
    item["pageSize"] = [float(page_size[0]), float(page_size[1])]
    item.setdefault("text", "")
    item.setdefault("table", [])
    item.setdefault("csvPath", "")
    item.setdefault("jsonPath", "")
    item.setdefault("pngPath", "")
    if not item.get("engine"):
        item["engine"] = fallback_engine
    try:
        item["confidence"] = float(item.get("confidence") or 0.0)
    except (TypeError, ValueError):
        item["confidence"] = 0.0
    item["needsReview"] = bool(item.get("needsReview", False))
    item.setdefault("latex", "")
    item.setdefault("html", "")
    item.setdefault("markdown", "")
    item.setdefault("caption", "")
    item["captionBBox"] = normalize_bbox(item.get("captionBBox") or []) if item.get("captionBBox") else []
    item.setdefault("raw", {})
    item.setdefault("sourceElementId", "")
    source_ids = item.get("sourceElementIds")
    if not isinstance(source_ids, list):
        source_ids = [item.get("sourceElementId")] if item.get("sourceElementId") else []
    item["sourceElementIds"] = [str(value) for value in source_ids if str(value or "").strip()]
    source_engines = item.get("sourceEngines")
    if not isinstance(source_engines, list):
        source_engines = [item.get("engine")] if item.get("engine") else []
    item["sourceEngines"] = [str(value) for value in source_engines if str(value or "").strip()]
    flags = item.get("qualityFlags")
    if not isinstance(flags, list):
        flags = []
    item["qualityFlags"] = [str(value) for value in flags if str(value or "").strip()]
    item.setdefault("structureType", "")
    return item


def merge_indexes(
    base_index: dict[str, Any],
    extra_index: dict[str, Any],
    prefer_engine_order: list[str] | tuple[str, ...],
) -> dict[str, Any]:
    base = ensure_version_3(base_index)
    extra = ensure_version_3(extra_index)
    preference = {name: order for order, name in enumerate(prefer_engine_order or [])}

    merged = deepcopy(base)
    base_engine = str(base.get("engine") or "")
    extra_engine = str(extra.get("engine") or "")
    merged["engine"] = "hybrid" if extra_engine and extra_engine != base_engine else base_engine

    chain: list[str] = []
    for name in list(base.get("engineChain") or []) + list(extra.get("engineChain") or []):
        value = str(name or "").strip()
        if value and value not in chain:
            chain.append(value)
    merged["engineChain"] = chain
    merged["pages"] = deepcopy(base.get("pages") or [])
    merged["pageCount"] = int(base.get("pageCount") or len(merged["pages"]))

    raw_outputs = dict(base.get("rawOutputs") or {})
    for key, value in (extra.get("rawOutputs") or {}).items():
        if value:
            raw_outputs[key] = value
    merged["rawOutputs"] = {name: str(raw_outputs.get(name) or "") for name in RAW_OUTPUT_ENGINES}
    if extra.get("markdownPath"):
        merged["markdownPath"] = extra.get("markdownPath")
    if extra.get("debugFiles"):
        debug = dict(base.get("debugFiles") or {})
        debug.update({key: value for key, value in (extra.get("debugFiles") or {}).items() if value})
        merged["debugFiles"] = debug

    if extra.get("engineErrors"):
        merged["engineErrors"] = list(base.get("engineErrors") or []) + list(extra.get("engineErrors") or [])

    element_by_key: dict[tuple[Any, ...], dict[str, Any]] = {}
    for element in base.get("elements") or []:
        element_by_key[_element_merge_key(element)] = normalize_element(element, base_engine)
    for element in extra.get("elements") or []:
        item = normalize_element(element, extra_engine)
        key = _element_merge_key(item)
        existing = element_by_key.get(key)
        if existing is None or _engine_rank(item, preference) >= _engine_rank(existing, preference):
            element_by_key[key] = item

    merged["elements"] = sorted(
        element_by_key.values(),
        key=lambda item: (
            int(item.get("page") or 0),
            str(item.get("type") or ""),
            float((item.get("bbox") or [0, 0, 0, 0])[1]),
            float((item.get("bbox") or [0, 0, 0, 0])[0]),
        ),
    )
    return merged


def validate_index(index: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(index, dict):
        return ["index must be a dictionary"]
    for field in ("version", "sourcePath", "sourceSha256", "engine", "pageCount", "pages", "elements"):
        if field not in index:
            errors.append(f"missing top-level field: {field}")
    if not isinstance(index.get("pages", []), list):
        errors.append("pages must be a list")
    if not isinstance(index.get("elements", []), list):
        errors.append("elements must be a list")
        return errors
    required_element_fields = (
        "id",
        "type",
        "page",
        "bbox",
        "pageSize",
        "text",
        "table",
        "csvPath",
        "jsonPath",
        "pngPath",
    )
    for offset, element in enumerate(index.get("elements") or []):
        if not isinstance(element, dict):
            errors.append(f"element {offset} must be a dictionary")
            continue
        for field in required_element_fields:
            if field not in element:
                errors.append(f"element {offset} missing field: {field}")
    return errors


def _engine_rank(element: dict[str, Any], preference: dict[str, int]) -> int:
    return preference.get(str(element.get("engine") or ""), -1)


def _summary_bucket(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        value = {}
    return {"count": int(value.get("count") or 0), "needsReview": int(value.get("needsReview") or 0)}


def _element_merge_key(element: dict[str, Any]) -> tuple[Any, ...]:
    source_id = str(element.get("sourceElementId") or "").strip()
    if source_id:
        return ("source", source_id)
    bbox = normalize_bbox(element.get("bbox"))
    if len(bbox) < 4:
        return ("id", str(element.get("id") or ""))
    return (
        int(element.get("page") or 0),
        str(element.get("type") or ""),
        round(bbox[0]),
        round(bbox[1]),
        round(bbox[2]),
        round(bbox[3]),
    )
