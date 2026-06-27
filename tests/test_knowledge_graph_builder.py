from __future__ import annotations

import json
import unittest
import time
from pathlib import Path

from omnilit_qt.knowledge_graph_builder import BUILDER_VERSION, build_document


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "knowledge_graph"


def load_golden_fixture(stem: str) -> tuple[dict, dict]:
    extraction = json.loads((FIXTURE_DIR / f"{stem}.extraction.json").read_text(encoding="utf-8"))
    expected = json.loads((FIXTURE_DIR / f"{stem}.expected_graph.json").read_text(encoding="utf-8"))
    return extraction, expected


class KnowledgeGraphBuilderTests(unittest.TestCase):
    def test_golden_fixtures_extract_required_nodes_and_entities(self) -> None:
        for stem in ("sample_paper_01", "sample_paper_02"):
            with self.subTest(stem=stem):
                fixture, expected = load_golden_fixture(stem)
                record = fixture["record"]
                document = build_document(record["recordId"], record, fixture["extraction_index"])
                node_types = {node.type for node in document.nodes}
                self.assertTrue(set(expected["required_node_types"]).issubset(node_types))
                for entity in expected["entities"]:
                    matches = [
                        node for node in document.nodes
                        if node.type == entity["type"] and node.label == entity["canonical_label"]
                    ]
                    self.assertEqual(len(matches), entity["expected_count"], entity)
                    self.assertGreaterEqual(len(matches[0].evidence), entity["minimum_evidence"])

    def test_builds_sections_claims_and_locatable_elements(self) -> None:
        index = {
            "engine": "pymupdf",
            "pages": [{"page": 1, "textBlocks": [
                {"blockNo": 1, "text": "Methods", "bbox": [10, 10, 100, 30]},
                {"blockNo": 2, "text": "We propose a transformer framework for robust prediction.", "bbox": [10, 40, 300, 80]},
                {"blockNo": 3, "text": "Results show that the model improves accuracy by 5 percent.", "bbox": [10, 90, 300, 130]},
            ]}],
            "elements": [{"id": "fig-1", "type": "figure", "page": 1, "bbox": [20, 150, 300, 400], "caption": "Model architecture"}],
        }
        document = build_document("p1", {"title": "Paper", "keywordsText": "transformer"}, index)
        types = {node.type for node in document.nodes}
        self.assertTrue({"paper", "section", "contribution", "result", "figure"}.issubset(types))
        figure = next(node for node in document.nodes if node.type == "figure")
        self.assertEqual(figure.evidence[0].element_id, "fig-1")
        self.assertEqual(figure.evidence[0].page, 1)
        self.assertGreater(document.metadata["stats"]["evidence"], 0)
        relations = {edge.type for edge in document.edges}
        self.assertIn("ACHIEVES", relations)
        self.assertIn("SUPPORTS", relations)
        self.assertTrue(all(edge.relation_evidence for edge in document.edges if edge.type in {"ACHIEVES", "SUPPORTS", "MEASURED_BY"}))
        self.assertNotIn("proximity_rule", {edge.relation_method for edge in document.edges})

    def test_metadata_only_degrades_gracefully(self) -> None:
        document = build_document("p1", {"title": "Graph Learning", "abstract": "A graph model."}, None)
        self.assertEqual(document.nodes[0].type, "paper")
        self.assertTrue(any(node.type == "concept" for node in document.nodes))

    def test_metadata_summary_builds_real_semantic_categories_and_citations(self) -> None:
        summary = (
            "We propose a transformer method for the battery degradation problem. "
            "The experiment and evaluation use a public benchmark dataset with accuracy. "
            "Results show improved accuracy over Smith et al., 2022. "
            "A limitation is the small evaluation cohort and future work should expand it."
        )
        document = build_document("p1", {"title": "Paper", "contentSummary": summary}, None)
        types = {node.type for node in document.nodes}
        expected = {"section", "method", "experiment", "dataset", "metric", "result", "citation", "limitation", "futurework"}
        self.assertTrue(expected.issubset(types))
        semantic = [node for node in document.nodes if node.type not in {"paper", "section", "concept"}]
        self.assertTrue(all(node.evidence and node.evidence[0].excerpt for node in semantic))
        self.assertTrue(any(edge.type == "CITES" for edge in document.edges))

    def test_repeated_page_headers_are_removed_and_false_contribution_is_rejected(self) -> None:
        pages = []
        for page in range(5):
            pages.append({"page": page, "height": 800, "textBlocks": [
                {"blockNo": 0, "text": "Journal of Example Research", "bbox": [10, 10, 300, 28]},
                {"blockNo": 1, "text": "Previous work proposes a model for this problem.", "bbox": [20, 100, 400, 140]},
            ]})
        document = build_document("p1", {"title": "Paper"}, {"pages": pages})
        self.assertFalse(any("Journal of Example" in evidence.excerpt for node in document.nodes for evidence in node.evidence))
        self.assertFalse(any(node.type == "contribution" for node in document.nodes))

    def test_chinese_semantic_types_have_evidence_and_layout(self) -> None:
        index = {"pages": [{"page": 0, "height": 800, "textBlocks": [
            {"blockNo": 1, "text": "本文提出一种新框架，解决现有方法的瓶颈问题。", "bbox": [20, 80, 500, 120]},
            {"blockNo": 2, "text": "实验在公开数据集上评估，准确率提升了百分之五。", "bbox": [20, 140, 500, 180]},
            {"blockNo": 3, "text": "该方法仍存在推理延迟较高的局限，未来工作将优化效率。", "bbox": [20, 200, 500, 240]},
        ]}]}
        document = build_document("zh", {"title": "中文论文"}, index)
        types = {node.type for node in document.nodes}
        self.assertTrue({"contribution", "experiment", "dataset", "metric", "limitation"}.issubset(types))
        self.assertTrue(all(node.evidence for node in document.nodes if node.type not in {"paper"}))
        payload = document.to_dict()
        self.assertEqual(payload["builder_version"], BUILDER_VERSION)
        self.assertEqual(set(payload["layout"]), {node.id for node in document.nodes})
        self.assertGreater(payload["quality_summary"]["evidence_coverage"], 0.9)
        self.assertEqual(payload["metadata"]["pipeline"], [
            "precision_section_filter", "entity_candidates", "canonical_normalization",
            "relation_candidates", "confidence_scoring", "quality_validation",
        ])

    def test_hundred_page_rule_build_stays_within_budget(self) -> None:
        pages = [{"page": page, "height": 800, "textBlocks": [{"blockNo": 1, "text": "We evaluate the model on a benchmark dataset and accuracy improves by five percent.", "bbox": [20, 80, 500, 120]}]} for page in range(100)]
        started = time.perf_counter()
        build_document("large", {"title": "Large"}, {"pages": pages})
        self.assertLess(time.perf_counter() - started, 2.0)
