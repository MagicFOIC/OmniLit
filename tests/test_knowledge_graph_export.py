from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from omnilit_qt.knowledge_graph_builder import build_document
from omnilit_qt.knowledge_graph_export import export_csv, export_markdown, export_mermaid


class KnowledgeGraphExportTests(unittest.TestCase):
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
