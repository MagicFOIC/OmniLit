from __future__ import annotations

import unittest

from omnilit_qt.knowledge_graph_builder import BUILDER_VERSION, build_document, node_is_visible_at_density, source_fingerprint
from omnilit_qt.knowledge_graph_extractor import EntityCandidate, extract_entity_candidates, section_aware_text_blocks
from omnilit_qt.knowledge_graph_normalizer import normalize_candidates
from omnilit_qt.knowledge_graph_quality import validate_graph
from omnilit_qt.knowledge_graph_relation_extractor import extract_relation_candidates
from omnilit_qt.knowledge_graph_schema import KnowledgeGraphEdge, KnowledgeGraphEvidence, KnowledgeGraphNode


def candidate(ordinal: int, label: str, text: str) -> EntityCandidate:
    evidence = KnowledgeGraphEvidence(page=0, element_id="block-1", excerpt=text, source="test", record_id="p1")
    return EntityCandidate(
        id=f"candidate:p1:{ordinal}", record_id="p1", kind="method", label=label,
        text=text, evidence=[evidence], confidence=0.72,
        confidence_reason=["rule_pattern_match"], extraction_method="rule",
        source_section="Method", page=0, block_id="block-1", sentence_index=ordinal,
        origin="pdf",
    )


class KnowledgeGraphPipelineTests(unittest.TestCase):
    def test_section_aware_blocks_feed_candidates_without_creating_nodes(self) -> None:
        index = {"pages": [{"page": 0, "height": 800, "textBlocks": [
            {"blockNo": 1, "text": "Methods", "bbox": [10, 20, 200, 40]},
            {"blockNo": 2, "text": "We use a large language model on the MIMIC benchmark dataset.", "bbox": [10, 60, 500, 100]},
        ]}]}
        blocks = section_aware_text_blocks(index)
        candidates, _ = extract_entity_candidates("p1", {"recordId": "p1"}, index)
        self.assertEqual(blocks[1].section, "Method")
        self.assertTrue(all(item.source_section == "Method" for item in candidates))
        self.assertTrue({"method", "dataset"}.issubset({item.kind for item in candidates}))
        self.assertTrue(all(not isinstance(item, KnowledgeGraphNode) for item in candidates))

    def test_llm_aliases_merge_into_one_canonical_entity(self) -> None:
        entities = normalize_candidates([
            candidate(1, "large language model", "We use a large language model for extraction."),
            candidate(2, "LLM", "The LLM validates candidate entities."),
            candidate(3, "language model", "The language model checks relations."),
        ])
        self.assertEqual(len(entities), 1)
        entity = entities[0]
        self.assertEqual(entity.label, "LLM")
        self.assertEqual(entity.canonical_id, "method:llm")
        self.assertEqual(len(entity.evidence), 3)
        self.assertEqual(entity.extraction_method, "merged")

    def test_relations_require_explainable_context_not_page_proximity(self) -> None:
        index = {"pages": [{"page": 0, "textBlocks": [
            {"blockNo": 1, "text": "Methods"},
            {"blockNo": 2, "text": "We use a transformer model on the MIMIC benchmark dataset.", "bbox": [1, 2, 3, 4]},
            {"blockNo": 3, "text": "Results show the model improves accuracy by five percent.", "bbox": [1, 5, 3, 8]},
        ]}]}
        candidates, _ = extract_entity_candidates("p1", {"recordId": "p1"}, index)
        relations = extract_relation_candidates("p1", normalize_candidates(candidates))
        methods = {relation.relation_method for relation in relations}
        types = {relation.relation_type for relation in relations}
        self.assertIn("same_sentence", methods)
        self.assertNotIn("proximity_rule", methods)
        self.assertTrue({"USES_METHOD", "USES_DATASET", "EVALUATED_BY", "REPORTS_RESULT"}.issubset(types))
        self.assertTrue(all(relation.evidence and relation.direction_reason for relation in relations))

    def test_same_page_entities_in_different_sections_are_not_linked_by_proximity(self) -> None:
        index = {"pages": [{"page": 0, "textBlocks": [
            {"blockNo": 1, "text": "Methods"},
            {"blockNo": 2, "text": "We use a transformer model for clinical prediction.", "bbox": [1, 2, 3, 4]},
            {"blockNo": 3, "text": "Results"},
            {"blockNo": 4, "text": "The MIMIC benchmark dataset contains clinical admissions.", "bbox": [1, 5, 3, 8]},
        ]}]}
        candidates, _ = extract_entity_candidates("p1", {"recordId": "p1"}, index)
        relations = extract_relation_candidates("p1", normalize_candidates(candidates))
        semantic_links = [
            relation for relation in relations
            if relation.source_id.startswith("method:") and relation.target_id.startswith("dataset:")
        ]
        self.assertEqual(semantic_links, [])

    def test_quality_validation_quarantines_ungrounded_low_confidence_items(self) -> None:
        node = KnowledgeGraphNode("method:p1:x", "method", "Uncertain", confidence=0.4, extraction_method="rule")
        edge = KnowledgeGraphEdge("e1", "paper:p1", node.id, "USES", confidence=0.4, extraction_method="rule")
        validation = validate_graph([KnowledgeGraphNode("paper:p1", "paper", "Paper"), node], [edge])
        self.assertTrue(node.needs_review)
        self.assertTrue(edge.needs_review)
        self.assertFalse(node_is_visible_at_density(node.to_dict(), "normal"))
        self.assertEqual(validation.summary["validation_issue_count"], 2)

    def test_builder_exposes_pipeline_counts_and_current_version(self) -> None:
        document = build_document("p1", {"recordId": "p1", "title": "Paper"}, {"pages": []})
        self.assertEqual(document.metadata["builder_version"], BUILDER_VERSION)
        self.assertEqual(BUILDER_VERSION, 11)
        self.assertEqual(document.metadata["stats"]["entity_candidates"], 0)
        self.assertEqual(document.metadata["pipeline"][-1], "quality_validation")

    def test_source_fingerprint_tracks_extracted_text_changes(self) -> None:
        first = {"pages": [{"page": 0, "textBlocks": [{"blockNo": 1, "text": "First method description."}]}]}
        second = {"pages": [{"page": 0, "textBlocks": [{"blockNo": 1, "text": "Revised method description."}]}]}
        self.assertNotEqual(source_fingerprint({"recordId": "p1"}, first), source_fingerprint({"recordId": "p1"}, second))


if __name__ == "__main__":
    unittest.main()
