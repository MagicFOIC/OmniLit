from __future__ import annotations

import unittest

from Download import literature_download_core as core
from Download.pack_builder import (
    build_journal_pack_from_records,
    build_topic_pack_from_keywords,
    normalize_user_keywords,
    resolve_journal_pack,
    resolve_topic_pack,
)


class PackBuilderTests(unittest.TestCase):
    def test_user_keywords_enter_auto_topic_pack(self) -> None:
        pack = build_topic_pack_from_keywords([" lithium-sulfur batteries ", "polysulfides", "polysulfides"])

        self.assertEqual(pack["exact_terms"], ["lithium-sulfur batteries", "polysulfides"])
        self.assertIn("lithium sulfur batteries", pack["normalized_terms"])
        self.assertIn("lithium sulfur battery", pack["normalized_terms"])
        self.assertIn("polysulfide", pack["normalized_terms"])

    def test_normalize_user_keywords_handles_empty_and_duplicate_values(self) -> None:
        self.assertEqual(
            normalize_user_keywords(["", "Solid  state battery", "solid  state battery"]),
            ["Solid state battery"],
        )

    def test_resolve_topic_pack_li_sulfur_uses_preset(self) -> None:
        pack = resolve_topic_pack(core.CrawlConfig(topic_pack="li_sulfur"), ["ignored"])

        self.assertEqual(pack["name"], "li_sulfur")
        self.assertEqual(pack["type"], "preset")
        self.assertTrue(pack["uses_li_sulfur_preset"])

    def test_topic_pack_auto_is_default(self) -> None:
        self.assertEqual(core.CrawlConfig().topic_pack, "auto")
        self.assertEqual(core.CrawlConfig().journal_pack, "auto")

    def test_missing_fields_do_not_raise(self) -> None:
        journal_pack = build_journal_pack_from_records([{}])
        topic_pack = resolve_topic_pack(core.CrawlConfig(), [])
        resolved_journal_pack = resolve_journal_pack(core.CrawlConfig(), [{}])

        self.assertEqual(journal_pack["journals"], [])
        self.assertEqual(topic_pack["exact_terms"], [])
        self.assertEqual(resolved_journal_pack["journals"], [])


if __name__ == "__main__":
    unittest.main()
