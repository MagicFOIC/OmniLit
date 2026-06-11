from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


class LiteratureLibraryQmlTests(unittest.TestCase):
    def test_qml_exposes_keyword_group_filter_and_new_metadata_fields(self) -> None:
        qml = (ROOT / "ui" / "qml" / "LiteratureLibraryPage.qml").read_text(encoding="utf-8")

        self.assertIn("property var selectedKeywordGroups", qml)
        self.assertIn("literatureLibraryController.keywordGroupOptions", qml)
        self.assertIn("root.selectedKeywordGroups", qml)
        self.assertIn("modelData.journalTitle", qml)
        self.assertIn("modelData.impactFactorText", qml)
        self.assertIn("root.selectedDetails.keywordsText", qml)
        self.assertIn("root.selectedDetails.contentSummary", qml)

    def test_qml_exposes_pdf_extraction_reader_entry(self) -> None:
        qml_dir = ROOT / "ui" / "qml"
        qml = (qml_dir / "LiteratureLibraryPage.qml").read_text(encoding="utf-8")

        self.assertIn("解析阅读", qml)
        self.assertIn("LiteratureReaderPage", qml)
        reader = (qml_dir / "LiteratureReaderPage.qml").read_text(encoding="utf-8")
        self.assertIn("pdfExtractionController", reader)
        self.assertIn("pdfExtractionController.pages", reader)
        self.assertIn("onPdfPathChanged", reader)
        self.assertTrue((qml_dir / "PdfElementBookmarkBar.qml").exists())
        self.assertTrue((qml_dir / "PdfElementOverlay.qml").exists())
        self.assertTrue((qml_dir / "PdfExtractionPanel.qml").exists())


if __name__ == "__main__":
    unittest.main()
