from __future__ import annotations

import unittest

from omnilit_qt.knowledge_graph_builder import build_document
from omnilit_qt.knowledge_graph_extractor import extract_entity_candidates, section_aware_text_blocks


class KnowledgeGraphExtractorPrecisionTests(unittest.TestCase):
    def test_heading_detection_supports_english_chinese_and_references_filter(self) -> None:
        index = {"pages": [{"page": 1, "height": 800, "textBlocks": [
            {"blockNo": 1, "text": "1. Introduction", "bbox": [20, 80, 300, 110]},
            {"blockNo": 2, "text": "This study addresses a difficult prediction problem.", "bbox": [20, 130, 520, 160]},
            {"blockNo": 3, "text": "2 方法", "bbox": [20, 190, 300, 220]},
            {"blockNo": 4, "text": "本文提出一种图神经网络方法，并在公开数据集上评估。", "bbox": [20, 240, 520, 280]},
            {"blockNo": 5, "text": "References", "bbox": [20, 320, 300, 350]},
            {"blockNo": 6, "text": "Smith et al. 2020 proposed a benchmark dataset.", "bbox": [20, 370, 520, 400]},
        ]}]}
        blocks = section_aware_text_blocks(index)
        self.assertEqual([block.section for block in blocks if block.is_heading], ["Introduction", "Method", "References"])
        candidates, _ = extract_entity_candidates("p1", {"recordId": "p1"}, index)
        excerpts = " ".join(evidence.excerpt for item in candidates for evidence in item.evidence)
        self.assertNotIn("Smith et al.", excerpts)

    def test_numeric_result_generic_label_and_limitation_context(self) -> None:
        index = {"pages": [{"page": 1, "height": 800, "textBlocks": [
            {"blockNo": 1, "text": "Results", "bbox": [20, 80, 300, 110]},
            {"blockNo": 2, "text": "Results show F1 = 0.91 and accuracy improved by 12%.", "bbox": [20, 130, 520, 160]},
            {"blockNo": 3, "text": "Methods", "bbox": [20, 190, 300, 220]},
            {"blockNo": 4, "text": "We use the model for several prediction tasks.", "bbox": [20, 240, 520, 280]},
            {"blockNo": 5, "text": "Limitations", "bbox": [20, 310, 300, 340]},
            {"blockNo": 6, "text": "A limitation is that the method cannot improve recall on small cohorts.", "bbox": [20, 360, 560, 390]},
        ]}]}
        candidates, _ = extract_entity_candidates("p1", {"recordId": "p1"}, index)
        self.assertIn("result", {item.kind for item in candidates})
        self.assertIn("model", {item.kind for item in candidates})
        generic = [item for item in candidates if item.label.casefold() == "model"]
        self.assertTrue(generic)
        self.assertTrue(generic[0].needs_review)
        limitation_texts = [item.text for item in candidates if item.kind == "limitation"]
        result_texts = [item.text for item in candidates if item.kind == "result"]
        self.assertTrue(any("cannot improve recall" in text for text in limitation_texts))
        self.assertFalse(any("cannot improve recall" in text for text in result_texts))

    def test_every_core_node_has_evidence(self) -> None:
        document = build_document("p1", {"recordId": "p1", "title": "Paper"}, {"pages": [{"page": 1, "height": 800, "textBlocks": [
            {"blockNo": 1, "text": "Methods", "bbox": [20, 80, 300, 110]},
            {"blockNo": 2, "text": "We propose AtlasNet and evaluate it on the OpenImages dataset.", "bbox": [20, 130, 520, 160]},
            {"blockNo": 3, "text": "Results show accuracy improved by 12%.", "bbox": [20, 190, 520, 220]},
        ]}]})
        for node in document.nodes:
            if node.type not in {"paper", "section"}:
                self.assertTrue(node.evidence, node.id)
                self.assertTrue(node.evidence[0].excerpt, node.id)
                self.assertTrue(node.evidence[0].source, node.id)


if __name__ == "__main__":
    unittest.main()
