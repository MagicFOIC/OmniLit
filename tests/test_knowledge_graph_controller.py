from __future__ import annotations

import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

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
            self.assertTrue(cached.generateGraph("paper/1", record, "paper.pdf"))
            self.assertEqual(cached.graph["title"], "Graph Paper")
            self.assertIn("缓存", cached.statusText)

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
            self.assertTrue(cached.generateGraph("p1", record, "paper.pdf"))
            self.assertLess(time.perf_counter() - started, 0.25)
            self.assertFalse(cached.loading)

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

            self.assertEqual(loaded_paths, [controller._graph_path("p1")])
            self.assertTrue(controller.loading)
            self.assertEqual(controller.graph["title"], "Cached")


if __name__ == "__main__":
    unittest.main()
