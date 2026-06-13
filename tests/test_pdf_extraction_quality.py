from __future__ import annotations

import unittest

from omnilit_qt.pdf_extraction_quality import apply_quality, score_formula, score_table


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


if __name__ == "__main__":
    unittest.main()
