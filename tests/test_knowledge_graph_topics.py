from __future__ import annotations

import time
import unittest

from omnilit_qt.knowledge_graph_topics import build_topic_graph, build_topic_map


def topic_graph(record_id: str, title: str, year: int, terms: list[tuple[str, str]], references=None) -> tuple[dict, dict]:
    nodes = [{
        "id": f"paper:{record_id}", "type": "paper", "label": title,
        "importance": 1.0, "confidence": 1.0,
        "details": {"recordId": record_id, "year": year},
    }]
    for index, (kind, term) in enumerate(terms):
        nodes.append({
            "id": f"{kind}:{record_id}:{index}", "type": kind, "label": term,
            "importance": 0.8, "confidence": 0.9,
            "tags": [kind, "keyword" if index == 0 else "semantic"],
            "evidence": [{"record_id": record_id, "page": index, "excerpt": term}],
        })
    graph = {
        "recordId": record_id, "source_fingerprint": f"fp:{record_id}",
        "paper": {"title": title, "year": str(year)}, "nodes": nodes, "edges": [],
        "metadata": {"summary": {"keywords": [term for _, term in terms[:2]]}},
    }
    record = {
        "recordId": record_id, "title": title, "year": year,
        "authors": [f"Author {record_id.split('-')[0]}"],
        "keywordsText": "; ".join(term for _, term in terms[:2]),
        "references": list(references or []),
    }
    return graph, record


class KnowledgeGraphTopicTests(unittest.TestCase):
    def _fixture(self) -> tuple[list[dict], list[dict]]:
        graphs = []
        records = []
        for index in range(4):
            graph, record = topic_graph(
                f"graph-{index}", f"Graph retrieval paper {index}", 2018 + index,
                [("concept", "knowledge graph"), ("method", "retrieval augmented generation"), ("dataset", "question answering")],
                ["graph-0"] if index else [],
            )
            graphs.append(graph); records.append(record)
        for index in range(4):
            graph, record = topic_graph(
                f"battery-{index}", f"Battery prognosis paper {index}", 2016 + index * 2,
                [("concept", "battery degradation"), ("method", "remaining useful life prediction"), ("dataset", "battery cycling data")],
                ["battery-0"] if index else [],
            )
            graphs.append(graph); records.append(record)
        return graphs, records

    def test_topics_are_deterministic_explainable_and_temporal(self) -> None:
        graphs, records = self._fixture()
        first = build_topic_map(graphs, records)
        second = build_topic_map(list(reversed(graphs)), list(reversed(records)))

        self.assertEqual(first["cacheKey"], second["cacheKey"])
        self.assertEqual(first["topics"], second["topics"])
        self.assertEqual(first["assignments"], second["assignments"])
        self.assertEqual(first["analyzedPaperCount"], 8)
        self.assertGreaterEqual(first["clusterCount"], 2)
        self.assertEqual({item["recordId"] for item in first["assignments"]}, {record["recordId"] for record in records})
        names = " ".join(topic["name"].casefold() for topic in first["topics"])
        self.assertIn("knowledge graph", names)
        self.assertIn("battery degradation", names)
        for topic in first["topics"]:
            self.assertTrue(topic["representativePapers"])
            self.assertTrue(topic["representativeAuthors"])
            self.assertIn("paperCount", topic["representativeAuthors"][0])
            self.assertTrue(topic["topTerms"])
            self.assertTrue(topic["explanation"]["method"])
            self.assertIn(topic["growth"]["trend"], {"growing", "declining", "stable", "unknown"})
            self.assertGreater(topic["radius"], 0)
        self.assertTrue(all(item["reasons"] and item["topTerms"] for item in first["assignments"]))
        self.assertGreater(first["diagnostics"]["citationLinkCount"], 0)
        self.assertIn("topicLinks", first)
        self.assertEqual(first["diagnostics"]["topicSimilarityLinkCount"], len(first["topicLinks"]))
        for link in first["topicLinks"]:
            self.assertGreaterEqual(link["similarity"], 0.04)
            self.assertTrue(link["reason"])
        changed_records = [dict(item) for item in records]
        changed_records[0]["keywordsText"] += "; causal reasoning"
        self.assertNotEqual(first["cacheKey"], build_topic_map(graphs, changed_records)["cacheKey"])

    def test_topic_graph_preserves_papers_terms_and_explanations(self) -> None:
        graphs, records = self._fixture()
        topic_map = build_topic_map(graphs, records)
        selected = topic_map["topics"][0]
        graph = build_topic_graph(topic_map, selected["id"], graphs, records)

        paper_nodes = [node for node in graph["nodes"] if node["type"] == "paper"]
        term_nodes = [node for node in graph["nodes"] if node["type"] == "concept"]
        self.assertEqual(len(paper_nodes), selected["size"])
        self.assertTrue(term_nodes)
        self.assertTrue(any(node["type"] == "topic" for node in graph["nodes"]))
        self.assertTrue(any(edge["type"] == "HAS_TOPIC" for edge in graph["edges"]))
        citation = next(edge for edge in graph["edges"] if edge["type"] == "CITES")
        self.assertTrue(citation["source"].endswith("1") or citation["source"].endswith("2") or citation["source"].endswith("3"))
        self.assertTrue(citation["target"].endswith("0"))
        self.assertEqual(graph["metadata"]["topic_id"], selected["id"])
        self.assertTrue(graph["metadata"]["topic_graph"])
        self.assertEqual(set(graph["layout"]), {node["id"] for node in graph["nodes"]})
        self.assertTrue(graph["adjacency"])

    def test_sparse_and_invalid_inputs_degrade_without_inventing_assignments(self) -> None:
        self.assertEqual(build_topic_map([], [])["topics"], [])
        graph, record = topic_graph("solo", "A", 2024, [])
        graph["nodes"].append({"id": "bad", "type": "method", "label": "Unique method", "importance": "bad", "confidence": None})
        result = build_topic_map([graph, {"nodes": "bad"}], [record])
        self.assertEqual(result["analyzedPaperCount"], 1)
        self.assertEqual(len(result["topics"]), 1)
        self.assertTrue(result["topics"][0]["lowConfidence"])
        self.assertFalse(build_topic_graph(result, "missing", [graph], [record]))

    def test_fixed_collection_scales_stay_within_analysis_budget(self) -> None:
        time_limits = {100: 0.5, 1_000: 1.5, 5_000: 3.0, 10_000: 5.0}
        for size in (100, 1_000, 5_000, 10_000):
            with self.subTest(size=size):
                graphs = []
                records = []
                for index in range(size):
                    cluster = index % 10
                    graph, record = topic_graph(
                        f"p{index}", f"Paper {index} about domain {cluster}", 2000 + index % 24,
                        [("concept", f"domain topic {cluster}"), ("method", f"method family {cluster}"), ("dataset", f"shared dataset {cluster}")],
                    )
                    graphs.append(graph); records.append(record)
                started = time.perf_counter()
                result = build_topic_map(graphs, records)
                self.assertLess(time.perf_counter() - started, time_limits[size])
                self.assertEqual(result["clusterCount"], 10)
                self.assertEqual(result["analyzedPaperCount"], size)
                self.assertEqual(len(result["assignments"]), size)
                for index, topic in enumerate(result["topics"]):
                    self.assertGreaterEqual(topic["x"] - topic["radius"], 0)
                    self.assertLessEqual(topic["x"] + topic["radius"], 1)
                    for other in result["topics"][:index]:
                        self.assertGreaterEqual(
                            ((topic["x"] - other["x"]) ** 2 + (topic["y"] - other["y"]) ** 2) ** 0.5 + 1e-6,
                            topic["radius"] + other["radius"],
                        )


if __name__ == "__main__":
    unittest.main()
