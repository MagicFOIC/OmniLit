from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    from PySide6.QtCore import QCoreApplication
    from omnilit_qt.pdf_extraction_controller import PdfExtractionController
except ModuleNotFoundError:  # pragma: no cover - depends on local test runtime.
    QCoreApplication = None
    PdfExtractionController = None


@unittest.skipUnless(PdfExtractionController is not None, "PySide6 is not installed in this environment")
class PdfExtractionControllerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._qt_app = QCoreApplication.instance() or QCoreApplication([])

    def test_analysis_progress_and_cancel_prompts_are_readable_chinese(self) -> None:
        class FakePaths:
            def __init__(self, root: Path) -> None:
                self.root = root

            def data(self, *parts: str) -> Path:
                return self.root.joinpath(*parts)

        class FakeWorker:
            def __init__(self, *args, **kwargs) -> None:
                self.started = False

            def start(self) -> None:
                self.started = True

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pdf_path = root / "paper.pdf"
            pdf_path.write_bytes(b"%PDF-1.4\n")
            controller = PdfExtractionController(None, FakePaths(root), None, None)

            with patch("omnilit_qt.pdf_extraction_controller.ManagedWorker", FakeWorker):
                self.assertTrue(controller.analyzeRecordWithEngine("record-1", str(pdf_path), "fast"))

            self.assertEqual(controller.progressText, "正在后台解析 PDF...")
            self.assertEqual(controller.statusText, "正在后台解析 PDF...")
            self.assertTrue(controller.cancelAnalysis())
            self.assertEqual(controller.statusText, "正在取消 PDF 云解析...")

    def test_formula_image_export_and_copy_are_blocked_even_with_legacy_png_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            legacy_png = Path(temp) / "formula.png"
            legacy_png.write_bytes(b"legacy formula image")
            controller = PdfExtractionController(None, None, None, None)
            controller._elements = [
                {
                    "id": "formula_1",
                    "type": "formula",
                    "text": "E = mc^2",
                    "pngPath": str(legacy_png),
                }
            ]

            self.assertEqual(controller.exportElement("formula_1", "png"), "")
            self.assertIn("Formula image export is not supported", controller.statusText)
            self.assertFalse(controller.copyElementImage("formula_1"))
            self.assertIn("Formula image copy is not supported", controller.statusText)

    def test_table_and_figure_exports_still_return_existing_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            csv_path = root / "table.csv"
            json_path = root / "table.json"
            png_path = root / "figure.png"
            csv_path.write_text("a,b\n1,2\n", encoding="utf-8")
            json_path.write_text('{"rows": [["a", "b"]]}', encoding="utf-8")
            png_path.write_bytes(b"figure image")
            controller = PdfExtractionController(None, None, None, None)
            controller._elements = [
                {
                    "id": "table_1",
                    "type": "table",
                    "csvPath": str(csv_path),
                    "jsonPath": str(json_path),
                },
                {
                    "id": "figure_1",
                    "type": "figure",
                    "pngPath": str(png_path),
                },
            ]

            self.assertEqual(controller.exportElement("table_1", "csv"), str(csv_path))
            self.assertEqual(controller.exportElement("table_1", "json"), str(json_path))
            self.assertEqual(controller.exportElement("figure_1", "png"), str(png_path))

    def test_load_index_rejects_stale_source_sha(self) -> None:
        class FakePaths:
            def __init__(self, root: Path) -> None:
                self.root = root

            def data(self, *parts: str) -> Path:
                return self.root.joinpath(*parts)

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pdf_path = root / "current.pdf"
            pdf_path.write_bytes(b"current pdf bytes")
            controller = PdfExtractionController(None, FakePaths(root), None, None)
            record_id = "record-1"
            index_dir = controller._record_dir(record_id)
            index_dir.mkdir(parents=True, exist_ok=True)
            (index_dir / "extraction_index.json").write_text(
                json.dumps(
                    {
                        "version": 2,
                        "sourcePath": str(pdf_path),
                        "sourceSha256": "not-the-current-sha",
                        "engine": "pymupdf",
                        "pageCount": 1,
                        "pages": [{"page": 0, "width": 100, "height": 100}],
                        "elements": [],
                    }
                ),
                encoding="utf-8",
            )
            controller._pdf_paths[record_id] = str(pdf_path)

            self.assertFalse(controller.loadIndex(record_id))
            self.assertIn("PDF extraction index is invalid", controller.statusText)
            self.assertNotIn(record_id, controller._indexes)

    def test_empty_engine_loads_fast_cached_result_without_starting_analysis(self) -> None:
        class FakePaths:
            def __init__(self, root: Path) -> None:
                self.root = root

            def data(self, *parts: str) -> Path:
                return self.root.joinpath(*parts)

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pdf_path = root / "current.pdf"
            pdf_path.write_bytes(b"current pdf bytes")
            controller = PdfExtractionController(None, FakePaths(root), None, None)
            record_id = "record-1"
            cached_dir = controller._index_path(record_id, "fast").parent
            cached_dir.mkdir(parents=True, exist_ok=True)
            cached_index = {
                "version": 3,
                "sourcePath": str(pdf_path),
                "engine": "pymupdf",
                "pageCount": 1,
                "pages": [{"page": 0, "width": 100, "height": 100}],
                "elements": [{"id": "table_1", "type": "table", "page": 0, "bbox": [1, 2, 3, 4]}],
            }
            controller._index_path(record_id, "fast").write_text(json.dumps(cached_index), encoding="utf-8")

            with patch.object(controller, "analyzeRecordWithEngine", side_effect=AssertionError("analysis should not start")):
                self.assertTrue(controller.selectExtractionEngine(record_id, str(pdf_path), ""))

        self.assertEqual(controller.currentIndex["engine"], "pymupdf")
        self.assertEqual(controller.elements[0]["id"], "table_1")
        self.assertIn("cached extraction index", controller.statusText)

    def test_cloud_engine_ignores_legacy_cache_without_config_marker(self) -> None:
        class FakePaths:
            def __init__(self, root: Path) -> None:
                self.root = root

            def data(self, *parts: str) -> Path:
                return self.root.joinpath(*parts)

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pdf_path = root / "current.pdf"
            pdf_path.write_bytes(b"current pdf bytes")
            controller = PdfExtractionController(None, FakePaths(root), None, None)
            cached_path = controller._index_path("record-1", "mineru")
            cached_path.parent.mkdir(parents=True, exist_ok=True)
            cached_path.write_text(json.dumps({"version": 3, "sourcePath": str(pdf_path), "engine": "mineru", "pages": [], "elements": []}), encoding="utf-8")

            with patch.object(controller, "analyzeRecordWithEngine", return_value=True) as analyze:
                self.assertTrue(controller.selectExtractionEngine("record-1", str(pdf_path), "mineru"))

            analyze.assert_called_once_with("record-1", str(pdf_path), "mineru")

    def test_element_override_persists_and_survives_reanalysis(self) -> None:
        class FakePaths:
            def __init__(self, root: Path) -> None:
                self.root = root

            def data(self, *parts: str) -> Path:
                return self.root.joinpath(*parts)

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            controller = PdfExtractionController(None, FakePaths(root), None, None)
            record_id = "record-override"
            index_dir = controller._record_dir(record_id)
            index_dir.mkdir(parents=True, exist_ok=True)
            initial_index = {
                "version": 3,
                "sourcePath": "",
                "engine": "pymupdf",
                "pageCount": 1,
                "pages": [{"page": 0, "width": 100, "height": 100}],
                "elements": [
                    {
                        "id": "formula_1",
                        "type": "formula",
                        "page": 0,
                        "bbox": [1, 2, 30, 10],
                        "latex": "bad",
                        "text": "bad (1)",
                        "pngPath": "clips/formula_1.png",
                        "needsReview": True,
                        "metadata": {"formulaNumber": "1"},
                    }
                ],
            }
            controller._index_path(record_id).write_text(json.dumps(initial_index), encoding="utf-8")

            self.assertTrue(controller.loadIndex(record_id))
            self.assertTrue(
                controller.saveElementOverride(
                    "formula_1",
                    {
                        "latex": "E = mc^2",
                        "text": "E = mc^2 (1)",
                        "needsReview": False,
                        "metadata": {"formulaNumber": "1", "userNote": "corrected"},
                        "pngPath": "should-not-be-accepted.png",
                    },
                )
            )

            saved_override = json.loads((index_dir / "overrides.json").read_text(encoding="utf-8"))
            self.assertEqual(saved_override["elements"]["formula_1"]["fields"]["latex"], "E = mc^2")
            element = controller.elements[0]
            self.assertEqual(element["latex"], "E = mc^2")
            self.assertEqual(element["pngPath"], "clips/formula_1.png")
            self.assertFalse(element["needsReview"])
            self.assertTrue(element["manualOverride"])
            self.assertTrue(element["metadata"]["manualOverride"])
            self.assertEqual(element["metadata"]["userNote"], "corrected")

            new_auto_index = {
                **initial_index,
                "elements": [
                    {
                        **initial_index["elements"][0],
                        "latex": "still wrong",
                        "text": "still wrong (1)",
                        "needsReview": True,
                    }
                ],
            }
            controller._write_active_index(record_id, new_auto_index, "fast")
            reloaded = json.loads(controller._index_path(record_id).read_text(encoding="utf-8"))
            self.assertEqual(reloaded["elements"][0]["latex"], "E = mc^2")
            self.assertFalse(reloaded["elements"][0]["needsReview"])

    def test_clear_element_override_removes_override_file_entry(self) -> None:
        class FakePaths:
            def __init__(self, root: Path) -> None:
                self.root = root

            def data(self, *parts: str) -> Path:
                return self.root.joinpath(*parts)

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            controller = PdfExtractionController(None, FakePaths(root), None, None)
            record_id = "record-clear"
            index_dir = controller._record_dir(record_id)
            index_dir.mkdir(parents=True, exist_ok=True)
            index = {
                "version": 3,
                "engine": "pymupdf",
                "pageCount": 1,
                "pages": [{"page": 0, "width": 100, "height": 100}],
                "elements": [{"id": "table_1", "type": "table", "page": 0, "caption": "Table 1"}],
            }
            controller._index_path(record_id).write_text(json.dumps(index), encoding="utf-8")
            self.assertTrue(controller.loadIndex(record_id))
            self.assertTrue(controller.saveElementOverride("table_1", {"caption": "Corrected Table 1"}))
            self.assertTrue(controller.clearElementOverride("table_1"))

            saved_override = json.loads((index_dir / "overrides.json").read_text(encoding="utf-8"))
            self.assertEqual(saved_override["elements"], {})


if __name__ == "__main__":
    unittest.main()
