from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from omnilit_qt.pdf_extraction_core import analyze_pdf, sha256_file

try:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
except ModuleNotFoundError as exc:  # pragma: no cover - depends on local test runtime.
    raise unittest.SkipTest("reportlab is not installed in this environment") from exc


def write_sample_pdf(path: Path) -> None:
    pdf = canvas.Canvas(str(path), pagesize=letter)
    pdf.setFont("Helvetica", 12)
    pdf.drawString(72, 740, "Sample extraction PDF")

    left, top = 72, 700
    col_widths = [120, 120]
    row_height = 24
    rows = [["Material", "Capacity"], ["Sulfur", "1672"], ["Carbon", "420"]]
    for row_index, row in enumerate(rows):
        y = top - row_index * row_height
        for col_index, cell in enumerate(row):
            x = left + sum(col_widths[:col_index])
            pdf.rect(x, y - row_height, col_widths[col_index], row_height, stroke=1, fill=0)
            pdf.drawString(x + 6, y - 16, cell)

    pdf.setFont("Helvetica", 13)
    pdf.drawCentredString(306, 560, "E = mc^2 (1)")

    pdf.setStrokeColorRGB(0.1, 0.45, 0.2)
    pdf.setLineWidth(2)
    pdf.rect(150, 400, 260, 90, stroke=1, fill=0)
    pdf.setFont("Helvetica", 10)
    pdf.drawCentredString(280, 382, "Figure 1. Rectangular image area")
    pdf.save()


class PdfExtractionCoreTests(unittest.TestCase):
    def test_analyze_pdf_outputs_index_and_export_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pdf_path = root / "sample.pdf"
            output_dir = root / "extraction"
            write_sample_pdf(pdf_path)

            index = analyze_pdf(pdf_path, output_dir)

            self.assertEqual(index["sourceSha256"], sha256_file(pdf_path))
            self.assertEqual(index["pageCount"], 1)
            self.assertTrue((output_dir / "extraction_index.json").exists())
            saved = json.loads((output_dir / "extraction_index.json").read_text(encoding="utf-8"))
            element_types = {element["type"] for element in saved["elements"]}
            self.assertIn("table", element_types)
            self.assertIn("figure", element_types)
            self.assertIn("formula", element_types)

            table = next(element for element in saved["elements"] if element["type"] == "table")
            self.assertTrue(Path(table["csvPath"]).exists())
            self.assertTrue(Path(table["jsonPath"]).exists())
            self.assertIn("Sulfur", Path(table["csvPath"]).read_text(encoding="utf-8-sig"))
            table_json = json.loads(Path(table["jsonPath"]).read_text(encoding="utf-8"))
            self.assertIn(["Sulfur", "1672"], table_json["rows"])

            figure = next(element for element in saved["elements"] if element["type"] == "figure")
            self.assertTrue(Path(figure["pngPath"]).exists())
            self.assertGreater(figure["metadata"].get("imageWidth", 0), 0)
            self.assertGreater(figure["metadata"].get("imageHeight", 0), 0)

            formula = next(element for element in saved["elements"] if element["type"] == "formula")
            self.assertIn("E = mc^2", formula["text"])
            self.assertTrue(Path(formula["pngPath"]).exists())


if __name__ == "__main__":
    unittest.main()
