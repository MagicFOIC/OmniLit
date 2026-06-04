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
        self.assertIn('"自动推荐"', qml)
        self.assertIn('"Li-S batteries 期刊预设"', qml)
        self.assertIn('"自定义"', qml)
        self.assertIn('text: "6"', qml)

    def test_qml_contains_filter_guidance_copy(self) -> None:
        qml = (ROOT / "ui" / "qml" / "DownloadPage.qml").read_text(encoding="utf-8")

        for text in (
            "主题相关性筛选",
            "推荐开放获取期刊",
            "相关性过滤强度",
            "只保留推荐开放获取期刊",
            "智能筛选说明",
            "OmniLit 会根据你输入的关键词自动判断论文是否相关，用于减少无关结果。",
            "用于优先显示来自开放获取期刊的论文，不会绕过付费墙。",
            "分数越高，结果越精准，但可能漏掉一些相关论文。",
            "开启后会更严格，可能漏掉其他合法开放获取论文。",
            "主题包是一组关键词和评分规则。",
            "开放获取期刊包用于给推荐期刊中的论文加权排序。",
            "推荐默认值为 6。",
        ):
            self.assertIn(text, qml)


if __name__ == "__main__":
    unittest.main()
