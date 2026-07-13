from __future__ import annotations

import unittest
import time

from omnilit_qt.knowledge_graph_facets import facet_options, facet_visible_node_ids, paper_facets


class KnowledgeGraphFacetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.graph = {
            "nodes": [
                {"id": "paper:p1", "type": "paper", "label": "One", "details": {"year": 2024, "authors": ["Ada"], "venue": "Nature"}},
                {"id": "paper:p2", "type": "paper", "label": "Two", "details": {"year": 2023, "authors": ["Ben"], "venue": "Science"}},
                {"id": "author:ada", "type": "author", "label": "Ada"},
                {"id": "institution:lab", "type": "institution", "label": "Graph Lab"},
                {"id": "topic:kg", "type": "topic", "label": "Knowledge Graph"},
                {"id": "method:m", "type": "method", "label": "Reasoning"},
            ],
            "edges": [
                {"source": "author:ada", "target": "paper:p1", "type": "AUTHOR_OF"},
                {"source": "author:ada", "target": "institution:lab", "type": "AFFILIATED_WITH"},
                {"source": "paper:p1", "target": "topic:kg", "type": "HAS_TOPIC"},
                {"source": "paper:p1", "target": "method:m", "type": "USES_METHOD"},
            ],
        }

    def test_options_come_from_metadata_and_declared_relations(self) -> None:
        facets = paper_facets(self.graph)
        self.assertEqual(facets["paper:p1"]["institution"], {"Graph Lab"})
        self.assertEqual(facets["paper:p1"]["topic"], {"Knowledge Graph"})
        options = facet_options(self.graph)
        self.assertEqual([item["value"] for item in options["year"]], ["2024", "2023"])
        self.assertEqual(options["author"][0], {"value": "Ada", "label": "Ada", "count": 1})

    def test_combined_facets_use_intersection_and_keep_context(self) -> None:
        visible = facet_visible_node_ids(self.graph, {"year": "2024", "institution": "Graph Lab"})
        self.assertIn("paper:p1", visible)
        self.assertIn("method:m", visible)
        self.assertIn("institution:lab", visible)
        self.assertNotIn("paper:p2", visible)
        self.assertEqual(facet_visible_node_ids(self.graph, {"year": "2024", "author": "Ben"}), set())

    def test_ten_thousand_paper_facets_stay_within_interactive_budget(self) -> None:
        size = 10_000
        graph = {
            "nodes": [
                {"id": f"paper:{index}", "type": "paper", "details": {
                    "year": 2020 + index % 5, "authors": [f"Author {index % 50}"],
                    "venue": f"Venue {index % 10}", "topic": f"Topic {index % 8}",
                    "institutions": [f"Lab {index % 20}"],
                }} for index in range(size)
            ],
            "edges": [],
        }
        started = time.perf_counter()
        options = facet_options(graph)
        visible = facet_visible_node_ids(graph, {"year": "2024", "topic": "Topic 4"})
        elapsed = time.perf_counter() - started
        self.assertEqual(len(options["author"]), 50)
        self.assertEqual(len(visible), 250)
        self.assertLess(elapsed, 1.0)
