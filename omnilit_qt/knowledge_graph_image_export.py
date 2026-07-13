from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
MAX_EXPORT_DIMENSION = 16_384
MAX_EXPORT_PIXELS = 100_000_000


def sanitize_export_stem(value: str, fallback: str = "knowledge-graph") -> str:
    text = re.sub(r"[<>:\"/\\|?*\x00-\x1f]+", "_", str(value or "").strip())
    text = re.sub(r"\s+", " ", text).strip(" ._")
    return (text[:96].rstrip(" ._") or fallback)[:96]


def normalize_export_options(scope: str, scale: Any, transparent: Any) -> dict[str, Any]:
    selected_scope = str(scope or "viewport").casefold()
    if selected_scope not in {"viewport", "full"}:
        selected_scope = "viewport"
    try:
        selected_scale = float(scale)
    except (TypeError, ValueError):
        selected_scale = 1.0
    selected_scale = max(1.0, min(4.0, selected_scale))
    return {"scope": selected_scope, "scale": selected_scale, "transparent": bool(transparent)}


def validate_export_dimensions(width: Any, height: Any, scale: Any) -> tuple[bool, str, tuple[int, int]]:
    try:
        pixel_width = max(1, int(round(float(width) * float(scale))))
        pixel_height = max(1, int(round(float(height) * float(scale))))
    except (TypeError, ValueError):
        return False, "导出尺寸无效。", (0, 0)
    if pixel_width > MAX_EXPORT_DIMENSION or pixel_height > MAX_EXPORT_DIMENSION:
        return False, f"导出尺寸超过 {MAX_EXPORT_DIMENSION}px 上限。", (pixel_width, pixel_height)
    if pixel_width * pixel_height > MAX_EXPORT_PIXELS:
        return False, "导出像素总量超过安全上限。", (pixel_width, pixel_height)
    return True, "", (pixel_width, pixel_height)


def unique_export_path(directory: Path, name: str) -> Path:
    directory = Path(directory)
    stem = sanitize_export_stem(name)
    candidate = directory / f"{stem}.png"
    counter = 2
    while candidate.exists():
        candidate = directory / f"{stem}-{counter}.png"
        counter += 1
    return candidate


def is_valid_png(path: Path) -> bool:
    try:
        with Path(path).open("rb") as handle:
            return handle.read(len(PNG_SIGNATURE)) == PNG_SIGNATURE
    except OSError:
        return False


def export_manifest(path: Path, record_id: str, options: dict[str, Any], graph_fingerprint: str) -> dict[str, Any]:
    return {
        "version": 1,
        "recordId": str(record_id or ""),
        "fileName": Path(path).name,
        "scope": str(options.get("scope") or "viewport"),
        "scale": float(options.get("scale") or 1.0),
        "transparent": bool(options.get("transparent", False)),
        "graphFingerprint": str(graph_fingerprint or ""),
        "exportedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
