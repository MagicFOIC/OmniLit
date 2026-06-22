from __future__ import annotations

import unittest

from omnilit_qt.knowledge_graph_core import build_knowledge_graph, merge_knowledge_graphs


class KnowledgeGraphCoreTests(unittest.TestCase):
    def test_metadata_only_builds_paper_graph(self) -> None:
        graph = build_knowledge_graph({"recordId": "p1", "title": "A Paper"})
        self.assertEqual(graph["nodes"][0]["id"], "paper:p1")
        self.assertEqual(graph["source"]["extractionEngine"], "")

    def test_keywords_create_nodes_and_edges(self) -> None:
        graph = build_knowledge_graph({"recordId": "p1", "title": "A Paper", "keywordsText": "Graph; Learning; graph"})
        keywords = [node for node in graph["nodes"] if node["type"] == "keyword"]
        edges = [edge for edge in graph["edges"] if edge["type"] == "has_keyword"]
        self.assertEqual([node["label"] for node in keywords], ["Graph", "Learning"])
        self.assertEqual(len(edges), 2)
        self.assertTrue(all(edge["evidence"] == "metadata.keywordsText" for edge in edges))

    def test_extraction_elements_create_supported_nodes(self) -> None:
        index = {"engine": "pymupdf", "elements": [
            {"id": "f1", "type": "figure", "caption": "Architecture", "page": 2, "bbox": [1, 2, 3, 4]},
            {"id": "t1", "type": "table", "markdown": "|A|", "page": 3},
            {"id": "e1", "type": "formula", "latex": "x^2", "page": 4},
            {"id": "x1", "type": "paragraph"},
        ]}
        graph = build_knowledge_graph({"recordId": "p1", "title": "A Paper"}, index)
        self.assertEqual({node["type"] for node in graph["nodes"]} & {"figure", "table", "formula"}, {"figure", "table", "formula"})
        self.assertEqual({edge["type"] for edge in graph["edges"]} & {"has_figure", "has_table", "has_formula"}, {"has_figure", "has_table", "has_formula"})

    def test_fallback_extracts_keywords(self) -> None:
        graph = build_knowledge_graph({"recordId": "p1", "title": "Neural Graph Models", "abstract": "Neural models learn graph representations."})
        self.assertGreater(len(graph["summary"]["keywords"]), 0)
        self.assertLessEqual(len(graph["summary"]["keywords"]), 20)
        self.assertTrue(any(edge["evidence"] == "local_fallback" for edge in graph["edges"]))

    def test_schema_is_complete(self) -> None:
        graph = build_knowledge_graph({"recordId": "p1", "title": "A Paper"})
        for key in ("version", "recordId", "title", "generatedAt", "source", "summary", "nodes", "edges"):
            self.assertIn(key, graph)
        self.assertEqual(graph["version"], 1)

    def test_comparison_graph_merges_shared_keywords(self) -> None:
        first = build_knowledge_graph({"recordId": "p1", "title": "First", "keywordsText": "graph; battery"})
        second = build_knowledge_graph({"recordId": "p2", "title": "Second", "keywordsText": "graph; model"})
        merged = merge_knowledge_graphs([first, second], "comparison:test")

        self.assertEqual(len([node for node in merged["nodes"] if node["type"] == "paper"]), 2)
        self.assertEqual(len([node for node in merged["nodes"] if node["id"] == "keyword:graph"]), 1)
        graph_edges = [edge for edge in merged["edges"] if edge["target"] == "keyword:graph"]
        self.assertEqual({edge["source"] for edge in graph_edges}, {"paper:p1", "paper:p2"})
        self.assertEqual(merged["comparisonRecordIds"], ["p1", "p2"])


if __name__ == "__main__":
    unittest.main()
