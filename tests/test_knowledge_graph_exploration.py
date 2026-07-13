from __future__ import annotations

import unittest

from omnilit_qt.knowledge_graph_exploration import neighbor_page, neighbor_summary, seed_node_ids


class KnowledgeGraphExplorationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.graph = {
            "nodes": [
                {"id": "paper:p", "type": "paper", "label": "Paper", "importance": 1.0},
                {"id": "paper:r1", "type": "paper", "label": "Reference 1", "importance": 0.9},
                {"id": "paper:r2", "type": "paper", "label": "Reference 2", "importance": 0.8},
                {"id": "paper:c1", "type": "paper", "label": "Citing paper", "importance": 0.7},
                {"id": "author:a", "type": "author", "label": "Ada", "importance": 0.6},
                {"id": "topic:t", "type": "topic", "label": "Graphs", "importance": 0.5},
            ],
            "edges": [
                {"id": "e1", "source": "paper:p", "target": "paper:r1", "type": "CITES"},
                {"id": "e2", "source": "paper:p", "target": "paper:r2", "type": "CITES"},
                {"id": "e3", "source": "paper:c1", "target": "paper:p", "type": "CITES"},
                {"id": "e4", "source": "author:a", "target": "paper:p", "type": "AUTHOR_OF"},
                {"id": "e5", "source": "paper:p", "target": "topic:t", "type": "HAS_TOPIC"},
            ],
        }

    def test_directional_citation_modes_and_pagination(self) -> None:
        first = neighbor_page(self.graph, "paper:p", "references", 0, 1)
        second = neighbor_page(self.graph, "paper:p", "references", first["nextOffset"], 1)

        self.assertEqual(first["nodeIds"], ["paper:r1"])
        self.assertTrue(first["hasMore"])
        self.assertEqual(second["nodeIds"], ["paper:r2"])
        self.assertFalse(second["hasMore"])
        self.assertEqual(neighbor_page(self.graph, "paper:p", "cited_by")["nodeIds"], ["paper:c1"])

    def test_summary_separates_semantic_families(self) -> None:
        summary = neighbor_summary(self.graph, "paper:p")

        self.assertEqual(summary["references"], 2)
        self.assertEqual(summary["cited_by"], 1)
        self.assertEqual(summary["authors"], 1)
        self.assertEqual(summary["topics"], 1)
        self.assertEqual(summary["all"], 5)

    def test_empty_and_seed_contracts_are_explicit(self) -> None:
        empty = neighbor_page(self.graph, "author:a", "venues")

        self.assertEqual(empty["status"], "empty")
        self.assertEqual(empty["total"], 0)
        self.assertEqual(seed_node_ids(self.graph), ["paper:p"])

    def test_parallel_relations_count_one_neighbor_but_reveal_all_edges(self) -> None:
        self.graph["edges"].append({"id": "e6", "source": "paper:p", "target": "topic:t", "type": "MENTIONS"})

        page = neighbor_page(self.graph, "paper:p", "topics")

        self.assertEqual(page["total"], 1)
        self.assertEqual(page["nodeIds"], ["topic:t"])
        self.assertEqual(page["edgeIds"], ["e5", "e6"])


if __name__ == "__main__":
    unittest.main()
