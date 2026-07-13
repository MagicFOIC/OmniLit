from __future__ import annotations

import time
import unittest

from omnilit_qt.knowledge_graph_evolution import build_evolution, build_evolution_graph
from omnilit_qt.knowledge_graph_topics import build_topic_map
from tests.test_knowledge_graph_topics import topic_graph


class KnowledgeGraphEvolutionTests(unittest.TestCase):
    def _chain_fixture(self):
        graphs = []
        records = []
        for index in range(6):
            references = [f"p{index - 1}"] if index else ["p5"]  # p0 -> p5 is deliberately impossible in time.
            graph, record = topic_graph(
                f"p{index}", f"Evolution paper {index}", 2010 + index,
                [("concept", "knowledge graph"), ("method", "retrieval augmented generation")],
                references,
            )
            graphs.append(graph); records.append(record)
        return graphs, records

    def test_directed_timeline_paths_and_turning_points_are_explainable(self) -> None:
        graphs, records = self._chain_fixture()
        topic_map = build_topic_map(graphs, records)
        evolution = build_evolution(topic_map, graphs, records)

        self.assertEqual(evolution["yearRange"]["minimum"], 2010)
        self.assertEqual(evolution["yearRange"]["maximum"], 2015)
        self.assertEqual(evolution["diagnostics"]["citationCount"], 6)
        self.assertEqual(evolution["diagnostics"]["chronologyConflictCount"], 1)
        self.assertEqual(evolution["diagnostics"]["validCitationCount"], 5)
        path = evolution["keyPaths"][0]
        self.assertEqual(path["paperIds"], [f"p{index}" for index in range(6)])
        self.assertEqual(path["years"], list(range(2010, 2016)))
        self.assertIn("真实有向引文", path["explanation"])
        self.assertIn("引用了", path["edges"][0]["explanation"])
        self.assertEqual(len(evolution["events"]), 6)
        self.assertTrue(evolution["topicSeries"][0]["points"])
        nonempty_points = [point for point in evolution["topicSeries"][0]["points"] if point["count"]]
        self.assertTrue(all(point["representativePaper"]["recordId"] for point in nonempty_points))
        self.assertIn("growthSpeed", evolution["topicSeries"][0])
        self.assertTrue(any(item["type"] == "topic_emergence" for item in evolution["turningPoints"]))

    def test_evolution_is_deterministic_and_missing_years_are_explicit(self) -> None:
        graphs, records = self._chain_fixture()
        missing_graph, missing_record = topic_graph(
            "missing", "Missing year paper", None,
            [("concept", "knowledge graph"), ("method", "retrieval augmented generation")],
        )
        graphs.append(missing_graph); records.append(missing_record)
        topic_map = build_topic_map(graphs, records)
        first = build_evolution(topic_map, graphs, records)
        second = build_evolution(topic_map, list(reversed(graphs)), list(reversed(records)))
        for key in ("papers", "events", "topicSeries", "citationLinks", "keyPaths", "turningPoints", "yearRange", "diagnostics", "cacheKey"):
            self.assertEqual(first[key], second[key])
        self.assertEqual(first["yearRange"]["missingYearCount"], 1)
        self.assertEqual(first["diagnostics"]["unknownCitationYearCount"], 0)

    def test_time_window_graph_keeps_original_citation_direction(self) -> None:
        graphs, records = self._chain_fixture()
        topic_map = build_topic_map(graphs, records)
        evolution = build_evolution(topic_map, graphs, records)
        graph = build_evolution_graph(evolution, topic_map, graphs, records, 2012, 2014)

        paper_nodes = [node for node in graph["nodes"] if node["type"] == "paper"]
        citations = [edge for edge in graph["edges"] if edge["type"] == "CITES"]
        self.assertEqual(len(paper_nodes), 3)
        self.assertEqual(len(citations), 2)
        self.assertEqual(citations[0]["source"], "paper:p3")
        self.assertEqual(citations[0]["target"], "paper:p2")
        self.assertTrue(graph["metadata"]["evolution_graph"])
        self.assertTrue(any(node["type"] == "topic" for node in graph["nodes"]))
        self.assertTrue(any(edge["type"] == "HAS_TOPIC" for edge in graph["edges"]))
        self.assertEqual((graph["metadata"]["time_start"], graph["metadata"]["time_end"]), (2012, 2014))
        self.assertFalse(build_evolution_graph(evolution, topic_map, graphs, records, 1990, 1995))

    def test_same_year_paths_follow_citations_not_lexical_ids(self) -> None:
        topic_id = "topic:same-year"
        graphs = [
            {"recordId": record_id, "paper": {"title": record_id, "year": "2024"}, "nodes": [{"id": f"paper:{record_id}", "type": "paper", "label": record_id, "details": {"year": 2024}}]}
            for record_id in ("a", "z")
        ]
        topic_map = {
            "cacheKey": "same-year",
            "topics": [{"id": topic_id, "name": "Same year", "paperIds": ["a", "z"], "representativePapers": []}],
            "assignments": [{"recordId": value, "topicId": topic_id, "score": 1.0} for value in ("a", "z")],
            "citationLinks": [{"source": "a", "target": "z", "sourceTopicId": topic_id, "targetTopicId": topic_id}],
        }
        evolution = build_evolution(topic_map, graphs, [])
        self.assertEqual(evolution["keyPaths"][0]["paperIds"], ["z", "a"])

        topic_map["citationLinks"].append({"source": "z", "target": "a", "sourceTopicId": topic_id, "targetTopicId": topic_id})
        cyclic = build_evolution(topic_map, graphs, [])
        self.assertGreater(cyclic["diagnostics"]["sameYearCycleBreakCount"], 0)

    def test_split_merge_decline_signals_and_topic_speed_comparisons_are_explicit(self) -> None:
        definitions = [("a", 2010, "A"), ("b", 2012, "B"), ("c", 2012, "C"), ("d", 2013, "D")]
        graphs, records = [], []
        for record_id, year, topic_name in definitions:
            graph, record = topic_graph(record_id, f"Paper {record_id}", year, [("concept", topic_name), ("method", "shared method")])
            graphs.append(graph); records.append(record)
        topic_map = {
            "cacheKey": "lifecycle-signals",
            "topics": [
                {"id": f"topic:{name}", "name": name, "size": 1, "paperIds": [record_id], "representativePapers": [{"recordId": record_id}]}
                for record_id, _year, name in definitions
            ],
            "assignments": [
                {"recordId": record_id, "topicId": f"topic:{name}", "score": 0.9}
                for record_id, _year, name in definitions
            ],
            "citationLinks": [
                {"source": "b", "target": "a"}, {"source": "c", "target": "a"},
                {"source": "d", "target": "b"}, {"source": "d", "target": "c"},
            ],
        }
        evolution = build_evolution(topic_map, graphs, records)
        signal_types = {item["type"] for item in evolution["turningPoints"]}
        self.assertIn("topic_split_signal", signal_types)
        self.assertIn("topic_merge_signal", signal_types)
        self.assertIn("topic_decline", signal_types)
        self.assertEqual(len(evolution["topicSpeedComparisons"]), 6)
        self.assertTrue(all(item["explanation"] for item in evolution["topicSpeedComparisons"]))
        self.assertEqual(evolution["diagnostics"]["splitSignalCount"], 1)
        self.assertEqual(evolution["diagnostics"]["mergeSignalCount"], 1)

    def test_ten_thousand_paper_chain_remains_linear(self) -> None:
        size = 10_000
        topic_id = "topic:one"
        graphs = []
        assignments = []
        citations = []
        paper_ids = []
        for index in range(size):
            record_id = f"p{index:05d}"
            paper_ids.append(record_id)
            graphs.append({
                "recordId": record_id,
                "nodes": [{"id": f"paper:{record_id}", "type": "paper", "label": f"Paper {index}", "importance": 0.5, "details": {"year": 2020}}],
                "paper": {"title": f"Paper {index}", "year": "2020"},
            })
            assignments.append({"recordId": record_id, "topicId": topic_id, "score": 0.8})
            if index:
                citations.append({"source": record_id, "target": f"p{index - 1:05d}", "sourceTopicId": topic_id, "targetTopicId": topic_id, "crossTopic": False})
        topic_map = {
            "cacheKey": "benchmark", "assignments": assignments, "citationLinks": citations,
            "topics": [{"id": topic_id, "name": "Benchmark", "size": size, "paperIds": paper_ids, "representativePapers": [], "colorIndex": 0}],
        }
        started = time.perf_counter()
        evolution = build_evolution(topic_map, graphs, [])
        self.assertLess(time.perf_counter() - started, 3.0)
        self.assertEqual(evolution["diagnostics"]["validCitationCount"], size - 1)
        self.assertEqual(evolution["keyPaths"][0]["length"], size)
        self.assertEqual(evolution["yearRange"]["knownYearCount"], size)


if __name__ == "__main__":
    unittest.main()
