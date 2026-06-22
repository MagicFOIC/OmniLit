from __future__ import annotations

import unittest

from omnilit_qt.knowledge_graph_schema import KnowledgeGraphDocument, KnowledgeGraphEdge, KnowledgeGraphEvidence, KnowledgeGraphNode


class KnowledgeGraphSchemaTests(unittest.TestCase):
    def test_document_round_trip_preserves_evidence(self) -> None:
        evidence = KnowledgeGraphEvidence(page=2, bbox=[1, 2, 3, 4], element_id="el-1", excerpt="supporting text", record_id="p1")
        document = KnowledgeGraphDocument(
            record_id="p1",
            paper={"title": "Paper"},
            nodes=[KnowledgeGraphNode("paper:p1", "paper", "Paper"), KnowledgeGraphNode("method:p1:1", "method", "Method", evidence=[evidence])],
            edges=[KnowledgeGraphEdge("e1", "paper:p1", "method:p1:1", "PROPOSES", evidence=[evidence])],
        )
        restored = KnowledgeGraphDocument.from_dict(document.to_dict())
        self.assertEqual(restored.schema_version, 1)
        self.assertEqual(restored.nodes[1].evidence[0].element_id, "el-1")
        self.assertEqual(restored.edges[0].evidence[0].page, 2)

    def test_legacy_graph_can_be_loaded(self) -> None:
        restored = KnowledgeGraphDocument.from_dict({"version": 1, "recordId": "old", "title": "Old", "nodes": [{"id": "paper:old", "type": "paper", "label": "Old", "details": {}}], "edges": []})
        self.assertEqual(restored.record_id, "old")
        self.assertEqual(restored.paper["title"], "Old")
