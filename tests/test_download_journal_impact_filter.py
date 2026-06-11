from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from Download import literature_download_core as core


def _write_metrics(path: Path) -> None:
    path.write_text(
        "journal_title,issn,issn_l,impact_factor,metric_year,source,quartile\n"
        "High IF Journal,1111-1111,1111-1111,8.0,2025,local_csv,Q1\n"
        "Low IF Journal,2222-2222,2222-2222,2.0,2025,local_csv,Q4\n",
        encoding="utf-8",
    )


def _config(root: Path, metrics: Path, **overrides):
    values = {
        "keywords": ["battery"],
        "from_date": "2025-01-01",
        "to_date": "2025-12-31",
        "strict_keyword_match": False,
        "topic_pack": None,
        "journal_pack": None,
        "min_topic_score": 0,
        "max_pages_per_keyword": 1,
        "request_delay": 0,
        "page_delay": 0,
        "resume": False,
        "fast_forward_existing_pages": False,
        "download_pdfs": False,
        "out_dir": root / "pdfs",
        "meta_path": root / "metadata.jsonl",
        "state_path": root / "crawl_state.json",
        "min_impact_factor": 5.0,
        "journal_metric_source": "local_csv",
        "journal_metric_csv": metrics,
    }
    values.update(overrides)
    return core.CrawlConfig(**values)


class DownloadJournalImpactFilterTests(unittest.TestCase):
    def test_state_key_changes_with_min_impact_factor(self) -> None:
        base = core.CrawlConfig(min_impact_factor=5.0)
        changed = core.CrawlConfig(min_impact_factor=6.0)

        self.assertNotEqual(core.state_key("battery", base), core.state_key("battery", changed))

    def test_state_key_changes_with_include_unknown_impact_factor(self) -> None:
        include_unknown = core.CrawlConfig(min_impact_factor=5.0, include_unknown_impact_factor=True)
        skip_unknown = core.CrawlConfig(min_impact_factor=5.0, include_unknown_impact_factor=False)

        self.assertNotEqual(core.state_key("battery", include_unknown), core.state_key("battery", skip_unknown))

    def test_low_if_record_does_not_call_pdf_download(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            metrics = root / "metrics.csv"
            _write_metrics(metrics)
            config = _config(root, metrics, download_pdfs=True)
            stats = core.CrawlStats()
            result = {
                "id": "https://openalex.org/W-low",
                "title": "Battery paper in a low IF journal",
                "abstract": "Battery materials.",
                "journal_title": "Low IF Journal",
                "open_access": {"is_oa": True},
                "pdf_candidates": ["https://example.test/low.pdf"],
            }

            with patch.object(core, "search_literature_source", return_value={"results": [result], "meta": {}}), \
                patch.object(core, "download_first_available_pdf") as download_mock:
                core.crawl_keyword(
                    object(),
                    core.SOURCE_OPENALEX,
                    "battery",
                    core.ExistingIndex(set(), set(), set()),
                    io.StringIO(),
                    config,
                    stats,
                    {},
                )

            self.assertEqual(stats.skipped_by_impact_factor, 1)
            self.assertEqual(stats.journal_metric_resolved, 1)
            self.assertEqual(stats.journal_metric_missing, 0)
            download_mock.assert_not_called()

    def test_unknown_if_default_is_kept(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            metrics = root / "metrics.csv"
            _write_metrics(metrics)
            config = _config(root, metrics)
            stats = core.CrawlStats()
            output = io.StringIO()
            result = {
                "id": "https://openalex.org/W-unknown",
                "title": "Battery paper in an unknown journal",
                "abstract": "Battery materials.",
                "journal_title": "Unknown Journal",
                "open_access": {"is_oa": True},
            }

            with patch.object(core, "search_literature_source", return_value={"results": [result], "meta": {}}):
                core.crawl_keyword(
                    object(),
                    core.SOURCE_OPENALEX,
                    "battery",
                    core.ExistingIndex(set(), set(), set()),
                    output,
                    config,
                    stats,
                    {},
                )

            self.assertEqual(stats.added_records, 1)
            self.assertEqual(stats.journal_metric_missing, 1)
            self.assertEqual(stats.skipped_by_impact_factor, 0)

    def test_unknown_if_can_be_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            metrics = root / "metrics.csv"
            _write_metrics(metrics)
            config = _config(root, metrics, include_unknown_impact_factor=False)
            stats = core.CrawlStats()
            result = {
                "id": "https://openalex.org/W-unknown-skip",
                "title": "Battery paper in an unknown journal",
                "abstract": "Battery materials.",
                "journal_title": "Unknown Journal",
                "open_access": {"is_oa": True},
            }

            with patch.object(core, "search_literature_source", return_value={"results": [result], "meta": {}}), \
                patch.object(core, "download_first_available_pdf") as download_mock:
                core.crawl_keyword(
                    object(),
                    core.SOURCE_OPENALEX,
                    "battery",
                    core.ExistingIndex(set(), set(), set()),
                    io.StringIO(),
                    config,
                    stats,
                    {},
                )

            self.assertEqual(stats.added_records, 0)
            self.assertEqual(stats.journal_metric_missing, 1)
            self.assertEqual(stats.skipped_by_impact_factor, 1)
            download_mock.assert_not_called()

    def test_metric_stats_count_resolved_missing_and_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            metrics = root / "metrics.csv"
            _write_metrics(metrics)
            config = _config(root, metrics)
            stats = core.CrawlStats()
            results = [
                {
                    "id": "https://openalex.org/W-high",
                    "title": "Battery paper in a high IF journal",
                    "abstract": "Battery materials.",
                    "journal_title": "High IF Journal",
                    "open_access": {"is_oa": True},
                },
                {
                    "id": "https://openalex.org/W-low",
                    "title": "Battery paper in a low IF journal",
                    "abstract": "Battery materials.",
                    "journal_title": "Low IF Journal",
                    "open_access": {"is_oa": True},
                },
                {
                    "id": "https://openalex.org/W-unknown",
                    "title": "Battery paper in an unknown journal",
                    "abstract": "Battery materials.",
                    "journal_title": "Unknown Journal",
                    "open_access": {"is_oa": True},
                },
            ]

            with patch.object(core, "search_literature_source", return_value={"results": results, "meta": {}}):
                core.crawl_keyword(
                    object(),
                    core.SOURCE_OPENALEX,
                    "battery",
                    core.ExistingIndex(set(), set(), set()),
                    io.StringIO(),
                    config,
                    stats,
                    {},
                )

            self.assertEqual(stats.journal_metric_resolved, 2)
            self.assertEqual(stats.journal_metric_missing, 1)
            self.assertEqual(stats.skipped_by_impact_factor, 1)


if __name__ == "__main__":
    unittest.main()
