from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from omnilit_qt.pdf_extraction_eval import evaluate_extraction_files, evaluate_extraction_index
from omnilit_qt.pdf_extraction_schema import make_base_index, make_element


def _index(elements: list[dict], engine: str = "pymupdf") -> dict:
    source = Path(__file__)
    index = make_base_index(source, Path(tempfile.gettempdir()), engine, page_count=1)
    index["pages"] = [{"page": 0, "width": 400.0, "height": 600.0, "rect": [0, 0, 400, 600], "textBlocks": []}]
    index["elements"] = elements
    return index


class PdfExtractionEvalTests(unittest.TestCase):
    def test_matching_golden_table_and_formula_passes(self) -> None:
        golden = {
            "name": "sample-golden",
            "expectedElements": [
                {
                    "id": "gold-table",
                    "type": "table",
                    "page": 0,
                    "bbox": [10, 20, 180, 100],
                    "pageSize": [400, 600],
                    "caption": "Table 1 Capacity summary",
                    "tableShape": [3, 2],
                    "needsReview": False,
                },
                {
                    "id": "gold-formula",
                    "type": "formula",
                    "page": 0,
                    "bbox": [120, 160, 260, 190],
                    "pageSize": [400, 600],
                    "latex": "E = mc^2",
                    "needsReview": False,
                },
            ],
        }
        actual = _index(
            [
                make_element(
                    "actual-table",
                    "table",
                    0,
                    [12, 22, 178, 98],
                    [400, 600],
                    table=[["Material", "Capacity"], ["Sulfur", "1672"], ["Carbon", "420"]],
                    caption="Table 1 Capacity summary",
                    confidence=0.9,
                    needs_review=False,
                ),
                make_element(
                    "actual-formula",
                    "formula",
                    0,
                    [120, 160, 260, 190],
                    [400, 600],
                    latex="E = mc^2",
                    text="E = mc^2",
                    png_path="clips/f1.png",
                    confidence=0.86,
                    needs_review=False,
                    quality_flags=[],
                ),
            ]
        )

        report = evaluate_extraction_index(actual, golden)

        self.assertTrue(report["summary"]["passed"])
        self.assertEqual(report["summary"]["matchedCount"], 2)
        self.assertEqual(report["issues"], [])
        self.assertGreater(report["summary"]["meanBBoxIoU"], 0.9)

    def test_table_shape_latex_needs_review_and_extra_elements_are_reported(self) -> None:
        golden = {
            "expectedElements": [
                {
                    "id": "gold-table",
                    "type": "table",
                    "page": 0,
                    "bbox": [10, 20, 180, 100],
                    "pageSize": [400, 600],
                    "caption": "Table 1 Capacity summary",
                    "tableShape": [3, 2],
                    "needsReview": False,
                },
                {
                    "id": "gold-formula",
                    "type": "formula",
                    "page": 0,
                    "bbox": [120, 160, 260, 190],
                    "pageSize": [400, 600],
                    "latex": "\\frac{a}{b} = c",
                    "needsReview": False,
                },
            ],
        }
        actual = _index(
            [
                make_element(
                    "actual-table",
                    "table",
                    0,
                    [10, 20, 180, 100],
                    [400, 600],
                    table=[["Material"], ["Sulfur"]],
                    caption="Table 1 Capacity summary",
                    needs_review=True,
                ),
                make_element(
                    "actual-formula",
                    "formula",
                    0,
                    [120, 160, 260, 190],
                    [400, 600],
                    latex="a / b",
                    text="a / b",
                    confidence=0.5,
                    needs_review=True,
                ),
                make_element("extra-table", "table", 0, [250, 260, 350, 320], [400, 600], table=[["Noise", "1"]]),
            ]
        )

        report = evaluate_extraction_index(actual, golden)
        codes = {issue["code"] for issue in report["issues"]}

        self.assertFalse(report["summary"]["passed"])
        self.assertIn("table_shape_mismatch", codes)
        self.assertIn("latex_mismatch", codes)
        self.assertIn("needs_review_mismatch", codes)
        self.assertIn("unexpected_element", codes)
        self.assertIn("count_mismatch", codes)

    def test_reading_order_mismatch_is_reported(self) -> None:
        golden = {
            "expectedElements": [
                {"id": "gold-formula", "type": "formula", "page": 0, "bbox": [10, 20, 100, 40], "pageSize": [400, 600], "latex": "x = 1"},
                {"id": "gold-table", "type": "table", "page": 0, "bbox": [10, 80, 180, 140], "pageSize": [400, 600], "tableShape": [2, 2]},
            ]
        }
        actual = _index(
            [
                make_element("actual-table", "table", 0, [10, 80, 180, 140], [400, 600], table=[["A", "B"], ["1", "2"]]),
                make_element("actual-formula", "formula", 0, [10, 20, 100, 40], [400, 600], latex="x = 1", text="x = 1", png_path="x.png"),
            ]
        )

        report = evaluate_extraction_index(actual, golden)

        self.assertFalse(report["summary"]["passed"])
        self.assertIn("reading_order_mismatch", {issue["code"] for issue in report["issues"]})

    def test_formula_number_mismatch_is_reported(self) -> None:
        golden = {
            "expectedElements": [
                {"id": "gold-formula", "type": "formula", "page": 0, "latex": "E = mc^2", "formulaNumber": "2", "pageSize": [400, 600]},
            ]
        }
        actual = _index(
            [
                make_element(
                    "actual-formula",
                    "formula",
                    0,
                    [],
                    [400, 600],
                    latex="E = mc^2",
                    text="E = mc^2 (1)",
                    png_path="x.png",
                    metadata={"formulaNumber": "1"},
                ),
            ]
        )

        report = evaluate_extraction_index(actual, golden)

        self.assertFalse(report["summary"]["passed"])
        self.assertIn("formula_number_mismatch", {issue["code"] for issue in report["issues"]})

    def test_evaluate_extraction_files_writes_report(self) -> None:
        golden = {"expectedElements": [{"id": "f1", "type": "formula", "page": 0, "latex": "x = 1", "pageSize": [400, 600]}]}
        actual = _index([make_element("f1", "formula", 0, [], [400, 600], latex="x = 1", text="x = 1", png_path="f1.png")])

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            actual_path = root / "actual.json"
            golden_path = root / "golden.json"
            report_path = root / "quality_report.json"
            actual_path.write_text(json.dumps(actual), encoding="utf-8")
            golden_path.write_text(json.dumps(golden), encoding="utf-8")

            report = evaluate_extraction_files(actual_path, golden_path, report_path)

            self.assertTrue(report_path.exists())
            self.assertEqual(json.loads(report_path.read_text(encoding="utf-8"))["summary"], report["summary"])


if __name__ == "__main__":
    unittest.main()
