from __future__ import annotations

import unittest
import time

from omnilit_qt.knowledge_graph_literature import project_literature_rows


class KnowledgeGraphLiteratureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.graph = {
            "recordId": "p1",
            "paper": {"title": "Seed Paper", "authors": ["Ada"], "year": "2024", "source": "Graph Journal"},
            "nodes": [
                {"id": "paper:p1", "type": "paper", "label": "Seed", "importance": 1.0, "details": {}},
                {"id": "citation:a", "type": "citation", "label": "Smith et al., 2021", "importance": 0.8, "evidence": [{"excerpt": "Smith et al., 2021"}]},
                {"id": "citation:b", "type": "citation", "label": "Brown et al., 2019", "importance": 0.6, "details": {"citationCount": 42}},
                {"id": "method:m", "type": "method", "label": "Transformer", "importance": 0.9},
            ],
            "edges": [
                {"id": "e1", "source": "paper:p1", "target": "citation:a", "type": "CITES"},
                {"id": "e2", "source": "paper:p1", "target": "citation:b", "type": "CITES"},
            ],
        }

    def test_projects_only_visible_papers_and_citations_with_metadata(self) -> None:
        rows = project_literature_rows(self.graph, {"paper:p1", "citation:a", "method:m"})

        self.assertEqual({row["nodeId"] for row in rows}, {"paper:p1", "citation:a"})
        paper = next(row for row in rows if row["kind"] == "paper")
        citation = next(row for row in rows if row["kind"] == "citation")
        self.assertEqual((paper["title"], paper["authors"], paper["year"]), ("Seed Paper", "Ada", "2024"))
        self.assertEqual(citation["year"], "2021")

    def test_sorting_and_query_relevance_are_deterministic(self) -> None:
        rows = project_literature_rows(self.graph, sort_key="citations", descending=True)
        self.assertEqual(rows[0]["nodeId"], "citation:b")

        searched = project_literature_rows(self.graph, query="Smith", sort_key="relevance", descending=True)
        self.assertEqual(searched[0]["nodeId"], "citation:a")

    def test_selection_and_hover_are_projected_for_bidirectional_linking(self) -> None:
        rows = project_literature_rows(self.graph, selected_node_id="citation:a", hovered_node_id="paper:p1")

        self.assertTrue(next(row for row in rows if row["nodeId"] == "citation:a")["selected"])
        self.assertTrue(next(row for row in rows if row["nodeId"] == "paper:p1")["hovered"])

    def test_comparison_paper_keeps_original_record_identity(self) -> None:
        graph = {
            "recordId": "comparison-x", "paper": {"title": "Comparison"},
            "nodes": [{
                "id": "paper:p2", "type": "paper", "label": "Second",
                "details": {"title": "Second", "paper_ids": ["p2"]},
            }],
            "edges": [],
        }

        rows = project_literature_rows(graph)

        self.assertEqual(rows[0]["recordId"], "p2")
        self.assertEqual(rows[0]["title"], "Second")

    def test_ten_thousand_row_projection_stays_within_interaction_budget(self) -> None:
        graph = {
            "recordId": "comparison-large",
            "nodes": [
                {
                    "id": f"paper:{index}", "type": "paper", "label": f"Paper {index}",
                    "importance": (index % 100) / 100,
                    "details": {"year": str(2000 + index % 25), "authors": ["Author"]},
                }
                for index in range(10_000)
            ],
            "edges": [],
        }

        started = time.perf_counter()
        rows = project_literature_rows(graph, sort_key="relevance", descending=True)

        self.assertEqual(len(rows), 10_000)
        self.assertLess(time.perf_counter() - started, 0.75)


if __name__ == "__main__":
    unittest.main()
