from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from omnilit_qt.pdf_extraction_quality import apply_quality, build_quality_report, score_formula, score_table, write_quality_report


class PdfExtractionQualityTests(unittest.TestCase):
    def test_single_cell_table_scores_low(self) -> None:
        score, flags = score_table({"type": "table", "table": [["x"]], "bbox": [1, 1, 20, 20], "pageSize": [100, 100]})
        self.assertLess(score, 0.65)
        self.assertIn("weak_table_shape", flags)

    def test_multicolumn_captioned_table_scores_high(self) -> None:
        score, flags = score_table(
            {
                "type": "table",
                "table": [["A", "B"], ["1", "2"], ["3", "4"]],
                "bbox": [10, 10, 90, 80],
                "pageSize": [100, 100],
                "caption": "Table 1",
                "sourceEngines": ["pymupdf", "mineru"],
            }
        )
        self.assertGreater(score, 0.75)
        self.assertEqual(flags, [])

    def test_formula_with_latex_and_bbox_scores_high(self) -> None:
        score, flags = score_formula({"type": "formula", "latex": "E = mc^2", "bbox": [10, 10, 90, 30], "pageSize": [100, 100]})
        self.assertGreater(score, 0.65)
        self.assertEqual(flags, [])

    def test_formula_without_bbox_needs_review(self) -> None:
        element = apply_quality({"type": "formula", "latex": "x", "bbox": [], "pageSize": [100, 100], "engine": "mineru"})
        self.assertTrue(element["needsReview"])
        self.assertIn("missing_bbox", element["qualityFlags"])

    def test_single_engine_formula_is_reviewable_even_with_good_text_and_bbox(self) -> None:
        element = apply_quality({"type": "formula", "latex": "E = mc^2", "bbox": [10, 10, 90, 30], "pageSize": [100, 100], "engine": "pymupdf"})
        self.assertTrue(element["needsReview"])
        self.assertIn("single_engine_formula", element["qualityFlags"])

    def test_weak_table_evidence_adds_quality_flag(self) -> None:
        element = apply_quality(
            {
                "type": "table",
                "table": [["A", "B"], ["", ""]],
                "bbox": [10, 10, 90, 80],
                "pageSize": [100, 100],
                "metadata": {"tableEvidenceScore": 0.2},
            }
        )
        self.assertTrue(element["needsReview"])
        self.assertIn("weak_table_evidence", element["qualityFlags"])

    def test_page_sized_unanchored_text_table_needs_review(self) -> None:
        element = apply_quality(
            {
                "type": "table",
                "table": [["body", "text"], ["more", "prose"]],
                "bbox": [5, 5, 95, 95],
                "pageSize": [100, 100],
                "metadata": {"textStrategy": True},
            }
        )
        self.assertTrue(element["needsReview"])
        self.assertIn("unanchored_text_table", element["qualityFlags"])
        self.assertIn("page_sized_table", element["qualityFlags"])

    def test_quality_report_collects_review_items_conflicts_and_schema_warnings(self) -> None:
        index = {
            "sourcePath": "paper.pdf",
            "sourceSha256": "abc",
            "engine": "fusion",
            "engineChain": ["pymupdf", "mineru", "fusion"],
            "pageCount": 1,
            "engineErrors": [{"engine": "mineru", "code": "ENGINE_FAILED", "message": "down"}],
            "elements": [
                {
                    "id": "t1",
                    "type": "table",
                    "page": 0,
                    "bbox": [1, 2, 50, 80],
                    "pageSize": [100, 100],
                    "confidence": 0.4,
                    "needsReview": True,
                    "qualityFlags": ["weak_table_evidence"],
                    "table": [["A"]],
                    "metadata": {"tableEvidenceScore": 0.2},
                    "sourceEngines": ["pymupdf", "mineru"],
                },
                {
                    "id": "f1",
                    "type": "formula",
                    "page": 0,
                    "bbox": [10, 10, 40, 20],
                    "pageSize": [100, 100],
                    "confidence": 0.9,
                    "needsReview": False,
                    "latex": "E = mc^2",
                    "qualityFlags": [],
                    "pngPath": "clips/f1.png",
                    "manualOverride": True,
                    "metadata": {"formulaNumber": "2", "manualOverride": True, "overrideUpdatedAt": "2026-07-01T00:00:00+00:00"},
                },
            ],
        }

        report = build_quality_report(index)

        self.assertEqual(report["summary"]["tables"], {"count": 1, "needsReview": 1})
        self.assertEqual(report["summary"]["formulas"], {"count": 1, "needsReview": 0})
        self.assertEqual(report["summary"]["engineErrors"], 1)
        self.assertEqual(report["summary"]["engineConflicts"], 1)
        self.assertEqual(report["summary"]["schemaWarnings"], 1)
        self.assertEqual(report["summary"]["manualOverrides"], 1)
        self.assertEqual(report["reviewItems"][0]["id"], "t1")
        formula_item = next(item for item in report["lowConfidenceElements"] + report["reviewItems"] if item["id"] == "t1")
        self.assertNotIn("formulaNumber", formula_item)
        self.assertEqual(report["engineConflicts"][0]["conflictFlags"], ["weak_table_evidence"])
        self.assertEqual(report["schemaWarnings"][0]["missingFields"], ["jsonPath", "csvPath", "pngPath"])
        self.assertEqual(report["manualOverrides"][0]["id"], "f1")
        self.assertEqual(report["manualOverrides"][0]["formulaNumber"], "2")
        self.assertEqual(report["manualOverrides"][0]["overrideUpdatedAt"], "2026-07-01T00:00:00+00:00")

    def test_quality_report_includes_formula_number_for_formula_review_items(self) -> None:
        report = build_quality_report(
            {
                "engine": "pymupdf",
                "pageCount": 1,
                "elements": [
                    {
                        "id": "f1",
                        "type": "formula",
                        "page": 0,
                        "bbox": [10, 10, 40, 20],
                        "confidence": 0.4,
                        "needsReview": True,
                        "latex": "E = mc^2",
                        "metadata": {"formulaNumber": "7"},
                    }
                ],
            }
        )

        self.assertEqual(report["reviewItems"][0]["formulaNumber"], "7")

    def test_write_quality_report_outputs_json_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            report_path = write_quality_report(
                Path(temp),
                {"engine": "pymupdf", "pageCount": 1, "elements": [{"id": "f1", "type": "formula", "needsReview": True}]},
            )

            self.assertTrue(report_path.exists())
            saved = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["summary"]["reviewItems"], 1)


if __name__ == "__main__":
    unittest.main()
