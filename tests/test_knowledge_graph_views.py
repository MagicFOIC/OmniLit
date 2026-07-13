from __future__ import annotations

import unittest

from omnilit_qt.knowledge_graph_views import make_snapshot, normalize_snapshot, normalize_viewport, reconcile_snapshot


class KnowledgeGraphViewSnapshotTests(unittest.TestCase):
    def test_viewport_values_are_bounded_and_unknown_layout_falls_back(self) -> None:
        viewport = normalize_viewport({"displayStyle": "unknown", "graphScale": 99, "focusDepth": -4, "panX": "bad"})

        self.assertEqual(viewport["displayStyle"], "overview")
        self.assertEqual(viewport["graphScale"], 2.5)
        self.assertEqual(viewport["focusDepth"], 0)
        self.assertEqual(viewport["panX"], 0.0)

    def test_legacy_keys_are_normalized_to_current_version(self) -> None:
        snapshot = normalize_snapshot({
            "record_id": "p1", "name": " Legacy ", "created_at": "2025-01-01T00:00:00Z",
            "exploration": {"nodeIds": ["paper:p1", "paper:p1"], "pages": {"paper:p1|all": 2}},
        }, "p1")

        self.assertEqual(snapshot["version"], 2)
        self.assertEqual(snapshot["name"], "Legacy")
        self.assertEqual(snapshot["exploration"]["nodeIds"], ["paper:p1"])

    def test_facet_filters_are_normalized_and_saved(self) -> None:
        snapshot = normalize_snapshot({
            "recordId": "p1", "filters": {"facets": {"year": "2024", "author": "Ada", "unknown": "drop"}},
        }, "p1")
        self.assertEqual(snapshot["filters"]["facets"], {"year": "2024", "author": "Ada"})

    def test_reconcile_drops_stale_ids_and_selection_without_rejecting_view(self) -> None:
        snapshot = make_snapshot(
            "p1", "Research", "old", {"nodeIds": ["paper:p1", "missing"], "edgeIds": ["e1", "gone"]},
            {"mode": "method"}, {"nodeId": "missing", "edgeId": "gone"}, {"graphScale": 1.4},
            path={"startId": "paper:p1", "endId": "missing", "directed": True, "relationFilter": "CITES"},
        )
        graph = {
            "recordId": "p1", "nodes": [{"id": "paper:p1"}],
            "edges": [{"id": "e1", "source": "paper:p1", "target": "paper:p1"}],
        }

        restored, report = reconcile_snapshot(snapshot, graph)

        self.assertEqual(restored["exploration"]["nodeIds"], ["paper:p1"])
        self.assertEqual(restored["exploration"]["edgeIds"], ["e1"])
        self.assertEqual(restored["selection"], {"nodeId": "", "edgeId": ""})
        self.assertEqual(restored["path"], {"startId": "paper:p1", "endId": "", "directed": True, "relationFilter": "CITES"})
        self.assertEqual(report, {"missingNodes": 1, "missingEdges": 1})


if __name__ == "__main__":
    unittest.main()
