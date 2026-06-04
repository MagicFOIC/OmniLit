from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from omnilit_qt.paths import AppPaths
from omnilit_qt.services import build_download_config


ROOT = Path(__file__).resolve().parent.parent


class DownloadUiConfigTests(unittest.TestCase):
    def test_build_download_config_maps_new_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            paths = AppPaths(ROOT, Path(temp) / "data", ROOT)
            _core, config = build_download_config(
                paths,
                {
                    "topicPack": "li_sulfur",
                    "journalPack": "li_sulfur",
                    "selectedJournals": ["Batteries", "ACS Omega"],
                    "minTopicScore": "8",
                    "journalWhitelistOnly": True,
                },
                lambda: False,
                lambda _stats, _message: None,
            )

            self.assertEqual(config.topic_pack, "li_sulfur")
            self.assertEqual(config.journal_pack, "li_sulfur")
            self.assertEqual(config.selected_journals, ["Batteries", "ACS Omega"])
            self.assertEqual(config.min_topic_score, 8)
            self.assertTrue(config.journal_whitelist_only)

    def test_build_download_config_treats_empty_selected_journals_as_none(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            paths = AppPaths(ROOT, Path(temp) / "data", ROOT)
            _core, config = build_download_config(
                paths,
                {"selectedJournals": []},
                lambda: False,
                lambda _stats, _message: None,
            )

            self.assertIsNone(config.selected_journals)
            self.assertEqual(config.topic_pack, "auto")
            self.assertEqual(config.journal_pack, "auto")

    def test_qml_config_contains_new_fields(self) -> None:
        qml = (ROOT / "ui" / "qml" / "DownloadPage.qml").read_text(encoding="utf-8")

        for field in (
            "topicPack",
            "journalPack",
            "selectedJournals",
            "minTopicScore",
            "journalWhitelistOnly",
        ):
            self.assertIn(field, qml)

        self.assertIn('property var packValues: ["auto", "li_sulfur", "custom"]', qml)
        self.assertIn('"自动根据关键词生成"', qml)
        self.assertIn('"Li-S batteries 预设"', qml)
        self.assertIn('"自定义"', qml)
        self.assertIn('text: "6"', qml)


if __name__ == "__main__":
    unittest.main()
