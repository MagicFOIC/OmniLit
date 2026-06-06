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


if __name__ == "__main__":
    unittest.main()

