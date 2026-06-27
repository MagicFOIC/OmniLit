from __future__ import annotations

import unittest

from omnilit_qt.knowledge_graph_extractor import extract_entity_candidates
from omnilit_qt.knowledge_graph_normalizer import normalize_candidates
from omnilit_qt.knowledge_graph_relation_extractor import extract_relation_candidates


def relations_for(index: dict) -> list:
    candidates, _ = extract_entity_candidates("p1", {"recordId": "p1"}, index)
    return extract_relation_candidates("p1", normalize_candidates(candidates))


class KnowledgeGraphRelationPrecisionTests(unittest.TestCase):
    def test_same_sentence_with_cue_is_retained(self) -> None:
        relations = relations_for({"pages": [{"page": 1, "textBlocks": [
            {"blockNo": 1, "text": "Methods"},
            {"blockNo": 2, "text": "We use AtlasNet on the OpenImages dataset.", "bbox": [1, 2, 3, 4]},
        ]}]})
        pair = [item for item in relations if item.relation_type == "EVALUATES_ON" and item.relation_method == "same_sentence"]
        self.assertTrue(pair)

    def test_same_block_with_evidence_is_retained(self) -> None:
        relations = relations_for({"pages": [{"page": 1, "textBlocks": [
            {"blockNo": 1, "text": "Methods"},
            {"blockNo": 2, "text": "We propose the AtlasNet method. The same paragraph evaluates AtlasNet on the OpenImages dataset.", "bbox": [1, 2, 3, 4]},
        ]}]})
        pair = [item for item in relations if item.relation_type == "EVALUATES_ON" and item.relation_method == "same_block"]
        self.assertTrue(pair)
        self.assertTrue(pair[0].evidence[0].excerpt)

    def test_same_section_without_cue_is_not_linked(self) -> None:
        relations = relations_for({"pages": [{"page": 1, "textBlocks": [
            {"blockNo": 1, "text": "Methods"},
            {"blockNo": 2, "text": "We use a temporal transformer model for prediction.", "bbox": [1, 2, 3, 4]},
            {"blockNo": 3, "text": "The OpenImages dataset contains labels.", "bbox": [1, 5, 3, 8]},
        ]}]})
        self.assertFalse(any(item.relation_type == "EVALUATES_ON" and item.relation_method == "same_section" for item in relations))

    def test_relation_evidence_and_direction_reason_are_required(self) -> None:
        relations = relations_for({"pages": [{"page": 1, "textBlocks": [
            {"blockNo": 1, "text": "Results"},
            {"blockNo": 2, "text": "Results show accuracy improved by 12%.", "bbox": [1, 2, 3, 4]},
        ]}]})
        semantic = [item for item in relations if item.relation_type == "MEASURED_BY" and item.source_id.startswith("result:")]
        self.assertTrue(semantic)
        for relation in semantic:
            self.assertTrue(relation.evidence)
            self.assertTrue(any(item.excerpt for item in relation.evidence))
            self.assertTrue(relation.direction_reason)
            self.assertTrue(relation.source_id.startswith("result:"))
            self.assertTrue(relation.target_id.startswith("metric:"))


if __name__ == "__main__":
    unittest.main()
