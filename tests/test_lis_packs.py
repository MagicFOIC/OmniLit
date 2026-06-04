from __future__ import annotations

import unittest

from Download.journal_registry import (
    get_oa_journal_pack,
    is_whitelisted_journal,
    journal_match_score,
    normalize_issn,
)
from Download.topic_packs import get_topic_pack, score_topic_relevance


class JournalRegistryTests(unittest.TestCase):
    def test_journal_registry_matches_issn_and_name(self) -> None:
        by_issn = {
            "primary_location": {
                "source": {
                    "display_name": "Unknown title from API",
                    "issn_l": "23130105",
                }
            }
        }
        by_name = {"container-title": ["RSC Advances"]}

        self.assertEqual(normalize_issn("ISSN 23130105"), "2313-0105")
        self.assertTrue(is_whitelisted_journal(by_issn))
        self.assertTrue(is_whitelisted_journal(by_name))
        self.assertGreaterEqual(journal_match_score(by_issn), 3)
        self.assertGreaterEqual(journal_match_score(by_name), 2)

    def test_selected_journals_limits_whitelist_matches(self) -> None:
        record = {"primary_location": {"source": {"display_name": "RSC Advances"}}}

        self.assertTrue(is_whitelisted_journal(record, selected_journals=["RSC Advances"]))
        self.assertFalse(is_whitelisted_journal(record, selected_journals=["Batteries"]))

    def test_get_oa_journal_pack_returns_copy(self) -> None:
        journals = get_oa_journal_pack("li_sulfur")
        journals[0]["name"] = "Mutated"

        self.assertEqual(get_oa_journal_pack("li_sulfur")[0]["name"], "Batteries")


class TopicPackTests(unittest.TestCase):
    def test_lis_topic_scoring_accepts_lithium_sulfur_polysulfide(self) -> None:
        record = {
            "title": "Catalytic conversion of lithium-sulfur batteries polysulfides on carbon hosts",
            "abstract": (
                "The sulfur cathode suppresses the polysulfide shuttle and promotes Li2S6 "
                "conversion using an electrocatalyst."
            ),
            "primary_location": {"source": {"display_name": "ACS Omega"}},
        }

        self.assertGreaterEqual(score_topic_relevance(record), 6)

    def test_lis_topic_scoring_rejects_unrelated_polysulfide(self) -> None:
        record = {
            "title": "Polysulfide sealants for construction joints",
            "abstract": "Mechanical aging of building sealants under humidity is evaluated.",
            "primary_location": {"source": {"display_name": "Journal of Construction Materials"}},
        }

        self.assertLess(score_topic_relevance(record), 6)

    def test_get_topic_pack_contains_default_lis_terms(self) -> None:
        terms = get_topic_pack("li_sulfur")

        self.assertIn("lithium-sulfur batteries", terms)
        self.assertIn("polysulfides", terms)


if __name__ == "__main__":
    unittest.main()
