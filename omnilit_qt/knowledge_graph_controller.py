from __future__ import annotations

import hashlib
import json
import re
import threading
from collections import Counter, OrderedDict
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Property, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices

from .background_tasks import ManagedWorker, shutdown_workers
from .knowledge_graph_builder import BUILDER_VERSION, build_knowledge_graph, source_fingerprint
from .knowledge_graph_compare import compare_graph_dicts
from .knowledge_graph_export import export_csv, export_markdown, export_mermaid
from .knowledge_graph_schema import KnowledgeGraphDocument


class KnowledgeGraphController(QObject):
    changed = Signal()
    graphReady = Signal(str)
    evidenceFocusRequested = Signal(str, int, "QVariantList", str)
    _taskFinished = Signal(str, object, str, bool)
    _batchFinished = Signal(int, str, bool)

    def __init__(self, shell, paths, store, locale) -> None:
        super().__init__()
        self.shell = shell
        self.paths = paths
        self.store = store
        self.locale = locale
        self._loading = False
        self._status = ""
        self._graph: dict[str, Any] = {}
        self._selected_node: dict[str, Any] = {}
        self._selected_edge: dict[str, Any] = {}
        self._filter_mode = "all"
        self._search_text = ""
        self._pdf_extraction = None
        self._current_record_id = ""
        self._graphs: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._graph_statuses: dict[str, str] = {}
        self._cache_state = "missing"
        self._node_limit = 80
        self._density = "normal"
        self._worker: ManagedWorker | None = None
        self._stop = threading.Event()
        self._taskFinished.connect(self._on_task_finished)
        self._batchFinished.connect(self._on_batch_finished)

    @staticmethod
    def _safe_record_id(record_id: str) -> str:
        value = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(record_id or "record")).strip("._")
        value = value[:72] or "record"
        suffix = hashlib.sha1(str(record_id).encode("utf-8")).hexdigest()[:8]
        return f"{value}_{suffix}"

    def _graph_dir(self, record_id: str) -> Path:
        return self.paths.data("Literature", "graphs", self._safe_record_id(record_id))

    def _graph_path(self, record_id: str) -> Path:
        return self._graph_dir(record_id) / "knowledge_graph.json"

    def _index_path(self, record_id: str) -> Path:
        return self.paths.data("Literature", "extractions", self._safe_record_id(record_id), "extraction_index.json")

    def _load_or_build_fast_index(self, record_id: str, pdf_path: str) -> tuple[dict[str, Any], bool]:
        index = self._load_json(self._index_path(record_id))
        if index:
            return index, False
        source = Path(str(pdf_path or "")).expanduser()
        if not source.is_file():
            return {}, False
        try:
            from .pdf_extraction_engines import PyMuPDFExtractionEngine

            engine = PyMuPDFExtractionEngine()
            if not engine.is_available():
                return {}, False
            index = engine.analyze(source, self._index_path(record_id).parent, {"engine": "fast"})
            return (index if isinstance(index, dict) else {}), True
        except Exception:
            return {}, False

    @Property(bool, notify=changed)
    def loading(self) -> bool:
        return self._loading

    @Property(str, notify=changed)
    def statusText(self) -> str:
        return self._status

    @Property("QVariantMap", notify=changed)
    def graph(self) -> dict[str, Any]:
        return dict(self._graph)

    @Property(str, notify=changed)
    def currentRecordId(self) -> str:
        return self._current_record_id

    @Property(str, notify=changed)
    def graphJson(self) -> str:
        return json.dumps(self._graph, ensure_ascii=False)

    @Property("QVariantList", notify=changed)
    def nodes(self) -> list[dict[str, Any]]:
        return self._visible_nodes()

    @Property("QVariantList", notify=changed)
    def edges(self) -> list[dict[str, Any]]:
        visible_ids = {str(node.get("id") or "") for node in self._visible_nodes()}
        return [dict(edge) for edge in self._graph.get("edges") or [] if edge.get("source") in visible_ids and edge.get("target") in visible_ids]

    @Property("QVariantMap", notify=changed)
    def selectedNode(self) -> dict[str, Any]:
        return dict(self._selected_node)

    @Property("QVariantMap", notify=changed)
    def selectedEdge(self) -> dict[str, Any]:
        return dict(self._selected_edge)

    @Property(str, notify=changed)
    def filterMode(self) -> str:
        return self._filter_mode

    @Property("QVariantMap", notify=changed)
    def filterCounts(self) -> dict[str, int]:
        counts = Counter(str(node.get("type") or "").casefold() for node in self._graph.get("nodes") or [])
        groups = {
            "structure": {"section", "paragraph"},
            "method": {"method", "algorithm", "model"},
            "experiment": {"experiment", "dataset", "metric", "baseline"},
            "result": {"result", "claim"},
            "figure": {"figure", "table", "equation"},
            "citation": {"citation", "baseline"},
            "limitation": {"limitation", "futurework", "missinginfo"},
            "conflict": {"conflict"},
        }
        result = {mode: sum(counts[kind] for kind in kinds) for mode, kinds in groups.items()}
        result["all"] = sum(counts.values())
        result["common"] = counts["comparison"]
        result["different"] = sum(bool((node.get("details") or {}).get("only_in")) for node in self._graph.get("nodes") or [])
        return result

    @Property(str, notify=changed)
    def cacheState(self) -> str:
        return self._cache_state

    @Property("QVariantMap", notify=changed)
    def qualitySummary(self) -> dict[str, Any]:
        return dict(self._graph.get("quality_summary") or (self._graph.get("metadata") or {}).get("quality_summary") or {})

    @Property("QVariantMap", notify=changed)
    def layout(self) -> dict[str, Any]:
        return dict(self._graph.get("layout") or (self._graph.get("metadata") or {}).get("layout") or {})

    def setPdfExtractionController(self, controller) -> None:
        self._pdf_extraction = controller

    def _visible_nodes(self) -> list[dict[str, Any]]:
        nodes = [dict(node) for node in self._graph.get("nodes") or []]
        mode_types = {
            "structure": {"paper", "section", "paragraph"},
            "method": {"paper", "method", "algorithm", "model"},
            "experiment": {"paper", "experiment", "dataset", "metric", "baseline"},
            "result": {"paper", "result", "claim"},
            "figure": {"paper", "figure", "table", "equation"},
            "citation": {"paper", "citation", "baseline"},
            "limitation": {"paper", "limitation", "futurework", "missinginfo"},
            "common": {"paper", "comparison"},
            "conflict": {"paper", "conflict"},
        }
        allowed = mode_types.get(self._filter_mode)
        if allowed:
            nodes = [node for node in nodes if str(node.get("type") or "").casefold() in allowed]
        elif self._filter_mode == "different":
            nodes = [node for node in nodes if str(node.get("type") or "").casefold() == "paper" or (node.get("details") or {}).get("only_in")]
        query = self._search_text.casefold().strip()
        if query:
            nodes = [node for node in nodes if query in " ".join((str(node.get("label") or ""), str(node.get("summary") or ""), " ".join(str(tag) for tag in node.get("tags") or []))).casefold() or str(node.get("type") or "").casefold() == "paper"]
        if self._density in {"compact", "normal"} and not query:
            nodes = [node for node in nodes if str(node.get("type") or "").casefold() == "paper" or float(node.get("confidence", 1.0) or 0.0) >= 0.6]
        paper = [node for node in nodes if str(node.get("type") or "").casefold() == "paper"]
        others = [node for node in nodes if str(node.get("type") or "").casefold() != "paper"]
        others.sort(key=lambda node: (-float(node.get("importance", node.get("weight", 0.5)) or 0.0), -float(node.get("confidence", 1.0) or 0.0), str(node.get("label") or "").casefold()))
        return paper + others[:max(0, self._node_limit - len(paper))]

    def _remember_graph(self, key: str, graph: dict[str, Any]) -> None:
        self._graphs.pop(key, None)
        self._graphs[key] = graph
        while len(self._graphs) > 16:
            self._graphs.popitem(last=False)

    def _load_json(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
        return value if isinstance(value, dict) else {}

    def _write_json(self, path: Path, graph: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(graph, handle, ensure_ascii=False, indent=2)
        temporary.replace(path)

    @Slot(str, str, result=bool)
    @Slot(str, "QVariantMap", str, result=bool)
    def generateGraph(self, record_id: str, record: Any, pdf_path: str = "") -> bool:
        if isinstance(record, str):
            pdf_path, record = record, {"recordId": record_id, "localPdfPath": record}
        return self._generate(record_id, dict(record or {}), pdf_path, force=False)

    @Slot(str, str, result=bool)
    @Slot(str, "QVariantMap", str, result=bool)
    def regenerateGraph(self, record_id: str, record: Any, pdf_path: str = "") -> bool:
        if isinstance(record, str):
            pdf_path, record = record, {"recordId": record_id, "localPdfPath": record}
        return self._generate(record_id, dict(record or {}), pdf_path, force=True)

    @staticmethod
    def _comparison_key(records: list[dict]) -> str:
        record_ids = sorted(str(record.get("recordId") or record.get("id") or "") for record in records)
        digest = hashlib.sha1("\n".join(record_ids).encode("utf-8")).hexdigest()[:12]
        return f"comparison_{digest}"

    @Slot("QVariantList", result=bool)
    def generateComparisonGraph(self, records: list) -> bool:
        return self._generate_comparison(records, force=False)

    @Slot("QVariantList", result=bool)
    def regenerateComparisonGraph(self, records: list) -> bool:
        return self._generate_comparison(records, force=True)

    def _generate_comparison(self, records: list, force: bool) -> bool:
        payloads = [dict(record) for record in (records or []) if isinstance(record, dict)]
        if not payloads or self._loading:
            return False
        key = self._comparison_key(payloads)
        cached = {} if force else self._load_json(self._graph_path(key))
        if cached:
            self._current_record_id = key
            self._graph = cached
            self._remember_graph(key, cached)
            self._cache_state = "fresh"
            self._filter_mode = "all"
            self._search_text = ""
            self._status = "已加载缓存对比知识图谱。"
            self.changed.emit()
            self.graphReady.emit(key)
            return True

        self._loading = True
        self._current_record_id = key
        self._status = "正在生成对比知识图谱..."
        self._stop.clear()
        self.changed.emit()

        def run() -> None:
            try:
                graphs: list[dict[str, Any]] = []
                for record in payloads:
                    if self._stop.is_set():
                        return
                    record_key = str(record.get("recordId") or record.get("id") or "record")
                    record["recordId"] = record_key
                    extraction_index = self._load_json(self._index_path(record_key))
                    graphs.append(build_knowledge_graph(record, extraction_index or None))
                graph = compare_graph_dicts(graphs, key)
                self._write_json(self._graph_path(key), graph)
                message = f"已生成 {len(graphs)} 篇文献的对比知识图谱。"
                task.update_state("completed", detail=message)
                self._taskFinished.emit(key, graph, message, True)
            except Exception as exc:
                message = f"对比知识图谱生成失败：{exc}"
                task.update_state("failed", detail=message)
                self._taskFinished.emit(key, {}, message, False)

        task = ManagedWorker(
            name="KnowledgeGraphComparisonBuild",
            target=run,
            state_path=self.paths.data("task_state", f"knowledge_graph_{self._safe_record_id(key)}.json"),
            cancel_event=self._stop,
            metadata={"record_ids": [str(record.get("recordId") or "") for record in payloads]},
        )
        self._worker = task
        task.start()
        return True

    @Slot("QVariantList", result=bool)
    def generateGraphs(self, records: list) -> bool:
        payloads = [dict(record) for record in (records or []) if isinstance(record, dict) and str(record.get("localPdfPath") or "").strip()]
        if not payloads or self._loading:
            self._status = "没有可批量生成图谱的本地 PDF。" if not payloads else "已有知识图谱任务正在运行。"
            self.changed.emit()
            return False
        self._loading = True
        self._current_record_id = "__batch__"
        self._status = f"正在批量生成知识图谱：0 / {len(payloads)}"
        self._stop.clear()
        self.changed.emit()

        def run() -> None:
            completed = 0
            try:
                for record in payloads:
                    if self._stop.is_set():
                        break
                    record_id = str(record.get("recordId") or record.get("id") or "record")
                    graph_path = self._graph_path(record_id)
                    if not graph_path.exists() or self.graphStatus(record_id, str(record.get("localPdfPath") or "")) == "需更新":
                        extraction_index, _ = self._load_or_build_fast_index(record_id, str(record.get("localPdfPath") or ""))
                        graph = build_knowledge_graph(record, extraction_index or None)
                        self._write_json(graph_path, graph)
                        self._remember_graph(record_id, graph)
                        self._graph_statuses[record_id] = "已生成"
                    completed += 1
                    self._status = f"正在批量生成知识图谱：{completed} / {len(payloads)}"
                    self.changed.emit()
                message = f"批量知识图谱生成完成：{completed} / {len(payloads)}。"
                task.update_state("completed", detail=message)
                self._batchFinished.emit(completed, message, True)
            except Exception as exc:
                message = f"批量知识图谱生成失败：{exc}"
                task.update_state("failed", detail=message)
                self._batchFinished.emit(completed, message, False)

        task = ManagedWorker(
            name="KnowledgeGraphBatchBuild",
            target=run,
            state_path=self.paths.data("task_state", "knowledge_graph_batch.json"),
            cancel_event=self._stop,
            metadata={"record_ids": [str(record.get("recordId") or "") for record in payloads]},
        )
        self._worker = task
        task.start()
        return True

    def _generate(self, record_id: str, record: dict, pdf_path: str, force: bool) -> bool:
        key = str(record_id or "").strip()
        if not key or self._loading:
            return False
        payload = dict(record or {})
        payload["recordId"] = key
        if pdf_path:
            payload["localPdfPath"] = str(pdf_path)
        extraction_index = self._load_json(self._index_path(key))
        cached = {} if force else self._load_json(self._graph_path(key))
        if cached:
            self._current_record_id = key
            self._graph = cached
            self._remember_graph(key, cached)
            self._filter_mode = "all"
            self._search_text = ""
            expected = source_fingerprint(payload, extraction_index)
            fresh = int(cached.get("builder_version") or 1) >= BUILDER_VERSION and str(cached.get("source_fingerprint") or "") == expected
            self._cache_state = "fresh" if fresh else "stale"
            self._status = "已加载缓存知识图谱。" if fresh else "已显示旧图谱，正在后台更新..."
            self.changed.emit()
            self.graphReady.emit(key)
            if fresh:
                return True
        self._loading = True
        self._current_record_id = key
        self._cache_state = "refreshing" if cached else "building"
        if not cached:
            self._status = "正在生成知识图谱..."
        self._stop.clear()
        self.changed.emit()

        def run() -> None:
            try:
                if self._stop.is_set():
                    return
                effective_index, generated_fast_index = self._load_or_build_fast_index(key, str(pdf_path or payload.get("localPdfPath") or ""))
                graph = build_knowledge_graph(payload, effective_index or extraction_index or None)
                self._write_json(self._graph_path(key), graph)
                message = "已完成本地快速解析并生成知识图谱。" if generated_fast_index else ("知识图谱已生成。" if effective_index or extraction_index else "未找到可解析正文，已使用文献元数据生成基础图谱。")
                task.update_state("completed", detail=message)
                self._taskFinished.emit(key, graph, message, True)
            except Exception as exc:
                message = f"知识图谱生成失败：{exc}"
                task.update_state("failed", detail=message)
                self._taskFinished.emit(key, {}, message, False)

        task = ManagedWorker(
            name="KnowledgeGraphBuild",
            target=run,
            state_path=self.paths.data("task_state", f"knowledge_graph_{self._safe_record_id(key)}.json"),
            cancel_event=self._stop,
            metadata={"record_id": key, "pdf_path": str(pdf_path or "")},
        )
        self._worker = task
        task.start()
        return True

    def _on_task_finished(self, record_id: str, graph: object, message: str, success: bool) -> None:
        self._loading = False
        self._status = message
        if success and isinstance(graph, dict):
            self._graph = graph
            self._filter_mode = "all"
            self._search_text = ""
            self._selected_node = {}
            self._selected_edge = {}
            self._remember_graph(record_id, graph)
            self._graph_statuses[record_id] = "已生成"
            self._cache_state = "fresh"
            self.graphReady.emit(record_id)
        self.changed.emit()

    def _on_batch_finished(self, completed: int, message: str, success: bool) -> None:
        self._loading = False
        self._status = message
        self.changed.emit()

    @Slot(str, result="QVariantMap")
    def graphFor(self, record_id: str) -> dict[str, Any]:
        key = str(record_id or "")
        graph = self._graphs.get(key) or self._load_json(self._graph_path(key))
        if graph:
            self._remember_graph(key, graph)
        return dict(graph)

    @Slot(str, str, result=str)
    def graphStatus(self, record_id: str, pdf_path: str = "") -> str:
        cached_status = self._graph_statuses.get(str(record_id or ""))
        if cached_status:
            return cached_status
        graph_path = self._graph_path(str(record_id or ""))
        if not graph_path.exists():
            return "未生成"
        try:
            source_paths = [Path(str(pdf_path)).expanduser()] if pdf_path else []
            source_paths.append(self._index_path(str(record_id or "")))
            if any(path.exists() and path.stat().st_mtime > graph_path.stat().st_mtime for path in source_paths):
                self._graph_statuses[str(record_id or "")] = "需更新"
                return "需更新"
        except OSError:
            pass
        self._graph_statuses[str(record_id or "")] = "已生成"
        return "已生成"

    @Slot(str, result=bool)
    def hasGraph(self, record_id: str) -> bool:
        return bool(str(record_id or "")) and self._graph_path(str(record_id)).is_file()

    @Slot(str, result=bool)
    def loadGraph(self, record_id: str) -> bool:
        graph = self.graphFor(record_id)
        if not graph:
            self._status = "未找到知识图谱缓存。"
            self.changed.emit()
            return False
        self._current_record_id = str(record_id or "")
        self._graph = graph
        self._cache_state = "fresh"
        self._filter_mode = "all"
        self._search_text = ""
        self._selected_node = {}
        self._selected_edge = {}
        self._status = "知识图谱已加载。"
        self.changed.emit()
        self.graphReady.emit(self._current_record_id)
        return True

    @Slot(str, result=bool)
    def selectNode(self, node_id: str) -> bool:
        node = next((item for item in self._graph.get("nodes") or [] if str(item.get("id") or "") == str(node_id)), None)
        self._selected_node = dict(node or {})
        self._selected_edge = {}
        self.changed.emit()
        return node is not None

    @Slot(str, result=bool)
    def selectEdge(self, edge_id: str) -> bool:
        edge = next((item for item in self._graph.get("edges") or [] if str(item.get("id") or "") == str(edge_id)), None)
        self._selected_edge = dict(edge or {})
        self._selected_node = {}
        self.changed.emit()
        return edge is not None

    @Slot(str, int, result=bool)
    def focusEvidence(self, node_id: str, evidence_index: int) -> bool:
        item = next((node for node in self._graph.get("nodes") or [] if str(node.get("id") or "") == str(node_id)), None)
        if item is None:
            item = next((edge for edge in self._graph.get("edges") or [] if str(edge.get("id") or "") == str(node_id)), None)
        evidence = (item or {}).get("evidence") or []
        if evidence_index < 0 or evidence_index >= len(evidence) or not isinstance(evidence[evidence_index], dict):
            return False
        target = evidence[evidence_index]
        record_id = str(target.get("record_id") or target.get("recordId") or self._current_record_id)
        element_id = str(target.get("element_id") or target.get("elementId") or "")
        page = int(target.get("page", -1) if target.get("page") is not None else -1)
        bbox = list(target.get("bbox") or [])
        self.evidenceFocusRequested.emit(record_id, page, bbox, element_id)
        return page >= 0 or bool(element_id)

    @Slot(str)
    def setFilterMode(self, mode: str) -> None:
        self._filter_mode = str(mode or "all").casefold()
        self._selected_edge = {}
        visible = self._visible_nodes()
        matching = [node for node in visible if str(node.get("type") or "").casefold() != "paper"]
        self._selected_node = dict(matching[0] if matching else (visible[0] if visible else {}))
        self.changed.emit()

    @Slot(str)
    def search(self, keyword: str) -> None:
        self._search_text = str(keyword or "")
        self.changed.emit()

    @Slot(str, result=bool)
    def prefetchGraph(self, record_id: str) -> bool:
        key = str(record_id or "")
        if key in self._graphs:
            self._graphs.move_to_end(key)
            return True
        graph = self._load_json(self._graph_path(key))
        if not graph:
            return False
        self._remember_graph(key, graph)
        return True

    @Slot(str)
    def invalidateRecord(self, record_id: str) -> None:
        key = str(record_id or "")
        self._graph_statuses.pop(key, None)
        self._graphs.pop(key, None)
        self.changed.emit()

    @Slot(str)
    def setDensity(self, density: str) -> None:
        self._density = str(density or "normal").casefold()
        self._node_limit = {"compact": 50, "normal": 80, "detailed": 120, "all": 10000}.get(self._density, 80)
        self.changed.emit()

    @Slot(str, result=str)
    def exportGraphJson(self, record_id: str) -> str:
        path = self._graph_path(str(record_id or ""))
        if not path.exists():
            return ""
        self._status = f"JSON 已导出：{path}"
        self.changed.emit()
        return str(path)

    @Slot(str, result=str)
    def exportGraphMarkdown(self, record_id: str) -> str:
        key = str(record_id or "")
        graph = self.graphFor(key)
        if not graph:
            return ""
        path = self._graph_dir(key) / "knowledge_graph.md"
        document = KnowledgeGraphDocument.from_dict(graph)
        export_markdown(document, path, comparison=bool((document.metadata or {}).get("comparison")))
        self._status = f"Markdown 已导出：{path}"
        self.changed.emit()
        return str(path)

    @Slot(str, str, result=str)
    def exportGraph(self, record_id: str, format_name: str) -> str:
        key = str(record_id or "")
        graph = self.graphFor(key)
        if not graph:
            return ""
        document = KnowledgeGraphDocument.from_dict(graph)
        export_dir = self._graph_dir(key)
        selected = str(format_name or "json").casefold()
        if selected == "json":
            return self.exportGraphJson(key)
        if selected in {"markdown", "md"}:
            return self.exportGraphMarkdown(key)
        if selected in {"mermaid", "mmd"}:
            path = export_mermaid(document, export_dir / "knowledge_graph.mmd")
        elif selected in {"csv", "csv_nodes", "csv_edges"}:
            nodes_path, edges_path = export_csv(document, export_dir / "knowledge_graph_nodes.csv", export_dir / "knowledge_graph_edges.csv")
            path = edges_path if selected == "csv_edges" else nodes_path
        else:
            self._status = f"不支持的图谱导出格式：{format_name}"
            self.changed.emit()
            return ""
        self._status = f"图谱已导出：{path}"
        self.changed.emit()
        return str(path)

    @Slot(str, result=bool)
    def openGraphDirectory(self, record_id: str) -> bool:
        path = self._graph_dir(str(record_id or ""))
        if not path.exists():
            return False
        return bool(QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))))

    def shutdown(self, timeout: float = 15.0) -> bool:
        self._stop.set()
        return shutdown_workers([self._worker], timeout=timeout)
