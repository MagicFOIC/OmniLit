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
from .knowledge_graph_builder import build_knowledge_graph, cache_is_fresh, node_is_visible_at_density
from .knowledge_graph_compare import compare_graph_dicts
from .knowledge_graph_export import export_csv, export_markdown, export_mermaid
from .knowledge_graph_facets import FACET_KEYS, facet_options, facet_visible_node_ids, normalize_facet_filters
from .knowledge_graph_exploration import neighbor_page, neighbor_summary, seed_node_ids
from .knowledge_graph_history import KnowledgeGraphHistory
from .knowledge_graph_image_export import export_manifest, is_valid_png, normalize_export_options, unique_export_path, validate_export_dimensions
from .knowledge_graph_literature import SORT_KEYS, project_literature_rows
from .knowledge_graph_lod import normalize_render_viewport, project_render_graph
from .knowledge_graph_ontology import canonical_relation_filter
from .knowledge_graph_paths import available_relation_types, shortest_path
from .knowledge_graph_schema import KnowledgeGraphDocument
from .knowledge_graph_share import build_share_package, load_share_package, write_share_package
from .knowledge_graph_replay import build_replay_events
from .knowledge_graph_semantic_comparison import build_semantic_comparison, clear_review, make_review
from .knowledge_graph_views import VIEW_SNAPSHOT_VERSION, make_snapshot, normalize_snapshot, normalize_viewport, reconcile_snapshot, view_summaries


class KnowledgeGraphController(QObject):
    changed = Signal()
    renderChanged = Signal()
    hoverChanged = Signal()
    graphReady = Signal(str)
    evidenceFocusRequested = Signal(str, int, "QVariantList", str)
    viewRestored = Signal("QVariantMap")
    historyRestored = Signal()
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
        self._selected_semantic_cell: dict[str, Any] = {}
        self._comparison_records: list[dict[str, Any]] = []
        self._filter_mode = "all"
        self._facet_filters: dict[str, str] = {}
        self._search_text = ""
        self._pdf_extraction = None
        self._current_record_id = ""
        self._graphs: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._graph_statuses: dict[str, str] = {}
        self._graph_exists_cache: dict[str, bool] = {}
        self._cache_state = "missing"
        self._node_limit = 80
        self._density = "normal"
        self._replay_events: list[dict[str, Any]] = []
        self._replay_index = -1
        self._replay_active = False
        self._exploration_active = False
        self._explored_node_ids: set[str] = set()
        self._explored_edge_ids: set[str] = set()
        self._exploration_pages: dict[str, int] = {}
        self._exploration_status: dict[str, Any] = {"status": "idle"}
        self._saved_views: list[dict[str, Any]] = []
        self._hovered_node_id = ""
        self._literature_sort_key = "relevance"
        self._literature_sort_descending = True
        self._path_start_id = ""
        self._path_end_id = ""
        self._path_directed = False
        self._path_relation_filter = "all"
        self._path_result: dict[str, Any] = {"status": "idle", "message": "请选择路径起点和终点。", "nodeIds": [], "edgeIds": [], "steps": []}
        self._history = KnowledgeGraphHistory(limit=60, coalesce_window=0.9)
        self._history_applying = False
        self._image_export_status: dict[str, Any] = {"status": "idle", "message": ""}
        self._pending_image_export_path: Path | None = None
        self._pending_image_export_options: dict[str, Any] = {}
        self._render_viewport: dict[str, float] = normalize_render_viewport({})
        self._render_display_style = "overview"
        self._render_projection_cache_key: tuple[Any, ...] | None = None
        self._render_projection_cache: dict[str, Any] = {}
        self._worker: ManagedWorker | None = None
        self._stop = threading.Event()
        self._taskFinished.connect(self._on_task_finished)
        self._batchFinished.connect(self._on_batch_finished)
        self.changed.connect(self._notify_render_changed)

    @staticmethod
    def _safe_record_id(record_id: str) -> str:
        value = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(record_id or "record")).strip("._")
        value = value[:72] or "record"
        suffix = hashlib.sha1(str(record_id).encode("utf-8")).hexdigest()[:8]
        return f"{value}_{suffix}"

    def _content_path(self, *parts: str) -> Path:
        if hasattr(self.paths, "content"):
            return self.paths.content(*parts)
        return self.paths.data(*parts)

    def _runtime_path(self, *parts: str) -> Path:
        if hasattr(self.paths, "runtime"):
            return self.paths.runtime(*parts)
        return self.paths.data(*parts)

    def _graph_dir(self, record_id: str) -> Path:
        return self._content_path("literature", "graphs", self._safe_record_id(record_id))

    def _graph_path(self, record_id: str) -> Path:
        return self._graph_dir(record_id) / "knowledge_graph.json"

    def _index_path(self, record_id: str) -> Path:
        return self._content_path("literature", "extractions", self._safe_record_id(record_id), "extraction_index.json")

    def _views_path(self, record_id: str) -> Path:
        return self._graph_dir(record_id) / "knowledge_graph_views.json"

    def _semantic_review_path(self, record_id: str) -> Path:
        return self._graph_dir(record_id) / "semantic_reviews.json"

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

    @Property("QVariantMap", notify=changed)
    def semanticComparison(self) -> dict[str, Any]:
        return dict((self._graph.get("metadata") or {}).get("semantic_comparison") or {})

    @Property("QVariantMap", notify=changed)
    def selectedSemanticCell(self) -> dict[str, Any]:
        return dict(self._selected_semantic_cell)

    @Property("QVariantList", notify=changed)
    def replayEvents(self) -> list[dict[str, Any]]:
        return list(self._replay_events)

    @Property(int, notify=changed)
    def replayIndex(self) -> int:
        return self._replay_index

    @Property(bool, notify=changed)
    def replayActive(self) -> bool:
        return self._replay_active

    @Property(bool, notify=changed)
    def replayComplete(self) -> bool:
        return bool(self._replay_active and self._replay_events and self._replay_index >= len(self._replay_events))

    @Property("QVariantMap", notify=changed)
    def replayEvent(self) -> dict[str, Any]:
        if 0 <= self._replay_index < len(self._replay_events):
            return dict(self._replay_events[self._replay_index])
        return {}

    @Property(bool, notify=changed)
    def explorationActive(self) -> bool:
        return self._exploration_active

    @Property("QVariantMap", notify=changed)
    def explorationStatus(self) -> dict[str, Any]:
        return dict(self._exploration_status)

    @Property("QVariantMap", notify=changed)
    def explorationSummary(self) -> dict[str, int]:
        node_id = str(self._selected_node.get("id") or "")
        if not node_id:
            node_id = next(iter(self._explored_node_ids), "")
        return neighbor_summary(self._graph, node_id) if node_id else {}

    @Property("QVariantMap", notify=changed)
    def explorationStats(self) -> dict[str, int]:
        return {
            "visibleNodes": len(self._exploration_node_ids()),
            "totalNodes": len(self._graph.get("nodes") or []),
            "visibleEdges": len(self._exploration_edge_ids()),
            "totalEdges": len(self._graph.get("edges") or []),
        }

    @Property("QVariantList", notify=changed)
    def savedViews(self) -> list[dict[str, Any]]:
        return view_summaries(self._saved_views)

    @Property(str, notify=changed)
    def searchText(self) -> str:
        return self._search_text

    @Property(str, notify=hoverChanged)
    def hoveredNodeId(self) -> str:
        return self._hovered_node_id

    @Property("QVariantList", notify=changed)
    def literatureRows(self) -> list[dict[str, Any]]:
        visible_ids = {str(item.get("id") or "") for item in self._visible_nodes(apply_limit=False)}
        return project_literature_rows(
            self._graph, visible_ids, self._search_text,
            str(self._selected_node.get("id") or ""), self._hovered_node_id,
            self._literature_sort_key, self._literature_sort_descending,
        )

    @Property(str, notify=changed)
    def literatureSortKey(self) -> str:
        return self._literature_sort_key

    @Property(bool, notify=changed)
    def literatureSortDescending(self) -> bool:
        return self._literature_sort_descending

    @Property("QVariantMap", notify=changed)
    def pathState(self) -> dict[str, Any]:
        result = dict(self._path_result)
        result.update({
            "startId": self._path_start_id,
            "startLabel": self._node_label(self._path_start_id),
            "endId": self._path_end_id,
            "endLabel": self._node_label(self._path_end_id),
            "directed": self._path_directed,
            "relationFilter": self._path_relation_filter,
        })
        return result

    @Property("QVariantList", notify=changed)
    def pathRelationTypes(self) -> list[str]:
        _, edges = self._path_context()
        return available_relation_types(edges)

    @Property(bool, notify=changed)
    def canUndo(self) -> bool:
        return self._history.can_undo

    @Property(bool, notify=changed)
    def canRedo(self) -> bool:
        return self._history.can_redo

    @Property("QVariantMap", notify=changed)
    def historyState(self) -> dict[str, Any]:
        return {
            "canUndo": self._history.can_undo,
            "canRedo": self._history.can_redo,
            "undoAction": self._history.undo_action,
            "redoAction": self._history.redo_action,
            "undoDepth": len(self._history.undo_entries),
            "redoDepth": len(self._history.redo_entries),
        }

    @Property("QVariantList", notify=changed)
    def imageExportNodes(self) -> list[dict[str, Any]]:
        nodes, _ = self._image_export_context()
        return [dict(item) for item in nodes]

    @Property("QVariantList", notify=changed)
    def imageExportEdges(self) -> list[dict[str, Any]]:
        _, edges = self._image_export_context()
        return [dict(item) for item in edges]

    @Property("QVariantMap", notify=changed)
    def imageExportStatus(self) -> dict[str, Any]:
        return dict(self._image_export_status)

    @Property("QVariantList", notify=renderChanged)
    def renderNodes(self) -> list[dict[str, Any]]:
        return [dict(item) for item in self._render_projection_context()["nodes"]]

    @Property("QVariantList", notify=renderChanged)
    def renderEdges(self) -> list[dict[str, Any]]:
        return [dict(item) for item in self._render_projection_context()["edges"]]

    @Property("QVariantMap", notify=renderChanged)
    def renderLayout(self) -> dict[str, Any]:
        return dict(self._render_projection_context()["layout"])

    @Property("QVariantMap", notify=renderChanged)
    def renderStatus(self) -> dict[str, Any]:
        return dict(self._render_projection_context()["status"])

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
        return self._visible_edges_for(self._visible_nodes())

    def _visible_edges_for(self, nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        visible_ids = {str(node.get("id") or "") for node in nodes}
        revealed_edges = None
        if self._replay_active:
            revealed_edges = {
                edge_id
                for event in self._replay_events[:self._replay_index + 1]
                for edge_id in event.get("edgeIds") or []
            }
        elif self._exploration_active and not self._facet_filters:
            revealed_edges = self._exploration_edge_ids()
        return [
            dict(edge) for edge in self._graph.get("edges") or []
            if edge.get("source") in visible_ids
            and edge.get("target") in visible_ids
            and (revealed_edges is None or str(edge.get("id") or "") in revealed_edges)
        ]

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
    def facetFilters(self) -> dict[str, str]:
        return dict(self._facet_filters)

    @Property("QVariantMap", notify=changed)
    def facetOptions(self) -> dict[str, list[dict[str, Any]]]:
        return facet_options(self._graph)

    @Property("QVariantMap", notify=changed)
    def filterCounts(self) -> dict[str, int]:
        counts = Counter(str(node.get("type") or "").casefold() for node in self._graph.get("nodes") or [])
        groups = {
            "structure": {"section", "paragraph"},
            "method": {"method", "algorithm", "model"},
            "experiment": {"experiment", "dataset", "metric", "baseline"},
            "result": {"result", "claim", "conclusion"},
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

    def _visible_nodes(self, *, apply_limit: bool = True) -> list[dict[str, Any]]:
        nodes = [dict(node) for node in self._graph.get("nodes") or []]
        if self._replay_active:
            revealed = {
                node_id
                for event in self._replay_events[:self._replay_index + 1]
                for node_id in event.get("nodeIds") or []
            }
            nodes = [node for node in nodes if str(node.get("type") or "").casefold() == "paper" or str(node.get("id") or "") in revealed]
        elif self._exploration_active and not self._facet_filters:
            revealed = self._exploration_node_ids()
            nodes = [node for node in nodes if str(node.get("id") or "") in revealed]
        facet_ids = facet_visible_node_ids(self._graph, self._facet_filters)
        if facet_ids is not None:
            nodes = [node for node in nodes if str(node.get("id") or "") in facet_ids]
        mode_types = {
            "structure": {"paper", "section", "paragraph"},
            "method": {"paper", "method", "algorithm", "model"},
            "experiment": {"paper", "experiment", "dataset", "metric", "baseline"},
            "result": {"paper", "result", "claim", "conclusion"},
            "figure": {"paper", "figure", "table", "equation"},
            "citation": {"paper", "citation", "baseline"},
            "limitation": {"paper", "limitation", "futurework", "missinginfo"},
            "common": {"paper", "comparison", "researchquestion"},
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
        nodes = [node for node in nodes if node_is_visible_at_density(node, self._density, query)]
        path_ids = {str(item) for item in self._path_result.get("nodeIds") or []}
        if path_ids and not self._replay_active and not self._facet_filters:
            existing_ids = {str(node.get("id") or "") for node in nodes}
            context_ids = {str(item.get("id") or "") for item in self._path_context()[0]}
            nodes.extend(
                dict(node) for node in self._graph.get("nodes") or []
                if isinstance(node, dict)
                and str(node.get("id") or "") in path_ids & context_ids
                and str(node.get("id") or "") not in existing_ids
            )
        paper = [node for node in nodes if str(node.get("type") or "").casefold() == "paper"]
        others = [node for node in nodes if str(node.get("type") or "").casefold() != "paper"]
        others.sort(key=lambda node: (-float(node.get("importance", node.get("weight", 0.5)) or 0.0), -float(node.get("confidence", 1.0) or 0.0), str(node.get("label") or "").casefold()))
        path_others = [node for node in others if str(node.get("id") or "") in path_ids]
        regular_others = [node for node in others if str(node.get("id") or "") not in path_ids]
        if not apply_limit:
            return paper + path_others + regular_others
        remaining = max(0, self._node_limit - len(paper) - len(path_others))
        return paper + path_others + regular_others[:remaining]

    def _render_projection_context(self) -> dict[str, Any]:
        path_node_ids = tuple(str(item) for item in self._path_result.get("nodeIds") or [])
        path_edge_ids = tuple(str(item) for item in self._path_result.get("edgeIds") or [])
        viewport_key = tuple(round(float(self._render_viewport.get(key, 0.0)), 3) for key in ("width", "height", "scale", "panX", "panY", "overscan"))
        cache_key = (
            id(self._graph), self._current_record_id, self._replay_active, self._replay_index,
            self._exploration_active, hash(frozenset(self._explored_node_ids)), hash(frozenset(self._explored_edge_ids)),
            self._filter_mode, self._search_text, self._density, str(self._selected_node.get("id") or ""),
            str(self._selected_edge.get("id") or ""),
            tuple(sorted(self._facet_filters.items())),
            path_node_ids, path_edge_ids, viewport_key, self._render_display_style,
        )
        if cache_key == self._render_projection_cache_key and self._render_projection_cache:
            return self._render_projection_cache
        semantic_nodes = self._visible_nodes(apply_limit=False)
        semantic_edges = self._visible_edges_for(semantic_nodes)
        pinned_nodes = set(path_node_ids)
        selected_id = str(self._selected_node.get("id") or "")
        if selected_id:
            pinned_nodes.add(selected_id)
        pinned_edges = set(path_edge_ids)
        selected_edge_id = str(self._selected_edge.get("id") or "")
        if selected_edge_id:
            pinned_edges.add(selected_edge_id)
            selected_edge = next((edge for edge in semantic_edges if str(edge.get("id") or "") == selected_edge_id), None)
            if selected_edge:
                pinned_nodes.update((str(selected_edge.get("source") or ""), str(selected_edge.get("target") or "")))
        base_layout = self._graph.get("layout") or (self._graph.get("metadata") or {}).get("layout") or {}
        self._render_projection_cache = project_render_graph(
            semantic_nodes,
            semantic_edges,
            base_layout,
            self._render_viewport,
            pinned_node_ids=pinned_nodes,
            pinned_edge_ids=pinned_edges,
            layout_style=self._render_display_style,
        )
        self._render_projection_cache_key = cache_key
        return self._render_projection_cache

    def _notify_render_changed(self) -> None:
        self._render_projection_cache_key = None
        self.renderChanged.emit()

    @Slot(float, float, float, float, float)
    @Slot(float, float, float, float, float, str)
    def setRenderViewport(self, width: float, height: float, scale: float, pan_x: float, pan_y: float, display_style: str = "") -> None:
        viewport = normalize_render_viewport({
            "width": width, "height": height, "scale": scale,
            "panX": pan_x, "panY": pan_y, "overscan": 120,
        })
        selected_style = str(display_style or self._render_display_style or "overview").casefold()
        selected_style = selected_style if selected_style in {"overview", "academic", "radial", "focus"} else "overview"
        previous = self._render_viewport
        if selected_style == self._render_display_style and all(abs(float(previous.get(key, 0.0)) - float(viewport[key])) < 0.01 for key in viewport):
            return
        self._render_viewport = viewport
        self._render_display_style = selected_style
        self._render_projection_cache_key = None
        self.renderChanged.emit()

    def _remember_graph(self, key: str, graph: dict[str, Any]) -> None:
        self._graphs.pop(key, None)
        self._graphs[key] = graph
        self._graph_exists_cache[str(key)] = True
        while len(self._graphs) > 16:
            self._graphs.popitem(last=False)

    def _prepare_replay(self, graph: dict[str, Any], *, preserve_exploration: bool = False) -> None:
        previous_nodes = set(self._explored_node_ids)
        previous_edges = set(self._explored_edge_ids)
        previous_pages = dict(self._exploration_pages)
        previous_path = (self._path_start_id, self._path_end_id, self._path_directed, self._path_relation_filter)
        self._replay_events = build_replay_events(graph)
        self._replay_index = -1
        self._replay_active = False
        self._prepare_exploration(graph, reset_history=not preserve_exploration)
        if preserve_exploration and self._exploration_active:
            valid_nodes = {str(item.get("id") or "") for item in graph.get("nodes") or [] if isinstance(item, dict)}
            valid_edges = {str(item.get("id") or "") for item in graph.get("edges") or [] if isinstance(item, dict)}
            self._explored_node_ids = (previous_nodes & valid_nodes) | set(seed_node_ids(graph))
            self._explored_edge_ids = previous_edges & valid_edges
            self._exploration_pages = previous_pages
        if preserve_exploration:
            self._path_start_id, self._path_end_id, self._path_directed, self._path_relation_filter = previous_path
            self._compute_shortest_path(emit=False)
        else:
            self._clear_path_state()

    def _prepare_exploration(self, graph: dict[str, Any], *, reset_history: bool = True) -> None:
        metadata = graph.get("metadata") or {}
        seeds = seed_node_ids(graph)
        self._exploration_active = bool(seeds and not metadata.get("comparison") and len(graph.get("nodes") or []) > len(seeds))
        self._explored_node_ids = set(seeds) if self._exploration_active else {
            str(item.get("id") or "") for item in graph.get("nodes") or [] if isinstance(item, dict) and item.get("id")
        }
        self._explored_edge_ids = set()
        self._exploration_pages = {}
        self._exploration_status = {
            "status": "idle",
            "nodeId": seeds[0] if seeds else "",
            "relationMode": "all",
            "revealed": 0,
            "total": neighbor_summary(graph, seeds[0]).get("all", 0) if seeds else 0,
            "hasMore": bool(seeds),
            "message": "选择关系类型并展开邻居。" if self._exploration_active else "",
        }
        self._load_saved_views(str(graph.get("recordId") or graph.get("record_id") or self._current_record_id or ""))
        if reset_history:
            self._facet_filters = {}
            self._history.reset()

    def _capture_history_state(self, viewport: dict[str, Any] | None = None) -> dict[str, Any]:
        state = {
            "exploration": {
                "nodeIds": sorted(self._explored_node_ids) if self._exploration_active else [],
                "edgeIds": sorted(self._explored_edge_ids) if self._exploration_active else [],
                "pages": dict(self._exploration_pages) if self._exploration_active else {},
            },
            "filters": {
                "mode": self._filter_mode,
                "searchText": self._search_text,
                "density": self._density,
                "literatureSortKey": self._literature_sort_key,
                "literatureSortDescending": self._literature_sort_descending,
                "facets": dict(self._facet_filters),
            },
            "selection": {
                "nodeId": str(self._selected_node.get("id") or ""),
                "edgeId": str(self._selected_edge.get("id") or ""),
            },
            "path": {
                "startId": self._path_start_id,
                "endId": self._path_end_id,
                "directed": self._path_directed,
                "relationFilter": self._path_relation_filter,
            },
        }
        if viewport is not None:
            state["viewport"] = normalize_viewport(viewport)
        return state

    def _record_history(self, action: str, *, coalesce_key: str = "", viewport: dict[str, Any] | None = None) -> None:
        if self._history_applying or not self._graph:
            return
        self._history.record(self._capture_history_state(viewport), action, coalesce_key=coalesce_key)

    def _apply_history_state(self, state: dict[str, Any], action: str, operation: str) -> None:
        self._history_applying = True
        try:
            node_ids = {str(item.get("id") or "") for item in self._graph.get("nodes") or [] if isinstance(item, dict)}
            edge_ids = {str(item.get("id") or "") for item in self._graph.get("edges") or [] if isinstance(item, dict)}
            exploration = dict(state.get("exploration") or {})
            if self._exploration_active:
                restored_nodes = {str(item) for item in exploration.get("nodeIds") or []} & node_ids
                self._explored_node_ids = restored_nodes | set(seed_node_ids(self._graph))
                self._explored_edge_ids = {str(item) for item in exploration.get("edgeIds") or []} & edge_ids
                self._exploration_pages = {
                    str(key): max(0, int(value))
                    for key, value in (exploration.get("pages") or {}).items()
                    if str(value).lstrip("-").isdigit()
                }
            filters = dict(state.get("filters") or {})
            self._filter_mode = str(filters.get("mode") or "all")
            self._search_text = str(filters.get("searchText") or "")
            density = str(filters.get("density") or "normal")
            self._density = density if density in {"compact", "normal", "detailed", "all"} else "normal"
            self._node_limit = {"compact": 50, "normal": 80, "detailed": 120, "all": 10000}[self._density]
            sort_key = str(filters.get("literatureSortKey") or "relevance")
            self._literature_sort_key = sort_key if sort_key in SORT_KEYS else "relevance"
            self._literature_sort_descending = bool(filters.get("literatureSortDescending", True))
            self._facet_filters = self._validated_facet_filters(filters.get("facets") or {})
            selection = dict(state.get("selection") or {})
            selected_node_id = str(selection.get("nodeId") or "")
            selected_edge_id = str(selection.get("edgeId") or "")
            self._selected_node = dict(next((item for item in self._graph.get("nodes") or [] if str(item.get("id") or "") == selected_node_id), {}) or {})
            self._selected_edge = dict(next((item for item in self._graph.get("edges") or [] if str(item.get("id") or "") == selected_edge_id), {}) or {}) if not self._selected_node else {}
            path = dict(state.get("path") or {})
            self._path_start_id = str(path.get("startId") or "") if str(path.get("startId") or "") in node_ids else ""
            self._path_end_id = str(path.get("endId") or "") if str(path.get("endId") or "") in node_ids else ""
            self._path_directed = bool(path.get("directed", False))
            relation_filter = canonical_relation_filter(str(path.get("relationFilter") or "all"))
            self._path_relation_filter = relation_filter if relation_filter in set(self.pathRelationTypes) else "all"
            self._compute_shortest_path(emit=False)
            self._hovered_node_id = ""
            self._exploration_status = {"status": "ready", "message": f"已{operation}：{action}"}
            self._status = f"已{operation}：{action}"
        finally:
            self._history_applying = False
        self.hoverChanged.emit()
        self.changed.emit()
        self.historyRestored.emit()
        if "viewport" in state:
            self.viewRestored.emit(dict(state["viewport"]))

    @Slot(result=bool)
    @Slot("QVariantMap", result=bool)
    def undo(self, viewport: dict[str, Any] | None = None) -> bool:
        entry = self._history.undo(self._capture_history_state(viewport))
        if entry is None:
            return False
        self._apply_history_state(entry.state, entry.action, "撤销")
        return True

    @Slot(result=bool)
    @Slot("QVariantMap", result=bool)
    def redo(self, viewport: dict[str, Any] | None = None) -> bool:
        entry = self._history.redo(self._capture_history_state(viewport))
        if entry is None:
            return False
        self._apply_history_state(entry.state, entry.action, "重做")
        return True

    def _load_saved_views(self, record_id: str) -> None:
        self._saved_views = []
        if not record_id:
            return
        try:
            payload = self._load_json(self._views_path(record_id))
        except (OSError, ValueError, json.JSONDecodeError):
            return
        for item in payload.get("views") or []:
            if not isinstance(item, dict):
                continue
            normalized = normalize_snapshot(item, record_id)
            if normalized:
                self._saved_views.append(normalized)

    def _write_saved_views(self) -> None:
        record_id = str(self._current_record_id or self._graph.get("recordId") or self._graph.get("record_id") or "")
        if not record_id:
            return
        self._write_json(self._views_path(record_id), {
            "version": VIEW_SNAPSHOT_VERSION,
            "recordId": record_id,
            "views": self._saved_views,
        })

    def _current_snapshot(
        self, name: str, viewport: dict[str, Any], existing: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        record_id = str(self._current_record_id or self._graph.get("recordId") or self._graph.get("record_id") or "")
        return make_snapshot(
            record_id,
            name,
            str(self._graph.get("source_fingerprint") or (self._graph.get("metadata") or {}).get("source_fingerprint") or ""),
            {
                "nodeIds": sorted(self._explored_node_ids) if self._exploration_active else [],
                "edgeIds": sorted(self._explored_edge_ids) if self._exploration_active else [],
                "pages": dict(self._exploration_pages) if self._exploration_active else {},
            },
            {
                "mode": self._filter_mode, "searchText": self._search_text, "density": self._density,
                "literatureSortKey": self._literature_sort_key,
                "literatureSortDescending": self._literature_sort_descending,
                "facets": dict(self._facet_filters),
            },
            {"nodeId": self._selected_node.get("id", ""), "edgeId": self._selected_edge.get("id", "")},
            dict(viewport or {}),
            existing,
            path={
                "startId": self._path_start_id, "endId": self._path_end_id,
                "directed": self._path_directed, "relationFilter": self._path_relation_filter,
            },
        )

    @Slot(str, "QVariantMap", result=str)
    def saveView(self, name: str, viewport: dict[str, Any]) -> str:
        record_id = str(self._current_record_id or self._graph.get("recordId") or self._graph.get("record_id") or "")
        clean_name = str(name or "").strip()[:80]
        if not record_id or not clean_name or not self._graph:
            self._status = "请输入视图名称后再保存。" if not clean_name else "当前没有可保存的知识图谱。"
            self.changed.emit()
            return ""
        existing = next((item for item in self._saved_views if str(item.get("name") or "").casefold() == clean_name.casefold()), None)
        snapshot = self._current_snapshot(clean_name, viewport, existing)
        if existing:
            self._saved_views[self._saved_views.index(existing)] = snapshot
        else:
            self._saved_views.append(snapshot)
        self._write_saved_views()
        self._status = f"研究视图已保存：{clean_name}"
        self.changed.emit()
        return str(snapshot.get("id") or "")

    @Slot(str, result=bool)
    def restoreView(self, view_id: str) -> bool:
        snapshot = next((item for item in self._saved_views if str(item.get("id") or "") == str(view_id or "")), None)
        if snapshot is None:
            self._status = "未找到要恢复的研究视图。"
            self.changed.emit()
            return False
        restored, report = reconcile_snapshot(snapshot, self._graph)
        if not restored:
            self._status = "研究视图与当前文献不兼容。"
            self.changed.emit()
            return False
        self._record_history("恢复研究视图")
        self._replay_active = False
        self._replay_index = -1
        if self._exploration_active:
            self._explored_node_ids = set(restored["exploration"]["nodeIds"]) | set(seed_node_ids(self._graph))
            self._explored_edge_ids = set(restored["exploration"]["edgeIds"])
            self._exploration_pages = dict(restored["exploration"]["pages"])
        filters = restored["filters"]
        self._filter_mode = str(filters.get("mode") or "all")
        self._search_text = str(filters.get("searchText") or "")
        density = str(filters.get("density") or "normal")
        self._density = density if density in {"compact", "normal", "detailed", "all"} else "normal"
        self._node_limit = {"compact": 50, "normal": 80, "detailed": 120, "all": 10000}[self._density]
        sort_key = str(filters.get("literatureSortKey") or "relevance")
        self._literature_sort_key = sort_key if sort_key in SORT_KEYS else "relevance"
        self._literature_sort_descending = bool(filters.get("literatureSortDescending", True))
        self._facet_filters = self._validated_facet_filters(filters.get("facets") or {})
        node_id = restored["selection"]["nodeId"]
        edge_id = restored["selection"]["edgeId"]
        self._selected_node = dict(next((item for item in self._graph.get("nodes") or [] if str(item.get("id") or "") == node_id), {}) or {})
        self._selected_edge = dict(next((item for item in self._graph.get("edges") or [] if str(item.get("id") or "") == edge_id), {}) or {}) if not self._selected_node else {}
        path = restored.get("path") or {}
        self._path_start_id = str(path.get("startId") or "")
        self._path_end_id = str(path.get("endId") or "")
        self._path_directed = bool(path.get("directed", False))
        relation_filter = canonical_relation_filter(str(path.get("relationFilter") or "all"))
        self._path_relation_filter = relation_filter if relation_filter in set(self.pathRelationTypes) else "all"
        self._compute_shortest_path(emit=False)
        missing = int(report["missingNodes"]) + int(report["missingEdges"])
        self._exploration_status = {
            "status": "ready", "message": f"已恢复视图；忽略 {missing} 个失效图元素。" if missing else "研究视图已完整恢复。",
        }
        self._status = f"研究视图已恢复：{restored['name']}" + (f"（忽略 {missing} 个失效元素）" if missing else "")
        self.changed.emit()
        self.viewRestored.emit(dict(restored["viewport"]))
        return True

    @Slot(str, result=bool)
    def deleteView(self, view_id: str) -> bool:
        before = len(self._saved_views)
        self._saved_views = [item for item in self._saved_views if str(item.get("id") or "") != str(view_id or "")]
        if len(self._saved_views) == before:
            return False
        self._write_saved_views()
        self._status = "研究视图已删除。"
        self.changed.emit()
        return True

    @Slot(str, "QVariantMap", result=str)
    def exportSharePackage(self, name: str, viewport: dict[str, Any]) -> str:
        clean_name = str(name or "研究视图").strip()[:80] or "研究视图"
        if not self._graph:
            self._status = "当前没有可分享的知识图谱。"
            self.changed.emit()
            return ""
        try:
            snapshot = self._current_snapshot(clean_name, viewport)
            package = build_share_package(self._graph, snapshot)
            record_id = str(package.get("recordId") or self._current_record_id or "record")
            export_dir = self._graph_dir(record_id) / "exports"
            stem = re.sub(r"[^A-Za-z0-9\u4e00-\u9fff_.-]+", "-", clean_name).strip(".-")[:60] or "knowledge-graph"
            path = export_dir / f"{stem}.omnilit-graph.json"
            suffix = 2
            while path.exists():
                path = export_dir / f"{stem}-{suffix}.omnilit-graph.json"
                suffix += 1
            write_share_package(path, package)
        except (OSError, ValueError) as exc:
            self._status = f"分享包导出失败：{exc}"
            self.changed.emit()
            return ""
        self._status = f"可恢复分享包已导出：{path}"
        self.changed.emit()
        return str(path)

    @Slot(str, result=bool)
    def importSharePackage(self, path: str) -> bool:
        raw_path = str(path or "")
        candidate = Path(QUrl(raw_path).toLocalFile() if raw_path.startswith("file:") else raw_path)
        try:
            graph, snapshot, _package = load_share_package(candidate)
            record_id = str(graph.get("recordId") or graph.get("record_id") or "")
            self._write_json(self._graph_path(record_id), graph)
        except (OSError, ValueError) as exc:
            self._status = f"分享包导入失败：{exc}"
            self.changed.emit()
            return False
        self._current_record_id = record_id
        self._graph = graph
        self._remember_graph(record_id, graph)
        self._prepare_replay(graph)
        existing = next((item for item in self._saved_views if str(item.get("id") or "") == str(snapshot.get("id") or "")), None)
        if existing:
            self._saved_views[self._saved_views.index(existing)] = snapshot
        else:
            self._saved_views.append(snapshot)
        self._write_saved_views()
        restored = self.restoreView(str(snapshot.get("id") or ""))
        if restored:
            self._status = f"已导入并恢复分享视图：{snapshot.get('name') or '研究视图'}"
            self.changed.emit()
        return restored

    @Slot(str, bool)
    def setLiteratureSort(self, sort_key: str, descending: bool) -> None:
        selected = str(sort_key or "relevance").casefold()
        selected = selected if selected in SORT_KEYS else "relevance"
        if selected == self._literature_sort_key and bool(descending) == self._literature_sort_descending:
            return
        self._record_history("调整文献排序")
        self._literature_sort_key = selected
        self._literature_sort_descending = bool(descending)
        self.changed.emit()

    @Slot(str)
    def setHoveredNode(self, node_id: str) -> None:
        value = str(node_id or "")
        if value == self._hovered_node_id:
            return
        self._hovered_node_id = value
        self.hoverChanged.emit()

    @Slot(str, result=bool)
    def selectLiteratureNode(self, node_id: str) -> bool:
        selected = self.selectNode(node_id)
        if selected:
            self._status = "已从文献列表定位图节点。"
            self.changed.emit()
        return selected

    @Slot(str, result=bool)
    def selectLiteratureRecord(self, record_id: str) -> bool:
        target = str(record_id or "")
        if not target:
            return False
        node = next((
            item for item in self._graph.get("nodes") or []
            if isinstance(item, dict)
            and str(item.get("type") or "").casefold() in {"paper", "citation"}
            and (
                str((item.get("details") or {}).get("recordId") or (item.get("details") or {}).get("record_id") or "") == target
                or (str(item.get("type") or "").casefold() == "paper" and str(item.get("id") or "") == f"paper:{target}")
            )
        ), None)
        return self.selectLiteratureNode(str((node or {}).get("id") or "")) if node else False

    def _search_match_ids(self) -> set[str]:
        query = self._search_text.casefold().strip()
        if not query:
            return set()
        return {
            str(node.get("id") or "") for node in self._graph.get("nodes") or []
            if isinstance(node, dict) and query in " ".join((
                str(node.get("label") or ""), str(node.get("summary") or ""),
                " ".join(str(tag) for tag in node.get("tags") or []),
            )).casefold()
        }

    def _exploration_node_ids(self) -> set[str]:
        return set(self._explored_node_ids) | self._search_match_ids()

    def _exploration_edge_ids(self) -> set[str]:
        result = set(self._explored_edge_ids)
        search_ids = self._search_match_ids()
        if not search_ids:
            return result
        anchors = set(self._explored_node_ids)
        for edge in self._graph.get("edges") or []:
            if not isinstance(edge, dict):
                continue
            source = str(edge.get("source") or "")
            target = str(edge.get("target") or "")
            if (source in search_ids and target in anchors) or (target in search_ids and source in anchors):
                result.add(str(edge.get("id") or ""))
        return result

    def _node_label(self, node_id: str) -> str:
        return str(next((item.get("label") for item in self._graph.get("nodes") or [] if str(item.get("id") or "") == str(node_id or "")), "") or "")

    def _path_context(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        nodes = [item for item in self._graph.get("nodes") or [] if isinstance(item, dict)]
        edges = [item for item in self._graph.get("edges") or [] if isinstance(item, dict)]
        if not self._exploration_active:
            return nodes, edges
        node_ids = set(self._explored_node_ids)
        edge_ids = set(self._explored_edge_ids)
        return (
            [item for item in nodes if str(item.get("id") or "") in node_ids],
            [item for item in edges if str(item.get("id") or "") in edge_ids],
        )

    def _clear_path_state(self) -> None:
        self._path_start_id = ""
        self._path_end_id = ""
        self._path_directed = False
        self._path_relation_filter = "all"
        self._path_result = {"status": "idle", "message": "请选择路径起点和终点。", "nodeIds": [], "edgeIds": [], "steps": []}

    def _compute_shortest_path(self, *, emit: bool) -> bool:
        if not self._path_start_id or not self._path_end_id:
            self._path_result = {"status": "idle", "message": "请选择路径起点和终点。", "nodeIds": [], "edgeIds": [], "steps": []}
            if emit:
                self.changed.emit()
            return False
        if self._replay_active:
            self._path_result = {"status": "invalid", "message": "请先结束图谱构建回放，再计算路径。", "nodeIds": [], "edgeIds": [], "steps": []}
            if emit:
                self.changed.emit()
            return False
        nodes, edges = self._path_context()
        relation_types = set() if self._path_relation_filter in {"", "all"} else {self._path_relation_filter}
        self._path_result = shortest_path(
            nodes, edges, self._path_start_id, self._path_end_id,
            directed=self._path_directed, relation_types=relation_types,
        )
        if emit:
            self.changed.emit()
        return self._path_result.get("status") == "ready"

    @Slot(str, result=bool)
    def setPathStart(self, node_id: str) -> bool:
        value = str(node_id or self._selected_node.get("id") or "")
        if not value or not self._node_label(value):
            return False
        if value == self._path_start_id:
            return True
        self._record_history("设置路径起点")
        self._path_start_id = value
        self._path_result = {"status": "idle", "message": "已设置起点，请选择终点。", "nodeIds": [], "edgeIds": [], "steps": []}
        self.changed.emit()
        return True

    @Slot(str, result=bool)
    def setPathEnd(self, node_id: str) -> bool:
        value = str(node_id or self._selected_node.get("id") or "")
        if not value or not self._node_label(value):
            return False
        if value == self._path_end_id:
            return True
        self._record_history("设置路径终点")
        self._path_end_id = value
        self._path_result = {"status": "idle", "message": "端点已就绪，可以计算最短路径。", "nodeIds": [], "edgeIds": [], "steps": []}
        self.changed.emit()
        return True

    @Slot(bool)
    def setPathDirected(self, directed: bool) -> None:
        if bool(directed) == self._path_directed:
            return
        self._record_history("切换路径方向")
        self._path_directed = bool(directed)
        self._path_result = {"status": "idle", "message": "路径方向设置已变化，请重新计算。", "nodeIds": [], "edgeIds": [], "steps": []}
        self.changed.emit()

    @Slot(str)
    def setPathRelationFilter(self, relation_type: str) -> None:
        value = canonical_relation_filter(str(relation_type or "all"))
        allowed = set(self.pathRelationTypes)
        selected = value if value in allowed else "all"
        if selected == self._path_relation_filter:
            return
        self._record_history("筛选路径关系")
        self._path_relation_filter = selected
        self._path_result = {"status": "idle", "message": "关系过滤已变化，请重新计算。", "nodeIds": [], "edgeIds": [], "steps": []}
        self.changed.emit()

    @Slot(result=bool)
    def computeShortestPath(self) -> bool:
        return self._compute_shortest_path(emit=True)

    @Slot()
    def clearPath(self) -> None:
        if not self._path_start_id and not self._path_end_id and self._path_result.get("status") == "idle":
            return
        self._record_history("清除路径")
        self._clear_path_state()
        self.changed.emit()

    @Slot(str, result=bool)
    @Slot(str, str, result=bool)
    @Slot(str, str, int, result=bool)
    def expandNeighbors(self, node_id: str, relation_mode: str = "all", page_size: int = 12) -> bool:
        if not self._exploration_active:
            return False
        key = f"{str(node_id or '')}|{str(relation_mode or 'all').casefold()}"
        offset = int(self._exploration_pages.get(key, 0))
        self._exploration_status = {
            "status": "loading", "nodeId": str(node_id or ""),
            "relationMode": str(relation_mode or "all").casefold(), "message": "正在加载邻居...",
        }
        self.changed.emit()
        try:
            page = neighbor_page(self._graph, node_id, relation_mode, offset, page_size)
            if page["status"] == "ready":
                label = self._node_label(str(node_id or "")) or str(node_id or "")
                self._record_history(f"展开 {label} 的邻居")
            self._explored_node_ids.update(page["nodeIds"])
            self._explored_edge_ids.update(page["edgeIds"])
            self._exploration_pages[key] = int(page["nextOffset"])
            self._exploration_status = dict(page)
            self._exploration_status["message"] = (
                f"已展开 {page['revealed']} / {page['total']} 个邻居。"
                if page["status"] == "ready" else "该关系类型没有可展开的邻居。"
            )
            self.changed.emit()
            return page["status"] == "ready"
        except Exception as exc:
            self._exploration_status = {
                "status": "error", "nodeId": str(node_id or ""),
                "relationMode": str(relation_mode or "all").casefold(),
                "message": f"邻居加载失败：{exc}",
            }
            self.changed.emit()
            return False

    @Slot(str, str, result=bool)
    def expandAllNeighbors(self, node_id: str, relation_mode: str = "all") -> bool:
        if not self._exploration_active:
            return False
        key = f"{str(node_id or '')}|{str(relation_mode or 'all').casefold()}"
        label = self._node_label(str(node_id or "")) or str(node_id or "")
        self._record_history(f"展开 {label} 的全部邻居")
        self._history_applying = True
        try:
            self._exploration_pages[key] = 0
            return self.expandNeighbors(node_id, relation_mode, 100)
        finally:
            self._history_applying = False

    @Slot()
    @Slot("QVariantMap")
    def resetExploration(self, viewport: dict[str, Any] | None = None) -> None:
        self._record_history("恢复默认视图", viewport=viewport)
        self._prepare_exploration(self._graph, reset_history=False)
        self._filter_mode = "all"
        self._facet_filters = {}
        self._search_text = ""
        self._density = "normal"
        self._node_limit = 80
        self._literature_sort_key = "relevance"
        self._literature_sort_descending = True
        self._selected_node = {}
        self._selected_edge = {}
        self._clear_path_state()
        self.changed.emit()
        self.historyRestored.emit()
        self.viewRestored.emit(normalize_viewport({}))

    @Slot(result=bool)
    def startReplay(self) -> bool:
        if not self._replay_events:
            self._prepare_replay(self._graph)
        if not self._replay_events:
            return False
        self._clear_path_state()
        self._replay_active = True
        self._replay_index = 0
        self.changed.emit()
        return True

    @Slot(result=bool)
    def advanceReplay(self) -> bool:
        if not self._replay_active or self._replay_index >= len(self._replay_events):
            return False
        if self._replay_index + 1 >= len(self._replay_events):
            self._replay_index = len(self._replay_events)
            self.changed.emit()
            return False
        self._replay_index += 1
        self.changed.emit()
        return True

    @Slot(int)
    def setReplayIndex(self, index: int) -> None:
        if not self._replay_events:
            self._prepare_replay(self._graph)
        self._replay_active = bool(self._replay_events)
        self._replay_index = max(0, min(int(index), len(self._replay_events) - 1)) if self._replay_events else -1
        self.changed.emit()

    @Slot()
    def stopReplay(self) -> None:
        self._replay_active = False
        self._replay_index = -1
        self.changed.emit()

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

    @Slot("QVariantMap", result=bool)
    def loadTopicGraph(self, graph: dict[str, Any]) -> bool:
        payload = dict(graph or {})
        metadata = dict(payload.get("metadata") or {})
        if not (metadata.get("topic_graph") or metadata.get("evolution_graph") or metadata.get("network_analysis_graph") or metadata.get("research_network_graph")) or not payload.get("nodes"):
            self._status = "主题或时间演化图谱数据无效。"
            self.changed.emit()
            return False
        try:
            normalized = KnowledgeGraphDocument.from_dict(payload).to_dict()
        except (TypeError, ValueError, KeyError) as exc:
            self._status = f"主题局部图谱加载失败：{exc}"
            self.changed.emit()
            return False
        key = str(normalized.get("recordId") or normalized.get("record_id") or "")
        if not key:
            self._status = "主题局部图谱缺少标识。"
            self.changed.emit()
            return False
        self._current_record_id = key
        self._graph = normalized
        self._prepare_replay(normalized)
        self._remember_graph(key, normalized)
        self._filter_mode = "all"
        self._search_text = ""
        self._cache_state = "fresh"
        context_label = "时间演化图谱" if metadata.get("evolution_graph") else "主题局部图谱"
        self._status = f"已进入{context_label}：{normalized.get('title') or '未命名主题'}"
        if metadata.get("network_analysis_graph"):
            self._status = f"已进入结构分析图谱：{normalized.get('title') or '未命名分析'}"
        elif metadata.get("research_network_graph"):
            self._status = f"已进入合作网络：{normalized.get('title') or '未命名网络'}"
        try:
            self._write_json(self._graph_path(key), normalized)
        except OSError as exc:
            self._status += f"（缓存写入失败：{exc}）"
        self.changed.emit()
        self.graphReady.emit(key)
        return True

    @Slot("QVariantList", result=bool)
    def regenerateComparisonGraph(self, records: list) -> bool:
        return self._generate_comparison(records, force=True)

    def _semantic_reviews_for(self, record_ids: list[str]) -> dict[str, dict[str, Any]]:
        return {
            record_id: self._load_json(self._semantic_review_path(record_id))
            for record_id in record_ids if record_id
        }

    def _comparison_source_graphs(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        graphs = []
        for record in records:
            record_id = str(record.get("recordId") or record.get("id") or "")
            if not record_id:
                continue
            graph = self._load_json(self._graph_path(record_id))
            extraction_index = self._load_json(self._index_path(record_id))
            if not graph or not cache_is_fresh(graph, record, extraction_index):
                graph = build_knowledge_graph(record, extraction_index or None)
                try:
                    self._write_json(self._graph_path(record_id), graph)
                except OSError:
                    pass
            graphs.append(graph)
        return graphs

    def _refresh_semantic_comparison(
        self, graph: dict[str, Any], records: list[dict[str, Any]], source_graphs: list[dict[str, Any]] | None = None,
    ) -> bool:
        source_graphs = source_graphs if source_graphs is not None else self._comparison_source_graphs(records)
        record_ids = [str(item.get("recordId") or item.get("id") or "") for item in records]
        semantic = build_semantic_comparison(source_graphs, records, self._semantic_reviews_for(record_ids))
        metadata = graph.setdefault("metadata", {})
        previous = dict(metadata.get("semantic_comparison") or {})
        metadata["semantic_comparison"] = semantic
        return previous.get("cacheKey") != semantic.get("cacheKey")

    def _generate_comparison(self, records: list, force: bool) -> bool:
        payloads = [dict(record) for record in (records or []) if isinstance(record, dict)]
        if not payloads or self._loading:
            return False
        key = self._comparison_key(payloads)
        self._comparison_records = [dict(item) for item in payloads]
        cached = {} if force else self._load_json(self._graph_path(key))
        if cached:
            source_graphs = self._comparison_source_graphs(payloads)
            fingerprints = sorted(str(graph.get("source_fingerprint") or "") for graph in source_graphs)
            reviews = self._semantic_reviews_for([str(item.get("recordId") or item.get("id") or "") for item in payloads])
            if list((cached.get("metadata") or {}).get("comparison_source_fingerprints") or []) != fingerprints:
                cached = compare_graph_dicts(source_graphs, key, payloads, reviews)
                self._write_json(self._graph_path(key), cached)
            elif self._refresh_semantic_comparison(cached, payloads, source_graphs):
                self._write_json(self._graph_path(key), cached)
            self._current_record_id = key
            self._graph = cached
            self._selected_semantic_cell = {}
            self._prepare_replay(cached)
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
                    source_graph = build_knowledge_graph(record, extraction_index or None)
                    graphs.append(source_graph)
                    try:
                        self._write_json(self._graph_path(record_key), source_graph)
                    except OSError:
                        pass
                record_ids = [str(record.get("recordId") or "") for record in payloads]
                graph = compare_graph_dicts(graphs, key, payloads, self._semantic_reviews_for(record_ids))
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
            state_path=self._runtime_path("task_state", f"knowledge_graph_{self._safe_record_id(key)}.json"),
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
            state_path=self._runtime_path("task_state", "knowledge_graph_batch.json"),
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
        cached = {} if force else self._load_json(self._graph_path(key))
        if cached:
            self._current_record_id = key
            self._graph = cached
            self._prepare_replay(cached)
            self._remember_graph(key, cached)
            self._filter_mode = "all"
            self._search_text = ""
            # Extraction indexes can contain the full text of a large PDF.
            # Loading and fingerprinting one on the Qt thread freezes input.
            # Display the compact graph cache immediately and validate it in
            # the worker below.
            self._cache_state = "refreshing"
            self._status = "已显示缓存图谱，正在后台检查更新..."
            self.changed.emit()
            self.graphReady.emit(key)
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
                extraction_index = self._load_json(self._index_path(key))
                if cached and not force and cache_is_fresh(cached, payload, extraction_index):
                    message = "已加载缓存知识图谱。"
                    task.update_state("completed", detail=message)
                    self._taskFinished.emit(key, cached, message, True)
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
            state_path=self._runtime_path("task_state", f"knowledge_graph_{self._safe_record_id(key)}.json"),
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
            preserve_context = bool(self._graph and str(record_id or "") == self._current_record_id)
            self._graph = graph
            self._prepare_replay(graph, preserve_exploration=preserve_context)
            if not preserve_context:
                self._filter_mode = "all"
                self._search_text = ""
                self._selected_node = {}
                self._selected_edge = {}
                self._selected_semantic_cell = {}
            else:
                valid_nodes = {str(item.get("id") or "") for item in graph.get("nodes") or [] if isinstance(item, dict)}
                valid_edges = {str(item.get("id") or "") for item in graph.get("edges") or [] if isinstance(item, dict)}
                if str(self._selected_node.get("id") or "") not in valid_nodes:
                    self._selected_node = {}
                if str(self._selected_edge.get("id") or "") not in valid_edges:
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
        key = str(record_id or "")
        if not key:
            return False
        cached = self._graph_exists_cache.get(key)
        if cached is not None:
            return cached
        exists = self._graph_path(key).is_file()
        self._graph_exists_cache[key] = exists
        return exists

    @Slot(str, result=bool)
    def loadGraph(self, record_id: str) -> bool:
        graph = self.graphFor(record_id)
        if not graph:
            self._status = "未找到知识图谱缓存。"
            self.changed.emit()
            return False
        self._current_record_id = str(record_id or "")
        self._graph = graph
        self._prepare_replay(graph)
        self._cache_state = "fresh"
        self._filter_mode = "all"
        self._search_text = ""
        self._selected_node = {}
        self._selected_edge = {}
        self._selected_semantic_cell = {}
        self._comparison_records = [dict(item) for item in (graph.get("metadata") or {}).get("comparison_records") or [] if isinstance(item, dict)]
        self._status = "知识图谱已加载。"
        self.changed.emit()
        self.graphReady.emit(self._current_record_id)
        return True

    def _semantic_cell(self, record_id: str, dimension: str) -> dict[str, Any]:
        semantic = (self._graph.get("metadata") or {}).get("semantic_comparison") or {}
        paper = next((item for item in semantic.get("papers") or [] if str(item.get("recordId") or "") == str(record_id or "")), None)
        if not isinstance(paper, dict):
            return {}
        cell = next((item for item in paper.get("cells") or [] if str(item.get("dimension") or "") == str(dimension or "")), None)
        return dict(cell or {})

    @Slot(str, str, result=bool)
    def selectSemanticCell(self, record_id: str, dimension: str) -> bool:
        cell = self._semantic_cell(record_id, dimension)
        self._selected_semantic_cell = cell
        items = cell.get("items") or []
        node_id = str((items[0] if items else {}).get("nodeId") or "")
        if node_id:
            self._selected_node = dict(next((item for item in self._graph.get("nodes") or [] if str(item.get("id") or "") == node_id), {}) or {})
            self._selected_edge = {}
        self.changed.emit()
        return bool(cell)

    def _rebuild_semantic_after_review(self, record_id: str, dimension: str) -> bool:
        semantic = (self._graph.get("metadata") or {}).get("semantic_comparison") or {}
        papers = [dict(item) for item in semantic.get("papers") or [] if isinstance(item, dict)]
        records = [dict(item) for item in self._comparison_records]
        if not records:
            records = [dict(item) for item in (self._graph.get("metadata") or {}).get("comparison_records") or [] if isinstance(item, dict)]
        if not records:
            records = [{"recordId": item.get("recordId"), "title": item.get("title"), "year": item.get("year")} for item in papers]
        if not records or not (self._graph.get("metadata") or {}).get("comparison"):
            return False
        source_graphs = self._comparison_source_graphs(records)
        record_ids = [str(item.get("recordId") or "") for item in records]
        refreshed = build_semantic_comparison(source_graphs, records, self._semantic_reviews_for(record_ids))
        self._graph.setdefault("metadata", {})["semantic_comparison"] = refreshed
        self._selected_semantic_cell = next((
            dict(cell) for paper in refreshed.get("papers") or [] if str(paper.get("recordId") or "") == record_id
            for cell in paper.get("cells") or [] if str(cell.get("dimension") or "") == dimension
        ), {})
        self._write_json(self._graph_path(self._current_record_id), self._graph)
        self._remember_graph(self._current_record_id, self._graph)
        return True

    @Slot(str, str, str, str, str, result=bool)
    def reviewSemanticCell(self, record_id: str, dimension: str, action: str, label: str, note: str) -> bool:
        if not (self._graph.get("metadata") or {}).get("comparison"):
            self._status = "人工语义审阅仅适用于多论文比较。"
            self.changed.emit()
            return False
        cell = self._semantic_cell(record_id, dimension)
        original_node_id = str(((cell.get("automaticItems") or [{}])[0]).get("nodeId") or "")
        try:
            current = self._load_json(self._semantic_review_path(record_id))
            updated = make_review(current, dimension, action, label, note, original_node_id)
            self._write_json(self._semantic_review_path(record_id), updated)
            if not self._rebuild_semantic_after_review(record_id, dimension):
                return False
        except (OSError, ValueError) as exc:
            self._status = f"语义审阅保存失败：{exc}"
            self.changed.emit()
            return False
        labels = {"confirm": "已确认", "replace": "已修正", "add": "已补充", "reject": "已排除"}
        self._status = f"{labels.get(str(action).casefold(), '已更新')} {dimension}；自动抽取结果仍保留，可撤销。"
        self.changed.emit()
        return True

    @Slot(str, str, result=bool)
    def clearSemanticReview(self, record_id: str, dimension: str) -> bool:
        try:
            current = self._load_json(self._semantic_review_path(record_id))
            updated = clear_review(current, dimension)
            self._write_json(self._semantic_review_path(record_id), updated)
            if not self._rebuild_semantic_after_review(record_id, dimension):
                return False
        except OSError as exc:
            self._status = f"撤销语义审阅失败：{exc}"
            self.changed.emit()
            return False
        self._status = f"已撤销 {dimension} 的人工审阅，恢复自动抽取展示。"
        self.changed.emit()
        return True

    @Slot(str, result=bool)
    def selectNode(self, node_id: str) -> bool:
        node = next((item for item in self._graph.get("nodes") or [] if str(item.get("id") or "") == str(node_id)), None)
        if str(self._selected_node.get("id") or "") == str((node or {}).get("id") or "") and not self._selected_edge:
            return node is not None
        self._record_history("选择图节点")
        self._selected_node = dict(node or {})
        self._selected_edge = {}
        self.changed.emit()
        return node is not None

    @Slot(str, result=bool)
    def selectEdge(self, edge_id: str) -> bool:
        edge = next((item for item in self._graph.get("edges") or [] if str(item.get("id") or "") == str(edge_id)), None)
        if str(self._selected_edge.get("id") or "") == str((edge or {}).get("id") or "") and not self._selected_node:
            return edge is not None
        self._record_history("选择图关系")
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
        selected_mode = str(mode or "all").casefold()
        if selected_mode == self._filter_mode:
            return
        self._record_history("切换图谱筛选")
        self._filter_mode = selected_mode
        self._selected_edge = {}
        if self._exploration_active and self._filter_mode != "all":
            mode_types = {
                "structure": {"section", "paragraph"},
                "method": {"method", "algorithm", "model"},
                "experiment": {"experiment", "dataset", "metric", "baseline"},
                "result": {"result", "claim"},
                "figure": {"figure", "table", "equation"},
                "citation": {"citation", "baseline"},
                "limitation": {"limitation", "futurework", "missinginfo"},
                "common": {"comparison"},
                "conflict": {"conflict"},
            }
            allowed = mode_types.get(self._filter_mode, set())
            candidates = [
                str(node.get("id") or "") for node in self._graph.get("nodes") or []
                if isinstance(node, dict) and str(node.get("type") or "").casefold() in allowed
            ][:12]
            anchors = set(self._explored_node_ids)
            self._explored_node_ids.update(candidates)
            candidate_ids = set(candidates)
            for edge in self._graph.get("edges") or []:
                if not isinstance(edge, dict):
                    continue
                source = str(edge.get("source") or "")
                target = str(edge.get("target") or "")
                if (source in candidate_ids and target in anchors) or (target in candidate_ids and source in anchors):
                    self._explored_edge_ids.add(str(edge.get("id") or ""))
        visible = self._visible_nodes()
        matching = [node for node in visible if str(node.get("type") or "").casefold() != "paper"]
        self._selected_node = dict(matching[0] if matching else (visible[0] if visible else {}))
        self.changed.emit()

    def _validated_facet_filters(self, value: dict[str, Any] | None) -> dict[str, str]:
        selected = normalize_facet_filters(value)
        options = self.facetOptions
        return {
            key: expected for key, expected in selected.items()
            if expected in {str(item.get("value") or "") for item in options.get(key) or []}
        }

    @Slot(str, str)
    def setFacetFilter(self, facet: str, value: str) -> None:
        key = str(facet or "").casefold()
        if key not in FACET_KEYS:
            return
        selected = str(value or "").strip()[:200]
        allowed = {str(item.get("value") or "") for item in self.facetOptions.get(key) or []}
        if selected and selected not in allowed:
            self._status = f"{key} 筛选值不在当前图谱中。"
            self.changed.emit()
            return
        next_filters = dict(self._facet_filters)
        if selected:
            next_filters[key] = selected
        else:
            next_filters.pop(key, None)
        if next_filters == self._facet_filters:
            return
        self._record_history("调整图谱分面筛选")
        self._facet_filters = next_filters
        self.changed.emit()

    @Slot()
    def clearFacetFilters(self) -> None:
        if not self._facet_filters:
            return
        self._record_history("清除图谱分面筛选")
        self._facet_filters = {}
        self.changed.emit()

    @Slot(str)
    def search(self, keyword: str) -> None:
        value = str(keyword or "")
        if value == self._search_text:
            return
        self._record_history("搜索图谱", coalesce_key="search")
        self._search_text = value
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
        self._graph_exists_cache.pop(key, None)
        self.changed.emit()

    @Slot(str)
    def setDensity(self, density: str) -> None:
        selected = str(density or "normal").casefold()
        selected = selected if selected in {"compact", "normal", "detailed", "all"} else "normal"
        if selected == self._density:
            return
        self._record_history("调整图谱密度")
        self._density = selected
        self._node_limit = {"compact": 50, "normal": 80, "detailed": 120, "all": 10000}.get(self._density, 80)
        self.changed.emit()

    def _image_export_context(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        nodes = [item for item in self._graph.get("nodes") or [] if isinstance(item, dict)]
        edges = [item for item in self._graph.get("edges") or [] if isinstance(item, dict)]
        if self._replay_active:
            node_ids = {
                node_id
                for event in self._replay_events[:self._replay_index + 1]
                for node_id in event.get("nodeIds") or []
            }
            node_ids.update(
                str(item.get("id") or "") for item in nodes
                if str(item.get("type") or "").casefold() == "paper"
            )
            edge_ids = {
                edge_id
                for event in self._replay_events[:self._replay_index + 1]
                for edge_id in event.get("edgeIds") or []
            }
            nodes = [item for item in nodes if str(item.get("id") or "") in node_ids]
            edges = [item for item in edges if str(item.get("id") or "") in edge_ids]
        elif self._exploration_active:
            node_ids = set(self._explored_node_ids)
            edge_ids = set(self._explored_edge_ids)
            nodes = [item for item in nodes if str(item.get("id") or "") in node_ids]
            edges = [item for item in edges if str(item.get("id") or "") in edge_ids]
        visible_ids = {str(item.get("id") or "") for item in nodes}
        edges = [item for item in edges if str(item.get("source") or "") in visible_ids and str(item.get("target") or "") in visible_ids]
        return nodes, edges

    @Slot(float, float, float, result="QVariantMap")
    def validateImageExport(self, width: float, height: float, scale: float) -> dict[str, Any]:
        valid, message, dimensions = validate_export_dimensions(width, height, scale)
        return {"ok": valid, "message": message, "width": dimensions[0], "height": dimensions[1]}

    @Slot(str, str, float, bool, result="QVariantMap")
    def prepareImageExport(self, name: str, scope: str, scale: float, transparent: bool) -> dict[str, Any]:
        if self._pending_image_export_path is not None:
            self._image_export_status = {"status": "error", "message": "已有图片导出任务正在进行。"}
            self.changed.emit()
            return {"ok": False, **self._image_export_status}
        if not self._graph:
            self._image_export_status = {"status": "error", "message": "当前没有可导出的知识图谱。"}
            self.changed.emit()
            return {"ok": False, **self._image_export_status}
        if self._replay_active and not self.replayComplete:
            self._image_export_status = {"status": "error", "message": "请先结束构建回放，再导出图片。"}
            self.changed.emit()
            return {"ok": False, **self._image_export_status}
        nodes, _ = self._image_export_context()
        if not nodes:
            self._image_export_status = {"status": "error", "message": "当前探索子图为空。"}
            self.changed.emit()
            return {"ok": False, **self._image_export_status}
        options = normalize_export_options(scope, scale, transparent)
        record_id = str(self._current_record_id or self._graph.get("recordId") or self._graph.get("record_id") or "record")
        title = str(name or self._graph.get("title") or "knowledge-graph")
        export_dir = self._graph_dir(record_id) / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)
        path = unique_export_path(export_dir.resolve(), title)
        self._pending_image_export_path = path
        self._pending_image_export_options = dict(options)
        self._image_export_status = {
            "status": "capturing", "message": "正在渲染知识图谱图片...",
            "path": str(path), **options,
        }
        self.changed.emit()
        return {"ok": True, "path": str(path), **options}

    @Slot(str, bool, str, result=bool)
    def completeImageExport(self, path: str, success: bool, message: str = "") -> bool:
        candidate = Path(str(path or ""))
        if self._pending_image_export_path is None or candidate != self._pending_image_export_path:
            self._image_export_status = {"status": "error", "message": "图片导出回调与待处理任务不匹配。"}
            self.changed.emit()
            return False
        valid = bool(success and is_valid_png(candidate))
        if not valid:
            self._image_export_status = {
                "status": "error",
                "message": str(message or "PNG 写入失败或文件格式无效。"),
                "path": str(candidate),
            }
            self._pending_image_export_path = None
            self._pending_image_export_options = {}
            self.changed.emit()
            return False
        record_id = str(self._current_record_id or self._graph.get("recordId") or self._graph.get("record_id") or "")
        fingerprint = str(self._graph.get("source_fingerprint") or (self._graph.get("metadata") or {}).get("source_fingerprint") or "")
        manifest = export_manifest(candidate, record_id, self._pending_image_export_options, fingerprint)
        self._write_json(candidate.with_suffix(".png.json"), manifest)
        self._image_export_status = {
            "status": "ready", "message": f"知识图谱图片已导出：{candidate}",
            "path": str(candidate), **self._pending_image_export_options,
        }
        self._status = self._image_export_status["message"]
        self._pending_image_export_path = None
        self._pending_image_export_options = {}
        self.changed.emit()
        return True

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
