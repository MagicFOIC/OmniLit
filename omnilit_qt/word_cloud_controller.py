from __future__ import annotations

import hashlib
import json
import re
import threading
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Property, Signal, Slot

from .background_tasks import ManagedWorker, shutdown_workers
from .knowledge_graph_builder import build_knowledge_graph
from .word_cloud_core import build_word_cloud


class WordCloudController(QObject):
    changed = Signal()
    cloudReady = Signal(str)
    _taskFinished = Signal(str, object, str, bool)

    def __init__(self, shell, paths, store, locale) -> None:
        super().__init__()
        self.paths = paths
        self._loading = False
        self._status = ""
        self._cloud: dict[str, Any] = {}
        self._selected: dict[str, Any] = {}
        self._scope = ""
        self._current_key = ""
        self._worker: ManagedWorker | None = None
        self._stop = threading.Event()
        self._taskFinished.connect(self._on_task_finished)

    @staticmethod
    def _safe_id(value: str) -> str:
        clean = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "record")).strip("._")[:72] or "record"
        return f"{clean}_{hashlib.sha1(str(value).encode('utf-8')).hexdigest()[:8]}"

    def _graph_path(self, record_id: str) -> Path:
        return self.paths.data("Literature", "graphs", self._safe_id(record_id), "knowledge_graph.json")

    def _index_path(self, record_id: str) -> Path:
        return self.paths.data("Literature", "extractions", self._safe_id(record_id), "extraction_index.json")

    def _record_cloud_path(self, record_id: str) -> Path:
        return self.paths.data("Literature", "graphs", self._safe_id(record_id), "word_cloud.json")

    def _collection_path(self, key: str) -> Path:
        return self.paths.data("Literature", "graphs", "word_cloud_collections", key, "word_cloud.json")

    @Property(bool, notify=changed)
    def loading(self) -> bool: return self._loading

    @Property(str, notify=changed)
    def statusText(self) -> str: return self._status

    @Property("QVariantMap", notify=changed)
    def cloud(self) -> dict[str, Any]: return dict(self._cloud)

    @Property("QVariantMap", notify=changed)
    def selectedTerm(self) -> dict[str, Any]: return dict(self._selected)

    @Property(str, notify=changed)
    def currentScope(self) -> str: return self._scope

    @Property(str, notify=changed)
    def currentKey(self) -> str: return self._current_key

    def _read(self, path: Path) -> dict[str, Any]:
        if not path.exists(): return {}
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}

    def _write(self, path: Path, value: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)

    @Slot(str, "QVariantMap", str, result=bool)
    def generateForRecord(self, record_id: str, record: dict, pdf_path: str) -> bool:
        key = str(record_id or "").strip()
        if not key or self._loading: return False
        cached = self._read(self._record_cloud_path(key))
        graph = self._read(self._graph_path(key))
        if cached and graph and cached.get("cacheKey") == build_word_cloud([graph], "record", str(record.get("title") or "词云"), 80).get("cacheKey"):
            self._set_cloud(key, cached, "已加载缓存词云。")
            return True
        return self._start(key, "record", [dict(record or {})], self._record_cloud_path(key), str(record.get("title") or "文献词云"), 80)

    @Slot("QVariantList", result=bool)
    def generateForRecords(self, records: list) -> bool:
        payloads = [dict(item) for item in records or [] if isinstance(item, dict)]
        if not payloads or self._loading: return False
        record_ids = sorted(str(item.get("recordId") or item.get("id") or "") for item in payloads)
        key = hashlib.sha1("\n".join(record_ids).encode("utf-8")).hexdigest()[:16]
        return self._start(key, "library", payloads, self._collection_path(key), f"当前筛选结果词云（{len(payloads)} 篇）", 120)

    def _start(self, key: str, scope: str, records: list[dict], path: Path, title: str, limit: int) -> bool:
        cached = self._read(path)
        if cached:
            graphs = [self._read(self._graph_path(str(item.get("recordId") or item.get("id") or ""))) for item in records]
            graphs = [item for item in graphs if item]
            if len(graphs) == len(records) and cached.get("cacheKey") == build_word_cloud(graphs, scope, title, limit).get("cacheKey"):
                self._set_cloud(key, cached, "已加载缓存词云。")
                return True
        self._loading = True; self._scope = scope; self._current_key = key; self._status = "正在生成词云..."; self._stop.clear(); self.changed.emit()

        def run() -> None:
            try:
                graphs = []
                for record in records:
                    if self._stop.is_set(): return
                    record_id = str(record.get("recordId") or record.get("id") or "record")
                    graph = self._read(self._graph_path(record_id))
                    if not graph:
                        graph = build_knowledge_graph(record, self._read(self._index_path(record_id)) or None)
                    graphs.append(graph)
                cloud = build_word_cloud(graphs, scope, title, limit)
                self._write(path, cloud)
                message = f"词云已生成：{len(cloud.get('terms') or [])} 个词。"
                task.update_state("completed", detail=message); self._taskFinished.emit(key, cloud, message, True)
            except Exception as exc:
                message = f"词云生成失败：{exc}"; task.update_state("failed", detail=message); self._taskFinished.emit(key, {}, message, False)

        task = ManagedWorker(name="WordCloudBuild", target=run, state_path=self.paths.data("task_state", f"word_cloud_{key}.json"), cancel_event=self._stop, metadata={"scope": scope, "key": key})
        self._worker = task; task.start(); return True

    def _set_cloud(self, key: str, cloud: dict[str, Any], status: str) -> None:
        self._current_key = key; self._scope = str(cloud.get("scope") or ""); self._cloud = cloud; self._selected = {}; self._status = status; self.changed.emit(); self.cloudReady.emit(key)

    def _on_task_finished(self, key: str, cloud: object, message: str, success: bool) -> None:
        self._loading = False; self._status = message
        if success and isinstance(cloud, dict): self._cloud = cloud; self._selected = {}; self.cloudReady.emit(key)
        self.changed.emit()

    @Slot(str, result=bool)
    def loadCloud(self, key: str) -> bool:
        path = self._record_cloud_path(key) if self._scope != "library" else self._collection_path(key)
        cloud = self._read(path)
        if not cloud: return False
        self._set_cloud(key, cloud, "词云已加载。"); return True

    @Slot(str, result=bool)
    def hasCloud(self, record_id: str) -> bool:
        return bool(str(record_id or "")) and self._record_cloud_path(str(record_id)).is_file()

    @Slot(str, result=bool)
    def selectTerm(self, normalized: str) -> bool:
        term = next((item for item in self._cloud.get("terms") or [] if str(item.get("normalized") or "") == str(normalized)), None)
        self._selected = dict(term or {}); self.changed.emit(); return term is not None

    @Slot(str, result="QVariantList")
    def evidenceForTerm(self, normalized: str) -> list[dict[str, Any]]:
        term = next((item for item in self._cloud.get("terms") or [] if str(item.get("normalized") or "") == str(normalized)), {})
        return [dict(item) for item in term.get("evidence") or [] if isinstance(item, dict)]

    def shutdown(self, timeout: float = 15.0) -> bool:
        self._stop.set(); return shutdown_workers([self._worker], timeout=timeout)
