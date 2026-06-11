from __future__ import annotations

import unittest
from pathlib import Path

from Download import literature_download_core as core
from Download.journal_metrics import JournalMetric, attach_journal_metric


class DownloadMetadataEnrichmentTests(unittest.TestCase):
    def test_build_record_writes_journal_metric_and_text_aliases(self) -> None:
        item = {
            "id": "https://openalex.org/W-meta",
            "title": "Lithium sulfur battery cathode with polysulfide control",
            "abstract": "This work improves lithium sulfur batteries with sulfur cathode design and polysulfide control.",
            "publication_date": "2025-03-14",
            "publication_year": 2025,
            "open_access": {"is_oa": True},
            "primary_location": {"source": {"display_name": "Batteries", "issn_l": "2313-0105"}},
        }
        metric = JournalMetric(
            journal_title="Batteries",
            issn=["2313-0105"],
            issn_l="2313-0105",
            impact_factor=7.1,
            metric_year=2025,
            source="local_csv",
            quartile="Q1",
        )
        attach_journal_metric(item, metric)

        record = core.build_record(
            "lithium sulfur battery",
            item,
            None,
            core.DownloadResult(None, "download_disabled"),
            [],
            Path("metadata.jsonl"),
            {"matched_keywords": ["sulfur cathode"], "matched_fields": ["title"]},
        )

        self.assertEqual(record["publication_date"], "2025-03-14")
        self.assertEqual(record["publication_year"], 2025)
        self.assertEqual(record["journal_title"], "Batteries")
        self.assertEqual(record["journal_name"], "Batteries")
        self.assertEqual(record["journal_issns"], ["2313-0105"])
        self.assertEqual(record["journal_issn_l"], "2313-0105")
        self.assertEqual(record["impact_factor"], 7.1)
        self.assertEqual(record["impact_factor_source"], "local_csv")
        self.assertEqual(record["impact_factor_metric"], "impact_factor")
        self.assertEqual(record["impact_factor_year"], 2025)
        self.assertEqual(record["impact_factor_quartile"], "Q1")
        self.assertEqual(record["journal_impact_value"], 7.1)
        self.assertEqual(record["journal_impact_metric"], "impact_factor")
        self.assertEqual(record["journal_impact_year"], 2025)
        self.assertEqual(record["journal_metric_source"], "local_csv")
        self.assertEqual(record["summary_text"], record["content_summary"])
        self.assertEqual(record["topic_tags"], record["keyword_groups"])
        self.assertIn("sulfur cathode", record["extracted_keywords"])
        self.assertTrue(record["keyword_groups"])

    def test_content_fields_do_not_read_pdf_text_for_keyword_enrichment(self) -> None:
        item = {
            "title": "Lithium sulfur battery cathode",
            "abstract": "A source abstract with polysulfide control.",
        }

        original_extract_pdf_text = core.extract_pdf_text
        try:
            core.extract_pdf_text = lambda _path: (_ for _ in ()).throw(AssertionError("PDF text should not be read"))
            fields = core.content_fields_for_record(
                "lithium sulfur battery",
                item,
                core.DownloadResult("paper.pdf", "downloaded"),
                Path("metadata.jsonl"),
                {"matched_keywords": ["polysulfide control"]},
            )
        finally:
            core.extract_pdf_text = original_extract_pdf_text

        self.assertEqual(fields["summary_text"], fields["content_summary"])
        self.assertEqual(fields["topic_tags"], fields["keyword_groups"])
        self.assertIn("polysulfide control", fields["extracted_keywords"])


if __name__ == "__main__":
    unittest.main()
