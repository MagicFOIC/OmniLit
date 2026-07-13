from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any


def safe_record_id(record_id: str) -> str:
    """Map an opaque record id to the existing traversal-safe cache directory name."""
    raw = str(record_id or "record")
    value = re.sub(r"[^A-Za-z0-9_.-]+", "_", raw).strip("._")
    value = value[:72] or "record"
    suffix = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:8]
    return f"{value}_{suffix}"


def graph_path(data_root: Path, record_id: str) -> Path:
    return Path(data_root).resolve() / "data" / "literature" / "graphs" / safe_record_id(record_id) / "knowledge_graph.json"


def views_path(data_root: Path, record_id: str) -> Path:
    return graph_path(data_root, record_id).with_name("knowledge_graph_views.json")


def load_graph(data_root: Path, record_id: str, *, max_bytes: int = 32 * 1024 * 1024) -> dict[str, Any]:
    path = graph_path(data_root, record_id)
    try:
        size = path.stat().st_size
    except FileNotFoundError:
        return {}
    if size > max_bytes:
        raise ValueError("graph cache exceeds the configured size limit")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("graph cache root must be an object")
    return payload


def load_views(data_root: Path, record_id: str, *, max_bytes: int = 1024 * 1024) -> list[dict[str, Any]]:
    from .knowledge_graph_views import normalize_snapshot

    path = views_path(data_root, record_id)
    try:
        size = path.stat().st_size
    except FileNotFoundError:
        return []
    if size > max_bytes:
        raise ValueError("graph views exceed the configured size limit")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or (payload.get("recordId") and str(payload["recordId"]) != record_id):
        raise ValueError("graph views root is invalid")
    raw_views = payload.get("views") or []
    if not isinstance(raw_views, list) or len(raw_views) > 100:
        raise ValueError("graph views must contain at most 100 entries")
    return [normalized for item in raw_views if isinstance(item, dict) and (normalized := normalize_snapshot(item, record_id))]


def save_views(data_root: Path, record_id: str, views: list[dict[str, Any]]) -> None:
    from .knowledge_graph_views import VIEW_SNAPSHOT_VERSION, normalize_snapshot

    if len(views) > 100:
        raise ValueError("graph views must contain at most 100 entries")
    normalized = [value for item in views if (value := normalize_snapshot(item, record_id))]
    path = views_path(data_root, record_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    payload = {"version": VIEW_SNAPSHOT_VERSION, "recordId": record_id, "views": normalized}
    try:
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def load_timeline_bundle(data_root: Path, timeline_key: str, *, max_collections: int = 256) -> tuple[str, dict[str, Any], dict[str, Any]]:
    """Load a cached desktop topic-map/evolution pair by collection or evolution cache key."""
    root = (Path(data_root).resolve() / "data" / "literature" / "graphs" / "topic_maps").resolve()

    def read_json(path: Path, max_bytes: int) -> dict[str, Any]:
        resolved = path.resolve()
        if resolved != root and not resolved.is_relative_to(root):
            raise ValueError("timeline cache path escapes the topic-map root")
        if resolved.stat().st_size > max_bytes:
            raise ValueError("timeline cache exceeds the configured size limit")
        payload = json.loads(resolved.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("timeline cache root must be an object")
        return payload

    candidates: list[Path] = []
    direct = root / str(timeline_key)
    if direct.is_dir():
        candidates.append(direct)
    if root.is_dir():
        for candidate in sorted((item for item in root.iterdir() if item.is_dir()), key=lambda item: item.name)[:max_collections]:
            if candidate not in candidates:
                candidates.append(candidate)
    for candidate in candidates:
        evolution_path = candidate / "evolution.json"
        topic_path = candidate / "topic_map.json"
        if not evolution_path.is_file() or not topic_path.is_file():
            continue
        evolution = read_json(evolution_path, 64 * 1024 * 1024)
        if candidate.name != timeline_key and str(evolution.get("cacheKey") or "") != timeline_key:
            continue
        topic_map = read_json(topic_path, 16 * 1024 * 1024)
        return candidate.name, topic_map, evolution
    return "", {}, {}
