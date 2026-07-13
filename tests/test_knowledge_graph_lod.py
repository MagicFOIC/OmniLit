from __future__ import annotations

import time
import unittest

from omnilit_qt.knowledge_graph_lod import (
    MAX_RENDER_NODES,
    RENDER_BUDGETS,
    normalize_render_viewport,
    project_render_graph,
    render_budget,
    render_level,
)
from tests.knowledge_graph_benchmarks import BENCHMARK_SIZES, make_lod_benchmark


class KnowledgeGraphLodTests(unittest.TestCase):
    def test_viewport_and_level_inputs_are_bounded(self) -> None:
        viewport = normalize_render_viewport({"width": "bad", "height": -1, "scale": 99, "panX": float("inf")})
        self.assertEqual((viewport["width"], viewport["height"], viewport["scale"], viewport["panX"]), (960.0, 1.0, 8.0, 0.0))
        self.assertEqual(render_level(0.5, 5000), "overview")
        self.assertEqual(render_level(1.0, 5000), "normal")
        self.assertEqual(render_level(2.0, 5000), "detail")
        self.assertLessEqual(render_budget(2.0, 100_000), MAX_RENDER_NODES)

    def test_small_graph_preserves_real_nodes_and_edges(self) -> None:
        nodes, edges, layout = make_lod_benchmark(100)
        result = project_render_graph(nodes, edges, layout, {"width": 900, "height": 600, "scale": 1})
        self.assertEqual(len(result["nodes"]), 100)
        self.assertFalse(any(node.get("aggregate") for node in result["nodes"]))
        self.assertEqual(len(result["layout"]), 100)
        self.assertFalse(result["status"]["degraded"])

    def test_overview_aggregates_within_budget_and_preserves_pins(self) -> None:
        nodes, edges, layout = make_lod_benchmark(5_000)
        nodes[123]["confidence"] = "unknown"
        nodes[456]["importance"] = None
        edges[100]["confidence"] = "unknown"
        result = project_render_graph(
            nodes, edges, layout,
            {"width": 1000, "height": 700, "scale": 0.5},
            pinned_node_ids={"node:4321", "node:4999"},
            pinned_edge_ids={"edge:chain:4999"},
        )
        node_ids = {node["id"] for node in result["nodes"]}
        self.assertIn("node:4321", node_ids)
        self.assertIn("node:4999", node_ids)
        self.assertLessEqual(len(result["nodes"]), RENDER_BUDGETS["overview"])
        self.assertGreater(result["status"]["aggregateNodes"], 0)
        self.assertGreater(result["status"]["aggregatedNodes"], 0)
        self.assertTrue(result["status"]["degraded"])
        self.assertTrue(all(edge["source"] in node_ids and edge["target"] in node_ids for edge in result["edges"]))

    def test_zoomed_view_culls_offscreen_nodes_deterministically(self) -> None:
        nodes, edges, layout = make_lod_benchmark(1_000)
        viewport = {"width": 900, "height": 600, "scale": 3.0, "panX": 0, "panY": 0, "overscan": 20}
        first = project_render_graph(nodes, edges, layout, viewport)
        second = project_render_graph(nodes, edges, layout, viewport)
        self.assertGreater(first["status"]["culledNodes"], 0)
        self.assertEqual([node["id"] for node in first["nodes"]], [node["id"] for node in second["nodes"]])
        shifted = project_render_graph(nodes, edges, layout, {**viewport, "panX": 700})
        self.assertNotEqual({node["id"] for node in first["nodes"]}, {node["id"] for node in shifted["nodes"]})

        overview = project_render_graph(nodes, edges, layout, viewport, layout_style="overview")
        self.assertFalse(overview["status"]["spatialCulling"])
        self.assertEqual(overview["status"]["viewportCandidates"], 1_000)

    def test_fixed_scale_benchmarks_stay_within_projection_budgets(self) -> None:
        time_limits = {100: 0.20, 1_000: 0.50, 5_000: 1.50, 10_000: 3.00}
        for size in BENCHMARK_SIZES:
            with self.subTest(size=size):
                nodes, edges, layout = make_lod_benchmark(size)
                started = time.perf_counter()
                result = project_render_graph(nodes, edges, layout, {"width": 1280, "height": 800, "scale": 0.6})
                elapsed = time.perf_counter() - started
                self.assertLess(elapsed, time_limits[size])
                expected_budget = size if size <= 180 else RENDER_BUDGETS["overview"]
                self.assertLessEqual(len(result["nodes"]), expected_budget)
                self.assertLessEqual(len(result["edges"]), max(400, expected_budget * 3))


if __name__ == "__main__":
    unittest.main()
