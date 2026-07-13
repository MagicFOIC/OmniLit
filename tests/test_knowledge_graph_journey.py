from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from omnilit_qt.knowledge_graph_builder import build_knowledge_graph
from omnilit_qt.knowledge_graph_semantic_comparison import build_semantic_comparison

try:
    from PySide6.QtCore import QCoreApplication
    from omnilit_qt.knowledge_graph_controller import KnowledgeGraphController
    from omnilit_qt.topic_map_controller import TopicMapController
except ModuleNotFoundError:  # pragma: no cover - optional runtime
    QCoreApplication = None
    KnowledgeGraphController = None
    TopicMapController = None


class FakePaths:
    def __init__(self, root: Path) -> None:
        self.root = root

    def data(self, *parts: str) -> Path:
        return self.root.joinpath(*parts)

    content = data
    runtime = data


class InstantWorker:
    def __init__(self, *, target, cancel_event, **_kwargs) -> None:
        self.target = target
        self.cancel_event = cancel_event

    def start(self) -> None:
        self.target()

    def update_state(self, _status: str, **_kwargs) -> None:
        pass

    def is_alive(self) -> bool:
        return False


@unittest.skipUnless(TopicMapController is not None, "PySide6 is not installed in this environment")
class KnowledgeGraphCriticalJourneyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QCoreApplication.instance() or QCoreApplication([])

    @staticmethod
    def _records_and_graphs() -> tuple[list[dict], list[dict]]:
        records, graphs = [], []
        themes = [
            ("knowledge graph", "retrieval", "WikiKG", "GraphNet"),
            ("battery prognosis", "remaining useful life", "NASA Battery", "BatteryNet"),
        ]
        previous_by_theme: dict[int, str] = {}
        for index in range(8):
            theme_index = index // 4
            theme, method, dataset, model = themes[theme_index]
            record_id = f"journey-{index}"
            record = {
                "recordId": record_id, "title": f"{theme.title()} Study {index}", "year": 2017 + index,
                "keywordsText": f"{theme}; {method}; {dataset}",
                "authors": [{"name": f"Author {theme_index}", "affiliations": [{"name": f"Lab {theme_index}"}]}],
                "journalTitle": f"Journal {theme_index}",
                "references": [previous_by_theme[theme_index]] if theme_index in previous_by_theme else [],
                "localPdfPath": f"/library/{record_id}.pdf", "favoriteProjectIds": ["favorites"] if index == 0 else [],
                "inCompare": index < 2,
            }
            previous_by_theme[theme_index] = record_id
            graph = build_knowledge_graph(record)
            paper_id = f"paper:{record_id}"
            semantic = [
                ("researchquestion", "question", f"How to improve {theme}?", "ADDRESSES"),
                ("method", "method", method, "USES_METHOD"), ("model", "model", model, "USES_MODEL"),
                ("dataset", "dataset", dataset, "USES_DATASET"), ("metric", "metric", "F1", "EVALUATED_BY"),
                ("result", "result", f"Improves {theme}", "REPORTS_RESULT"),
                ("conclusion", "conclusion", f"{model} is effective", "REPORTS_RESULT"),
                ("limitation", "limitation", "Limited external validation", "LIMITS"),
            ]
            for kind, suffix, label, relation in semantic:
                node_id = f"{kind}:{record_id}:{suffix}"
                evidence = [{"record_id": record_id, "page": 0, "excerpt": label, "source": "journey_fixture"}]
                graph["nodes"].append({
                    "id": node_id, "type": kind, "label": label, "confidence": 0.92,
                    "importance": 0.8, "evidence": evidence, "extraction_method": "structured_test_source",
                })
                graph["edges"].append({
                    "id": f"journey-edge:{record_id}:{suffix}", "source": paper_id, "target": node_id,
                    "type": relation, "confidence": 0.92, "evidence": evidence,
                })
            records.append(record); graphs.append(graph)
        return records, graphs

    def test_seed_to_recommendation_share_and_semantic_comparison_journey(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            paths = FakePaths(Path(temp))
            records, graphs = self._records_and_graphs()
            topic_controller = TopicMapController(None, paths, None, None)
            for record, graph in zip(records, graphs):
                topic_controller._write(topic_controller._graph_path(record["recordId"]), graph)
            with patch("omnilit_qt.topic_map_controller.ManagedWorker", InstantWorker):
                self.assertTrue(topic_controller.generateForRecords(records))

            self.assertEqual(topic_controller.state, "ready")
            self.assertGreaterEqual(len(topic_controller.topics), 2)
            self.assertTrue(topic_controller.evolution["events"])
            self.assertTrue(topic_controller.networkAnalysis["paperMetrics"])
            self.assertTrue(topic_controller.researchNetwork["recommendations"])

            topic = topic_controller.topics[0]
            self.assertTrue(topic_controller.selectTopic(topic["id"]))
            local_graph = topic_controller.topicGraph(topic["id"], topic["paperIds"])
            self.assertTrue(local_graph.get("nodes"))
            graph_controller = KnowledgeGraphController(None, paths, None, None)
            self.assertTrue(graph_controller.loadTopicGraph(local_graph))
            paper = next(item for item in local_graph["nodes"] if item["type"] == "paper")
            topic_node = next(item for item in local_graph["nodes"] if item["type"] == "topic")
            graph_controller.setPathStart(paper["id"])
            graph_controller.setPathEnd(topic_node["id"])
            self.assertTrue(graph_controller.computeShortestPath())
            year = str((paper.get("details") or {}).get("year") or "")
            graph_controller.setFacetFilter("year", year)
            self.assertEqual(graph_controller.facetFilters.get("year"), year)

            view_id = graph_controller.saveView("Critical journey", {"displayStyle": "focus", "graphScale": 1.3})
            self.assertTrue(view_id)
            package_path = graph_controller.exportSharePackage("Critical journey", {"displayStyle": "focus"})
            self.assertTrue(Path(package_path).is_file())
            imported = KnowledgeGraphController(None, paths, None, None)
            self.assertTrue(imported.importSharePackage(package_path))
            self.assertEqual(imported.savedViews[0]["name"], "Critical journey")

            self.assertTrue(topic_controller.startEvolutionPlayback())
            while topic_controller.advanceEvolutionPlayback():
                pass
            evolution_graph = topic_controller.evolutionGraph()
            self.assertTrue(evolution_graph.get("metadata", {}).get("evolution_graph"))
            analysis_graph = topic_controller.networkAnalysisGraph("core")
            self.assertTrue(analysis_graph.get("metadata", {}).get("network_analysis_graph"))
            reading_graph = topic_controller.researchNetworkGraph("reading")
            self.assertTrue(reading_graph.get("metadata", {}).get("research_network_graph"))

            comparison = build_semantic_comparison(graphs[:3], records[:3])
            self.assertEqual(comparison["diagnostics"]["paperCount"], 3)
            self.assertEqual(comparison["diagnostics"]["dimensionCount"], 9)
            self.assertTrue(all(paper["presentDimensionCount"] >= 7 for paper in comparison["papers"]))
