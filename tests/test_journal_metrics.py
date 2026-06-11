from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from Download.journal_metrics import (
    JournalMetric,
    JournalMetricResolver,
    attach_journal_metric,
    fetch_openalex_source_metric,
    load_journal_metrics,
    match_journal_metric,
    normalize_issn,
    record_passes_impact_factor_filter,
)


class MockResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self.payload


class MockSession:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.calls: list[tuple[str, dict | None]] = []

    def get(self, url: str, params: dict | None = None, timeout: int | None = None) -> MockResponse:
        self.calls.append((url, params))
        return MockResponse(self.payload)


class JournalMetricTests(unittest.TestCase):
    def test_normalize_issn_accepts_compact_and_dashed_values(self) -> None:
        self.assertEqual(normalize_issn("23130105"), "2313-0105")
        self.assertEqual(normalize_issn("2470-1343"), "2470-1343")

    def test_matches_metric_by_issn_and_name(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "metrics.csv"
            path.write_text(
                "journal_title,issn,issn_l,impact_factor,metric_year,source,quartile\n"
                "Batteries,2313-0105,2313-0105,7.1,2025,local_csv,Q1\n"
                "ACS Omega,2470-1343,2470-1343,4.0,2025,local_csv,Q2\n",
                encoding="utf-8",
            )
            metrics = load_journal_metrics(path)

        issn_match = match_journal_metric({"primary_location": {"source": {"issn_l": "23130105"}}}, metrics)
        name_match = match_journal_metric({"journal": "ACS Omega"}, metrics)
        missing = match_journal_metric({"journal": "Unknown Journal"}, metrics)

        self.assertEqual(issn_match.impact_factor, 7.1)
        self.assertEqual(name_match.impact_factor, 4.0)
        self.assertTrue(missing.impact_factor_unknown)

    def test_resolver_prefers_local_csv_over_openalex(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "metrics.csv"
            path.write_text(
                "journal_title,issn,issn_l,impact_factor,metric_year,source,quartile\n"
                "Batteries,2313-0105,2313-0105,7.1,2025,local_csv,Q1\n",
                encoding="utf-8",
            )
            session = MockSession(
                {
                    "results": [
                        {
                            "display_name": "Batteries",
                            "issn": ["2313-0105"],
                            "issn_l": "2313-0105",
                            "summary_stats": {"2yr_mean_citedness": 99.0},
                        }
                    ]
                }
            )
            resolver = JournalMetricResolver(local_csv=path, session=session)
            metric = resolver.resolve({"journal_title": "Batteries", "issn_l": "2313-0105"})

        self.assertIsNotNone(metric)
        self.assertEqual(metric.impact_factor, 7.1)
        self.assertEqual(metric.source, "local_csv")
        self.assertEqual(session.calls, [])

    def test_resolver_falls_back_to_openalex_after_local_miss(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "metrics.csv"
            path.write_text(
                "journal_title,issn,issn_l,impact_factor,metric_year,source,quartile\n",
                encoding="utf-8",
            )
            session = MockSession(
                {
                    "results": [
                        {
                            "display_name": "Open Journal",
                            "issn": ["1111-1111"],
                            "issn_l": "1111-1111",
                            "summary_stats": {"2yr_mean_citedness": 5.5},
                        }
                    ]
                }
            )
            resolver = JournalMetricResolver(local_csv=path, session=session)
            metric = resolver.resolve({"journal_title": "Open Journal", "issn_l": "1111-1111"})

        self.assertIsNotNone(metric)
        self.assertEqual(metric.impact_factor, 5.5)
        self.assertEqual(metric.source, "openalex")
        self.assertEqual(metric.metric_name, "openalex_2yr_mean_citedness")
        self.assertEqual(len(session.calls), 1)

    def test_openalex_summary_stats_written_as_impact_factor(self) -> None:
        session = MockSession(
            {
                "results": [
                    {
                        "display_name": "Open Journal",
                        "issn": ["1111-1111"],
                        "issn_l": "1111-1111",
                        "summary_stats": {"2yr_mean_citedness": 3.25},
                    }
                ]
            }
        )

        metric = fetch_openalex_source_metric(session, issn_l="11111111")

        self.assertIsNotNone(metric)
        self.assertEqual(metric.impact_factor, 3.25)
        self.assertEqual(metric.source, "openalex")
        self.assertEqual(metric.metric_name, "openalex_2yr_mean_citedness")

    def test_unknown_impact_passes_when_include_unknown_true(self) -> None:
        self.assertTrue(record_passes_impact_factor_filter({}, 5.0, include_unknown=True))

    def test_unknown_impact_skips_when_include_unknown_false(self) -> None:
        self.assertFalse(record_passes_impact_factor_filter({}, 5.0, include_unknown=False))

    def test_impact_factor_below_threshold_skips(self) -> None:
        self.assertFalse(record_passes_impact_factor_filter({"impact_factor": 2.0}, 5.0))

    def test_attach_journal_metric_writes_main_fields_and_aliases(self) -> None:
        record = {"journal_title": "Input Journal", "journal_issns": ["12345678"]}
        metric = JournalMetric(
            journal_title="Metric Journal",
            issn=["1234-5678"],
            issn_l="1234-5678",
            impact_factor=6.2,
            metric_year=2025,
            source="local_csv",
            quartile="Q1",
        )

        attach_journal_metric(record, metric)

        self.assertEqual(record["journal_title"], "Input Journal")
        self.assertEqual(record["journal_issns"], ["1234-5678"])
        self.assertEqual(record["journal_issn_l"], "1234-5678")
        self.assertEqual(record["impact_factor"], 6.2)
        self.assertEqual(record["impact_factor_source"], "local_csv")
        self.assertEqual(record["impact_factor_metric"], "impact_factor")
        self.assertEqual(record["impact_factor_year"], 2025)
        self.assertEqual(record["impact_factor_quartile"], "Q1")
        self.assertEqual(record["journal_name"], "Input Journal")
        self.assertEqual(record["journal_impact_value"], 6.2)
        self.assertEqual(record["journal_impact_metric"], "impact_factor")
        self.assertEqual(record["journal_impact_year"], 2025)
        self.assertEqual(record["journal_metric_source"], "local_csv")


if __name__ == "__main__":
    unittest.main()
