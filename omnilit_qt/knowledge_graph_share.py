from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .knowledge_graph_ontology import ONTOLOGY_VERSION
from .knowledge_graph_schema import KnowledgeGraphDocument
from .knowledge_graph_views import normalize_snapshot


SHARE_PACKAGE_KIND = "omnilit.knowledge-graph-share"
SHARE_PACKAGE_VERSION = 1
MAX_SHARE_PACKAGE_BYTES = 100 * 1024 * 1024


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _digest(graph: dict[str, Any], view: dict[str, Any]) -> str:
    payload = json.dumps({"graph": graph, "view": view}, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_share_package(graph: dict[str, Any], view: dict[str, Any]) -> dict[str, Any]:
    document = KnowledgeGraphDocument.from_dict(graph)
    canonical_graph = document.to_dict()
    if not document.record_id or not canonical_graph.get("nodes"):
        raise ValueError("分享包需要包含有效文献标识和至少一个图谱节点。")
    snapshot = normalize_snapshot(view, document.record_id)
    if snapshot is None:
        raise ValueError("分享视图与图谱文献不匹配。")
    return {
        "kind": SHARE_PACKAGE_KIND,
        "version": SHARE_PACKAGE_VERSION,
        "createdAt": _timestamp(),
        "ontologyVersion": ONTOLOGY_VERSION,
        "recordId": document.record_id,
        "graphFingerprint": str(canonical_graph.get("source_fingerprint") or ""),
        "graph": canonical_graph,
        "view": snapshot,
        "integrity": {"algorithm": "sha256", "digest": _digest(canonical_graph, snapshot)},
    }


def load_share_package(path: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    candidate = Path(path).expanduser().resolve()
    if not candidate.is_file():
        raise ValueError("未找到知识图谱分享包。")
    if candidate.stat().st_size > MAX_SHARE_PACKAGE_BYTES:
        raise ValueError("分享包超过 100 MB 安全上限。")
    try:
        with candidate.open("r", encoding="utf-8") as handle:
            package = json.load(handle)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("分享包不是有效的 UTF-8 JSON 文件。") from exc
    if not isinstance(package, dict) or package.get("kind") != SHARE_PACKAGE_KIND:
        raise ValueError("文件不是 OmniLit 知识图谱分享包。")
    if int(package.get("version") or 0) != SHARE_PACKAGE_VERSION:
        raise ValueError(f"不支持的分享包版本：{package.get('version')}。")
    graph = dict(package.get("graph") or {})
    document = KnowledgeGraphDocument.from_dict(graph)
    canonical_graph = document.to_dict()
    if not document.record_id or not document.nodes:
        raise ValueError("分享包中的图谱为空或已损坏。")
    snapshot = normalize_snapshot(dict(package.get("view") or {}), document.record_id)
    if snapshot is None:
        raise ValueError("分享包中的视图与图谱不匹配。")
    integrity = dict(package.get("integrity") or {})
    expected = str(integrity.get("digest") or "")
    # Verify the serialized payload first; canonicalization happens only after trust is established.
    if not expected or expected != _digest(graph, dict(package.get("view") or {})):
        raise ValueError("分享包完整性校验失败，文件可能已被修改。")
    return canonical_graph, snapshot, package


def write_share_package(path: Path, package: dict[str, Any]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(package, handle, ensure_ascii=False, indent=2)
    temporary.replace(target)
    return target
