from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from omnilit_qt.paths import AppPaths
from omnilit_qt.services import AccountStore, build_download_config, normalize_download_form_config

try:
    from omnilit_qt.download_controller import DOWNLOAD_FORM_FIELDS, DownloadController
except ModuleNotFoundError:  # pragma: no cover - depends on local Qt runtime.
    DOWNLOAD_FORM_FIELDS = ()
    DownloadController = None


ROOT = Path(__file__).resolve().parent.parent


class DownloadUiConfigTests(unittest.TestCase):
    def test_build_download_config_maps_pack_and_metric_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            paths = AppPaths(ROOT, Path(temp) / "data", ROOT)
            _core, config = build_download_config(
                paths,
                {
                    "qualityPreset": "strict",
                    "topicPack": "li_sulfur",
                    "journalPack": "li_sulfur",
                    "selectedJournals": ["Batteries", "ACS Omega"],
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
            self.assertEqual(config.min_topic_score, 9)
            self.assertFalse(config.journal_whitelist_only)
            self.assertEqual(config.min_impact_factor, 5.5)
            self.assertFalse(config.include_unknown_impact_factor)
            self.assertEqual(config.journal_metric_source, "openalex_only")
            self.assertEqual(config.journal_metric_csv, Path(temp) / "metrics.csv")

    def test_build_download_config_defaults_impact_metric_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            paths = AppPaths(ROOT, Path(temp) / "data", ROOT)
            _core, config = build_download_config(paths, {"minImpactFactor": ""}, lambda: False, lambda _stats, _message: None)

            self.assertIsNone(config.min_impact_factor)
            self.assertTrue(config.include_unknown_impact_factor)
            self.assertEqual(config.journal_metric_source, "local_then_openalex")
            self.assertIsNone(config.journal_metric_csv)

    def test_build_download_config_uses_metrics_csv_from_output_dir(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            output_dir = Path(temp) / "data" / "data" / "downloads"
            output_dir.mkdir(parents=True)
            metrics = output_dir / "journal_metrics.csv"
            metrics.write_text("journal_title,issn\nBatteries,2313-0105\n", encoding="utf-8")
            paths = AppPaths(ROOT, Path(temp) / "data", ROOT)
            _core, config = build_download_config(paths, {}, lambda: False, lambda _stats, _message: None)

            self.assertEqual(config.journal_metric_csv.resolve(), metrics.resolve())
            self.assertEqual(config.state_path.resolve(), (Path(temp) / "data" / "runtime" / "downloads" / "crawl_state.json").resolve())

    def test_build_download_config_treats_empty_selected_journals_as_none(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            paths = AppPaths(ROOT, Path(temp) / "data", ROOT)
            _core, config = build_download_config(paths, {"selectedJournals": []}, lambda: False, lambda _stats, _message: None)

            self.assertIsNone(config.selected_journals)
            self.assertEqual(config.topic_pack, "auto")
            self.assertEqual(config.journal_pack, "auto")
            self.assertEqual(config.min_topic_score, 6)

    def test_build_download_config_quality_preset_controls_core_filters(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            paths = AppPaths(ROOT, Path(temp) / "data", ROOT)
            _core, config = build_download_config(
                paths,
                {
                    "qualityPreset": "very_strict",
                    "strictKeywordMatch": False,
                    "minKeywordMatchRatio": "0.3",
                    "minTopicScore": "0",
                    "journalWhitelistOnly": False,
                    "resume": False,
                    "fastForwardExistingPages": False,
                    "oaOnly": False,
                },
                lambda: False,
                lambda _stats, _message: None,
            )

            self.assertTrue(config.strict_keyword_match)
            self.assertEqual(config.min_keyword_match_ratio, 0.9)
            self.assertEqual(config.min_topic_score, 12)
            self.assertTrue(config.journal_whitelist_only)
            self.assertTrue(config.oa_only)
            self.assertTrue(config.resume)
            self.assertTrue(config.fast_forward_existing_pages)

    def test_build_download_config_uses_hidden_runtime_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            paths = AppPaths(ROOT, Path(temp) / "data", ROOT)
            _core, config = build_download_config(
                paths,
                {"downloadPdfs": False, "loop": True, "maxRuntimeHours": "2", "maxRecords": "5"},
                lambda: False,
                lambda _stats, _message: None,
            )

            self.assertTrue(config.download_pdfs)
            self.assertTrue(config.retry_missing_pdfs)
            self.assertFalse(config.write_retry_records)
            self.assertFalse(config.loop)
            self.assertIsNone(config.max_runtime_hours)
            self.assertIsNone(config.max_records)
            self.assertEqual(config.max_pages_per_keyword, 1000)
            self.assertEqual(config.per_page, 50)

    def test_build_download_config_splits_and_deduplicates_keywords(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            paths = AppPaths(ROOT, Path(temp) / "data", ROOT)
            _core, config = build_download_config(
                paths,
                {"keywords": "lithium-sulfur batteries\npolysulfides, lithium-sulfur batteries; Polysulfides"},
                lambda: False,
                lambda _stats, _message: None,
            )

            self.assertEqual(config.keywords, ["lithium-sulfur batteries", "polysulfides"])

    def test_saved_legacy_workspace_download_dir_rebases_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            paths = AppPaths(ROOT, root / "current", ROOT)
            store = AccountStore(paths.config("accounts.sqlite3"))
            old_default = root / "old-install" / "Workspace" / "Download"

            normalized = normalize_download_form_config(paths, store, {"outputDir": str(old_default)})

            self.assertEqual(normalized["outputDir"], str(paths.content("downloads")))

    def test_custom_download_dir_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            paths = AppPaths(ROOT, root / "current", ROOT)
            store = AccountStore(paths.config("accounts.sqlite3"))
            custom = root / "projects" / "Download"
            custom.mkdir(parents=True)

            normalized = normalize_download_form_config(paths, store, {"outputDir": str(custom)})

            self.assertEqual(normalized["outputDir"], str(custom))

    def test_qml_uses_unified_quality_and_research_keyword_tags(self) -> None:
        qml = (ROOT / "ui" / "qml" / "DownloadPage.qml").read_text(encoding="utf-8")
        checkbox = (ROOT / "ui" / "qml" / "ModernCheckBox.qml").read_text(encoding="utf-8")

        self.assertIn('property var qualityValues: ["keyword", "relaxed", "balanced", "strict", "very_strict"]', qml)
        self.assertIn('property var qualityTipKeys: ["quality_keyword_tip", "quality_relaxed_tip", "quality_balanced_tip", "quality_strict_tip", "quality_very_strict_tip"]', qml)
        self.assertIn("property int selectedQualityIndex: 2", qml)
        self.assertIn("qualityPreset: root.qualityValues[root.selectedQualityIndex]", qml)
        self.assertIn("text: i18n.text(root.qualityTipKeys[index])", qml)
        self.assertIn("property var keywordTerms: []", qml)
        self.assertIn("model: root.keywordTerms", qml)
        self.assertIn("function addKeywords(value)", qml)
        self.assertIn("function startEditKeyword(index)", qml)
        self.assertIn("function startAddKeyword()", qml)
        self.assertIn("function commitNewKeyword(value)", qml)
        self.assertIn("function commitKeywordEdit(index, value)", qml)
        self.assertIn("function removeKeyword(index)", qml)
        self.assertIn("root.editingKeywordIndex === index", qml)
        self.assertIn("onAccepted: root.commitKeywordEdit(index, text)", qml)
        self.assertIn("id: addKeywordChip", qml)
        self.assertIn("id: addKeywordEdit", qml)
        self.assertIn("onClicked: root.startAddKeyword()", qml)
        self.assertIn("onAccepted: root.commitNewKeyword(text)", qml)
        self.assertIn('placeholderText: i18n.text("keyword_input_placeholder")', qml)
        self.assertNotIn("id: keywordInput", qml)
        self.assertNotIn('text: i18n.text("add_keyword")', qml)
        self.assertIn("downloadController.keywordSuggestions", qml)
        self.assertIn("downloadController.contactEmail", qml)
        self.assertIn('Text { text: i18n.text("from_date"); color: theme.textMuted }', qml)
        self.assertIn("maxPages: 1000", qml)
        self.assertIn("perPage: 50", qml)
        self.assertIn("downloadPdfs: true", qml)
        self.assertIn("resume: true", qml)
        self.assertIn("loop: false", qml)
        self.assertIn('property var selectedSources: ["openalex", "europe_pmc", "arxiv", "crossref", "doaj"]', qml)
        self.assertIn('text: i18n.text("pdf_backfill")', qml)
        self.assertIn('text: i18n.text("pdf_backfill_tip")', qml)
        self.assertIn("downloadController.backfillMissingPdfs(config())", qml)
        self.assertNotIn('text: "PDF backfill"', qml)
        self.assertNotIn("Scan existing metadata and download missing legal OA PDFs.", qml)
        self.assertNotIn("chooseDirectory", qml)
        for hidden in ('i18n.text("email")', "id: email", "id: keywordSuggestion", "model: root.keywordOptions", "id: filterStrategy", "id: journalScope", "id: downloadPdfs", "id: resume", "id: oaOnly", "id: pages", "id: perPage", "id: maxRecords"):
            self.assertNotIn(hidden, qml)

        self.assertIn("activePulse: downloadController.running && downloadController.activeSourceKey === modelData.key", qml)
        self.assertIn("downloadController.activeSourceText", qml)
        self.assertIn('text: i18n.text("source_api_settings")', qml)
        self.assertIn("downloadController.availableSourceApiStatuses", qml)
        self.assertIn("downloadController.saveSourceApiSettings(root.apiSettings())", qml)
        self.assertIn("downloadController.testSourceApi(modelData.source)", qml)
        self.assertIn("downloadController.clearSourceApiKey(modelData.source)", qml)
        self.assertIn("id: openalexApiKey", qml)
        self.assertIn("id: doajApiKey", qml)
        self.assertIn("id: semanticScholarApiKey", qml)
        self.assertIn("property bool activePulse: false", checkbox)
        self.assertIn("SequentialAnimation on opacity", checkbox)

    @unittest.skipUnless(DownloadController is not None, "PySide6 is not installed in this environment")
    def test_download_controller_tracks_quality_email_and_stats(self) -> None:
        for field in ("includeUnknownImpactFactor", "journalMetricSource", "journalMetricCsv", "qualityPreset"):
            self.assertIn(field, DOWNLOAD_FORM_FIELDS)

        stats = DownloadController._empty_stats()
        self.assertIn("journal_metric_resolved", stats)
        self.assertIn("journal_metric_missing", stats)
        self.assertIn("skipped_by_impact_factor", stats)


if __name__ == "__main__":
    unittest.main()
