from __future__ import annotations

import unittest

from omnilit_qt.knowledge_graph_layout import academic_layout, adjacency_index


class KnowledgeGraphLayoutTests(unittest.TestCase):
    def test_layout_is_deterministic_layered_and_wraps_dense_layers(self) -> None:
        nodes = [{"id": "paper:p1", "type": "paper", "label": "Paper", "importance": 1.0}]
        nodes.extend({"id": f"concept:{index}", "type": "concept", "label": f"Concept {index}", "importance": 0.5} for index in range(20))
        first = academic_layout(nodes)
        second = academic_layout(nodes)
        self.assertEqual(first, second)
        self.assertLess(first["paper:p1"]["y"], first["concept:0"]["y"])
        positions = {(item["x"], item["y"]) for item in first.values()}
        self.assertEqual(len(positions), len(nodes))
        self.assertGreater(len({first[f"concept:{index}"]["y"] for index in range(20)}), 1)
        self.assertEqual(first["paper:p1"]["stage"], "paper")
        self.assertEqual(first["concept:0"]["stage"], "context")
        self.assertEqual(first["concept:0"]["type_lane"], "concept")

    def test_academic_stages_follow_paper_reasoning_order(self) -> None:
        nodes = [
            {"id": "paper", "type": "paper", "label": "Paper"},
            {"id": "problem", "type": "problem", "label": "Problem"},
            {"id": "method", "type": "method", "label": "Method"},
            {"id": "dataset", "type": "dataset", "label": "Dataset"},
            {"id": "result", "type": "result", "label": "Result"},
            {"id": "figure", "type": "figure", "label": "Figure"},
        ]
        layout = academic_layout(nodes)
        self.assertEqual([layout[node["id"]]["stage"] for node in nodes], [
            "paper", "context", "approach", "evaluation", "findings", "evidence",
        ])
        self.assertEqual([layout[node["id"]]["y"] for node in nodes], sorted(layout[node["id"]]["y"] for node in nodes))

    def test_adjacency_is_bidirectional(self) -> None:
        adjacency = adjacency_index([{"source": "a", "target": "b"}, {"source": "b", "target": "c"}])
        self.assertEqual(adjacency["b"], ["a", "c"])
