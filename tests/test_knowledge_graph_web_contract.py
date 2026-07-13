from __future__ import annotations

import json
from pathlib import Path
import unittest

from omnilit_qt.shared_protocol import from_shared_graph_data, validate_graph_data


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "packages" / "shared-schema" / "fixtures" / "shared-graph-v1.json"


class KnowledgeGraphWebContractTests(unittest.TestCase):
    def test_shared_fixture_has_same_counts_and_types_in_python_qml_shape(self) -> None:
        payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
        validate_graph_data(payload)
        legacy = from_shared_graph_data(payload).to_dict()
        self.assertEqual(len(legacy["nodes"]), 6)
        self.assertEqual(len(legacy["edges"]), 5)
        self.assertEqual(
            {node["type"] for node in legacy["nodes"]},
            {"paper", "citation", "author", "method", "dataset", "result"},
        )
        self.assertEqual(
            {edge["type"] for edge in legacy["edges"]},
            {"AUTHOR_OF", "USES_METHOD", "USES_DATASET", "REPORTS_RESULT", "CITES"},
        )

    def test_web_module_has_one_renderer_and_no_platform_globals(self) -> None:
        source_dir = ROOT / "packages" / "knowledge-graph" / "src"
        source = "\n".join(path.read_text(encoding="utf-8") for path in source_dir.glob("*.*") if path.suffix in {".ts", ".tsx"})
        self.assertIn("interface GraphRenderer", source)
        self.assertIn("class G6GraphRenderer", source)
        self.assertNotIn("SigmaGraphRenderer", source)
        for forbidden in ("window.qt", "window.qtBridge", "window.__TAURI__", "window.electron"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
