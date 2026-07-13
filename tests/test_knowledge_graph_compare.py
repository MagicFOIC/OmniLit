from __future__ import annotations

import unittest

from omnilit_qt.knowledge_graph_builder import build_document
from omnilit_qt.knowledge_graph_compare import compare_documents, compare_graph_dicts
from omnilit_qt.knowledge_graph_schema import KnowledgeGraphDocument, KnowledgeGraphEvidence, KnowledgeGraphNode


class KnowledgeGraphCompareTests(unittest.TestCase):
    def test_graph_dict_comparison_contains_orkg_matrix_contract(self) -> None:
        first = build_document("p1", {"title": "One", "keywordsText": "graph"}).to_dict()
        second = build_document("p2", {"title": "Two", "keywordsText": "graph"}).to_dict()
        result = compare_graph_dicts([first, second])
        semantic = result["metadata"]["semantic_comparison"]
        self.assertEqual(len(semantic["papers"]), 2)
        self.assertEqual([item["key"] for item in semantic["dimensions"]], [
            "problem", "method", "model", "dataset", "metric", "result", "contribution", "limitation", "futurework",
        ])

    def test_common_and_missing_information_are_marked(self) -> None:
        first = build_document("p1", {"title": "One", "keywordsText": "graph"})
        second = build_document("p2", {"title": "Two", "keywordsText": "graph"})
        compared = compare_documents([first, second])
        common = [node for node in compared.nodes if node.details.get("common")]
        missing = [node for node in compared.nodes if node.type == "missinginfo"]
        self.assertTrue(common)
        self.assertTrue(missing)
        self.assertTrue(any(edge.type == "SAME_AS" for edge in compared.edges))
        self.assertTrue(all(node.evidence for node in common))

    def test_similar_methods_and_opposite_results_keep_bilateral_evidence(self) -> None:
        def document(record_id: str, method: str, result: str) -> KnowledgeGraphDocument:
            evidence = KnowledgeGraphEvidence(page=1, excerpt=result, record_id=record_id)
            return KnowledgeGraphDocument(
                record_id=record_id,
                paper={"title": record_id},
                nodes=[
                    KnowledgeGraphNode(f"paper:{record_id}", "paper", record_id),
                    KnowledgeGraphNode(f"method:{record_id}", "method", method, evidence=[evidence]),
                    KnowledgeGraphNode(f"result:{record_id}", "result", result, summary=result, evidence=[evidence]),
                ],
            )

        compared = compare_documents([
            document("p1", "deep transformer encoder model", "Accuracy improves on the shared benchmark"),
            document("p2", "deep transformer encoder architecture", "Accuracy does not improve on the shared benchmark"),
        ])
        self.assertTrue(any(edge.type == "SIMILAR_TO" for edge in compared.edges))
        conflict = next(edge for edge in compared.edges if edge.type == "CONTRADICTS")
        self.assertEqual({item.record_id for item in conflict.evidence}, {"p1", "p2"})
