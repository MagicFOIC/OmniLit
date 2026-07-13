from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from omnilit_qt.knowledge_graph_image_export import (
    PNG_SIGNATURE,
    export_manifest,
    is_valid_png,
    normalize_export_options,
    sanitize_export_stem,
    unique_export_path,
    validate_export_dimensions,
)


class KnowledgeGraphImageExportTests(unittest.TestCase):
    def test_filename_and_options_are_cross_platform_safe(self) -> None:
        self.assertEqual(sanitize_export_stem(' Graph: A/B? '), "Graph_ A_B")
        self.assertEqual(normalize_export_options("bad", 9, 1), {"scope": "viewport", "scale": 4.0, "transparent": True})

    def test_dimensions_reject_unsafe_exports(self) -> None:
        self.assertEqual(validate_export_dimensions(800, 600, 2)[2], (1600, 1200))
        self.assertFalse(validate_export_dimensions(9000, 9000, 2)[0])
        self.assertFalse(validate_export_dimensions("bad", 10, 1)[0])

    def test_unique_path_png_validation_and_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            first = unique_export_path(root, "Graph")
            first.write_bytes(PNG_SIGNATURE + b"payload")
            second = unique_export_path(root, "Graph")

            self.assertTrue(is_valid_png(first))
            self.assertEqual(second.name, "Graph-2.png")
            manifest = export_manifest(first, "p1", {"scope": "full", "scale": 2, "transparent": False}, "fp")
            self.assertEqual((manifest["recordId"], manifest["scope"], manifest["fileName"]), ("p1", "full", "Graph.png"))


if __name__ == "__main__":
    unittest.main()
