from __future__ import annotations

import time
import unittest

from omnilit_qt.knowledge_graph_paths import available_relation_types, shortest_path


class KnowledgeGraphPathTests(unittest.TestCase):
    def setUp(self) -> None:
        self.nodes = [{"id": item, "label": item.upper()} for item in ("a", "b", "c", "d")]
        self.edges = [
            {"id": "e1", "source": "a", "target": "b", "type": "CITES", "confidence": 0.9},
            {"id": "e2", "source": "b", "target": "c", "type": "USES", "confidence": 0.8},
            {"id": "e3", "source": "a", "target": "d", "type": "CITES", "confidence": 0.7},
            {"id": "e4", "source": "d", "target": "c", "type": "CITES", "confidence": 0.6},
        ]

    def test_undirected_path_returns_edges_nodes_and_explanations(self) -> None:
        result = shortest_path(self.nodes, self.edges, "c", "a")

        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["nodeIds"], ["c", "b", "a"])
        self.assertEqual(result["edgeIds"], ["e2", "e1"])
        self.assertFalse(result["steps"][0]["forward"])
        self.assertIn("逆关系方向", result["steps"][0]["explanation"])

    def test_directed_and_relation_filters_change_reachability(self) -> None:
        self.assertEqual(shortest_path(self.nodes, self.edges, "c", "a", directed=True)["status"], "no_path")
        cites = shortest_path(self.nodes, self.edges, "a", "c", directed=True, relation_types={"CITES"})
        self.assertEqual(cites["nodeIds"], ["a", "d", "c"])
        self.assertEqual(cites["edgeIds"], ["e3", "e4"])

    def test_legacy_relation_filter_and_edges_use_canonical_ontology(self) -> None:
        nodes = [{"id": "paper"}, {"id": "result"}]
        edges = [{"id": "legacy", "source": "paper", "target": "result", "type": "ACHIEVES"}]
        result = shortest_path(nodes, edges, "paper", "result", directed=True, relation_types={"ACHIEVES"})
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["steps"][0]["relationType"], "REPORTS_RESULT")
        self.assertEqual(available_relation_types(edges), ["REPORTS_RESULT"])
        self.assertEqual(available_relation_types(self.edges), ["CITES", "USES_METHOD"])

    def test_invalid_endpoints_and_no_path_have_explicit_states(self) -> None:
        self.assertEqual(shortest_path(self.nodes, self.edges, "missing", "a")["status"], "invalid")
        self.assertEqual(shortest_path(self.nodes, [], "a", "c")["status"], "no_path")

    def test_ten_thousand_node_path_stays_within_budget(self) -> None:
        count = 10_000
        nodes = [{"id": str(index)} for index in range(count)]
        edges = [{"id": f"e{index}", "source": str(index), "target": str(index + 1), "type": "NEXT"} for index in range(count - 1)]
        started = time.perf_counter()
        result = shortest_path(nodes, edges, "0", str(count - 1), directed=True)
        self.assertEqual(result["length"], count - 1)
        self.assertLess(time.perf_counter() - started, 1.0)


if __name__ == "__main__":
    unittest.main()
