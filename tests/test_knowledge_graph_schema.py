from __future__ import annotations

import unittest

from omnilit_qt.knowledge_graph_schema import KnowledgeGraphDocument, KnowledgeGraphEdge, KnowledgeGraphEvidence, KnowledgeGraphNode


class KnowledgeGraphSchemaTests(unittest.TestCase):
    def test_document_round_trip_preserves_evidence(self) -> None:
        evidence = KnowledgeGraphEvidence(page=2, bbox=[1, 2, 3, 4], element_id="el-1", excerpt="supporting text", record_id="p1")
        document = KnowledgeGraphDocument(
            record_id="p1",
            paper={"title": "Paper"},
            nodes=[
                KnowledgeGraphNode("paper:p1", "paper", "Paper"),
                KnowledgeGraphNode(
                    "method:p1:1", "method", "Method", evidence=[evidence],
                    extraction_method="rule", confidence_reason=["rule_pattern_match"],
                    source_section="Method", needs_review=True,
                ),
            ],
            edges=[KnowledgeGraphEdge(
                "e1", "paper:p1", "method:p1:1", "PROPOSES", evidence=[evidence],
                extraction_method="rule", confidence_reason=["relation_from_extracted_node"],
                source_section="Method", relation_method="direct_extraction",
                relation_evidence=[evidence], direction_reason="paper is the source record",
            )],
        )
        restored = KnowledgeGraphDocument.from_dict(document.to_dict())
        self.assertEqual(restored.schema_version, 1)
        self.assertEqual(restored.nodes[1].evidence[0].element_id, "el-1")
        self.assertEqual(restored.edges[0].evidence[0].page, 2)
        self.assertEqual(restored.nodes[1].normalized_label, "method")
        self.assertEqual(restored.nodes[1].canonical_id, "method:method")
        self.assertEqual(restored.nodes[1].extraction_method, "rule")
        self.assertEqual(restored.nodes[1].confidence_reason, ["rule_pattern_match"])
        self.assertEqual(restored.nodes[1].source_section, "Method")
        self.assertTrue(restored.nodes[1].needs_review)
        self.assertEqual(restored.edges[0].relation_method, "direct_extraction")
        self.assertEqual(restored.edges[0].relation_evidence[0].element_id, "el-1")
        self.assertEqual(restored.edges[0].direction_reason, "paper is the source record")

    def test_legacy_graph_can_be_loaded(self) -> None:
        restored = KnowledgeGraphDocument.from_dict({"version": 1, "recordId": "old", "title": "Old", "nodes": [{"id": "paper:old", "type": "paper", "label": "Old", "details": {}}], "edges": []})
        self.assertEqual(restored.record_id, "old")
        self.assertEqual(restored.paper["title"], "Old")
        self.assertEqual(restored.nodes[0].normalized_label, "old")
        self.assertEqual(restored.nodes[0].canonical_id, "paper:old")
        self.assertEqual(restored.nodes[0].extraction_method, "legacy")
        self.assertEqual(restored.nodes[0].confidence_reason, ["legacy_construction"])
