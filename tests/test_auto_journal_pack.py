from __future__ import annotations

import unittest

from Download import literature_download_core as core
from Download.pack_builder import build_journal_pack_from_records, journal_pack_match_score, resolve_journal_pack


class AutoJournalPackTests(unittest.TestCase):
    def test_auto_journal_pack_only_counts_oa_records(self) -> None:
        pack = build_journal_pack_from_records(
            [
                {
                    "title": "OA paper",
                    "open_access": {"is_oa": True},
                    "primary_location": {"source": {"display_name": "OA Journal", "issn_l": "1234-5678"}},
                },
                {
                    "title": "Closed paper",
                    "open_access": {"is_oa": False},
                    "primary_location": {"source": {"display_name": "Closed Journal", "issn_l": "9999-9999"}},
                },
            ]
        )

        names = [journal["name"] for journal in pack["journals"]]
        self.assertEqual(names, ["OA Journal"])

    def test_high_topic_score_journal_ranks_first(self) -> None:
        pack = build_journal_pack_from_records(
            [
                {
                    "open_access": {"is_oa": True},
                    "topic_score": 2,
                    "primary_location": {"source": {"display_name": "Low Score OA"}},
                },
                {
                    "open_access": {"is_oa": True},
                    "topic_score": 10,
                    "primary_location": {"source": {"display_name": "High Score OA"}},
                },
            ]
        )

        self.assertEqual(pack["journals"][0]["name"], "High Score OA")

    def test_journal_pack_match_score_matches_name_and_issn(self) -> None:
        pack = build_journal_pack_from_records(
            [
                {
                    "open_access": {"is_oa": True},
                    "primary_location": {"source": {"display_name": "Batteries", "issn_l": "2313-0105"}},
                }
            ]
        )
        record = {"primary_location": {"source": {"display_name": "Different title", "issn_l": "23130105"}}}

        self.assertGreaterEqual(journal_pack_match_score(record, pack), 3)

    def test_resolve_journal_pack_li_sulfur_still_uses_preset(self) -> None:
        pack = resolve_journal_pack(core.CrawlConfig(journal_pack="li_sulfur"), [])

        self.assertEqual(pack["name"], "li_sulfur")
        self.assertIn("Batteries", [journal["name"] for journal in pack["journals"]])


if __name__ == "__main__":
    unittest.main()
