from __future__ import annotations

import unittest

from Download.pack_builder import build_topic_pack_from_keywords
from Download.topic_packs import score_topic_relevance


class AutoTopicPackTests(unittest.TestCase):
    def test_lithium_sulfur_keywords_merge_lis_expanded_terms(self) -> None:
        pack = build_topic_pack_from_keywords(["lithium-sulfur batteries", "polysulfides"])

        self.assertTrue(pack["uses_li_sulfur_preset"])
        self.assertIn("shuttle effect", pack["optional_expanded_terms"])
        self.assertIn("sulfur cathode", pack["optional_expanded_terms"])

    def test_unrelated_keywords_do_not_merge_lis_terms(self) -> None:
        pack = build_topic_pack_from_keywords(["perovskite solar cells", "hole transport layer"])

        self.assertFalse(pack["uses_li_sulfur_preset"])
        self.assertNotIn("shuttle effect", pack["optional_expanded_terms"])
        self.assertNotIn("polysulfide conversion", pack["optional_expanded_terms"])

    def test_auto_topic_pack_scores_non_lis_direction_from_exact_keyword(self) -> None:
        pack = build_topic_pack_from_keywords(["perovskite solar cells"])
        record = {
            "title": "Perovskite solar cells with stable hole transport layers",
            "abstract": "",
        }

        self.assertGreaterEqual(score_topic_relevance(record, pack), 6)

    def test_lis_auto_pack_rejects_unrelated_polysulfide_chemistry(self) -> None:
        pack = build_topic_pack_from_keywords(["lithium-sulfur batteries", "polysulfides"])
        record = {
            "title": "Polysulfide crosslinking chemistry in industrial sealants",
            "abstract": "This paper studies polymer curing and civil engineering durability.",
        }

        self.assertLess(score_topic_relevance(record, pack), 6)


if __name__ == "__main__":
    unittest.main()
