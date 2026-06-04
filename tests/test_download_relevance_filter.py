from __future__ import annotations

import io
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from Download import literature_download_core as core


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


if __name__ == "__main__":
    unittest.main()
