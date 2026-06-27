from __future__ import annotations

import unittest

from omnilit_qt.knowledge_graph_extractor import EntityCandidate
from omnilit_qt.knowledge_graph_normalizer import normalize_candidates
from omnilit_qt.knowledge_graph_schema import KnowledgeGraphEvidence


def candidate(record_id: str, ordinal: int, label: str, confidence: float = 0.82) -> EntityCandidate:
    evidence = KnowledgeGraphEvidence(
        page=1,
        element_id=f"b{ordinal}",
        excerpt=f"{label} evidence",
        source="test",
        record_id=record_id,
        section="Method",
        extraction_method="rule",
    )
    return EntityCandidate(
        id=f"candidate:{record_id}:{ordinal}",
        record_id=record_id,
        kind="method",
        label=label,
        text=f"{label} evidence",
        evidence=[evidence],
        confidence=confidence,
        confidence_reason=["test"],
        extraction_method="rule",
        source_section="Method",
        page=1,
        block_id=f"b{ordinal}",
        sentence_index=ordinal,
        origin="pdf",
    )


class KnowledgeGraphNormalizerPrecisionTests(unittest.TestCase):
    def test_large_language_model_acronym_merges_with_llm(self) -> None:
        entities = normalize_candidates([
            candidate("p1", 1, "Large Language Model (LLM)"),
            candidate("p1", 2, "LLM"),
        ])
        self.assertEqual(len(entities), 1)
        self.assertEqual(entities[0].label, "LLM")
        self.assertEqual(len(entities[0].evidence), 2)

    def test_generic_label_is_not_high_confidence_core_node(self) -> None:
        entity = normalize_candidates([candidate("p1", 1, "model", confidence=0.95)])[0]
        node = entity.to_node()
        self.assertLess(node.confidence, 0.6)
        self.assertTrue(node.needs_review)
        self.assertIn("generic_label", node.review_reasons)

    def test_different_record_ids_do_not_merge(self) -> None:
        entities = normalize_candidates([
            candidate("p1", 1, "AtlasNet"),
            candidate("p2", 1, "AtlasNet"),
        ])
        self.assertEqual(len(entities), 2)
        self.assertEqual({entity.record_id for entity in entities}, {"p1", "p2"})

    def test_merge_preserves_all_evidence(self) -> None:
        entity = normalize_candidates([
            candidate("p1", 1, "LLM"),
            candidate("p1", 2, "large language model"),
        ])[0]
        self.assertEqual({item.element_id for item in entity.evidence}, {"b1", "b2"})


if __name__ == "__main__":
    unittest.main()
