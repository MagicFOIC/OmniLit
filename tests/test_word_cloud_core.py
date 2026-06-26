from __future__ import annotations

import unittest

from omnilit_qt.word_cloud_core import build_word_cloud, extract_phrases


class WordCloudCoreTests(unittest.TestCase):
    def test_english_bigrams_and_trigrams_bind_back_to_graph_nodes(self) -> None:
        graph = {"recordId": "p1", "nodes": [{
            "id": "method:p1:rag", "type": "method", "label": "RAG pipeline",
            "importance": 0.9, "confidence": 0.9, "tags": [],
            "evidence": [{"page": 1, "excerpt": "Knowledge graph systems use retrieval augmented generation with a graph neural network.", "record_id": "p1"}],
        }]}
        cloud = build_word_cloud([graph], "record", "Paper", 80)
        by_normalized = {item["normalized"]: item for item in cloud["terms"]}
        for phrase in ("knowledge graph", "retrieval augmented generation", "graph neural network"):
            self.assertIn(phrase, by_normalized)
            self.assertEqual(by_normalized[phrase]["primaryNodeId"], "method:p1:rag")
            self.assertEqual(by_normalized[phrase]["category"], "Method")
        self.assertTrue(all(item["nodeIds"] and item["nodeRefs"] for item in cloud["terms"]))

    def test_optional_chinese_tokenizer_adds_domain_phrases(self) -> None:
        calls = []

        def tokenizer(text: str) -> list[str]:
            calls.append(text)
            return ["电池退化预测", "跨域迁移"]

        graph = {"recordId": "zh", "nodes": [{
            "id": "method:zh:1", "type": "method", "label": "时序框架",
            "importance": 0.8, "confidence": 0.8,
            "evidence": [{"page": 0, "excerpt": "该框架用于电池退化预测与跨域迁移。", "record_id": "zh"}],
        }]}
        cloud = build_word_cloud([graph], "record", "论文", 40, chinese_tokenizer=tokenizer)
        normalized = {item["normalized"] for item in cloud["terms"]}
        self.assertTrue(calls)
        self.assertTrue({"电池退化预测", "跨域迁移"}.issubset(normalized))

    def test_formula_reference_and_header_noise_is_downweighted(self) -> None:
        normal = {"recordId": "p1", "nodes": [{
            "id": "method:1", "type": "method", "label": "Pipeline", "importance": 0.8,
            "evidence": [{"excerpt": "Robust retrieval pipeline improves ranking quality.", "source": "extraction_index.pages"}],
        }]}
        noisy = {"recordId": "p1", "nodes": [{
            "id": "method:1", "type": "method", "label": "Pipeline", "importance": 0.8,
            "source_section": "References",
            "evidence": [{"excerpt": "Robust retrieval pipeline improves ranking quality.", "source": "formula.header"}],
        }]}
        normal_terms = {item["normalized"]: item for item in build_word_cloud([normal], "record", "Paper", 80)["terms"]}
        noisy_terms = {item["normalized"]: item for item in build_word_cloud([noisy], "record", "Paper", 80)["terms"]}
        phrase = "retrieval pipeline improves"
        self.assertGreater(normal_terms[phrase]["weight"], noisy_terms[phrase]["weight"] * 5)

    def test_local_chinese_phrase_fallback_knows_core_terms(self) -> None:
        phrases = extract_phrases("知识图谱结合大语言模型完成关系抽取。")
        self.assertTrue({"知识图谱", "大语言模型", "关系抽取"}.issubset(set(phrases)))

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
