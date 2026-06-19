from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from omnilit_qt.pdf_extraction_fusion import fuse_pymupdf_mineru_indexes
from omnilit_qt.pdf_extraction_schema import make_base_index, make_element


def _index(engine: str, elements: list[dict]) -> dict:
    source = Path(__file__)
    index = make_base_index(source, Path(tempfile.gettempdir()), engine, page_count=1)
    index["pages"] = [
        {
            "page": 0,
            "width": 400.0,
            "height": 600.0,
            "rect": [0.0, 0.0, 400.0, 600.0],
            "textBlocks": [{"bbox": [110, 250, 290, 270], "text": "Figure 2. Model architecture"}],
        }
    ]
    index["elements"] = elements
    return index


class PdfExtractionFusionTests(unittest.TestCase):
    def test_overlapping_tables_are_fused_with_pymupdf_bbox_and_mineru_rows(self) -> None:
        pymupdf_table = make_element("p-table", "table", 0, [10, 20, 200, 120], [400, 600], engine="pymupdf", table=[["A"]], confidence=0.75)
        mineru_table = make_element("m-table", "table", 0, [12, 22, 198, 118], [400, 600], engine="mineru", table=[["A", "B"], ["1", "2"]], confidence=0.82)

        with tempfile.TemporaryDirectory() as temp:
            fused = fuse_pymupdf_mineru_indexes(_index("pymupdf", [pymupdf_table]), _index("mineru", [mineru_table]), Path(temp))

        table = next(element for element in fused["elements"] if element["type"] == "table")
        self.assertEqual(fused["engine"], "fusion")
        self.assertEqual(table["engine"], "fusion")
        self.assertEqual(table["bbox"], [10.0, 20.0, 200.0, 120.0])
        self.assertEqual(table["table"], [["A", "B"], ["1", "2"]])
        self.assertIn("pymupdf", table["sourceEngines"])
        self.assertIn("mineru", table["sourceEngines"])
        self.assertEqual(table["metadata"]["tableSourceEngine"], "mineru")
        self.assertEqual(table["metadata"]["locationSourceEngine"], "pymupdf")
        self.assertEqual(table["metadata"]["tableShape"], [2, 2])
        self.assertGreater(table["confidence"], pymupdf_table["confidence"])

    def test_table_fusion_keeps_better_pymupdf_rows_when_deep_table_is_sparse(self) -> None:
        pymupdf_table = make_element(
            "p-table",
            "table",
            0,
            [10, 20, 240, 150],
            [400, 600],
            engine="pymupdf",
            table=[["Material", "Capacity", "Unit"], ["Sulfur", "1672", "mAh g-1"], ["Carbon", "420", "mAh g-1"]],
            caption="Table 1",
        )
        mineru_table = make_element("m-table", "table", 0, [12, 22, 238, 148], [400, 600], engine="mineru", table=[["Material"], [""]])

        with tempfile.TemporaryDirectory() as temp:
            fused = fuse_pymupdf_mineru_indexes(_index("pymupdf", [pymupdf_table]), _index("mineru", [mineru_table]), Path(temp))

        table = next(element for element in fused["elements"] if element["type"] == "table")
        self.assertEqual(table["table"], pymupdf_table["table"])
        self.assertEqual(table["metadata"]["tableSourceEngine"], "pymupdf")
        self.assertFalse(table["needsReview"])

    def test_structured_mineru_html_wins_when_shapes_are_equal(self) -> None:
        pymupdf_table = make_element(
            "p-table",
            "table",
            0,
            [10, 20, 240, 150],
            [400, 600],
            engine="pymupdf",
            table=[["Header", "Value"], ["truncated", "1"]],
            caption="Table 1",
        )
        mineru_table = make_element(
            "m-table",
            "table",
            0,
            [12, 22, 238, 148],
            [400, 600],
            engine="mineru",
            table=[["Complete header", "Value"], ["full text", "1"]],
            caption="Table 1 Complete caption",
            html="<table><tr><td>Complete header</td><td>Value</td></tr></table>",
        )

        with tempfile.TemporaryDirectory() as temp:
            fused = fuse_pymupdf_mineru_indexes(_index("pymupdf", [pymupdf_table]), _index("mineru", [mineru_table]), Path(temp))

        table = next(element for element in fused["elements"] if element["type"] == "table")
        self.assertEqual(table["table"], mineru_table["table"])
        self.assertEqual(table["metadata"]["tableSourceEngine"], "mineru")
        self.assertEqual(table["bbox"], pymupdf_table["bbox"])

    def test_formula_latex_without_mineru_bbox_matches_pymupdf_candidate(self) -> None:
        pymupdf_formula = make_element("p-formula", "formula", 0, [120, 200, 280, 230], [400, 600], engine="pymupdf", text="E = mc^2", confidence=0.55)
        mineru_formula = make_element("m-formula", "formula", 0, [], [400, 600], engine="mineru", latex="E = mc^2", confidence=0.84)

        with tempfile.TemporaryDirectory() as temp:
            fused = fuse_pymupdf_mineru_indexes(_index("pymupdf", [pymupdf_formula]), _index("mineru", [mineru_formula]), Path(temp))

        formula = next(element for element in fused["elements"] if element["type"] == "formula")
        self.assertEqual(formula["bbox"], [120.0, 200.0, 280.0, 230.0])
        self.assertEqual(formula["latex"], "E = mc^2")
        self.assertEqual(formula["metadata"]["formulaSourceEngine"], "mineru")
        self.assertEqual(formula["metadata"]["locationSourceEngine"], "pymupdf")
        self.assertGreaterEqual(formula["metadata"]["formulaMatchScore"], 0.9)
        self.assertFalse(formula["needsReview"])

    def test_figure_overlapping_table_is_not_duplicated_as_clean_figure(self) -> None:
        table = make_element("p-table", "table", 0, [10, 20, 200, 120], [400, 600], engine="pymupdf", table=[["A", "B"], ["1", "2"]])
        figure = make_element("p-figure", "figure", 0, [12, 22, 198, 118], [400, 600], engine="pymupdf", png_path="x.png")

        with tempfile.TemporaryDirectory() as temp:
            fused = fuse_pymupdf_mineru_indexes(_index("pymupdf", [table, figure]), _index("mineru", []), Path(temp))

        figures = [element for element in fused["elements"] if element["type"] == "figure"]
        self.assertEqual(figures, [])

    def test_caption_binding_and_bbox_clipping(self) -> None:
        figure = make_element("p-figure", "figure", 0, [100, 100, 300, 240], [400, 600], engine="pymupdf", png_path="x.png")
        out_of_page = make_element("m-figure", "figure", 0, [-5, 320, 500, 390], [400, 600], engine="mineru")

        with tempfile.TemporaryDirectory() as temp:
            fused = fuse_pymupdf_mineru_indexes(_index("pymupdf", [figure]), _index("mineru", [out_of_page]), Path(temp))

        first = next(element for element in fused["elements"] if element["id"] == "p-figure")
        self.assertEqual(first["caption"], "Figure 2. Model architecture")
        self.assertTrue(first["captionBBox"])
        clipped = next(element for element in fused["elements"] if element["id"] == "m-figure")
        self.assertIn("bbox_clipped", clipped["qualityFlags"])
        self.assertTrue(clipped["needsReview"])


if __name__ == "__main__":
    unittest.main()
