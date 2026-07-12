from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

try:
    from PySide6.QtCore import QCoreApplication
    from omnilit_qt.selection_translation_controller import SelectionTranslationController
except ModuleNotFoundError:  # pragma: no cover - depends on local test runtime.
    QCoreApplication = None
    SelectionTranslationController = None


class FakePaths:
    def __init__(self, root: Path) -> None:
        self.root = root

    def cache(self, *parts: str) -> Path:
        return self.root.joinpath("cache", *parts)

    def runtime(self, *parts: str) -> Path:
        return self.root.joinpath("runtime", *parts)


@unittest.skipUnless(SelectionTranslationController is not None, "PySide6 is not installed in this environment")
class SelectionTranslationControllerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._qt_app = QCoreApplication.instance() or QCoreApplication([])

    def test_missing_translation_controller_reports_configuration_hint(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            controller = SelectionTranslationController(None, FakePaths(Path(temp)), None, None)

            controller.translateSelection("record-1", "missing.pdf", "important catalyst stability", "zh")

            self.assertFalse(controller.loading)
            self.assertIn("API Key", controller.statusText)
            self.assertEqual(controller.sourceText, "important catalyst stability")
            self.assertEqual(controller.translatedText, "")

    def test_selection_cache_is_reused_per_record_pdf_text_and_profile(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pdf = root / "paper.pdf"
            pdf.write_bytes(b"%PDF-1.4\nselection cache identity")
            controller = SelectionTranslationController(None, FakePaths(root), None, None)

            controller._write_cache_entry("record-1", str(pdf), "The active site is stable.", "zh", "活性位点是稳定的。")

            self.assertTrue(controller.hasCachedRecord("record-1", str(pdf)))
            self.assertEqual(
                controller.cachedTranslation("record-1", str(pdf), "The active site is stable.", "zh"),
                "活性位点是稳定的。",
            )
            self.assertEqual(controller.cachedTranslation("record-1", str(pdf), "Different text", "zh"), "")


if __name__ == "__main__":
    unittest.main()
