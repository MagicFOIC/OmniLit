from __future__ import annotations

import json
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from omnilit_qt.knowledge_graph_exploration import RELATION_FAMILIES, neighbor_page, seed_node_ids
from omnilit_qt.knowledge_graph_literature import SORT_KEYS, project_literature_rows
from omnilit_qt.knowledge_graph_lod import project_render_graph
from omnilit_qt.knowledge_graph_evolution import EVOLUTION_VERSION, build_evolution_graph
from omnilit_qt.knowledge_graph_schema import KnowledgeGraphDocument
from omnilit_qt.knowledge_graph_storage import load_graph, load_timeline_bundle, load_views, save_views
from omnilit_qt.knowledge_graph_views import make_snapshot, reconcile_snapshot, view_summaries
from omnilit_qt.literature_library_shared import LibraryStateConflict, LibraryStateStore, filter_library_records, library_facets, project_library_detail, project_library_state, project_library_summary, read_library_cache
from omnilit_qt.research_business_shared import BusinessSettingsConflict, BusinessSettingsStore, build_research_brief, project_research_statistics, project_research_workspace
from omnilit_qt.shared_protocol import (
    GRAPH_SCHEMA_VERSION, PROTOCOL_VERSION, to_shared_graph_data, validate_graph_projection,
    validate_graph_timeline, validate_graph_timeline_query,
    validate_graph_view_list, validate_graph_view_mutation, validate_graph_view_restore,
    validate_graph_view_save_request, validate_graph_view_state,
    validate_library_page, validate_library_query, validate_library_record_detail,
    validate_library_mutation_request, validate_library_mutation_result, validate_library_state,
    validate_business_settings, validate_business_settings_update_request,
    validate_research_brief_request, validate_research_brief_result,
    validate_research_statistics, validate_research_workspace,
)
from .sync_store import WorkspaceSyncStore


_SAFE_VALUE = re.compile(r"^[^\x00-\x1f\x7f]{1,256}$")


class GraphServiceError(ValueError):
    def __init__(self, code: str, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


def _identifier(value: Any, field: str) -> str:
    result = str(value or "").strip()
    if not _SAFE_VALUE.fullmatch(result) or ".." in result or "/" in result or "\\" in result:
        raise GraphServiceError("invalid_input", f"Invalid {field}")
    return result


def _opaque_identifier(value: Any, field: str) -> str:
    result = str(value or "").strip()
    if not _SAFE_VALUE.fullmatch(result):
        raise GraphServiceError("invalid_input", f"Invalid {field}")
    return result


class GraphService:
    def __init__(self, data_root: Path) -> None:
        self.data_root = Path(data_root).resolve()
        self._views_lock = threading.RLock()
        self._library_state_store = LibraryStateStore(self.data_root / "data" / "downloads" / "library_state.json")
        self._business_settings_store = BusinessSettingsStore(self.data_root / "config" / "web_business_settings.json")
        self._sync_store = WorkspaceSyncStore(self.data_root / "runtime" / "sync" / "sync.sqlite3")

    def local_sync_preferences(self) -> dict[str, Any]:
        return self._sync_store.preferences()

    def update_local_sync_preferences(self, request: dict[str, Any]) -> dict[str, Any]:
        return self._sync_store.update_preferences(bool(request.get("enabled")), request.get("categories") if isinstance(request.get("categories"), dict) else {}, cloud_account_id=str(request.get("cloudAccountId") or ""), cloud_workspace_id=str(request.get("cloudWorkspaceId") or ""))

    def local_sync_status(self) -> dict[str, Any]:
        return self._sync_store.status()

    def enqueue_local_sync_change(self, request: dict[str, Any]) -> dict[str, Any]:
        return self._sync_store.enqueue(request)

    def local_sync_batch(self, limit: int = 200) -> dict[str, Any]:
        return self._sync_store.batch(limit)

    def apply_local_sync_result(self, request: dict[str, Any]) -> dict[str, Any]:
        return self._sync_store.apply_result(request)

    def resolve_local_sync_conflict(self, conflict_id: str, request: dict[str, Any]) -> dict[str, Any]:
        return self._sync_store.resolve_conflict(conflict_id, str(request.get("resolution") or ""))

    def _legacy_graph(self, record_id: str) -> dict[str, Any]:
        record_id = _identifier(record_id, "recordId")
        try:
            payload = load_graph(self.data_root, record_id)
        except (OSError, ValueError) as exc:
            raise GraphServiceError("invalid_graph_cache", str(exc), 422) from exc
        if not payload:
            raise GraphServiceError("graph_not_found", "Knowledge graph not found", 404)
        return KnowledgeGraphDocument.from_dict(payload).to_dict()

    def list_graphs(self) -> dict[str, Any]:
        """Return valid local graph caches, newest first, without exposing paths."""
        graph_root = self.data_root / "data" / "literature" / "graphs"
        if not graph_root.is_dir():
            return {"protocolVersion": PROTOCOL_VERSION, "graphs": []}

        graphs: list[dict[str, Any]] = []
        try:
            candidates = sorted(
                graph_root.glob("*/knowledge_graph.json"),
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            )[:10_000]
        except OSError:
            candidates = []
        for path in candidates:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                document = KnowledgeGraphDocument.from_dict(payload).to_dict()
                record_id = _identifier(document.get("record_id") or document.get("recordId"), "recordId")
                paper = document.get("paper") if isinstance(document.get("paper"), dict) else {}
                updated_at = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat().replace("+00:00", "Z")
                graphs.append({
                    "recordId": record_id,
                    "title": str(paper.get("title") or record_id),
                    "cloudRevision": 0,
                    "updatedAt": str(document.get("generated_at") or updated_at),
                    "nodeCount": len(document.get("nodes") or []),
                    "edgeCount": len(document.get("edges") or []),
                })
            except (OSError, ValueError, TypeError, json.JSONDecodeError, GraphServiceError):
                continue
        return {"protocolVersion": PROTOCOL_VERSION, "graphs": graphs}

    def _saved_views(self, record_id: str) -> list[dict[str, Any]]:
        try:
            return load_views(self.data_root, record_id)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise GraphServiceError("invalid_graph_views", str(exc), 422) from exc

    def initial_graph(self, record_id: str) -> dict[str, Any]:
        graph = self._legacy_graph(record_id)
        shared = dict(to_shared_graph_data(graph))
        seeds = set(seed_node_ids(graph))
        shared["nodes"] = [node for node in shared["nodes"] if node["id"] in seeds]
        shared["edges"] = []
        shared["metadata"] = {**dict(shared.get("metadata") or {}), "projection": "seed", "totalNodes": len(graph.get("nodes") or []), "totalEdges": len(graph.get("edges") or [])}
        return shared

    def neighbors(self, record_id: str, node_id: str, mode: str = "all", offset: int = 0, limit: int = 12) -> dict[str, Any]:
        graph = self._legacy_graph(record_id)
        node_id = _identifier(node_id, "nodeId")
        selected_mode = str(mode or "all").casefold()
        if selected_mode != "all" and selected_mode not in RELATION_FAMILIES:
            raise GraphServiceError("invalid_relation_mode", "Unsupported relation mode")
        node_ids = {str(node.get("id") or "") for node in graph.get("nodes") or [] if isinstance(node, dict)}
        if node_id not in node_ids:
            raise GraphServiceError("node_not_found", "Graph node not found", 404)
        page = neighbor_page(graph, node_id, selected_mode, max(0, int(offset)), max(1, min(100, int(limit))))
        shared = to_shared_graph_data(graph)
        wanted_nodes, wanted_edges = set(page.pop("nodeIds")), set(page.pop("edgeIds"))
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "schemaVersion": GRAPH_SCHEMA_VERSION,
            "recordId": str(shared["recordId"]),
            **page,
            "nodes": [node for node in shared["nodes"] if node["id"] in wanted_nodes],
            "edges": [edge for edge in shared["edges"] if edge["id"] in wanted_edges],
        }

    def literature(self, record_id: str, request: dict[str, Any]) -> dict[str, Any]:
        graph = self._legacy_graph(record_id)
        visible_values = request.get("visibleNodeIds")
        if visible_values is not None and (not isinstance(visible_values, list) or len(visible_values) > 10_000):
            raise GraphServiceError("invalid_input", "visibleNodeIds must be an array of at most 10000 ids")
        visible = {_identifier(value, "visibleNodeId") for value in visible_values} if visible_values is not None else None
        sort_key = str(request.get("sortKey") or "relevance").casefold()
        if sort_key not in SORT_KEYS:
            raise GraphServiceError("invalid_sort_key", "Unsupported literature sort key")
        rows = project_literature_rows(
            graph,
            visible,
            str(request.get("query") or "")[:512],
            str(request.get("selectedNodeId") or ""),
            str(request.get("hoveredNodeId") or ""),
            sort_key,
            bool(request.get("descending", True)),
        )
        offset = max(0, int(request.get("offset") or 0))
        limit = max(1, min(500, int(request.get("limit") or 100)))
        page_rows = rows[offset:offset + limit]
        return {"protocolVersion": PROTOCOL_VERSION, "recordId": _identifier(record_id, "recordId"), "rows": page_rows, "offset": offset, "nextOffset": offset + len(page_rows), "total": len(rows), "hasMore": offset + len(page_rows) < len(rows)}

    def library(self, request: dict[str, Any]) -> dict[str, Any]:
        validate_library_query(request)
        cache_available, records = read_library_cache(self.data_root)
        if not cache_available:
            payload = {"protocolVersion": PROTOCOL_VERSION, "status": "unavailable", "records": [], "offset": 0, "nextOffset": 0, "total": 0, "hasMore": False, "cacheAvailable": False, "facets": library_facets([]), "message": "Desktop literature cache is unavailable; refresh the library in OmniLit."}
            validate_library_page(payload)
            return payload
        groups = request.get("keywordGroups") or []
        if not isinstance(groups, list) or len(groups) > 64:
            raise GraphServiceError("invalid_input", "keywordGroups must be an array of at most 64 values")
        state = self._library_state_store.load()
        filtered = filter_library_records(records, query=str(request.get("query") or "")[:500], relevance=str(request.get("relevance") or "all"), pdf_status=str(request.get("pdfStatus") or "all"), journal_type=str(request.get("journalType") or "all"), keyword_groups={str(value)[:128] for value in groups}, sort=str(request.get("sort") or "relevance_desc"), collection_id=str(request.get("collectionId") or "all"), favorites=state.get("favorites") or {})
        offset = max(0, int(request.get("offset") or 0))
        limit = max(1, min(200, int(request.get("limit") or 50)))
        page = filtered[offset:offset + limit]
        status = "ready" if page else "empty"
        payload = {"protocolVersion": PROTOCOL_VERSION, "status": status, "records": [project_library_summary(record, self.data_root) for record in page], "offset": offset, "nextOffset": offset + len(page), "total": len(filtered), "hasMore": offset + len(page) < len(filtered), "cacheAvailable": True, "facets": library_facets(records), "message": "" if page else "No literature records match the current filters."}
        validate_library_page(payload)
        return payload

    def library_detail(self, record_id: str) -> dict[str, Any]:
        record_id = _opaque_identifier(record_id, "recordId")
        cache_available, records = read_library_cache(self.data_root)
        if not cache_available:
            raise GraphServiceError("library_unavailable", "Desktop literature cache is unavailable", 503)
        record = next((item for item in records if str(item.get("recordId") or "") == record_id), None)
        if record is None:
            raise GraphServiceError("library_record_not_found", "Literature record not found", 404)
        payload = project_library_detail(record, self.data_root, PROTOCOL_VERSION)
        validate_library_record_detail(payload)
        return payload

    def library_state(self) -> dict[str, Any]:
        payload = project_library_state(self._library_state_store.load(), PROTOCOL_VERSION)
        validate_library_state(payload)
        return payload

    def mutate_library_state(self, request: dict[str, Any]) -> dict[str, Any]:
        validate_library_mutation_request(request)
        try:
            state, changed = self._library_state_store.mutate(str(request["action"]), expected_revision=int(request["expectedRevision"]), collection_id=str(request.get("collectionId") or ""), name=str(request.get("name") or ""), record_id=str(request.get("recordId") or ""))
        except LibraryStateConflict as exc:
            raise GraphServiceError("library_state_conflict", str(exc), 409) from exc
        except KeyError as exc:
            raise GraphServiceError("library_collection_not_found", str(exc), 404) from exc
        except (ValueError, TimeoutError) as exc:
            raise GraphServiceError("invalid_library_mutation", str(exc), 400) from exc
        payload = {"protocolVersion": PROTOCOL_VERSION, "changed": changed, "message": "updated" if changed else "unchanged", "state": project_library_state(state, PROTOCOL_VERSION)}
        validate_library_mutation_result(payload)
        return payload

    def research_workspace(self) -> dict[str, Any]:
        cache_available, records = read_library_cache(self.data_root)
        payload = project_research_workspace(self.data_root, cache_available, records, self._library_state_store.load())
        validate_research_workspace(payload)
        return payload

    def research_statistics(self) -> dict[str, Any]:
        cache_available, records = read_library_cache(self.data_root)
        payload = project_research_statistics(cache_available, records, self._library_state_store.load())
        validate_research_statistics(payload)
        return payload

    def business_settings(self) -> dict[str, Any]:
        payload = self._business_settings_store.load()
        validate_business_settings(payload)
        return payload

    def update_business_settings(self, request: dict[str, Any]) -> dict[str, Any]:
        validate_business_settings_update_request(request)
        try:
            payload = self._business_settings_store.update(request)
        except BusinessSettingsConflict as exc:
            raise GraphServiceError("business_settings_conflict", str(exc), 409) from exc
        except (ValueError, TimeoutError) as exc:
            raise GraphServiceError("invalid_business_settings", str(exc), 400) from exc
        validate_business_settings(payload)
        return payload

    def research_brief_task(self, request: dict[str, Any], context) -> dict[str, Any]:
        validate_research_brief_request(request)
        workspace = self.research_workspace()
        if workspace["status"] != "ready":
            raise GraphServiceError("research_workspace_empty", workspace["message"], 409)
        payload = build_research_brief(workspace, request, context, self.business_settings())
        validate_research_brief_result(payload)
        return payload

    def projection(self, record_id: str, request: dict[str, Any]) -> dict[str, Any]:
        graph = self._legacy_graph(record_id)
        return self._project_graph(graph, record_id, request)

    def _project_graph(self, graph: dict[str, Any], record_id: str, request: dict[str, Any]) -> dict[str, Any]:
        viewport = request.get("viewport") or {}
        if not isinstance(viewport, dict):
            raise GraphServiceError("invalid_input", "viewport must be an object")

        def ids(name: str) -> list[str]:
            values = request.get(name) or []
            if not isinstance(values, list) or len(values) > 200:
                raise GraphServiceError("invalid_input", f"{name} must contain at most 200 ids")
            return [_identifier(value, name) for value in values]

        layout_style = str(request.get("layoutStyle") or "academic").casefold()
        if layout_style not in {"academic", "overview"}:
            raise GraphServiceError("invalid_layout_style", "Unsupported projection layout style")
        metadata = dict(graph.get("metadata") or {})
        layout = graph.get("layout") or metadata.get("layout") or {}
        projection = project_render_graph(
            graph.get("nodes") or [], graph.get("edges") or [], layout, viewport,
            pinned_node_ids=ids("pinnedNodeIds"), pinned_edge_ids=ids("pinnedEdgeIds"), layout_style=layout_style,
        )
        projected_nodes = []
        for value in projection["nodes"]:
            node = dict(value)
            details = dict(node.get("details") or {})
            for key in ("aggregate", "memberCount", "memberSample"):
                if key in node:
                    details[key] = node[key]
            node["details"] = details
            projected_nodes.append(node)
        projected_edges = []
        for value in projection["edges"]:
            edge = dict(value)
            details = dict(edge.get("details") or {})
            for key in ("aggregate", "count"):
                if key in edge:
                    details[key] = edge[key]
            edge["details"] = details
            projected_edges.append(edge)
        projected_graph = {**graph, "nodes": projected_nodes, "edges": projected_edges, "metadata": {**metadata, "projectionStatus": projection["status"]}}
        shared = to_shared_graph_data(projected_graph)
        result = {"protocolVersion": PROTOCOL_VERSION, "schemaVersion": GRAPH_SCHEMA_VERSION, "recordId": str(shared["recordId"]), "graph": shared, "layout": projection["layout"], "status": projection["status"]}
        validate_graph_projection(result)
        return result

    def timeline(self, timeline_key: str, request: dict[str, Any]) -> dict[str, Any]:
        timeline_key = _identifier(timeline_key, "timelineKey")
        validate_graph_timeline_query(request)
        try:
            collection_key, topic_map, evolution = load_timeline_bundle(self.data_root, timeline_key)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise GraphServiceError("invalid_timeline_cache", str(exc), 422) from exc
        if not evolution or not topic_map:
            raise GraphServiceError("timeline_not_found", "Knowledge graph timeline not found", 404)
        try:
            years = sorted({
                int(value)
                for value in (evolution.get("yearRange") or {}).get("years") or []
                if 1900 <= int(value) <= 2100
            })
        except (TypeError, ValueError) as exc:
            raise GraphServiceError("invalid_timeline_cache", "Timeline contains an invalid year", 422) from exc
        if not years:
            raise GraphServiceError("timeline_empty", "Timeline has no papers with known years", 404)
        start = max(years[0], min(years[-1], int(request.get("startYear") or years[0])))
        end = max(years[0], min(years[-1], int(request.get("endYear") or years[-1])))
        if start > end:
            start, end = end, start
        range_years = [year for year in years if start <= year <= end]
        if not range_years:
            raise GraphServiceError("timeline_range_empty", "Timeline range contains no known years", 400)
        requested_playback = int(request.get("playbackYear") or range_years[-1])
        playback = min(range_years, key=lambda year: (abs(year - requested_playback), year))
        effective_end = min(end, playback)
        legacy_graph = build_evolution_graph(evolution, topic_map, [], [], start, effective_end)
        if not legacy_graph:
            raise GraphServiceError("timeline_range_empty", "Timeline range contains no graph papers", 400)
        legacy_graph["metadata"] = {
            **dict(legacy_graph.get("metadata") or {}),
            "timelineKey": str(evolution.get("cacheKey") or timeline_key),
            "timelineCollectionKey": collection_key,
        }
        projection = self._project_graph(legacy_graph, str(legacy_graph.get("recordId") or f"timeline:{collection_key}"), {
            "viewport": dict(request.get("viewport") or {}),
            "pinnedNodeIds": list(request.get("pinnedNodeIds") or []),
            "layoutStyle": "academic",
        })
        events = [dict(item) for item in evolution.get("events") or [] if start <= int(item.get("year") or 0) <= effective_end]
        topic_series = []
        for value in evolution.get("topicSeries") or []:
            if not isinstance(value, dict):
                continue
            points = [dict(point) for point in value.get("points") or [] if start <= int(point.get("year") or 0) <= effective_end]
            if points and any(int(point.get("count") or 0) for point in points):
                topic_series.append({**value, "points": points})
        turning_points = [dict(item) for item in evolution.get("turningPoints") or [] if start <= int(item.get("year") or 0) <= effective_end]
        key_paths = []
        for value in evolution.get("keyPaths") or []:
            if not isinstance(value, dict):
                continue
            try:
                pairs = [
                    (str(paper_id), int(year))
                    for paper_id, year in zip(value.get("paperIds") or [], value.get("years") or [])
                    if start <= int(year) <= effective_end
                ]
            except (TypeError, ValueError) as exc:
                raise GraphServiceError("invalid_timeline_cache", "Timeline key path contains an invalid year", 422) from exc
            if len(pairs) < 2:
                continue
            paper_ids = [paper_id for paper_id, _year in pairs]
            window_years = [year for _paper_id, year in pairs]
            key_paths.append({
                **value,
                "label": f"{str(value.get('label') or 'Key citation path')} ({start}–{effective_end})",
                "paperIds": paper_ids,
                "years": window_years,
                "displayPaperIds": paper_ids[:12],
                "displayTruncated": len(paper_ids) > 12,
                "length": len(paper_ids),
                "yearSpan": max(window_years) - min(window_years),
                "explanation": f"Current window retains {len(paper_ids)} papers in the original directed citation order.",
                "originalExplanation": str(value.get("explanation") or ""),
            })
        result = {
            "protocolVersion": PROTOCOL_VERSION,
            "schemaVersion": GRAPH_SCHEMA_VERSION,
            "timelineVersion": EVOLUTION_VERSION,
            "timelineKey": str(evolution.get("cacheKey") or timeline_key),
            "status": "ready" if events else "empty",
            "generatedAt": str(evolution.get("generatedAt") or ""),
            "selection": {"startYear": start, "endYear": end, "playbackYear": playback, "effectiveEndYear": effective_end},
            "yearRange": dict(evolution.get("yearRange") or {}),
            "events": events,
            "topicSeries": topic_series,
            "keyPaths": key_paths,
            "turningPoints": turning_points,
            "topicSpeedComparisons": [dict(item) for item in evolution.get("topicSpeedComparisons") or [] if isinstance(item, dict)],
            "diagnostics": dict(evolution.get("diagnostics") or {}),
            "graph": projection["graph"],
            "projection": projection["status"],
        }
        validate_graph_timeline(result)
        return result

    def list_views(self, record_id: str) -> dict[str, Any]:
        record_id = _identifier(record_id, "recordId")
        with self._views_lock:
            views = self._saved_views(record_id)
        result = {"protocolVersion": PROTOCOL_VERSION, "recordId": record_id, "views": view_summaries(views)}
        validate_graph_view_list(result)
        return result

    def save_view(self, record_id: str, request: dict[str, Any]) -> dict[str, Any]:
        record_id = _identifier(record_id, "recordId")
        validate_graph_view_save_request(request)
        graph = self._legacy_graph(record_id)
        with self._views_lock:
            views = self._saved_views(record_id)
            requested_id = str(request.get("id") or "")
            clean_name = str(request.get("name") or "").strip()[:80]
            existing = next((item for item in views if requested_id and item["id"] == requested_id), None)
            if existing is None:
                existing = next((item for item in views if str(item.get("name") or "").casefold() == clean_name.casefold()), None)
            snapshot = make_snapshot(
                record_id, clean_name,
                str(request.get("graphFingerprint") or graph.get("source_fingerprint") or (graph.get("metadata") or {}).get("source_fingerprint") or ""),
                dict(request.get("exploration") or {}), dict(request.get("filters") or {}),
                dict(request.get("selection") or {}), dict(request.get("viewport") or {}),
                existing, path=dict(request.get("path") or {}),
            )
            if existing:
                views[views.index(existing)] = snapshot
            else:
                if len(views) >= 100:
                    raise GraphServiceError("view_limit_reached", "At most 100 graph views can be saved", 409)
                views.append(snapshot)
            save_views(self.data_root, record_id, views)
        validate_graph_view_state(snapshot)
        return snapshot

    def restore_view(self, record_id: str, view_id: str) -> dict[str, Any]:
        record_id = _identifier(record_id, "recordId")
        view_id = _identifier(view_id, "viewId")
        graph = self._legacy_graph(record_id)
        with self._views_lock:
            views = self._saved_views(record_id)
        snapshot = next((item for item in views if item["id"] == view_id), None)
        if snapshot is None:
            raise GraphServiceError("view_not_found", "Saved graph view not found", 404)
        restored, report = reconcile_snapshot(snapshot, graph)
        requested_nodes = set(restored["exploration"]["nodeIds"])
        requested_edges = set(restored["exploration"]["edgeIds"])
        if requested_nodes:
            nodes = [node for node in graph.get("nodes") or [] if str(node.get("id") or "") in requested_nodes]
            node_ids = {str(node.get("id") or "") for node in nodes}
            edges = [edge for edge in graph.get("edges") or [] if str(edge.get("source") or "") in node_ids and str(edge.get("target") or "") in node_ids and (not requested_edges or str(edge.get("id") or "") in requested_edges)]
            restored_graph = {**graph, "nodes": nodes, "edges": edges, "metadata": {**dict(graph.get("metadata") or {}), "projection": "saved-view"}}
            shared_graph = to_shared_graph_data(restored_graph, view_state=restored)
        else:
            shared_graph = self.initial_graph(record_id)
            shared_graph["viewState"] = restored
        result = {"protocolVersion": PROTOCOL_VERSION, "recordId": record_id, "view": restored, "graph": shared_graph, "reconciliation": report}
        validate_graph_view_restore(result)
        return result

    def delete_view(self, record_id: str, view_id: str) -> dict[str, Any]:
        record_id = _identifier(record_id, "recordId")
        view_id = _identifier(view_id, "viewId")
        with self._views_lock:
            views = self._saved_views(record_id)
            remaining = [item for item in views if item["id"] != view_id]
            if len(remaining) == len(views):
                raise GraphServiceError("view_not_found", "Saved graph view not found", 404)
            save_views(self.data_root, record_id, remaining)
        result = {"protocolVersion": PROTOCOL_VERSION, "recordId": record_id, "viewId": view_id, "deleted": True}
        validate_graph_view_mutation(result)
        return result

    def audit_task(self, request: dict[str, Any], context) -> dict[str, Any]:
        record_id = _identifier(request.get("recordId"), "recordId")
        graph = self._legacy_graph(record_id)
        nodes = [item for item in graph.get("nodes") or [] if isinstance(item, dict)]
        edges = [item for item in graph.get("edges") or [] if isinstance(item, dict)]
        total = max(1, len(nodes) + len(edges))
        node_types: dict[str, int] = {}
        relation_types: dict[str, int] = {}
        completed = 0
        for node in nodes:
            context.check_cancelled()
            node_type = str(node.get("type") or "unknown")
            node_types[node_type] = node_types.get(node_type, 0) + 1
            completed += 1
            if completed % 250 == 0:
                context.report(completed, total, "elements", "Auditing graph nodes")
        for edge in edges:
            context.check_cancelled()
            relation_type = str(edge.get("type") or "unknown")
            relation_types[relation_type] = relation_types.get(relation_type, 0) + 1
            completed += 1
            if completed % 250 == 0:
                context.report(completed, total, "elements", "Auditing graph relations")
        literature_count = len(project_literature_rows(graph))
        context.report(total, total, "elements", "Graph audit complete")
        return {"protocolVersion": PROTOCOL_VERSION, "recordId": record_id, "nodeCount": len(nodes), "edgeCount": len(edges), "nodeTypes": node_types, "relationTypes": relation_types, "literatureCount": literature_count}
