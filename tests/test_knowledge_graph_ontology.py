from __future__ import annotations

import unittest

from omnilit_qt.knowledge_graph_builder import build_document
from omnilit_qt.knowledge_graph_ontology import MINIMUM_RELATIONS, RELATION_CONFIG, canonical_relation_type
from omnilit_qt.knowledge_graph_schema import KnowledgeGraphDocument


class KnowledgeGraphOntologyTests(unittest.TestCase):
    def test_minimum_relation_contract_is_centralized(self) -> None:
        self.assertTrue(set(MINIMUM_RELATIONS).issubset(RELATION_CONFIG))
        self.assertEqual(canonical_relation_type("USES", "paper", "model"), "USES_MODEL")
        self.assertEqual(canonical_relation_type("EVALUATES_ON", "method", "dataset"), "USES_DATASET")
        self.assertEqual(canonical_relation_type("MEASURED_BY", "result", "metric"), "EVALUATED_BY")
        self.assertEqual(canonical_relation_type("ACHIEVES", "paper", "result"), "REPORTS_RESULT")

    def test_old_edge_types_migrate_with_original_type_preserved(self) -> None:
        document = KnowledgeGraphDocument.from_dict({
            "recordId": "legacy", "paper": {"title": "Legacy"},
            "nodes": [
                {"id": "paper:legacy", "type": "paper", "label": "Legacy"},
                {"id": "problem:x", "type": "researchquestion", "label": "Problem"},
                {"id": "model:x", "type": "model", "label": "Model"},
                {"id": "result:x", "type": "result", "label": "Result"},
            ],
            "edges": [
                {"source": "paper:legacy", "target": "problem:x", "type": "PROPOSES"},
                {"source": "paper:legacy", "target": "model:x", "type": "USES"},
                {"source": "paper:legacy", "target": "result:x", "type": "ACHIEVES"},
            ],
        })
        self.assertEqual([item.type for item in document.edges], ["ADDRESSES", "USES_MODEL", "REPORTS_RESULT"])
        self.assertEqual([item.details["legacyRelationType"] for item in document.edges], ["PROPOSES", "USES", "ACHIEVES"])

    def test_extraction_emits_formal_semantic_entities_and_relations(self) -> None:
        index = {"pages": [{"page": 0, "height": 800, "textBlocks": [
            {"blockNo": 1, "text": "Methods", "bbox": [20, 50, 200, 70]},
            {"blockNo": 2, "text": "We use the AtlasNet model and graph method on the OpenImages dataset.", "bbox": [20, 80, 520, 110]},
            {"blockNo": 3, "text": "This study addresses the retrieval problem and evaluates accuracy.", "bbox": [20, 130, 520, 160]},
            {"blockNo": 4, "text": "Results show accuracy improves by 12 percent.", "bbox": [20, 180, 520, 210]},
            {"blockNo": 5, "text": "Conclusion", "bbox": [20, 230, 200, 250]},
            {"blockNo": 6, "text": "In conclusion, the model improves robust retrieval.", "bbox": [20, 270, 520, 300]},
            {"blockNo": 7, "text": "We extend Smith et al. 2020 and improve on their method.", "bbox": [20, 320, 520, 350]},
        ]}]}
        document = build_document("formal", {"title": "Formal Ontology"}, index)
        node_types = {item.type for item in document.nodes}
        relation_types = {item.type for item in document.edges}
        self.assertTrue({"researchquestion", "method", "model", "dataset", "metric", "result", "conclusion"}.issubset(node_types))
        self.assertTrue({
            "ADDRESSES", "USES_METHOD", "USES_MODEL", "USES_DATASET", "EVALUATED_BY",
            "REPORTS_RESULT", "CITES", "EXTENDS", "IMPROVES_ON",
        }.issubset(relation_types))
        self.assertTrue(all(item.label for item in document.edges))


if __name__ == "__main__":
    unittest.main()
