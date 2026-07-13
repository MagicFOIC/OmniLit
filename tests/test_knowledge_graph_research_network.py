from __future__ import annotations

import time
import unittest

from omnilit_qt.knowledge_graph_research_network import build_research_network, build_research_network_graph


def fixture(size: int = 12):
    records = []
    assignments = []
    papers = []
    metrics = []
    citations = []
    for index in range(size):
        record_id = f"p{index}"
        records.append({
            "recordId": record_id, "title": f"Paper {index}", "year": 2015 + index % 9,
            "authors": [
                {"name": f"Author {index % 5}", "affiliations": [{"name": f"Institute {index % 3}"}]},
                {"name": f"Author {(index + 1) % 5}"},
            ],
            "institutions": [f"Institute {index % 3}", f"Institute {(index + 1) % 3}"],
            "favoriteProjectIds": ["read_archive"] if index == size - 1 else (["to_read"] if index == 2 else []),
            "inCompare": index == 3, "localPdfPath": f"p{index}.pdf" if index % 2 == 0 else "",
        })
        assignments.append({"recordId": record_id, "topicId": f"t{index % 3}"})
        papers.append({"recordId": record_id, "title": f"Paper {index}", "year": 2015 + index % 9, "keyScore": (index + 1) / size})
        metrics.append({"recordId": record_id, "coreScore": (size - index) / size, "bridgeScore": (index % 4) / 4, "citationIn": index % 5, "crossTopicLinks": index % 3})
        if index:
            citations.append({"source": record_id, "target": f"p{index - 1}"})
    topic_map = {
        "cacheKey": "topics", "assignments": assignments, "citationLinks": citations,
        "topics": [{"id": f"t{i}", "name": f"Topic {i}", "growth": {"trend": "growing" if i == 2 else "stable"}} for i in range(3)],
    }
    evolution = {"cacheKey": "evolution", "papers": papers}
    network = {"cacheKey": "network", "paperMetrics": metrics}
    return topic_map, evolution, network, records


class ResearchNetworkTests(unittest.TestCase):
    def test_collaboration_importance_and_affiliations_are_evidence_bounded(self) -> None:
        result = build_research_network(*fixture())
        self.assertEqual(result["coverage"]["authorCoverage"], 1.0)
        self.assertEqual(result["coverage"]["institutionCoverage"], 1.0)
        self.assertTrue(result["authorLinks"])
        self.assertTrue(all(not item["label"].startswith("{") for item in result["authors"]))
        self.assertTrue(result["institutionLinks"])
        self.assertTrue(result["affiliations"])
        self.assertTrue(result["authors"][0]["reasons"])
        self.assertTrue(result["authors"][0]["explanation"])
        self.assertTrue(result["institutions"][0]["importanceScore"])
        graph = build_research_network_graph(result, "authors")
        self.assertTrue(graph["metadata"]["research_network_graph"])
        self.assertTrue(all(edge["type"] == "COAUTHOR_WITH" for edge in graph["edges"]))

    def test_recommendations_exclude_read_archive_and_explain_real_vs_topic_transitions(self) -> None:
        result = build_research_network(*fixture())
        recommendations = result["recommendations"]
        self.assertNotIn("p11", {item["recordId"] for item in recommendations})
        self.assertTrue(all(item["reasons"] and item["explanation"] for item in recommendations))
        self.assertEqual(result["recommendationContext"]["archivedExcluded"], 1)
        path = result["readingPaths"][0]
        self.assertTrue(path["steps"])
        self.assertTrue(all(item["transition"]["type"] in {"start", "cites_previous", "cited_by_previous", "shared_topic", "cross_topic"} for item in path["steps"]))
        for step in path["steps"][1:]:
            if step["transition"]["type"] in {"shared_topic", "cross_topic"}:
                self.assertIn("不", step["transition"]["explanation"])
        graph = build_research_network_graph(result, "reading")
        self.assertEqual(graph["metadata"]["research_network_mode"], "reading")
        self.assertTrue(all(edge["type"] == "READING_NEXT" for edge in graph["edges"]))
        self.assertTrue(all(edge["direction_reason"] for edge in graph["edges"]))

    def test_missing_metadata_degrades_without_invented_affiliations(self) -> None:
        topic, evolution, network, records = fixture(2)
        records[0]["authors"] = []
        records[0]["institutions"] = []
        records[1]["authors"] = ["Solo"]
        records[1]["institutions"] = []
        result = build_research_network(topic, evolution, network, records)
        self.assertLess(result["coverage"]["authorCoverage"], 1.0)
        self.assertEqual(result["coverage"]["institutionCoverage"], 0.0)
        self.assertEqual(result["affiliations"], [])
        self.assertTrue(result["coverage"]["warnings"])

    def test_fixed_collection_scales_are_bounded(self) -> None:
        limits = {100: 0.4, 1_000: 1.0, 5_000: 4.0, 10_000: 8.0}
        for size in (100, 1_000, 5_000, 10_000):
            with self.subTest(size=size):
                started = time.perf_counter()
                result = build_research_network(*fixture(size))
                self.assertLess(time.perf_counter() - started, limits[size])
                self.assertLessEqual(len(result["authorLinks"]), 600)
                self.assertLessEqual(len(result["institutionLinks"]), 600)
                self.assertLessEqual(len(result["recommendations"]), 24)


if __name__ == "__main__":
    unittest.main()
