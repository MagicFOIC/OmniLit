from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    from PySide6.QtCore import QCoreApplication
    from omnilit_qt.topic_map_controller import TopicMapController
except ModuleNotFoundError:
    QCoreApplication = None
    TopicMapController = None

from tests.test_knowledge_graph_controller import FakePaths, InstantWorker


@unittest.skipUnless(TopicMapController is not None, "PySide6 is not installed")
class TopicMapControllerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._qt_app = QCoreApplication.instance() or QCoreApplication([])

    @staticmethod
    def records() -> list[dict]:
        values = []
        for index in range(3):
            values.append({
                "recordId": f"graph-{index}", "title": f"Knowledge Graph Retrieval {index}",
                "year": 2019 + index, "keywordsText": "knowledge graph; retrieval augmented generation",
                "authors": ["Ada Lovelace", f"Graph Author {index}"], "institutions": ["Graph Lab"],
                "references": ["graph-0"] if index else [],
            })
        for index in range(3):
            values.append({
                "recordId": f"battery-{index}", "title": f"Battery Prognosis {index}",
                "year": 2017 + index, "keywordsText": "battery degradation; remaining useful life",
                "authors": ["Grace Hopper", f"Battery Author {index}"], "institutions": ["Battery Lab"],
                "references": ["battery-0"] if index else [],
            })
        return values

    def test_generate_cache_select_and_build_local_graph(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            paths = FakePaths(Path(temp))
            controller = TopicMapController(None, paths, None, None)
            with patch("omnilit_qt.topic_map_controller.ManagedWorker", InstantWorker):
                self.assertTrue(controller.generateForRecords(self.records()))
            self.assertFalse(controller.loading)
            self.assertEqual(controller.state, "ready")
            self.assertGreaterEqual(len(controller.topics), 2)
            self.assertTrue(controller._topic_map_path(controller.currentKey).is_file())
            self.assertTrue(controller._evolution_path(controller.currentKey).is_file())
            self.assertTrue(controller._network_analysis_path(controller.currentKey).is_file())
            self.assertTrue(controller._research_network_path(controller.currentKey).is_file())
            self.assertTrue(controller.evolutionYears)
            self.assertTrue(controller.evolution["keyPaths"])
            self.assertTrue(controller.networkAnalysis["keywordNetwork"]["nodes"])
            self.assertTrue(controller.researchNetwork["authors"])
            self.assertTrue(controller.researchNetwork["recommendations"])

            topic = controller.topics[0]
            self.assertTrue(controller.selectTopic(topic["id"]))
            self.assertEqual(controller.selectedTopic["id"], topic["id"])
            graph = controller.topicGraph(topic["id"])
            self.assertTrue(graph["metadata"]["topic_graph"])
            self.assertEqual(len([node for node in graph["nodes"] if node["type"] == "paper"]), topic["size"])
            filtered_graph = controller.topicGraph(topic["id"], [topic["paperIds"][0]])
            self.assertEqual(len([node for node in filtered_graph["nodes"] if node["type"] == "paper"]), 1)
            self.assertFalse(controller.selectTopic("missing"))

            years = controller.evolutionYears
            self.assertTrue(controller.setEvolutionRange(years[0], years[-1]))
            self.assertTrue(controller.startEvolutionPlayback())
            self.assertEqual(controller.evolutionRange["playbackYear"], years[0])
            self.assertTrue(controller.visibleEvolutionEvents)
            self.assertTrue(controller.windowTopics)
            self.assertLessEqual(sum(item["size"] for item in controller.windowTopics), len(self.records()))
            self.assertTrue(controller.advanceEvolutionPlayback())
            path = controller.evolution["keyPaths"][0]
            self.assertTrue(controller.selectEvolutionPath(path["id"]))
            self.assertEqual(controller.selectedEvolutionPath["id"], path["id"])
            evolution_graph = controller.evolutionGraph()
            self.assertTrue(evolution_graph["metadata"]["evolution_graph"])
            analysis_graph = controller.networkAnalysisGraph("core")
            self.assertTrue(analysis_graph["metadata"]["network_analysis_graph"])
            research_graph = controller.researchNetworkGraph("authors")
            self.assertTrue(research_graph["metadata"]["research_network_graph"])

            cached = TopicMapController(None, paths, None, None)
            with patch("omnilit_qt.topic_map_controller.ManagedWorker", InstantWorker):
                self.assertTrue(cached.generateForRecords(self.records()))
            self.assertEqual(cached.topicMap["cacheKey"], controller.topicMap["cacheKey"])
            self.assertEqual(cached.evolution["cacheKey"], controller.evolution["cacheKey"])
            self.assertEqual(cached.networkAnalysis["cacheKey"], controller.networkAnalysis["cacheKey"])
            self.assertEqual(cached.researchNetwork["cacheKey"], controller.researchNetwork["cacheKey"])

    def test_empty_and_duplicate_task_states_are_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            controller = TopicMapController(None, FakePaths(Path(temp)), None, None)
            self.assertFalse(controller.generateForRecords([]))
            self.assertEqual(controller.state, "empty")
            controller._loading = True
            self.assertFalse(controller.generateForRecords(self.records()))
            self.assertIn("正在运行", controller.statusText)
            self.assertTrue(controller.cancel())
            controller._on_task_finished("key", {}, "领域主题分析已取消。", False)
            self.assertEqual(controller.state, "idle")


if __name__ == "__main__":
    unittest.main()
