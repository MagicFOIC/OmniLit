from __future__ import annotations

import io
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from Download import literature_download_core as core
from Download.journal_metrics import JournalMetricMatch


class DownloadRelevanceFilterTests(unittest.TestCase):
    def test_record_passes_relevance_filters_accepts_lis_record(self) -> None:
        config = core.CrawlConfig(request_delay=0, page_delay=0)
        record = {
            "title": "Lithium-sulfur batteries with catalytic polysulfide conversion",
            "abstract": "A sulfur cathode improves Li2S6 conversion and suppresses shuttle effect.",
        }

        passed, score, reason = core.record_passes_relevance_filters(record, config)

        self.assertTrue(passed)
        self.assertGreaterEqual(score, config.min_topic_score)
        self.assertIsNone(reason)

    def test_record_passes_relevance_filters_rejects_keyword_only_record(self) -> None:
        config = core.CrawlConfig(request_delay=0, page_delay=0)
        record = {
            "title": "Polysulfide sealants for construction joints",
            "abstract": "Mechanical aging of building sealants under humidity is evaluated.",
        }

        passed, score, reason = core.record_passes_relevance_filters(record, config)

        self.assertFalse(passed)
        self.assertLess(score, config.min_topic_score)
        self.assertEqual(reason, "low_topic_score")

    def test_crawl_keyword_filters_after_keyword_match_before_metadata_write(self) -> None:
        related = {
            "id": "https://openalex.org/W-related",
            "title": "Lithium-sulfur batteries with polysulfide adsorption",
            "abstract": "A sulfur cathode suppresses the shuttle effect with Li2S6 conversion.",
            "open_access": {"is_oa": True, "oa_url": "https://example.test/related.pdf"},
        }
        unrelated = {
            "id": "https://openalex.org/W-unrelated",
            "title": "Polysulfide sealants for construction joints",
            "abstract": "Mechanical aging of building sealants under humidity is evaluated.",
            "open_access": {"is_oa": True, "oa_url": "https://example.test/unrelated.pdf"},
        }
        config = core.CrawlConfig(
            out_dir=Path("unused"),
            keywords=["polysulfides"],
            download_pdfs=False,
            request_delay=0,
            page_delay=0,
            strict_keyword_match=True,
            resume=False,
        )
        stats = core.CrawlStats()
        output = io.StringIO()

        with patch.object(
            core,
            "search_literature_source",
            return_value={"results": [related, unrelated], "meta": {"next_cursor": None}},
        ):
            core.crawl_keyword(
                object(),
                core.SOURCE_OPENALEX,
                "polysulfides",
                core.ExistingIndex(set(), set(), set()),
                output,
                config,
                stats,
                {},
            )

        lines = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual([line["source_record_id"] for line in lines], ["https://openalex.org/W-related"])
        self.assertEqual(stats.added_records, 1)
        self.assertEqual(stats.skipped_irrelevant, 1)

    def test_journal_whitelist_only_rejects_non_whitelisted_journal(self) -> None:
        config = core.CrawlConfig(
            journal_pack="li_sulfur",
            journal_whitelist_only=True,
            strict_keyword_match=False,
            request_delay=0,
            page_delay=0,
        )
        record = {
            "title": "Lithium-sulfur batteries in a closed journal",
            "primary_location": {"source": {"display_name": "Closed Battery Letters"}},
        }

        passed, _score, reason = core.record_passes_relevance_filters(record, config)

        self.assertFalse(passed)
        self.assertEqual(reason, "journal_not_whitelisted")

    def test_impact_factor_filter_rejects_known_low_if_but_keeps_unknown(self) -> None:
        low_match = JournalMetricMatch("Low IF Journal", ("1111-1111",), 2.1, "2025", "local", "", False)
        unknown_match = JournalMetricMatch("Unknown Journal", (), None, "", "", "", True)
        config = core.CrawlConfig(min_impact_factor=5.0)

        with patch.object(core, "match_journal_metric", return_value=low_match):
            passed_low, low_fields = core.record_passes_impact_factor_filter({"journal": "Low IF Journal"}, config)
        with patch.object(core, "match_journal_metric", return_value=unknown_match):
            passed_unknown, unknown_fields = core.record_passes_impact_factor_filter({"journal": "Unknown Journal"}, config)

        self.assertFalse(passed_low)
        self.assertEqual(low_fields["impact_factor"], 2.1)
        self.assertTrue(passed_unknown)
        self.assertTrue(unknown_fields["impact_factor_unknown"])

    def test_content_extraction_helpers_find_abstract_and_keywords(self) -> None:
        text = (
            "Title\nAbstract\n"
            "This study improves lithium sulfur batteries by catalytic polysulfide conversion.\n"
            "Keywords: lithium-sulfur batteries; polysulfide conversion; sulfur cathode\n"
            "1. Introduction\nBody"
        )

        abstract = core.extract_abstract_from_text(text)
        keywords = core.extract_keywords_from_text(text)

        self.assertIn("catalytic polysulfide conversion", abstract)
        self.assertEqual(keywords[:2], ["lithium-sulfur batteries", "polysulfide conversion"])

    def test_build_record_writes_journal_metrics_and_keywords(self) -> None:
        metric = JournalMetricMatch("Batteries", ("2313-0105",), 7.1, "2025", "local", "Q1", False)
        item = {
            "id": "https://openalex.org/W-metric",
            "title": "Lithium-sulfur batteries with polysulfide conversion",
            "abstract": "This paper discusses sulfur cathode design and polysulfide conversion.",
            "open_access": {"is_oa": True},
            "primary_location": {"source": {"display_name": "Batteries", "issn_l": "2313-0105"}},
        }
        relevance_info = {"matched_keywords": ["lithium-sulfur batteries"], "matched_fields": ["title"]}

        with patch.object(core, "match_journal_metric", return_value=metric):
            record = core.build_record(
                "lithium-sulfur batteries",
                item,
                None,
                core.DownloadResult(None, "download_disabled"),
                [],
                Path("metadata.jsonl"),
                relevance_info,
            )

        self.assertEqual(record["journal_title"], "Batteries")
        self.assertEqual(record["impact_factor"], 7.1)
        self.assertIn("lithium-sulfur batteries", record["extracted_keywords"])
        self.assertIn("sulfur cathode", record["content_summary"])


if __name__ == "__main__":
    unittest.main()
