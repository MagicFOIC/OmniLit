from __future__ import annotations

import time
import unittest

from omnilit_qt.knowledge_graph_evolution import build_evolution
from omnilit_qt.knowledge_graph_network_analysis import build_network_analysis, build_network_analysis_graph
from omnilit_qt.knowledge_graph_topics import build_topic_map, extract_feature_documents


def fixture(size: int = 12) -> tuple[list[dict], list[dict]]:
    graphs = []
    records = []
    for index in range(size):
        cluster = index % 3
        record_id = f"p{index}"
        references = []
        if index >= 3:
            references = [f"p{cluster}", f"p{(cluster + 1) % 3}"]
        graph = {
            "recordId": record_id,
            "paper": {"title": f"Paper {index}", "year": str(2015 + index % 8)},
            "nodes": [
                {"id": f"paper:{record_id}", "type": "paper", "label": f"Paper {index}", "importance": 1.0},
                {"id": f"concept:{record_id}", "type": "concept", "label": f"domain topic {cluster}", "importance": 0.9, "confidence": 1.0},
                {"id": f"method:{record_id}", "type": "method", "label": "shared emerging method" if index >= size // 2 else "legacy method", "importance": 0.8, "confidence": 1.0},
            ],
            "edges": [], "metadata": {"summary": {"keywords": [f"domain topic {cluster}"]}},
        }
        record = {"recordId": record_id, "title": f"Paper {index}", "year": 2015 + index % 8, "references": references}
        graphs.append(graph); records.append(record)
    return graphs, records


class KnowledgeGraphNetworkAnalysisTests(unittest.TestCase):
    def test_feature_documents_keep_sources_and_are_deterministic(self) -> None:
        graphs, records = fixture()
        first = extract_feature_documents(graphs, records)
        second = extract_feature_documents(list(reversed(graphs)), list(reversed(records)))
        self.assertEqual(first, second)
        self.assertTrue(first[0]["features"])
        self.assertTrue(first[0]["features"][0]["sources"])

    def test_structural_analysis_is_explainable_and_directionally_correct(self) -> None:
        graphs, records = fixture()
        topic_map = build_topic_map(graphs, records)
        evolution = build_evolution(topic_map, graphs, records)
        result = build_network_analysis(topic_map, evolution, graphs, records)

        reversed_result = build_network_analysis(topic_map, evolution, list(reversed(graphs)), list(reversed(records)))
        self.assertEqual(result["cacheKey"], reversed_result["cacheKey"])
        self.assertEqual(result["keywordNetwork"], reversed_result["keywordNetwork"])
        self.assertGreater(result["coverage"]["citationLinkCount"], 0)
        self.assertTrue(result["coCitation"]["links"])
        self.assertTrue(result["coupling"]["links"])
        self.assertTrue(result["keywordNetwork"]["nodes"])
        self.assertTrue(result["keywordNetwork"]["links"])
        self.assertTrue(result["corePapers"])
        self.assertTrue(result["bridgePapers"])
        self.assertTrue(result["topicTrends"])
        self.assertTrue(result["methods"]["core"])
        self.assertTrue(all(item["explanation"] for item in result["coCitation"]["links"]))
        coupling = next(item for item in result["coupling"]["links"] if item["source"] == "p3" and item["target"] == "p6")
        self.assertEqual(coupling["sharedReferences"], 2)
        cocitation = next(item for item in result["coCitation"]["links"] if item["source"] == "p0" and item["target"] == "p1")
        self.assertGreaterEqual(cocitation["sharedCiters"], 1)

    def test_sparse_inputs_report_coverage_without_inventing_links(self) -> None:
        graphs, records = fixture(1)
        topic_map = build_topic_map(graphs, records)
        evolution = build_evolution(topic_map, graphs, records)
        result = build_network_analysis(topic_map, evolution, graphs, records)
        self.assertEqual(result["coCitation"]["links"], [])
        self.assertEqual(result["coupling"]["links"], [])
        self.assertTrue(result["coverage"]["warnings"])
        self.assertFalse(build_network_analysis_graph({}, "core"))
        graph = build_network_analysis_graph(result, "core")
        self.assertTrue(graph["metadata"]["network_analysis_graph"])
        self.assertEqual(graph["metadata"]["quality_summary"]["node_count"], 1)

    def test_fixed_scales_stay_sparse_and_bounded(self) -> None:
        limits = {100: 0.5, 1_000: 1.5, 5_000: 5.0, 10_000: 10.0}
        for size in (100, 1_000, 5_000, 10_000):
            with self.subTest(size=size):
                graphs, records = fixture(size)
                topic_map = {
                    "cacheKey": f"topic-{size}",
                    "assignments": [{"recordId": f"p{index}", "topicId": f"t{index % 3}"} for index in range(size)],
                    "citationLinks": [
                        {"source": f"p{index}", "target": f"p{index % 3}"}
                        for index in range(3, size)
                    ],
                }
                evolution = {
                    "cacheKey": f"evolution-{size}",
                    "papers": [{"recordId": f"p{index}", "title": f"Paper {index}", "year": 2015 + index % 8} for index in range(size)],
                }
                started = time.perf_counter()
                result = build_network_analysis(topic_map, evolution, graphs, records)
                self.assertLess(time.perf_counter() - started, limits[size])
                self.assertLessEqual(len(result["keywordNetwork"]["nodes"]), 120)
                self.assertLessEqual(len(result["keywordNetwork"]["links"]), 480)
                self.assertEqual(len(result["paperMetrics"]), size)


if __name__ == "__main__":
    unittest.main()
