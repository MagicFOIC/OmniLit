from __future__ import annotations

import json
import threading
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

from omnilit_qt.knowledge_graph_storage import graph_path, safe_record_id, views_path
from omnilit_qt.knowledge_graph_evolution import build_evolution
from omnilit_qt.knowledge_graph_topics import build_topic_map
from omnilit_qt.shared_protocol import from_shared_graph_data
from services.local_agent import GraphService, GraphServiceError, create_local_agent_server
from tests.knowledge_graph_benchmarks import make_lod_benchmark
from tests.test_knowledge_graph_topics import topic_graph


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "packages" / "shared-schema" / "fixtures" / "shared-graph-v1.json"
TOKEN = "local-agent-integration-token-0001"
ORIGIN = "http://127.0.0.1:4173"


class _ServiceTaskContext:
    def check_cancelled(self) -> None:
        return None

    def report(self, _completed: float, _total: float, _unit: str, _message: str = "") -> None:
        return None


def _update_business_settings(revision: int, **overrides) -> dict:
    payload = {
        "protocolVersion": "1.0", "expectedRevision": revision, "themeMode": "system", "density": "comfortable",
        "reduceMotion": False, "highContrast": False, "startPage": "graph", "defaultLibrarySort": "relevance_desc",
        "aiEvidenceLimit": 4, "aiEndpoint": "", "aiModel": "", "allowRemoteResearchContent": False,
    }
    payload.update(overrides)
    return payload


def seed_timeline(data_root: Path, collection_key: str = "demo-timeline") -> dict:
    graphs, records = [], []
    for index, year in enumerate((2020, 2022, 2024, 2024)):
        graph, record = topic_graph(
            f"timeline-{index}", f"Timeline paper {index}", year,
            [("concept", "knowledge graph" if index < 3 else "scientific discovery"), ("method", "retrieval augmented generation")],
            [f"timeline-{index - 1}"] if index else [],
        )
        graphs.append(graph)
        records.append(record)
    topic_map = build_topic_map(graphs, records)
    evolution = build_evolution(topic_map, graphs, records)
    target = data_root / "data" / "literature" / "graphs" / "topic_maps" / collection_key
    target.mkdir(parents=True)
    (target / "topic_map.json").write_text(json.dumps(topic_map), encoding="utf-8")
    (target / "evolution.json").write_text(json.dumps(evolution), encoding="utf-8")
    return evolution


def seed_library_cache(data_root: Path) -> None:
    target = data_root / "cache" / "downloads" / "library_cache.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    records = [
        {"recordId": "paper-001", "title": "Contract-First Knowledge Graphs", "authorsText": "Ada Example", "year": "2024", "source": "OpenAlex", "journalTitle": "Research Systems", "journalType": "field_journal", "journalTypeLabel": "专业领域", "impactFactorText": "8.2", "keywordsText": "knowledge graph", "contentSummary": "Interoperable graph contracts", "topicTagsText": "Graphs", "pdfStatus": "downloaded", "localPdfPath": "private/paper.pdf", "relevanceLabel": "严格相关", "relevance_level": "strict", "relevance_score": 0.96, "matchedKeywordsText": "knowledge graph", "keywordGroupKeys": ["knowledge graph"], "abstract": "A shared contract for research graphs.", "doi": "10.1000/graphs"},
        {"recordId": "doi:10.1000/evidence", "title": "Evidence Discovery", "authorsText": "Mira Chen", "year": "2022", "source": "Crossref", "journalTitle": "Open Science", "journalType": "oa_journal", "journalTypeLabel": "开放获取", "impactFactorText": "4.1", "keywordsText": "evidence", "contentSummary": "Evidence provenance", "topicTagsText": "Evidence", "pdfStatus": "no_candidate", "localPdfPath": "", "relevanceLabel": "均衡相关", "relevance_level": "balanced", "relevance_score": 0.78, "matchedKeywordsText": "evidence", "keywordGroupKeys": ["evidence"]},
    ]
    target.write_text(json.dumps({"version": 2, "signature": {}, "records": records}), encoding="utf-8")


def graph_view_request(name: str = "Research view") -> dict:
    return {
        "protocolVersion": "1.0", "name": name,
        "exploration": {"nodeIds": ["paper:paper-001", "author:ada-example"], "edgeIds": ["edge:author-of"], "pages": {}},
        "filters": {"mode": "all", "searchText": "Ada", "density": "normal", "literatureSortKey": "relevance", "literatureSortDescending": True, "facets": {}, "nodeTypes": ["author"], "needsReviewOnly": False},
        "selection": {"nodeId": "author:ada-example", "edgeId": ""},
        "path": {"startId": "", "endId": "", "directed": False, "relationFilter": "ALL"},
        "viewport": {"displayStyle": "academic", "focusDepth": 0, "reviewMode": False, "graphScale": 1.4, "panX": 24, "panY": -12, "width": 1280, "height": 720, "showArrows": True, "showLabels": True, "dimUnrelated": True, "textFadeThreshold": 1.15, "nodeSizeScale": 1, "linkThickness": 1, "animateLayout": False},
    }


class LocalAgentGraphServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.data_root = Path(self.temporary.name)
        shared = json.loads(FIXTURE.read_text(encoding="utf-8"))
        target = graph_path(self.data_root, "paper-001")
        target.parent.mkdir(parents=True)
        target.write_text(json.dumps(from_shared_graph_data(shared).to_dict()), encoding="utf-8")
        self.evolution = seed_timeline(self.data_root)
        seed_library_cache(self.data_root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_storage_mapping_is_stable_and_traversal_safe(self) -> None:
        self.assertEqual(safe_record_id("paper-001"), safe_record_id("paper-001"))
        self.assertNotIn("..", safe_record_id("../../private"))
        self.assertEqual(graph_path(self.data_root, "../../private").parents[4], self.data_root.resolve())

    def test_service_returns_seed_then_paginated_neighbors_and_literature(self) -> None:
        service = GraphService(self.data_root)
        graph_list = service.list_graphs()
        self.assertEqual(graph_list["graphs"][0]["recordId"], "paper-001")
        self.assertEqual(graph_list["graphs"][0]["nodeCount"], 6)
        self.assertNotIn("path", graph_list["graphs"][0])
        initial = service.initial_graph("paper-001")
        self.assertEqual([node["id"] for node in initial["nodes"]], ["paper:paper-001"])
        self.assertEqual(initial["edges"], [])

        first = service.neighbors("paper-001", "paper:paper-001", limit=2)
        second = service.neighbors("paper-001", "paper:paper-001", offset=first["nextOffset"], limit=10)
        self.assertEqual(first["revealed"], 2)
        self.assertTrue(first["hasMore"])
        self.assertEqual({node["id"] for node in first["nodes"] + second["nodes"]}, {"author:ada-example", "method:paper-001:1", "result:paper-001:1", "citation:contract-systems"})

        literature = service.literature("paper-001", {"visibleNodeIds": ["paper:paper-001", "citation:contract-systems"], "selectedNodeId": "citation:contract-systems"})
        self.assertEqual(literature["total"], 2)
        self.assertTrue(next(row for row in literature["rows"] if row["nodeId"] == "citation:contract-systems")["selected"])

    def test_service_rejects_paths_and_unknown_modes(self) -> None:
        service = GraphService(self.data_root)
        with self.assertRaises(GraphServiceError):
            service.initial_graph("../paper-001")
        with self.assertRaises(GraphServiceError):
            service.neighbors("paper-001", "paper:paper-001", "commands")

    def test_large_graph_projection_reuses_lod_budget_and_preserves_cluster_metadata(self) -> None:
        nodes, edges, layout = make_lod_benchmark(1_000)
        target = graph_path(self.data_root, "large-001")
        target.parent.mkdir(parents=True)
        target.write_text(json.dumps({"recordId": "large-001", "paper": {"title": "Large graph"}, "nodes": nodes, "edges": edges, "layout": layout}), encoding="utf-8")
        projection = GraphService(self.data_root).projection("large-001", {"viewport": {"width": 1280, "height": 800, "scale": 0.5}, "layoutStyle": "overview"})
        self.assertEqual(projection["status"]["level"], "overview")
        self.assertLessEqual(len(projection["graph"]["nodes"]), 240)
        self.assertTrue(projection["status"]["degraded"])
        clusters = [node for node in projection["graph"]["nodes"] if node["type"] == "cluster"]
        self.assertTrue(clusters)
        self.assertTrue(clusters[0]["attributes"]["aggregate"])
        self.assertGreater(clusters[0]["attributes"]["memberCount"], 0)
        self.assertFalse(projection["status"]["budgetExceeded"])

    def test_saved_views_share_desktop_storage_and_restore_reconciled_graph(self) -> None:
        service = GraphService(self.data_root)
        saved = service.save_view("paper-001", graph_view_request())
        self.assertTrue(saved["id"].startswith("view-"))
        self.assertTrue(views_path(self.data_root, "paper-001").is_file())
        self.assertEqual(service.list_views("paper-001")["views"][0]["name"], "Research view")

        restored = service.restore_view("paper-001", saved["id"])
        self.assertEqual(restored["view"]["selection"]["nodeId"], "author:ada-example")
        self.assertEqual({node["id"] for node in restored["graph"]["nodes"]}, {"paper:paper-001", "author:ada-example"})
        self.assertEqual(restored["reconciliation"], {"missingNodes": 0, "missingEdges": 0})
        self.assertTrue(service.delete_view("paper-001", saved["id"])["deleted"])
        self.assertEqual(service.list_views("paper-001")["views"], [])

    def test_timeline_reuses_desktop_cache_and_clips_playback_window(self) -> None:
        service = GraphService(self.data_root)
        full = service.timeline("demo-timeline", {
            "protocolVersion": "1.0", "viewport": {"width": 1280, "height": 720, "scale": 1},
        })
        self.assertEqual(full["timelineVersion"], 2)
        self.assertEqual(full["yearRange"]["years"], [2020, 2022, 2024])
        self.assertEqual(full["selection"], {"startYear": 2020, "endYear": 2024, "playbackYear": 2024, "effectiveEndYear": 2024})
        self.assertEqual({event["year"] for event in full["events"]}, {2020, 2022, 2024})
        self.assertTrue(full["graph"]["nodes"])
        self.assertEqual(full["graph"]["metadata"]["timelineCollectionKey"], "demo-timeline")

        playback = service.timeline(self.evolution["cacheKey"], {
            "protocolVersion": "1.0", "startYear": 2022, "endYear": 2024, "playbackYear": 2022,
            "viewport": {"width": 900, "height": 600, "scale": 1},
        })
        self.assertEqual(playback["selection"]["effectiveEndYear"], 2022)
        self.assertEqual([event["year"] for event in playback["events"]], [2022])
        self.assertTrue(all(max(path["years"]) <= 2022 for path in playback["keyPaths"]))
        self.assertTrue(all("Current window retains" in path["explanation"] for path in playback["keyPaths"]))
        self.assertTrue(all(int(node.get("attributes", {}).get("year") or 2022) <= 2022 for node in playback["graph"]["nodes"] if node["type"] == "paper"))

    def test_library_reuses_desktop_cache_filters_and_hides_local_paths(self) -> None:
        service = GraphService(self.data_root)
        page = service.library({"protocolVersion": "1.0", "query": "contract", "pdfStatus": "downloaded", "sort": "year_desc", "limit": 10})
        self.assertEqual(page["total"], 1)
        self.assertEqual(page["records"][0]["recordId"], "paper-001")
        self.assertTrue(page["records"][0]["downloaded"])
        self.assertNotIn("localPdfPath", page["records"][0])
        detail = service.library_detail("paper-001")
        self.assertEqual(detail["doi"], "10.1000/graphs")
        self.assertNotIn("localPdfPath", detail)

    def test_library_state_mutations_use_revisions_and_report_conflicts(self) -> None:
        service = GraphService(self.data_root)
        initial = service.library_state()
        created = service.mutate_library_state({"protocolVersion": "1.0", "action": "create_collection", "expectedRevision": initial["revision"], "name": "Methods"})
        self.assertTrue(created["changed"])
        self.assertEqual(created["state"]["revision"], initial["revision"] + 1)
        collection_id = next(item["id"] for item in created["state"]["collections"] if item["name"] == "Methods")
        favorited = service.mutate_library_state({"protocolVersion": "1.0", "action": "toggle_collection_record", "expectedRevision": created["state"]["revision"], "collectionId": collection_id, "recordId": "paper-001"})
        page = service.library({"protocolVersion": "1.0", "collectionId": collection_id})
        self.assertEqual([item["recordId"] for item in page["records"]], ["paper-001"])
        with self.assertRaises(GraphServiceError) as conflict:
            service.mutate_library_state({"protocolVersion": "1.0", "action": "clear_compare", "expectedRevision": initial["revision"]})
        self.assertEqual(conflict.exception.status, 409)
        self.assertEqual(favorited["state"]["revision"], initial["revision"] + 2)

    def test_research_workspace_statistics_settings_and_local_brief_share_one_service(self) -> None:
        service = GraphService(self.data_root)
        state = service.library_state()
        selected = service.mutate_library_state({"protocolVersion": "1.0", "action": "toggle_compare_record", "expectedRevision": state["revision"], "recordId": "paper-001"})
        workspace = service.research_workspace()
        self.assertEqual(workspace["records"][0]["recordId"], "paper-001")
        self.assertNotIn("localPdfPath", workspace["records"][0])
        statistics = service.research_statistics()
        self.assertEqual(statistics["totalRecords"], 2)
        self.assertEqual(statistics["compareRecords"], 1)
        settings = service.business_settings()
        updated = service.update_business_settings(_update_business_settings(settings["revision"], startPage="workspace"))
        self.assertEqual(updated["startPage"], "workspace")
        brief = service.research_brief_task({"protocolVersion": "1.0", "recordIds": ["paper-001"], "focus": "overview", "question": "", "mode": "evidence_only"}, _ServiceTaskContext())
        self.assertEqual(brief["mode"], "evidence_only")
        self.assertEqual(selected["state"]["workspace"]["compareRecordIds"], ["paper-001"])


class LocalAgentHttpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.data_root = Path(self.temporary.name)
        shared = json.loads(FIXTURE.read_text(encoding="utf-8"))
        target = graph_path(self.data_root, "paper-001")
        target.parent.mkdir(parents=True)
        target.write_text(json.dumps(from_shared_graph_data(shared).to_dict()), encoding="utf-8")
        seed_timeline(self.data_root)
        seed_library_cache(self.data_root)
        self.web_root = self.data_root / "embedded-web"
        self.web_root.mkdir()
        (self.web_root / "index.html").write_text("<!doctype html><title>OmniLit Embedded</title>", encoding="utf-8")
        (self.web_root / "app.js").write_text("globalThis.omnilitEmbedded = true", encoding="utf-8")
        self.server = create_local_agent_server(data_root=self.data_root, token=TOKEN, allowed_origins={ORIGIN}, web_root=self.web_root)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temporary.cleanup()

    def request(self, path: str, *, token: str | None = TOKEN, origin: str | None = ORIGIN, body: dict | None = None, method: str | None = None):
        headers = {}
        if token is not None:
            headers["Authorization"] = f"Bearer {token}"
        if origin is not None:
            headers["Origin"] = origin
        data = None if body is None else json.dumps(body).encode()
        if data is not None:
            headers["Content-Type"] = "application/json"
        return urlopen(Request(self.base_url + path, headers=headers, data=data, method=method or ("POST" if data is not None else "GET")), timeout=2)

    def test_authenticated_http_workflow_and_cors(self) -> None:
        with self.request("/v1/health") as response:
            self.assertEqual(json.load(response)["status"], "ready")
            self.assertEqual(response.headers["Access-Control-Allow-Origin"], ORIGIN)
        with self.request("/v1/graphs") as response:
            self.assertEqual(json.load(response)["graphs"][0]["recordId"], "paper-001")
        node = quote("paper:paper-001", safe="")
        with self.request(f"/v1/graphs/paper-001/nodes/{node}:neighbors?limit=1") as response:
            self.assertEqual(json.load(response)["revealed"], 1)
        with self.request("/v1/graphs/paper-001/literature/query", body={"visibleNodeIds": ["paper:paper-001"]}) as response:
            self.assertEqual(json.load(response)["total"], 1)
        with self.request("/v1/graphs/paper-001/projection", body={"viewport": {"width": 900, "height": 600, "scale": 1}}) as response:
            projection = json.load(response)
        self.assertEqual(projection["status"]["totalSemanticNodes"], 6)
        self.assertEqual(projection["graph"]["recordId"], "paper-001")

        preflight = Request(self.base_url + "/v1/health", headers={
            "Origin": ORIGIN,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization,x-omnilit-protocol-version",
            "Access-Control-Request-Private-Network": "true",
        }, method="OPTIONS")
        with urlopen(preflight, timeout=2) as response:
            self.assertEqual(response.status, 204)
            self.assertEqual(response.headers["Access-Control-Allow-Private-Network"], "true")

        with self.request("/v1/graphs/paper-001/projection", origin=self.base_url, body={"viewport": {"width": 900, "height": 600, "scale": 1}}) as response:
            self.assertEqual(response.headers["Access-Control-Allow-Origin"], self.base_url)

        with self.request("/v1/timelines/demo-timeline/query", body={"protocolVersion": "1.0", "startYear": 2020, "endYear": 2024, "playbackYear": 2022, "viewport": {"width": 900, "height": 600, "scale": 1}}) as response:
            timeline = json.load(response)
        self.assertEqual(timeline["selection"]["effectiveEndYear"], 2022)
        self.assertEqual([event["year"] for event in timeline["events"]], [2020, 2022])

        with self.request("/v1/library/query", body={"protocolVersion": "1.0", "query": "evidence", "limit": 20}) as response:
            library = json.load(response)
        self.assertEqual(library["records"][0]["recordId"], "doi:10.1000/evidence")
        with self.request(f"/v1/library/records/{quote('doi:10.1000/evidence', safe='')}") as response:
            self.assertEqual(json.load(response)["title"], "Evidence Discovery")
        with self.request("/v1/library/state") as response:
            state = json.load(response)
        with self.request("/v1/library/state/mutations", body={"protocolVersion": "1.0", "action": "toggle_compare_record", "expectedRevision": state["revision"], "recordId": "paper-001"}) as response:
            mutation = json.load(response)
        self.assertEqual(mutation["state"]["workspace"]["compareRecordIds"], ["paper-001"])
        with self.request("/v1/workspace") as response:
            self.assertEqual(json.load(response)["records"][0]["recordId"], "paper-001")
        with self.request("/v1/statistics") as response:
            self.assertEqual(json.load(response)["totalRecords"], 2)
        with self.request("/v1/settings/business") as response:
            settings = json.load(response)
        with self.request("/v1/settings/business", body=_update_business_settings(settings["revision"], startPage="statistics")) as response:
            self.assertEqual(json.load(response)["startPage"], "statistics")

        with self.request("/app/index.html") as response:
            self.assertEqual(response.headers.get_content_type(), "text/html")
            self.assertIn("frame-ancestors 'none'", response.headers["Content-Security-Policy"])
            self.assertIn("http://127.0.0.1:*", response.headers["Content-Security-Policy"])
            self.assertEqual(response.headers["Referrer-Policy"], "no-referrer")
            self.assertIn(b"OmniLit Embedded", response.read())
        with self.request("/app/app.js") as response:
            self.assertEqual(response.headers.get_content_type(), "text/javascript")
        with self.assertRaises(HTTPError) as missing_asset:
            self.request("/app/private.txt")
        self.assertEqual(missing_asset.exception.code, 404)
        with self.assertRaises(HTTPError) as unauthorized_asset:
            self.request("/app/index.html", token=None)
        self.assertEqual(unauthorized_asset.exception.code, 401)

        with self.request("/v1/graphs/paper-001/views", body=graph_view_request("HTTP view")) as response:
            saved_view = json.load(response)
        with self.request("/v1/graphs/paper-001/views") as response:
            self.assertEqual(json.load(response)["views"][0]["id"], saved_view["id"])
        with self.request(f"/v1/graphs/paper-001/views/{saved_view['id']}") as response:
            self.assertEqual(json.load(response)["view"]["name"], "HTTP view")
        with self.request(f"/v1/graphs/paper-001/views/{saved_view['id']}", method="DELETE") as response:
            self.assertTrue(json.load(response)["deleted"])

    def test_http_task_create_poll_and_result_workflow(self) -> None:
        with self.request("/v1/tasks", body={"type": "graph.audit", "input": {"recordId": "paper-001"}}) as response:
            self.assertEqual(response.status, 202)
            task = json.load(response)
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            with self.request(f"/v1/tasks/{task['id']}") as response:
                task = json.load(response)
            if task["status"] in {"succeeded", "failed", "cancelled"}:
                break
            time.sleep(0.01)
        self.assertEqual(task["status"], "succeeded")
        self.assertEqual(task["resultRef"], f"/v1/tasks/{task['id']}/result")
        with self.request(task["resultRef"]) as response:
            result = json.load(response)
        self.assertEqual(result["nodeCount"], 6)
        self.assertEqual(result["edgeCount"], 5)
        self.assertEqual(result["literatureCount"], 2)

        with self.request("/v1/library/state") as response:
            state = json.load(response)
        with self.request("/v1/library/state/mutations", body={"protocolVersion": "1.0", "action": "toggle_compare_record", "expectedRevision": state["revision"], "recordId": "paper-001"}):
            pass
        with self.request("/v1/tasks", body={"type": "research.brief", "input": {"protocolVersion": "1.0", "recordIds": ["paper-001"], "focus": "overview", "question": "", "mode": "evidence_only"}}) as response:
            brief_task = json.load(response)
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            with self.request(f"/v1/tasks/{brief_task['id']}") as response:
                brief_task = json.load(response)
            if brief_task["status"] in {"succeeded", "failed", "cancelled"}:
                break
            time.sleep(0.01)
        self.assertEqual(brief_task["status"], "succeeded")
        with self.request(brief_task["resultRef"]) as response:
            brief = json.load(response)
        self.assertEqual(brief["mode"], "evidence_only")
        self.assertIn("未调用生成式模型", brief["warnings"][0])

    def test_auth_origin_and_bind_guards(self) -> None:
        with self.assertRaises(HTTPError) as unauthorized:
            self.request("/v1/health", token=None)
        self.assertEqual(unauthorized.exception.code, 401)
        with self.assertRaises(HTTPError) as forbidden:
            self.request("/v1/health", origin="https://evil.example")
        self.assertEqual(forbidden.exception.code, 403)
        with self.assertRaises(ValueError):
            create_local_agent_server(data_root=self.data_root, host="0.0.0.0", token=TOKEN)


if __name__ == "__main__":
    unittest.main()
