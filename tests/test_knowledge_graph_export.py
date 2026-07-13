from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from omnilit_qt.knowledge_graph_builder import build_document
from omnilit_qt.knowledge_graph_compare import compare_graph_dicts
from omnilit_qt.knowledge_graph_export import export_csv, export_markdown, export_mermaid
from omnilit_qt.knowledge_graph_schema import KnowledgeGraphDocument


class KnowledgeGraphExportTests(unittest.TestCase):
    def test_comparison_markdown_contains_semantic_matrix_provenance(self) -> None:
        first = build_document("p1", {"title": "One", "keywordsText": "graph"}).to_dict()
        second = build_document("p2", {"title": "Two", "keywordsText": "battery"}).to_dict()
        document = KnowledgeGraphDocument.from_dict(compare_graph_dicts([first, second]))
        with tempfile.TemporaryDirectory() as temp:
            output = export_markdown(document, Path(temp) / "comparison.md", comparison=True).read_text(encoding="utf-8")
        self.assertIn("ORKG 语义比较矩阵", output)
        self.assertIn("未识别（不等于不存在）", output)
        self.assertIn("自动抽取", output)

    def test_markdown_mermaid_and_csv_exports(self) -> None:
        document = build_document("p1", {"title": "Paper", "keywordsText": "graph"})
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            markdown = export_markdown(document, root / "graph.md")
            mermaid = export_mermaid(document, root / "graph.mmd")
            nodes_csv, edges_csv = export_csv(document, root / "nodes.csv", root / "edges.csv")
            self.assertIn("# Paper", markdown.read_text(encoding="utf-8"))
            self.assertIn("graph LR", mermaid.read_text(encoding="utf-8"))
            self.assertTrue(nodes_csv.is_file())
            self.assertTrue(edges_csv.is_file())
