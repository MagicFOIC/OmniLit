from __future__ import annotations

import unittest

from omnilit_qt.word_cloud_core import build_word_cloud


class WordCloudCoreTests(unittest.TestCase):
    def test_aliases_stopwords_and_layout_are_deterministic(self) -> None:
        graph = {"recordId": "p1", "source_fingerprint": "abc", "nodes": [
            {"id": "c1", "type": "metric", "label": "Acc", "importance": 0.8, "confidence": 0.9, "tags": [], "evidence": [{"page": 1, "excerpt": "Accuracy improves", "record_id": "p1"}]},
            {"id": "c2", "type": "metric", "label": "Accuracy", "importance": 0.7, "confidence": 0.9, "tags": [], "evidence": []},
            {"id": "c3", "type": "concept", "label": "the", "importance": 1.0, "confidence": 1.0, "tags": [], "evidence": []},
        ]}
        first = build_word_cloud([graph], "record", "Paper", 80)
        second = build_word_cloud([graph], "record", "Paper", 80)
        self.assertEqual(first["terms"], second["terms"])
        self.assertEqual(first["cacheKey"], second["cacheKey"])
        normalized = [item["normalized"] for item in first["terms"]]
        self.assertIn("accuracy", normalized)
        self.assertNotIn("the", normalized)
        accuracy = next(item for item in first["terms"] if item["normalized"] == "accuracy")
        self.assertGreaterEqual(accuracy["count"], 2)

    def test_word_rectangles_do_not_overlap(self) -> None:
        graph = {"recordId": "p1", "nodes": [{"id": f"c{i}", "type": "concept", "label": f"keyword{i}", "importance": 1 - i / 100, "confidence": 1.0, "tags": ["keyword"], "evidence": []} for i in range(40)]}
        cloud = build_word_cloud([graph], "record", "Paper", 80)
        rects = []
        for item in cloud["terms"]:
            rect = (item["x"] - item["width"] / 2, item["y"] - item["height"] / 2, item["x"] + item["width"] / 2, item["y"] + item["height"] / 2)
            self.assertFalse(any(rect[0] < other[2] and rect[2] > other[0] and rect[1] < other[3] and rect[3] > other[1] for other in rects))
            rects.append(rect)
