from __future__ import annotations

import unittest

from Download import literature_download_core as core


class LisFilterPipelineTests(unittest.TestCase):
    def test_lithium_sulfur_polysulfides_high_score_passes(self) -> None:
        record = {
            "title": "Lithium-sulfur batteries with catalytic polysulfide conversion",
            "abstract": "Sulfur cathode designs suppress the shuttle effect and improve Li2S6 conversion.",
            "primary_location": {"source": {"display_name": "ACS Omega"}},
        }
        passed, score, reason = core.record_passes_relevance_filters(record, core.CrawlConfig())

        self.assertTrue(passed)
        self.assertGreaterEqual(score, 6)
        self.assertIsNone(reason)

    def test_unrelated_polysulfide_chemistry_low_score_filters(self) -> None:
        record = {
            "title": "Polysulfide crosslinking chemistry in industrial sealants",
            "abstract": "This paper studies polymer curing and civil engineering durability.",
        }
        passed, score, reason = core.record_passes_relevance_filters(record, core.CrawlConfig())

        self.assertFalse(passed)
        self.assertLess(score, 6)
        self.assertEqual(reason, "low_topic_score")

    def test_journal_whitelist_only_keeps_only_whitelisted_journals(self) -> None:
        config = core.CrawlConfig(journal_pack="li_sulfur", journal_whitelist_only=True, strict_keyword_match=False)
        allowed = {"primary_location": {"source": {"display_name": "Batteries", "issn_l": "2313-0105"}}}
        rejected = {"primary_location": {"source": {"display_name": "Closed Battery Letters"}}}

        self.assertTrue(core.record_passes_relevance_filters(allowed, config)[0])
        self.assertFalse(core.record_passes_relevance_filters(rejected, config)[0])

    def test_min_topic_score_is_enforced(self) -> None:
        record = {
            "title": "Lithium-sulfur batteries with polysulfide adsorption",
            "abstract": "A sulfur cathode and electrolyte design are discussed.",
        }
        passed, score, reason = core.record_passes_relevance_filters(
            record,
            core.CrawlConfig(min_topic_score=20),
        )

        self.assertFalse(passed)
        self.assertLess(score, 20)
        self.assertEqual(reason, "low_topic_score")


if __name__ == "__main__":
    unittest.main()
