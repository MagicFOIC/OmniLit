from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from omnilit_qt.paths import AppPaths
from omnilit_qt.services import build_download_config


ROOT = Path(__file__).resolve().parent.parent


class DownloadConfigLisFieldsTests(unittest.TestCase):
    def test_qml_and_service_fields_enter_crawl_config(self) -> None:
        qml = (ROOT / "ui" / "qml" / "DownloadPage.qml").read_text(encoding="utf-8")
        for field in ("topicPack", "journalPack", "selectedJournals", "minTopicScore", "journalWhitelistOnly"):
            self.assertIn(field, qml)
        self.assertIn("function config()", qml)
        self.assertIn("function restoreSavedConfig()", qml)
        self.assertIn("root.scheduleSave()", qml)

        with tempfile.TemporaryDirectory() as temp:
            paths = AppPaths(ROOT, Path(temp) / "data", ROOT)
            _core, config = build_download_config(
                paths,
                {
                    "topicPack": "li_sulfur",
                    "journalPack": "li_sulfur",
                    "selectedJournals": ["Batteries"],
                    "minTopicScore": "7",
                    "journalWhitelistOnly": True,
                },
                lambda: False,
                lambda _stats, _message: None,
            )

        self.assertEqual(config.topic_pack, "li_sulfur")
        self.assertEqual(config.journal_pack, "li_sulfur")
        self.assertEqual(config.selected_journals, ["Batteries"])
        self.assertEqual(config.min_topic_score, 7)
        self.assertTrue(config.journal_whitelist_only)

    def test_download_controller_persists_lis_fields(self) -> None:
        controller = (ROOT / "omnilit_qt" / "download_controller.py").read_text(encoding="utf-8")
        for field in ("topicPack", "journalPack", "selectedJournals", "minTopicScore", "journalWhitelistOnly"):
            self.assertIn(f'"{field}"', controller)


if __name__ == "__main__":
    unittest.main()
