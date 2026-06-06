from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from Download.journal_metrics import load_journal_metrics, match_journal_metric, normalize_issn


class JournalMetricTests(unittest.TestCase):
    def test_normalize_issn_accepts_compact_and_dashed_values(self) -> None:
        self.assertEqual(normalize_issn("23130105"), "2313-0105")
        self.assertEqual(normalize_issn("2470-1343"), "2470-1343")

    def test_matches_metric_by_issn_and_name(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "metrics.csv"
            path.write_text(
                "journal_title,issn,issn_l,impact_factor,metric_year,source,quartile\n"
                "Batteries,2313-0105,2313-0105,7.1,2025,local,Q1\n"
                "ACS Omega,2470-1343,2470-1343,4.0,2025,local,Q2\n",
                encoding="utf-8",
            )
            metrics = load_journal_metrics(path)

        issn_match = match_journal_metric({"primary_location": {"source": {"issn_l": "23130105"}}}, metrics)
        name_match = match_journal_metric({"journal": "ACS Omega"}, metrics)
        missing = match_journal_metric({"journal": "Unknown Journal"}, metrics)

        self.assertEqual(issn_match.impact_factor, 7.1)
        self.assertEqual(name_match.impact_factor, 4.0)
        self.assertTrue(missing.impact_factor_unknown)


if __name__ == "__main__":
    unittest.main()

