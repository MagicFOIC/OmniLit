from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from omnilit_qt.knowledge_graph_share import build_share_package, load_share_package, write_share_package


class KnowledgeGraphShareTests(unittest.TestCase):
    def setUp(self) -> None:
        self.graph = {
            "recordId": "p1", "title": "Paper", "source_fingerprint": "fingerprint",
            "nodes": [
                {"id": "paper:p1", "type": "paper", "label": "Paper"},
                {"id": "result:r", "type": "result", "label": "Result"},
            ],
            "edges": [{"id": "e1", "source": "paper:p1", "target": "result:r", "type": "ACHIEVES"}],
        }
        self.view = {
            "recordId": "p1", "name": "Shared view",
            "exploration": {"nodeIds": ["paper:p1", "result:r"], "edgeIds": ["e1"]},
            "filters": {"mode": "result"}, "viewport": {"displayStyle": "radial", "graphScale": 1.4},
        }

    def test_round_trip_is_versioned_integrity_checked_and_canonicalized(self) -> None:
        package = build_share_package(self.graph, self.view)
        with tempfile.TemporaryDirectory() as temp:
            path = write_share_package(Path(temp) / "view.omnilit-graph.json", package)
            graph, view, metadata = load_share_package(path)
        self.assertEqual(metadata["kind"], "omnilit.knowledge-graph-share")
        self.assertEqual(metadata["version"], 1)
        self.assertEqual(graph["edges"][0]["type"], "REPORTS_RESULT")
        self.assertEqual(view["filters"]["mode"], "result")
        self.assertEqual(view["viewport"]["displayStyle"], "radial")

    def test_modified_package_is_rejected(self) -> None:
        package = build_share_package(self.graph, self.view)
        package["graph"]["title"] = "Tampered"
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "tampered.json"
            path.write_text(json.dumps(package), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "完整性"):
                load_share_package(path)
