from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import patch

from omnilit_qt import knowledge_graph_builder
from omnilit_qt.knowledge_graph_builder import build_document, cache_is_fresh, node_is_visible_at_density


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "knowledge_graph"
CORE_TYPES = {"method", "dataset", "metric", "result", "limitation", "futurework"}
EVIDENCE_EXEMPT_TYPES = {"paper", "section", "metadata"}


def golden_cases():
    for extraction_path in sorted(FIXTURE_DIR.glob("*.extraction.json")):
        stem = extraction_path.name.removesuffix(".extraction.json")
        fixture = json.loads(extraction_path.read_text(encoding="utf-8"))
        expected = json.loads((FIXTURE_DIR / f"{stem}.expected_graph.json").read_text(encoding="utf-8"))
        record = fixture["record"]
        yield stem, fixture, expected, build_document(record["recordId"], record, fixture["extraction_index"])


class KnowledgeGraphQualityTests(unittest.TestCase):
    def test_core_nodes_and_edges_are_grounded(self) -> None:
        for stem, _, expected, document in golden_cases():
            with self.subTest(stem=stem):
                core_nodes = [node for node in document.nodes if node.type in CORE_TYPES]
                self.assertTrue(core_nodes)
                self.assertTrue(all(node.evidence and any(item.excerpt or item.source for item in node.evidence) for node in core_nodes))
                self.assertTrue(all(node.evidence for node in document.nodes if node.type not in EVIDENCE_EXEMPT_TYPES))
                self.assertTrue(all(edge.evidence or edge.details.get("source") for edge in document.edges))
                quality = document.metadata["quality_summary"]
                self.assertGreaterEqual(quality["evidence_coverage"], expected["minimum_evidence_coverage"])
                self.assertGreaterEqual(quality["edge_evidence_coverage"], expected["minimum_edge_evidence_coverage"])
                self.assertGreater(quality["edge_evidence_coverage"], 0)

    def test_low_confidence_nodes_are_marked_for_review(self) -> None:
        for stem, _, expected, document in golden_cases():
            with self.subTest(stem=stem):
                low_confidence = [node for node in document.nodes if node.confidence < 0.6]
                self.assertTrue(all("needs_review" in node.tags for node in low_confidence))
                self.assertTrue(all(node.needs_review for node in low_confidence))
                actual_types = {node.type for node in low_confidence}
                self.assertTrue(set(expected["needs_review_types"]).issubset(actual_types))
                self.assertGreaterEqual(document.metadata["quality_summary"]["needs_review_count"], len(low_confidence))
                self.assertEqual(document.metadata["quality_summary"]["needs_review_count"], len([node for node in document.nodes if node.type != "paper" and node.needs_review]))

    def test_every_node_and_edge_has_provenance(self) -> None:
        for stem, _, _, document in golden_cases():
            with self.subTest(stem=stem):
                for node in document.nodes:
                    self.assertTrue(node.normalized_label, node.id)
                    self.assertTrue(node.canonical_id, node.id)
                    self.assertIn(node.extraction_method, {"rule", "section", "metadata", "llm", "merged"})
                    self.assertTrue(node.confidence_reason, node.id)
                for edge in document.edges:
                    self.assertTrue(edge.normalized_label, edge.id)
                    self.assertTrue(edge.canonical_id, edge.id)
                    self.assertIn(edge.extraction_method, {"rule", "section", "metadata", "llm", "merged"})
                    self.assertTrue(edge.confidence_reason, edge.id)
                    self.assertIn(edge.relation_method, {"metadata", "section", "caption", "direct_extraction", "same_sentence", "same_block", "same_section", "merged"})
                    self.assertTrue(edge.relation_evidence, edge.id)
                    self.assertTrue(edge.direction_reason, edge.id)
                    self.assertNotEqual(edge.relation_method, "proximity_rule")

    def test_normal_and_compact_contract_excludes_low_confidence_nodes(self) -> None:
        _, _, _, document = next(golden_cases())
        for density in ("normal", "compact"):
            visible = [node for node in document.nodes if node_is_visible_at_density(node.to_dict(), density)]
            self.assertFalse(any(node.confidence < 0.6 for node in visible), density)
        low_confidence = next(node for node in document.nodes if node.confidence < 0.6)
        self.assertTrue(node_is_visible_at_density(low_confidence.to_dict(), "detailed"))
        self.assertTrue(node_is_visible_at_density(low_confidence.to_dict(), "normal", "benchmark"))
        reviewed = {"type": "method", "confidence": 0.9, "needs_review": True}
        self.assertFalse(node_is_visible_at_density(reviewed, "normal"))

    def test_builder_version_change_invalidates_cache(self) -> None:
        _, fixture, _, document = next(golden_cases())
        cached = document.to_dict()
        self.assertTrue(cache_is_fresh(cached, fixture["record"], fixture["extraction_index"]))
        with patch.object(knowledge_graph_builder, "BUILDER_VERSION", cached["builder_version"] + 1):
            self.assertFalse(cache_is_fresh(cached, fixture["record"], fixture["extraction_index"]))


if __name__ == "__main__":
    unittest.main()
