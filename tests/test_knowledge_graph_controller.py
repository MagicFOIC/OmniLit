from __future__ import annotations

import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from omnilit_qt.knowledge_graph_image_export import PNG_SIGNATURE
from tests.knowledge_graph_benchmarks import make_lod_benchmark
from tests.test_knowledge_graph_topics import topic_graph
from omnilit_qt.knowledge_graph_topics import build_topic_graph, build_topic_map
from omnilit_qt.knowledge_graph_evolution import build_evolution, build_evolution_graph
from omnilit_qt.knowledge_graph_network_analysis import build_network_analysis, build_network_analysis_graph
from omnilit_qt.knowledge_graph_research_network import build_research_network, build_research_network_graph

try:
    from PySide6.QtCore import QCoreApplication
    from omnilit_qt.knowledge_graph_controller import KnowledgeGraphController
except ModuleNotFoundError:  # pragma: no cover - depends on local test runtime.
    QCoreApplication = None
    KnowledgeGraphController = None


class FakePaths:
    def __init__(self, root: Path) -> None:
        self.root = root

    def data(self, *parts: str) -> Path:
        return self.root.joinpath(*parts)


class InstantWorker:
    def __init__(self, *, target, cancel_event, **kwargs) -> None:
        self.target = target
        self.cancel_event = cancel_event
        self.alive = False

    def start(self) -> None:
        self.alive = True
        self.target()
        self.alive = False

    def update_state(self, status: str, *, detail: str = "") -> None:
        pass

    def is_alive(self) -> bool:
        return self.alive


class DeferredWorker(InstantWorker):
    def start(self) -> None:
        self.alive = True


class FakePdfExtraction:
    def __init__(self) -> None:
        self.focused: list[str] = []

    def focusElement(self, element_id: str) -> bool:
        self.focused.append(element_id)
        return True


@unittest.skipUnless(KnowledgeGraphController is not None, "PySide6 is not installed in this environment")
class KnowledgeGraphControllerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._qt_app = QCoreApplication.instance() or QCoreApplication([])

    def test_generate_cache_and_exports(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            paths = FakePaths(root)
            controller = KnowledgeGraphController(None, paths, None, None)
            record = {"recordId": "paper/1", "title": "Graph Paper", "keywordsText": "graph; offline"}

            with patch("omnilit_qt.knowledge_graph_controller.ManagedWorker", InstantWorker):
                self.assertTrue(controller.generateGraph("paper/1", record, "paper.pdf"))

            self.assertFalse(controller.loading)
            self.assertEqual(controller.graph["recordId"], "paper/1")
            json_path = Path(controller.exportGraphJson("paper/1"))
            markdown_path = Path(controller.exportGraphMarkdown("paper/1"))
            self.assertTrue(json_path.is_file())
            self.assertTrue(markdown_path.is_file())
            self.assertEqual(json.loads(json_path.read_text(encoding="utf-8"))["version"], 1)
            self.assertIn("## 关键词", markdown_path.read_text(encoding="utf-8"))

            cached = KnowledgeGraphController(None, paths, None, None)
            with patch("omnilit_qt.knowledge_graph_controller.ManagedWorker", InstantWorker):
                self.assertTrue(cached.generateGraph("paper/1", record, "paper.pdf"))
            self.assertEqual(cached.graph["title"], "Graph Paper")
            self.assertIn("缓存", cached.statusText)

    def test_png_export_transaction_and_explored_graph_context(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            controller = KnowledgeGraphController(None, FakePaths(Path(temp)), None, None)
            controller._current_record_id = "paper/1"
            controller._graph = {
                "recordId": "paper/1",
                "title": "Graph Paper",
                "source_fingerprint": "fingerprint",
                "nodes": [
                    {"id": "paper:p1", "type": "paper"},
                    {"id": "method:m1", "type": "method"},
                    {"id": "dataset:d1", "type": "dataset"},
                ],
                "edges": [
                    {"id": "e1", "source": "paper:p1", "target": "method:m1"},
                    {"id": "e2", "source": "method:m1", "target": "dataset:d1"},
                ],
            }
            controller._exploration_active = True
            controller._explored_node_ids = {"paper:p1", "method:m1"}
            controller._explored_edge_ids = {"e1", "e2"}

            self.assertEqual({item["id"] for item in controller.imageExportNodes}, {"paper:p1", "method:m1"})
            self.assertEqual([item["id"] for item in controller.imageExportEdges], ["e1"])
            self.assertEqual(controller.validateImageExport(800, 600, 2)["width"], 1600)
            self.assertFalse(controller.validateImageExport(9000, 9000, 2)["ok"])

            prepared = controller.prepareImageExport("Graph: A/B?", "full", 2, True)
            self.assertTrue(prepared["ok"])
            path = Path(prepared["path"])
            self.assertEqual(path.parent.name, "exports")
            self.assertNotIn(":", path.name)
            self.assertFalse(controller.prepareImageExport("Second", "viewport", 1, False)["ok"])
            path.write_bytes(PNG_SIGNATURE + b"payload")

            self.assertTrue(controller.completeImageExport(str(path), True, ""))
            self.assertEqual(controller.imageExportStatus["status"], "ready")
            manifest = json.loads(path.with_suffix(".png.json").read_text(encoding="utf-8"))
            self.assertEqual((manifest["scope"], manifest["scale"], manifest["transparent"]), ("full", 2.0, True))

    def test_png_export_rejects_invalid_or_mismatched_completion(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            controller = KnowledgeGraphController(None, FakePaths(Path(temp)), None, None)
            controller._current_record_id = "p1"
            controller._graph = {"recordId": "p1", "nodes": [{"id": "paper:p1"}], "edges": []}
            prepared = controller.prepareImageExport("Graph", "viewport", 1, False)
            path = Path(prepared["path"])
            self.assertFalse(controller.completeImageExport(str(path.with_name("other.png")), True, ""))
            self.assertEqual(controller.imageExportStatus["status"], "error")
            path.write_bytes(b"not a png")
            self.assertFalse(controller.completeImageExport(str(path), True, ""))
            self.assertIn("PNG", controller.imageExportStatus["message"])

            controller._replay_events = [{"nodeIds": ["paper:p1"], "edgeIds": []}]
            controller._replay_active = True
            controller._replay_index = 0
            self.assertFalse(controller.prepareImageExport("Replay", "viewport", 1, False)["ok"])
            controller._replay_index = 1
            self.assertTrue(controller.prepareImageExport("Replay Complete", "full", 1, False)["ok"])

    def test_render_projection_separates_semantic_graph_from_qml_instances(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            controller = KnowledgeGraphController(None, FakePaths(Path(temp)), None, None)
            nodes, edges, layout = make_lod_benchmark(5_000)
            controller._current_record_id = "benchmark"
            controller._graph = {"recordId": "benchmark", "nodes": nodes, "edges": edges, "layout": layout}
            controller._density = "all"
            controller._node_limit = 10_000
            controller.setRenderViewport(1280, 800, 0.6, 0, 0)

            rendered = controller.renderNodes
            status = controller.renderStatus
            self.assertLessEqual(len(rendered), 240)
            self.assertEqual(status["totalSemanticNodes"], 5_000)
            self.assertGreater(status["aggregatedNodes"], 0)
            self.assertEqual(len(controller.imageExportNodes), 5_000)
            self.assertEqual(len(controller.nodes), 5_000)

            controller._path_result = {
                "status": "ready", "nodeIds": ["node:4999"], "edgeIds": [], "steps": []
            }
            controller.changed.emit()
            self.assertIn("node:4999", {node["id"] for node in controller.renderNodes})

    def test_render_viewport_emits_only_render_change_signal(self) -> None:
        controller = KnowledgeGraphController(None, FakePaths(Path.cwd()), None, None)
        changed_count = 0
        render_count = 0

        def changed() -> None:
            nonlocal changed_count
            changed_count += 1

        def rendered() -> None:
            nonlocal render_count
            render_count += 1

        controller.changed.connect(changed)
        controller.renderChanged.connect(rendered)
        controller.setRenderViewport(1200, 700, 1.2, 20, -10)
        self.assertEqual(changed_count, 0)
        self.assertEqual(render_count, 1)

    def test_load_topic_graph_validates_and_enters_derived_context(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            controller = KnowledgeGraphController(None, FakePaths(Path(temp)), None, None)
            graphs = []
            records = []
            for index in range(3):
                graph, record = topic_graph(
                    f"p{index}", f"Graph paper {index}", 2020 + index,
                    [("concept", "knowledge graph"), ("method", "retrieval augmented generation")],
                )
                record["authors"] = ["Ada Lovelace", f"Author {index}"]
                record["institutions"] = ["Graph Lab"]
                graphs.append(graph); records.append(record)
            topic_map = build_topic_map(graphs, records)
            derived = build_topic_graph(topic_map, topic_map["topics"][0]["id"], graphs, records)

            self.assertTrue(controller.loadTopicGraph(derived))
            self.assertTrue(controller.graph["metadata"]["topic_graph"])
            self.assertEqual(controller.currentRecordId, derived["recordId"])
            self.assertTrue(controller._graph_path(controller.currentRecordId).is_file())
            self.assertFalse(controller.explorationActive)
            self.assertFalse(controller.loadTopicGraph({"nodes": [{"id": "bad"}]}))

            evolution = build_evolution(topic_map, graphs, records)
            evolution_graph = build_evolution_graph(evolution, topic_map, graphs, records, 2020, 2022)
            self.assertTrue(controller.loadTopicGraph(evolution_graph))
            self.assertTrue(controller.graph["metadata"]["evolution_graph"])
            self.assertIn("时间演化图谱", controller.statusText)
            self.assertTrue(controller.selectLiteratureRecord("p1"))
            self.assertEqual((controller.selectedNode.get("details") or {}).get("recordId"), "p1")

            analysis = build_network_analysis(topic_map, evolution, graphs, records)
            analysis_graph = build_network_analysis_graph(analysis, "core")
            self.assertTrue(controller.loadTopicGraph(analysis_graph))
            self.assertTrue(controller.graph["metadata"]["network_analysis_graph"])
            self.assertIn("结构分析图谱", controller.statusText)

            research = build_research_network(topic_map, evolution, analysis, records)
            research_graph = build_research_network_graph(research, "authors")
            self.assertTrue(controller.loadTopicGraph(research_graph))
            self.assertTrue(controller.graph["metadata"]["research_network_graph"])
            self.assertIn("合作网络", controller.statusText)

    def test_generate_comparison_graph(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            controller = KnowledgeGraphController(None, FakePaths(Path(temp)), None, None)
            records = [
                {"recordId": "p1", "title": "First", "keywordsText": "graph; battery"},
                {"recordId": "p2", "title": "Second", "keywordsText": "graph; model"},
            ]

            with patch("omnilit_qt.knowledge_graph_controller.ManagedWorker", InstantWorker):
                self.assertTrue(controller.generateComparisonGraph(records))

            self.assertTrue(controller.currentRecordId.startswith("comparison_"))
            self.assertEqual(len([node for node in controller.graph["nodes"] if node["type"] == "paper"]), 2)
            self.assertEqual(len([node for node in controller.graph["nodes"] if node["id"] == "concept:graph"]), 1)
            self.assertEqual(controller.graph["comparisonRecordIds"], ["p1", "p2"])
            self.assertEqual(len(controller.semanticComparison["papers"]), 2)
            self.assertTrue(controller.selectSemanticCell("p1", "method"))
            self.assertEqual(controller.selectedSemanticCell["status"], "missing")
            self.assertTrue(controller.reviewSemanticCell("p1", "method", "add", "Human verified method", "checked appendix"))
            self.assertEqual(controller.selectedSemanticCell["items"][0]["source"], "human_review")
            self.assertTrue(controller._semantic_review_path("p1").is_file())
            self.assertTrue(controller.clearSemanticReview("p1", "method"))
            self.assertEqual(controller.selectedSemanticCell["status"], "missing")

            cached = KnowledgeGraphController(None, FakePaths(Path(temp)), None, None)
            self.assertTrue(cached.generateComparisonGraph(records))
            self.assertEqual(cached.semanticComparison["cacheKey"], controller.semanticComparison["cacheKey"])

    def test_selection_filter_export_and_evidence_focus(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            paths = FakePaths(root)
            controller = KnowledgeGraphController(None, paths, None, None)
            record_id = "p1"
            index_path = controller._index_path(record_id)
            index_path.parent.mkdir(parents=True, exist_ok=True)
            index_path.write_text(json.dumps({"elements": [{"id": "fig-1", "type": "figure", "page": 2, "bbox": [1, 2, 3, 4], "caption": "Architecture"}]}), encoding="utf-8")
            with patch("omnilit_qt.knowledge_graph_controller.ManagedWorker", InstantWorker):
                self.assertTrue(controller.generateGraph(record_id, {"title": "Paper", "keywordsText": "graph"}, "paper.pdf"))

            figure = next(node for node in controller.graph["nodes"] if node["type"] == "figure")
            self.assertTrue(controller.selectNode(figure["id"]))
            self.assertEqual(controller.selectedNode["label"], "Architecture")
            fake_pdf = FakePdfExtraction()
            controller.setPdfExtractionController(fake_pdf)
            focused = []
            controller.evidenceFocusRequested.connect(lambda record, page, bbox, element: focused.append((record, page, element)))
            self.assertTrue(controller.focusEvidence(figure["id"], 0))
            self.assertEqual(fake_pdf.focused, [])
            self.assertEqual(focused, [(record_id, 2, "fig-1")])
            controller.setFilterMode("figure")
            self.assertTrue(all(node["type"] in {"paper", "figure", "table", "equation"} for node in controller.nodes))
            self.assertEqual(controller.selectedNode["type"], "figure")
            controller.search("architecture")
            self.assertTrue(any(node["type"] == "figure" for node in controller.nodes))
            self.assertTrue(Path(controller.exportGraph(record_id, "mermaid")).is_file())
            self.assertEqual(controller.graphStatus(record_id, ""), "已生成")
            self.assertTrue(controller.hasGraph(record_id))

    def test_batch_generation_skips_records_without_local_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            controller = KnowledgeGraphController(None, FakePaths(Path(temp)), None, None)
            records = [
                {"recordId": "p1", "title": "One", "localPdfPath": "one.pdf", "keywordsText": "graph"},
                {"recordId": "p2", "title": "Two", "localPdfPath": ""},
            ]
            with patch("omnilit_qt.knowledge_graph_controller.ManagedWorker", InstantWorker):
                self.assertTrue(controller.generateGraphs(records))
            self.assertFalse(controller.loading)
            self.assertTrue(controller._graph_path("p1").is_file())
            self.assertFalse(controller._graph_path("p2").exists())
            self.assertIn("1 / 1", controller.statusText)

    def test_missing_index_uses_fast_local_pdf_extraction(self) -> None:
        try:
            import fitz
        except ImportError:
            self.skipTest("PyMuPDF is not installed")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pdf_path = root / "paper.pdf"
            document = fitz.open()
            page = document.new_page()
            page.insert_text((72, 72), "Methods")
            page.insert_text((72, 100), "We propose a transformer method for a difficult prediction problem.")
            page.insert_text((72, 128), "The experiment uses a benchmark dataset and accuracy metric.")
            page.insert_text((72, 156), "Results show that the method improves accuracy by five percent.")
            document.save(pdf_path)
            document.close()

            controller = KnowledgeGraphController(None, FakePaths(root), None, None)
            with patch("omnilit_qt.knowledge_graph_controller.ManagedWorker", InstantWorker):
                self.assertTrue(controller.generateGraph("p1", {"recordId": "p1", "title": "Paper"}, str(pdf_path)))
            self.assertTrue(controller._index_path("p1").is_file())
            types = {node["type"] for node in controller.graph["nodes"]}
            self.assertTrue({"section", "method", "experiment", "dataset", "metric", "result"}.issubset(types))

    def test_semantic_filters_select_a_real_node_from_the_requested_category(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            controller = KnowledgeGraphController(None, FakePaths(Path(temp)), None, None)
            controller._graph = {
                "nodes": [
                    {"id": "paper:p1", "type": "paper", "label": "Paper", "importance": 1.0},
                    {"id": "section:1", "type": "section", "label": "Methods", "importance": 0.7},
                    {"id": "method:1", "type": "method", "label": "Transformer", "importance": 0.9},
                    {"id": "dataset:1", "type": "dataset", "label": "ImageNet", "importance": 0.8},
                    {"id": "result:1", "type": "result", "label": "Improved accuracy", "importance": 0.85},
                    {"id": "contribution:1", "type": "contribution", "label": "Contribution", "importance": 0.99},
                ],
                "edges": [],
            }
            expected = {
                "structure": {"section", "paragraph"},
                "method": {"method", "algorithm", "model"},
                "experiment": {"experiment", "dataset", "metric", "baseline"},
                "result": {"result", "claim"},
            }
            for mode, allowed in expected.items():
                with self.subTest(mode=mode):
                    controller.setFilterMode(mode)
                    self.assertIn(controller.selectedNode["type"], allowed)
            self.assertEqual(controller.filterCounts["method"], 1)
            self.assertEqual(controller.filterCounts["experiment"], 1)
            self.assertEqual(controller.filterCounts["result"], 1)

    def test_stale_cache_is_visible_while_background_refresh_is_pending(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            controller = KnowledgeGraphController(None, FakePaths(Path(temp)), None, None)
            with patch("omnilit_qt.knowledge_graph_controller.ManagedWorker", InstantWorker):
                controller.generateGraph("p1", {"recordId": "p1", "title": "Old", "keywordsText": "graph"}, "paper.pdf")
            refreshed = KnowledgeGraphController(None, controller.paths, None, None)
            with patch("omnilit_qt.knowledge_graph_controller.ManagedWorker", DeferredWorker):
                self.assertTrue(refreshed.generateGraph("p1", {"recordId": "p1", "title": "New", "keywordsText": "graph"}, "paper.pdf"))
            self.assertEqual(refreshed.graph["title"], "Old")
            self.assertTrue(refreshed.loading)
            self.assertEqual(refreshed.cacheState, "refreshing")
            refreshed._worker.target()
            self.assertFalse(refreshed.loading)
            self.assertEqual(refreshed.graph["title"], "New")

    def test_fresh_cache_load_is_under_interaction_budget(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            paths = FakePaths(Path(temp))
            record = {"recordId": "p1", "title": "Cached", "keywordsText": "graph"}
            controller = KnowledgeGraphController(None, paths, None, None)
            with patch("omnilit_qt.knowledge_graph_controller.ManagedWorker", InstantWorker):
                controller.generateGraph("p1", record, "paper.pdf")
            cached = KnowledgeGraphController(None, paths, None, None)
            started = time.perf_counter()
            with patch("omnilit_qt.knowledge_graph_controller.ManagedWorker", DeferredWorker):
                self.assertTrue(cached.generateGraph("p1", record, "paper.pdf"))
            self.assertLess(time.perf_counter() - started, 0.25)
            self.assertTrue(cached.loading)
            self.assertEqual(cached.graph["title"], "Cached")
            cached._worker.target()
            self.assertFalse(cached.loading)

    def test_replay_reveals_graph_incrementally_then_enters_complete_state(self) -> None:
        controller = KnowledgeGraphController(None, FakePaths(Path(".")), None, None)
        first = {"page": 0, "element_id": "b1", "excerpt": "We propose A."}
        second = {"page": 1, "element_id": "b2", "excerpt": "A achieves a result."}
        controller._graph = {
            "nodes": [
                {"id": "paper:p", "type": "paper", "label": "Paper", "importance": 1.0},
                {"id": "method:a", "type": "method", "label": "A", "importance": 1.0, "evidence": [first]},
                {"id": "result:a", "type": "result", "label": "Result", "importance": 1.0, "evidence": [second]},
            ],
            "edges": [
                {"id": "e1", "source": "paper:p", "target": "method:a", "type": "PROPOSES", "relation_evidence": [first]},
                {"id": "e2", "source": "method:a", "target": "result:a", "type": "ACHIEVES", "relation_evidence": [second]},
            ],
        }
        controller._prepare_replay(controller._graph)

        self.assertTrue(controller.startReplay())
        self.assertEqual([node["id"] for node in controller.nodes], ["paper:p", "method:a"])
        self.assertEqual([edge["id"] for edge in controller.edges], ["e1"])
        self.assertTrue(controller.advanceReplay())
        self.assertEqual({node["id"] for node in controller.nodes}, {"paper:p", "method:a", "result:a"})
        self.assertFalse(controller.advanceReplay())
        self.assertTrue(controller.replayComplete)
        self.assertEqual(controller.replayEvent, {})

    def test_progressive_exploration_pages_neighbors_and_resets_to_seed(self) -> None:
        controller = KnowledgeGraphController(None, FakePaths(Path(".")), None, None)
        controller._graph = {
            "recordId": "p",
            "nodes": [
                {"id": "paper:p", "type": "paper", "label": "Paper", "importance": 1.0},
                {"id": "citation:1", "type": "citation", "label": "Prior work", "importance": 0.9},
                {"id": "author:a", "type": "author", "label": "Ada", "importance": 0.8},
                {"id": "concept:t", "type": "concept", "label": "Graphs", "importance": 0.7},
            ],
            "edges": [
                {"id": "e1", "source": "paper:p", "target": "citation:1", "type": "CITES"},
                {"id": "e2", "source": "author:a", "target": "paper:p", "type": "AUTHOR_OF"},
                {"id": "e3", "source": "paper:p", "target": "concept:t", "type": "MENTIONS"},
            ],
        }
        controller._prepare_replay(controller._graph)

        self.assertTrue(controller.explorationActive)
        self.assertEqual([node["id"] for node in controller.nodes], ["paper:p"])
        self.assertTrue(controller.selectNode("paper:p"))
        self.assertEqual(controller.explorationSummary["all"], 3)
        self.assertTrue(controller.expandNeighbors("paper:p", "authors", 1))
        self.assertEqual({node["id"] for node in controller.nodes}, {"paper:p", "author:a"})
        self.assertEqual([edge["id"] for edge in controller.edges], ["e2"])
        self.assertEqual(controller.explorationStatus["status"], "ready")
        controller.resetExploration()
        self.assertEqual([node["id"] for node in controller.nodes], ["paper:p"])
        self.assertEqual(controller.edges, [])

    def test_literature_rows_follow_exploration_sort_selection_and_hover(self) -> None:
        controller = KnowledgeGraphController(None, FakePaths(Path(".")), None, None)
        controller._current_record_id = "p1"
        controller._graph = {
            "recordId": "p1",
            "paper": {"title": "Seed", "authors": ["Ada"], "year": "2024"},
            "nodes": [
                {"id": "paper:p1", "type": "paper", "label": "Seed", "importance": 1.0},
                {"id": "citation:a", "type": "citation", "label": "Alpha 2020", "importance": 0.8, "details": {"citationCount": 5}},
                {"id": "citation:b", "type": "citation", "label": "Beta 2022", "importance": 0.7, "details": {"citationCount": 30}},
                {"id": "method:m", "type": "method", "label": "Method", "importance": 0.9},
            ],
            "edges": [
                {"id": "e1", "source": "paper:p1", "target": "citation:a", "type": "CITES"},
                {"id": "e2", "source": "paper:p1", "target": "citation:b", "type": "CITES"},
                {"id": "e3", "source": "paper:p1", "target": "method:m", "type": "USES"},
            ],
        }
        controller._prepare_replay(controller._graph)

        self.assertEqual([row["nodeId"] for row in controller.literatureRows], ["paper:p1"])
        self.assertTrue(controller.expandNeighbors("paper:p1", "references", 12))
        controller.setLiteratureSort("citations", True)
        self.assertEqual([row["nodeId"] for row in controller.literatureRows], ["citation:b", "citation:a", "paper:p1"])
        controller.setHoveredNode("citation:a")
        self.assertTrue(next(row for row in controller.literatureRows if row["nodeId"] == "citation:a")["hovered"])
        self.assertTrue(controller.selectLiteratureNode("citation:b"))
        self.assertEqual(controller.selectedNode["id"], "citation:b")
        self.assertTrue(next(row for row in controller.literatureRows if row["nodeId"] == "citation:b")["selected"])

    def test_shortest_path_uses_current_exploration_context_and_explains_steps(self) -> None:
        controller = KnowledgeGraphController(None, FakePaths(Path(".")), None, None)
        controller._current_record_id = "p1"
        controller._graph = {
            "recordId": "p1",
            "nodes": [
                {"id": "paper:p1", "type": "paper", "label": "Paper"},
                {"id": "method:m", "type": "method", "label": "Method"},
                {"id": "result:r", "type": "result", "label": "Result"},
            ],
            "edges": [
                {"id": "e1", "source": "paper:p1", "target": "method:m", "type": "USES"},
                {"id": "e2", "source": "method:m", "target": "result:r", "type": "ACHIEVES"},
            ],
        }
        controller._prepare_replay(controller._graph)
        controller.expandNeighbors("paper:p1", "all", 12)
        controller.expandNeighbors("method:m", "all", 12)
        self.assertTrue(controller.setPathStart("paper:p1"))
        self.assertTrue(controller.setPathEnd("result:r"))
        controller.setPathDirected(True)

        self.assertTrue(controller.computeShortestPath())
        self.assertEqual(controller.pathState["nodeIds"], ["paper:p1", "method:m", "result:r"])
        self.assertEqual(controller.pathState["edgeIds"], ["e1", "e2"])
        self.assertIn("沿关系方向", controller.pathState["steps"][0]["explanation"])
        self.assertEqual(controller.pathRelationTypes, ["REPORTS_RESULT", "USES_METHOD"])
        controller.setFilterMode("result")
        self.assertEqual({node["id"] for node in controller.nodes}, {"paper:p1", "method:m", "result:r"})

        controller.setPathRelationFilter("ACHIEVES")
        self.assertFalse(controller.computeShortestPath())
        self.assertEqual(controller.pathState["status"], "no_path")
        controller.resetExploration()
        self.assertEqual(controller.pathState["status"], "idle")
        self.assertEqual(controller.pathState["startId"], "")

    def test_undo_redo_coalesces_search_and_restores_default_reset(self) -> None:
        controller = KnowledgeGraphController(None, FakePaths(Path(".")), None, None)
        controller._current_record_id = "p1"
        controller._graph = {
            "recordId": "p1",
            "nodes": [
                {"id": "paper:p1", "type": "paper", "label": "Paper"},
                {"id": "method:m", "type": "method", "label": "Graph Method"},
            ],
            "edges": [{"id": "e1", "source": "paper:p1", "target": "method:m", "type": "USES"}],
        }
        controller._prepare_replay(controller._graph)
        restored_viewports = []
        controller.viewRestored.connect(lambda viewport: restored_viewports.append(dict(viewport)))

        controller.expandNeighbors("paper:p1", "all", 12)
        controller.search("g")
        controller.search("gr")
        controller.search("graph")
        self.assertEqual(controller.historyState["undoDepth"], 2)
        self.assertEqual(controller.historyState["undoAction"], "搜索图谱")
        controller._on_task_finished("p1", dict(controller._graph), "background refresh", True)
        self.assertEqual(controller.historyState["undoDepth"], 2)
        self.assertTrue(controller.undo())
        self.assertEqual(controller.searchText, "")
        self.assertTrue(controller.redo())
        self.assertEqual(controller.searchText, "graph")

        controller.selectNode("method:m")
        controller.setPathStart("paper:p1")
        controller.setPathEnd("method:m")
        controller.setFilterMode("method")
        controller.resetExploration({"displayStyle": "radial", "graphScale": 1.7, "panX": 24})
        self.assertEqual(controller.nodes[0]["id"], "paper:p1")
        self.assertEqual(controller.searchText, "")
        self.assertEqual(controller.filterMode, "all")
        self.assertEqual(controller.pathState["startId"], "")
        self.assertEqual(restored_viewports[-1]["displayStyle"], "overview")
        self.assertTrue(controller.undo({"displayStyle": "overview", "graphScale": 1.0}))
        self.assertEqual({node["id"] for node in controller.nodes}, {"paper:p1", "method:m"})
        self.assertEqual(controller.filterMode, "method")
        self.assertEqual(controller.pathState["startId"], "paper:p1")
        self.assertEqual(controller.pathState["endId"], "method:m")
        self.assertEqual(restored_viewports[-1]["displayStyle"], "radial")
        self.assertEqual(restored_viewports[-1]["graphScale"], 1.7)
        self.assertTrue(controller.canRedo)
        self.assertTrue(controller.redo({"displayStyle": "radial", "graphScale": 1.7}))
        self.assertEqual(restored_viewports[-1]["displayStyle"], "overview")
        self.assertTrue(controller.undo({"displayStyle": "overview", "graphScale": 1.0}))
        controller.search("new branch")
        self.assertFalse(controller.canRedo)

    def test_comparison_history_does_not_copy_full_graph_membership(self) -> None:
        controller = KnowledgeGraphController(None, FakePaths(Path(".")), None, None)
        controller._current_record_id = "comparison"
        controller._graph = {
            "recordId": "comparison", "metadata": {"comparison": True},
            "nodes": [{"id": f"paper:{index}", "type": "paper", "label": str(index)} for index in range(1_000)],
            "edges": [],
        }
        controller._prepare_replay(controller._graph)

        state = controller._capture_history_state()

        self.assertFalse(controller.explorationActive)
        self.assertEqual(state["exploration"], {"nodeIds": [], "edgeIds": [], "pages": {}})

    def test_saved_view_round_trip_overwrite_and_delete_are_separate_from_graph_cache(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            controller = KnowledgeGraphController(None, FakePaths(Path(temp)), None, None)
            controller._current_record_id = "p1"
            controller._graph = {
                "recordId": "p1", "source_fingerprint": "fingerprint-1",
                "nodes": [
                    {"id": "paper:p1", "type": "paper", "label": "Paper", "importance": 1.0},
                    {"id": "method:m", "type": "method", "label": "Method", "importance": 0.9},
                ],
                "edges": [{"id": "e1", "source": "paper:p1", "target": "method:m", "type": "USES"}],
            }
            controller._prepare_replay(controller._graph)
            controller.expandNeighbors("paper:p1", "all", 12)
            controller.selectNode("method:m")
            controller.setFilterMode("method")
            controller.search("Method")
            controller.setLiteratureSort("title", False)
            controller.setPathStart("paper:p1")
            controller.setPathEnd("method:m")
            self.assertTrue(controller.computeShortestPath())
            restored_viewports = []
            controller.viewRestored.connect(lambda viewport: restored_viewports.append(dict(viewport)))

            view_id = controller.saveView("My View", {"displayStyle": "radial", "graphScale": 1.6, "panX": 42})

            self.assertTrue(view_id)
            self.assertEqual(len(controller.savedViews), 1)
            self.assertTrue(controller._views_path("p1").is_file())
            self.assertFalse(controller._graph_path("p1").exists())
            overwritten = controller.saveView("my view", {"displayStyle": "focus", "graphScale": 1.2})
            self.assertEqual(overwritten, view_id)
            self.assertEqual(len(controller.savedViews), 1)

            controller.resetExploration()
            controller.setFilterMode("all")
            controller.search("")
            controller.setLiteratureSort("citations", True)
            self.assertTrue(controller.restoreView(view_id))
            self.assertEqual({node["id"] for node in controller.nodes}, {"paper:p1", "method:m"})
            self.assertEqual(controller.filterMode, "method")
            self.assertEqual(controller.searchText, "Method")
            self.assertEqual(controller.literatureSortKey, "title")
            self.assertFalse(controller.literatureSortDescending)
            self.assertEqual(controller.selectedNode["id"], "method:m")
            self.assertEqual(controller.pathState["status"], "ready")
            self.assertEqual(controller.pathState["edgeIds"], ["e1"])
            self.assertEqual(restored_viewports[-1]["displayStyle"], "focus")
            self.assertEqual(restored_viewports[-1]["graphScale"], 1.2)
            refreshed_graph = dict(controller._graph)
            refreshed_graph["nodes"] = list(controller._graph["nodes"]) + [
                {"id": "result:r", "type": "result", "label": "New result", "importance": 0.7}
            ]
            controller._on_task_finished("p1", refreshed_graph, "refreshed", True)
            self.assertEqual({node["id"] for node in controller.nodes}, {"paper:p1", "method:m"})
            self.assertEqual(controller.filterMode, "method")
            self.assertEqual(controller.selectedNode["id"], "method:m")
            self.assertTrue(controller.deleteView(view_id))
            self.assertEqual(controller.savedViews, [])

            reloaded = KnowledgeGraphController(None, FakePaths(Path(temp)), None, None)
            reloaded._current_record_id = "p1"
            reloaded._graph = controller._graph
            reloaded._prepare_replay(reloaded._graph)
            self.assertEqual(reloaded.savedViews, [])

    def test_share_package_round_trip_restores_graph_and_view(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            paths = FakePaths(Path(temp))
            source = KnowledgeGraphController(None, paths, None, None)
            source._current_record_id = "shared-p1"
            source._graph = {
                "recordId": "shared-p1", "title": "Shared Paper", "source_fingerprint": "shared-fingerprint",
                "nodes": [
                    {"id": "paper:shared-p1", "type": "paper", "label": "Shared Paper", "importance": 1.0},
                    {"id": "result:r", "type": "result", "label": "Result", "importance": 0.8},
                ],
                "edges": [{"id": "e1", "source": "paper:shared-p1", "target": "result:r", "type": "ACHIEVES"}],
            }
            source._prepare_replay(source._graph)
            source.expandNeighbors("paper:shared-p1", "all", 12)
            source.setFilterMode("result")
            package_path = source.exportSharePackage("Shared View", {"displayStyle": "radial", "graphScale": 1.5})
            self.assertTrue(Path(package_path).is_file())

            target = KnowledgeGraphController(None, paths, None, None)
            restored_viewports = []
            target.viewRestored.connect(lambda viewport: restored_viewports.append(dict(viewport)))
            self.assertTrue(target.importSharePackage(package_path))
            self.assertEqual(target._current_record_id, "shared-p1")
            self.assertEqual(target.filterMode, "result")
            self.assertEqual(target.graph["edges"][0]["type"], "REPORTS_RESULT")
            self.assertEqual(target.savedViews[0]["name"], "Shared View")
            self.assertEqual(restored_viewports[-1]["displayStyle"], "radial")
            self.assertTrue(target._graph_path("shared-p1").is_file())

    def test_facets_filter_graph_and_literature_and_survive_view_restore(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            controller = KnowledgeGraphController(None, FakePaths(Path(temp)), None, None)
            controller._current_record_id = "facet-graph"
            controller._graph = {
                "recordId": "facet-graph", "nodes": [
                    {"id": "paper:p1", "type": "paper", "label": "One", "details": {"year": 2024, "authors": ["Ada"], "venue": "Nature"}},
                    {"id": "paper:p2", "type": "paper", "label": "Two", "details": {"year": 2023, "authors": ["Ben"], "venue": "Science"}},
                    {"id": "method:m1", "type": "method", "label": "Method One"},
                    {"id": "method:m2", "type": "method", "label": "Method Two"},
                ], "edges": [
                    {"id": "e1", "source": "paper:p1", "target": "method:m1", "type": "USES_METHOD"},
                    {"id": "e2", "source": "paper:p2", "target": "method:m2", "type": "USES_METHOD"},
                ],
            }
            controller._prepare_replay(controller._graph)
            controller.setFacetFilter("year", "2024")
            self.assertEqual(controller.facetFilters, {"year": "2024"})
            self.assertEqual({item["id"] for item in controller.nodes}, {"paper:p1", "method:m1"})
            self.assertEqual([item["nodeId"] for item in controller.literatureRows], ["paper:p1"])
            view_id = controller.saveView("2024 papers", {"displayStyle": "focus"})
            controller.clearFacetFilters()
            self.assertEqual(controller.facetFilters, {})
            self.assertTrue(controller.restoreView(view_id))
            self.assertEqual(controller.facetFilters, {"year": "2024"})
            controller.resetExploration()
            self.assertEqual(controller.facetFilters, {})

    def test_extraction_index_is_not_loaded_on_ui_thread(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            paths = FakePaths(Path(temp))
            record = {"recordId": "p1", "title": "Cached", "keywordsText": "graph"}
            original = KnowledgeGraphController(None, paths, None, None)
            with patch("omnilit_qt.knowledge_graph_controller.ManagedWorker", InstantWorker):
                original.generateGraph("p1", record, "paper.pdf")

            controller = KnowledgeGraphController(None, paths, None, None)
            loaded_paths = []
            real_load_json = controller._load_json

            def track_load(path):
                loaded_paths.append(path)
                return real_load_json(path)

            with patch.object(controller, "_load_json", side_effect=track_load), \
                    patch("omnilit_qt.knowledge_graph_controller.ManagedWorker", DeferredWorker):
                self.assertTrue(controller.generateGraph("p1", record, "paper.pdf"))

            self.assertEqual(loaded_paths, [controller._graph_path("p1"), controller._views_path("p1")])
            self.assertNotIn(controller._index_path("p1"), loaded_paths)
            self.assertTrue(controller.loading)
            self.assertEqual(controller.graph["title"], "Cached")


if __name__ == "__main__":
    unittest.main()
