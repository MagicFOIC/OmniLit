from __future__ import annotations

import time
import unittest

from omnilit_qt.knowledge_graph_semantic_comparison import build_semantic_comparison, clear_review, make_review


def graph(record_id: str, nodes: list[dict]) -> dict:
    return {
        "recordId": record_id, "paper": {"title": f"Paper {record_id}", "year": 2024},
        "nodes": [{"id": f"paper:{record_id}", "type": "paper", "label": record_id}, *nodes], "edges": [],
    }


def node(record_id: str, kind: str, label: str, confidence: float = 0.9) -> dict:
    return {
        "id": f"{kind}:{record_id}:{label}", "type": kind, "label": label, "confidence": confidence,
        "needs_review": confidence < 0.6, "review_reasons": ["low_confidence"] if confidence < 0.6 else [],
        "extraction_method": "rule", "source_section": kind.title(),
        "evidence": [{"record_id": record_id, "page": 1, "bbox": [1, 2, 3, 4], "excerpt": label}],
    }


class SemanticComparisonTests(unittest.TestCase):
    def fixture(self):
        return [
            graph("p1", [node("p1", "problem", "How to improve retrieval"), node("p1", "method", "Graph transformer"), node("p1", "dataset", "Dataset A"), node("p1", "metric", "F1"), node("p1", "result", "F1 improves on benchmark")]),
            graph("p2", [node("p2", "researchgap", "Retrieval remains weak"), node("p2", "method", "Graph transformer", 0.55), node("p2", "dataset", "Dataset B"), node("p2", "result", "F1 does not improve on benchmark")]),
        ]

    def test_matrix_preserves_evidence_confidence_missing_and_conflicts(self) -> None:
        result = build_semantic_comparison(self.fixture())
        self.assertEqual(len(result["dimensions"]), 9)
        self.assertEqual(len(result["papers"]), 2)
        p1 = result["papers"][0]
        method = next(item for item in p1["cells"] if item["dimension"] == "method")
        self.assertEqual(method["status"], "present")
        self.assertEqual(method["evidenceCount"], 1)
        self.assertEqual(method["items"][0]["source"], "automatic_extraction")
        limitation = next(item for item in p1["cells"] if item["dimension"] == "limitation")
        self.assertEqual(limitation["status"], "missing")
        self.assertIn("不表示", limitation["explanation"])
        p2_method = next(item for item in result["papers"][1]["cells"] if item["dimension"] == "method")
        self.assertTrue(p2_method["needsReview"])
        self.assertTrue(result["conflicts"])

    def test_human_review_overlays_but_does_not_destroy_automatic_items(self) -> None:
        review = make_review({}, "method", "replace", "Human corrected method", "verified from appendix", "method:p2")
        result = build_semantic_comparison(self.fixture(), reviews={"p2": review})
        cell = next(item for item in result["papers"][1]["cells"] if item["dimension"] == "method")
        self.assertEqual(cell["status"], "reviewed")
        self.assertEqual(cell["items"][0]["label"], "Human corrected method")
        self.assertEqual(cell["items"][0]["source"], "human_review")
        self.assertEqual(cell["automaticItems"][0]["label"], "Graph transformer")
        restored = clear_review(review, "method")
        self.assertFalse(restored["revisions"])
        with self.assertRaises(ValueError):
            make_review({}, "method", "replace", "")

    def test_order_is_deterministic_and_large_node_sets_are_linear(self) -> None:
        first = build_semantic_comparison(self.fixture())
        second = build_semantic_comparison(list(reversed(self.fixture())))
        self.assertEqual(first["cacheKey"], second["cacheKey"])
        self.assertEqual(first["papers"], second["papers"])
        limits = {100: 0.1, 1_000: 0.25, 5_000: 0.8, 10_000: 1.5}
        for size in (100, 1_000, 5_000, 10_000):
            with self.subTest(size=size):
                nodes = [node("scale", "method" if index % 2 else "dataset", f"Item {index}") for index in range(size)]
                started = time.perf_counter()
                result = build_semantic_comparison([graph("scale", nodes)])
                self.assertLess(time.perf_counter() - started, limits[size])
                self.assertEqual(result["diagnostics"]["automaticItemCount"], 16)


if __name__ == "__main__":
    unittest.main()
