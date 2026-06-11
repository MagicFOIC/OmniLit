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
        self.assertIn("literatureLibraryController.ensureLoaded()", qml)
        self.assertIn("onClicked: literatureLibraryController.refresh()", qml)

    def test_qml_exposes_pdf_extraction_reader_entry(self) -> None:
        qml_dir = ROOT / "ui" / "qml"
        qml = (qml_dir / "LiteratureLibraryPage.qml").read_text(encoding="utf-8")

        self.assertIn("解析阅读", qml)
        self.assertIn("LiteratureReaderPage", qml)
        reader = (qml_dir / "LiteratureReaderPage.qml").read_text(encoding="utf-8")
        self.assertIn("pdfExtractionController", reader)
        self.assertIn("pdfExtractionController.pages", reader)
        self.assertIn("property real zoom: 1.0", reader)
        self.assertIn("Timer { id: openRecordTimer", reader)
        self.assertIn("onPdfPathChanged: root.scheduleOpenRecord()", reader)
        self.assertIn("function openRecordNow()", reader)
        self.assertIn("WheelHandler", reader)
        self.assertIn("acceptedModifiers: Qt.ControlModifier", reader)
        self.assertIn("pdfExtractionController.openExportDirectory(root.exportedPath)", reader)
        panel = (qml_dir / "PdfExtractionPanel.qml").read_text(encoding="utf-8")
        self.assertIn("property string exportedPath", panel)
        self.assertIn("打开 PNG 目录", panel)
        self.assertIn("pdfExtractionController.openExportDirectory(root.exportedPath)", panel)
        self.assertIn("wrapMode: Text.WrapAnywhere", panel)
        self.assertTrue((qml_dir / "PdfElementBookmarkBar.qml").exists())
        self.assertTrue((qml_dir / "PdfElementOverlay.qml").exists())
        self.assertTrue((qml_dir / "PdfExtractionPanel.qml").exists())


if __name__ == "__main__":
    unittest.main()
