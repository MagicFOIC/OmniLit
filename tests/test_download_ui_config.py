from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from omnilit_qt.paths import AppPaths
from omnilit_qt.services import build_download_config
from omnilit_qt.download_controller import DOWNLOAD_FORM_FIELDS, DownloadController


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
                    "minImpactFactor": "5.5",
                    "includeUnknownImpactFactor": False,
                    "journalMetricSource": "openalex_only",
                    "journalMetricCsv": str(Path(temp) / "metrics.csv"),
                },
                lambda: False,
                lambda _stats, _message: None,
            )

            self.assertEqual(config.topic_pack, "li_sulfur")
            self.assertEqual(config.journal_pack, "li_sulfur")
            self.assertEqual(config.selected_journals, ["Batteries", "ACS Omega"])
            self.assertEqual(config.min_topic_score, 8)
            self.assertTrue(config.journal_whitelist_only)
            self.assertEqual(config.min_impact_factor, 5.5)
            self.assertFalse(config.include_unknown_impact_factor)
            self.assertEqual(config.journal_metric_source, "openalex_only")
            self.assertEqual(config.journal_metric_csv, Path(temp) / "metrics.csv")

    def test_build_download_config_defaults_impact_metric_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            paths = AppPaths(ROOT, Path(temp) / "data", ROOT)
            _core, config = build_download_config(
                paths,
                {"minImpactFactor": ""},
                lambda: False,
                lambda _stats, _message: None,
            )

            self.assertIsNone(config.min_impact_factor)
            self.assertTrue(config.include_unknown_impact_factor)
            self.assertEqual(config.journal_metric_source, "local_then_openalex")
            self.assertIsNone(config.journal_metric_csv)

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
            self.assertEqual(config.min_topic_score, 0)

    def test_build_download_config_discovery_mode_relaxes_core_filters(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            paths = AppPaths(ROOT, Path(temp) / "data", ROOT)
            _core, config = build_download_config(
                paths,
                {
                    "discoveryMode": True,
                    "strictKeywordMatch": True,
                    "minKeywordMatchRatio": "0.9",
                    "minTopicScore": "12",
                    "journalWhitelistOnly": True,
                    "resume": True,
                    "fastForwardExistingPages": True,
                },
                lambda: False,
                lambda _stats, _message: None,
            )

            self.assertFalse(config.strict_keyword_match)
            self.assertEqual(config.min_keyword_match_ratio, 0.3)
            self.assertEqual(config.min_topic_score, 0)
            self.assertFalse(config.journal_whitelist_only)
            self.assertFalse(config.resume)
            self.assertFalse(config.fast_forward_existing_pages)

    def test_qml_config_contains_new_fields(self) -> None:
        qml = (ROOT / "ui" / "qml" / "DownloadPage.qml").read_text(encoding="utf-8")
        checkbox = (ROOT / "ui" / "qml" / "ModernCheckBox.qml").read_text(encoding="utf-8")

        for field in (
            "topicPack",
            "journalPack",
            "selectedJournals",
            "minTopicScore",
            "journalWhitelistOnly",
            "includeUnknownImpactFactor",
            "journalMetricSource",
            "journalMetricCsv",
            "discoveryMode",
        ):
            self.assertIn(field, qml)

        self.assertIn("activePulse: downloadController.running && downloadController.activeSourceKey === modelData.key", qml)
        self.assertIn("downloadController.activeSourceText", qml)
        self.assertIn("property bool activePulse: false", checkbox)
        self.assertIn("SequentialAnimation on opacity", checkbox)
        self.assertIn('topicPack: "auto", journalPack: "auto"', qml)
        self.assertIn('property var topicScoreValues: [0, 4, 6, 9, 12]', qml)
        self.assertIn('currentIndex: 0', qml)
        self.assertIn('关键词提及即可 / 0', qml)

    def test_qml_uses_compact_hidden_filter_guidance(self) -> None:
        qml = (ROOT / "ui" / "qml" / "DownloadPage.qml").read_text(encoding="utf-8")

        self.assertIn('property var topicScoreValues: [0, 4, 6, 9, 12]', qml)
        self.assertIn('property var topicScoreLabels:', qml)
        self.assertIn('id: journalScope', qml)
        self.assertIn('id: filterStrategy', qml)
        self.assertIn('text: i18n.text("journal_scope")', qml)
        self.assertIn('journalWhitelistOnly: journalScope.currentIndex === 1', qml)
        self.assertIn('minImpactFactor: minImpactFactor.text', qml)
        self.assertIn('includeUnknownImpactFactor: includeUnknownImpactFactor.checked', qml)
        self.assertIn('journalMetricSource: root.journalMetricSourceValues[journalMetricSource.currentIndex]', qml)
        self.assertIn('journalMetricCsv: journalMetricCsv.text', qml)
        self.assertIn('discoveryMode: filterStrategy.currentIndex === 1', qml)
        self.assertIn('minTopicScore.currentIndex=topicScoreIndex', qml)
        self.assertIn('journalScope.currentIndex=journalScopeIndex(savedValue(settings, "journalWhitelistOnly", false))', qml)
        self.assertIn('minImpactFactor.text=savedValue(settings, "minImpactFactor", "")', qml)
        self.assertIn('includeUnknownImpactFactor.checked=savedValue(settings, "includeUnknownImpactFactor", true)', qml)
        self.assertIn('journalMetricSource.currentIndex=journalMetricSourceIndex(savedValue(settings, "journalMetricSource", "local_then_openalex"))', qml)
        self.assertIn('journalMetricCsv.text=savedValue(settings, "journalMetricCsv", "")', qml)
        self.assertIn('filterStrategy.currentIndex=filterStrategyIndex(savedValue(settings, "discoveryMode", false))', qml)
        self.assertIn('text: i18n.text("topic_filter_hint")', qml)
        self.assertIn('text: i18n.text("settings_group_search_scope")', qml)
        self.assertIn('text: i18n.text("settings_group_filter_quality")', qml)
        self.assertIn('text: i18n.text("settings_group_runtime")', qml)
        self.assertIn('text: i18n.text("settings_group_filter_strategy")', qml)
        self.assertNotIn('id: smartFilterChip', qml)
        self.assertNotIn('id: oaFilterChip', qml)
        self.assertNotIn('id: smartFilterHelp\n                        anchors.fill: parent', qml)
        self.assertNotIn("\\u767d\\u540d\\u5355".encode().decode("unicode_escape"), qml)
        self.assertNotIn("\\u76f8\\u5173\\u6027\\u8fc7\\u6ee4\\u5f3a\\u5ea6\\uff1a".encode().decode("unicode_escape"), qml)

    def test_qml_discovery_mode_snapshots_and_restores_managed_settings(self) -> None:
        qml = (ROOT / "ui" / "qml" / "DownloadPage.qml").read_text(encoding="utf-8")

        self.assertIn("property var discoverySnapshot", qml)
        self.assertIn("property bool discoverySnapshotAvailable: false", qml)
        self.assertIn("function saveDiscoverySnapshot()", qml)
        self.assertIn("function applyDiscoveryMode(rememberPrevious)", qml)
        self.assertIn("function restoreDiscoveryMode()", qml)
        self.assertIn("function handleFilterStrategyChanged(index)", qml)
        self.assertIn("root.applyDiscoveryMode(true)", qml)
        self.assertIn("root.restoreDiscoveryMode()", qml)
        self.assertIn("root.applyDiscoveryMode(false)", qml)
        self.assertIn("enabled: !root.discoveryModeActive", qml)
        self.assertIn("readonly property bool discoveryModeActive: filterStrategy.currentIndex === 1", qml)
        self.assertIn('text: i18n.text("discovery_mode_active_tip")', qml)
        self.assertIn('ToolTip.text: i18n.text("discovery_mode_tip")', qml)

    def test_download_controller_tracks_impact_metric_fields_and_stats(self) -> None:
        for field in ("includeUnknownImpactFactor", "journalMetricSource", "journalMetricCsv"):
            self.assertIn(field, DOWNLOAD_FORM_FIELDS)

        stats = DownloadController._empty_stats()
        self.assertIn("journal_metric_resolved", stats)
        self.assertIn("journal_metric_missing", stats)
        self.assertIn("skipped_by_impact_factor", stats)

if __name__ == "__main__":
    unittest.main()
