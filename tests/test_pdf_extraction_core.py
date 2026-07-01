from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from omnilit_qt.pdf_extraction_core import _write_table_json, analyze_pdf, sha256_file

try:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas
    from PIL import Image
except ModuleNotFoundError as exc:  # pragma: no cover - depends on local test runtime.
    raise unittest.SkipTest("reportlab/Pillow is not installed in this environment") from exc


def write_sample_pdf(path: Path) -> None:
    pdf = canvas.Canvas(str(path), pagesize=letter)
    pdf.setFont("Helvetica", 12)
    pdf.drawString(72, 740, "Sample extraction PDF")
    pdf.drawString(72, 720, "The fitted value x = 1 improved stability and should stay body text.")

    left, top = 72, 700
    col_widths = [120, 120]
    row_height = 24
    rows = [["Material", "Capacity"], ["Sulfur", "1672"], ["Carbon", "420"]]
    pdf.setFont("Helvetica", 8)
    pdf.drawString(left, top + 10, "Table 1 Effect of cathode parameters")
    pdf.setFont("Helvetica", 12)
    for row_index, row in enumerate(rows):
        y = top - row_index * row_height
        for col_index, cell in enumerate(row):
            x = left + sum(col_widths[:col_index])
            pdf.rect(x, y - row_height, col_widths[col_index], row_height, stroke=1, fill=0)
            pdf.drawString(x + 6, y - 16, cell)

    pdf.setFont("Helvetica", 13)
    pdf.drawCentredString(306, 560, "E = mc^2 (1)")
    pdf.drawCentredString(306, 525, "a = b + c")
    pdf.drawCentredString(306, 510, "d = e + f (2)")

    sample_image = Image.new("RGB", (4, 4), (37, 99, 235))
    pdf.drawImage(ImageReader(sample_image), 150, 400, width=260, height=90)
    pdf.setFont("Helvetica", 10)
    pdf.drawCentredString(280, 382, "Figure 1. Rectangular image area")
    pdf.save()


def write_borderless_table_pdf(path: Path) -> None:
    pdf = canvas.Canvas(str(path), pagesize=letter)
    pdf.setFont("Helvetica", 9)
    pdf.drawString(72, 740, "Table 1 Borderless measurements")
    pdf.line(72, 734, 500, 734)
    rows = [["Material", "Capacity", "Voltage"], ["Sulfur", "1672", "2.1"], ["Carbon", "420", "3.2"]]
    for row_index, row in enumerate(rows):
        y = 718 - row_index * 18
        for column, value in enumerate(row):
            pdf.drawString(72 + column * 140, y, value)
    pdf.line(72, 660, 500, 660)
    pdf.save()


def write_two_column_prose_pdf(path: Path) -> None:
    pdf = canvas.Canvas(str(path), pagesize=letter)
    pdf.setFont("Helvetica", 10)
    for row in range(35):
        y = 740 - row * 18
        pdf.drawString(54, y, f"Left column paragraph line {row} with value {row + 10} and ordinary prose.")
        pdf.drawString(324, y, f"Right column paragraph line {row} with value {row + 20} and ordinary prose.")
    pdf.save()


def write_separated_formula_number_pdf(path: Path) -> None:
    pdf = canvas.Canvas(str(path), pagesize=letter)
    pdf.setFont("Helvetica", 10)
    pdf.drawString(72, 720, "It is possible to study electrochemical kinetics according the equation:")
    pdf.setFont("Times-Italic", 12)
    pdf.drawCentredString(306, 695, "I = av^b")
    pdf.setFont("Helvetica", 10)
    pdf.drawRightString(520, 695, "(2)")
    pdf.drawString(72, 670, "where i represents the current and v is the sweep rate.")
    pdf.save()


def write_table_with_header_text_above_detected_body_pdf(path: Path) -> None:
    pdf = canvas.Canvas(str(path), pagesize=letter)
    pdf.setFont("Helvetica", 8)
    pdf.drawCentredString(306, 740, "Table 1. Impedance parameter values extracted from the equivalent circuit.")
    headers = ["Cycle number", "R0 [Ohm]", "Rs [Ohm]", "Rct [Ohm]"]
    rows = [
        ["Fresh cell", "3.8", "-", "197.5"],
        ["1st", "5.2", "33.5", "100.3"],
        ["5th", "2.9", "14", "31.9"],
        ["50th", "3.2", "11.4", "15.7"],
        ["100th", "4", "15.5", "13.9"],
    ]
    x_positions = [170, 285, 350, 415]
    pdf.line(140, 724, 460, 724)
    for column, value in enumerate(headers):
        pdf.drawCentredString(x_positions[column], 710, value)
    pdf.line(140, 700, 460, 700)
    for row_index, row in enumerate(rows):
        y = 686 - row_index * 13
        for column, value in enumerate(row):
            pdf.drawCentredString(x_positions[column], y, value)
    pdf.line(140, 618, 460, 618)
    pdf.save()


class PdfExtractionCoreTests(unittest.TestCase):
    def test_table_json_preserves_structure_context_units_and_footnotes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "table.json"
            _write_table_json(
                path,
                {
                    "id": "t1",
                    "type": "table",
                    "page": 2,
                    "bbox": [10, 20, 200, 120],
                    "pageSize": [400, 600],
                    "caption": "Table 3 Performance",
                    "table": [["Metric", "Value"], ["", "mAh"], ["Capacity", "1672"], ["Note: measured at room temperature", ""]],
                    "confidence": 0.72,
                    "needsReview": True,
                    "qualityFlags": ["weak_table_evidence"],
                    "engine": "pymupdf",
                    "sourceEngines": ["pymupdf"],
                },
            )

            payload = json.loads(path.read_text(encoding="utf-8"))

            self.assertEqual(payload["rows"][2], ["Capacity", "1672"])
            self.assertEqual(payload["shape"], {"rows": 4, "columns": 2})
            self.assertEqual(payload["headerRows"], [0])
            self.assertEqual(payload["unitRows"], [1])
            self.assertEqual(payload["footnoteRows"], [3])
            self.assertEqual(payload["quality"]["qualityFlags"], ["weak_table_evidence"])
            self.assertTrue(all("rowspan" in cell and "colspan" in cell for cell in payload["cells"]))

    def test_borderless_captioned_table_is_found_without_page_prose(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pdf_path = root / "borderless.pdf"
            write_borderless_table_pdf(pdf_path)

            index = analyze_pdf(pdf_path, root / "out")

            tables = [element for element in index["elements"] if element["type"] == "table"]
            self.assertEqual(len(tables), 1)
            self.assertIn("Table 1", tables[0]["caption"])
            self.assertIn(["Sulfur", "1672", "2.1"], tables[0]["table"])

    def test_two_column_prose_is_not_treated_as_table(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pdf_path = root / "prose.pdf"
            write_two_column_prose_pdf(pdf_path)

            index = analyze_pdf(pdf_path, root / "out")

            self.assertFalse(any(element["type"] == "table" for element in index["elements"]))

    def test_formula_body_merges_with_separated_right_aligned_number(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pdf_path = root / "separated_formula.pdf"
            write_separated_formula_number_pdf(pdf_path)

            index = analyze_pdf(pdf_path, root / "out")

            formulas = [element for element in index["elements"] if element["type"] == "formula"]
            self.assertEqual(len(formulas), 1)
            self.assertEqual(formulas[0]["latex"], "I = av^b")
            self.assertEqual(formulas[0]["metadata"]["formulaNumber"], "2")
            self.assertNotEqual(formulas[0]["text"], "(2)")

    def test_table_rows_are_reconstructed_from_positioned_text_when_header_is_missed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pdf_path = root / "positioned_table.pdf"
            write_table_with_header_text_above_detected_body_pdf(pdf_path)

            index = analyze_pdf(pdf_path, root / "out")

            tables = [element for element in index["elements"] if element["type"] == "table"]
            self.assertEqual(len(tables), 1)
            table = tables[0]
            self.assertEqual(table["table"][0], ["Cycle number", "R0 [Ohm]", "Rs [Ohm]", "Rct [Ohm]"])
            self.assertIn(["Fresh cell", "3.8", "-", "197.5"], table["table"])
            self.assertIn("reconstruct_from_positioned_text", table["metadata"]["normalization"])

    def test_analyze_pdf_outputs_index_and_export_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pdf_path = root / "sample.pdf"
            output_dir = root / "extraction"
            write_sample_pdf(pdf_path)

            index = analyze_pdf(pdf_path, output_dir)

            self.assertEqual(index["version"], 3)
            self.assertEqual(index["engine"], "pymupdf")
            self.assertEqual(index["engineChain"], ["pymupdf"])
            self.assertEqual(index["sourceSha256"], sha256_file(pdf_path))
            self.assertEqual(index["pageCount"], 1)
            self.assertTrue((output_dir / "extraction_index.json").exists())
            self.assertTrue((output_dir / "quality_report.json").exists())
            self.assertTrue((output_dir / "parsed.md").exists())
            saved = json.loads((output_dir / "extraction_index.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["version"], 3)
            self.assertEqual(saved["engine"], "pymupdf")
            self.assertIn("rawOutputs", saved)
            self.assertIn("qualitySummary", saved)
            self.assertEqual(saved["markdownPath"], str(output_dir / "parsed.md"))
            self.assertEqual(saved["debugFiles"]["qualityReportJson"], str(output_dir / "quality_report.json"))
            quality_report = json.loads((output_dir / "quality_report.json").read_text(encoding="utf-8"))
            self.assertEqual(quality_report["engine"], "pymupdf")
            self.assertEqual(quality_report["summary"]["tables"]["count"], 1)
            markdown = (output_dir / "parsed.md").read_text(encoding="utf-8")
            self.assertIn("# sample", markdown)
            self.assertIn("The fitted value x = 1 improved stability", markdown)
            self.assertIn("| Material | Capacity |", markdown)
            self.assertIn("E = mc^2 \\tag{1}", markdown)
            self.assertIn("![Fig. 1", markdown)
            element_types = {element["type"] for element in saved["elements"]}
            self.assertIn("table", element_types)
            self.assertIn("figure", element_types)
            self.assertIn("formula", element_types)

            table = next(element for element in saved["elements"] if element["type"] == "table")
            self.assertEqual(table["engine"], "pymupdf")
            self.assertGreaterEqual(table["confidence"], 0.75)
            self.assertFalse(table["needsReview"])
            self.assertTrue(Path(table["csvPath"]).exists())
            self.assertTrue(Path(table["jsonPath"]).exists())
            self.assertIn("Sulfur", Path(table["csvPath"]).read_text(encoding="utf-8-sig"))
            table_json = json.loads(Path(table["jsonPath"]).read_text(encoding="utf-8"))
            self.assertEqual(table_json["version"], 2)
            self.assertIn(["Sulfur", "1672"], table_json["rows"])
            self.assertEqual(table_json["id"], table["id"])
            self.assertEqual(table_json["caption"], table["caption"])
            self.assertEqual(table_json["bbox"], table["bbox"])
            self.assertEqual(table_json["shape"]["columns"], 2)
            self.assertEqual(table_json["headerRows"], [0])
            self.assertTrue(any(cell["text"] == "Sulfur" and cell["rowspan"] == 1 and cell["colspan"] == 1 for cell in table_json["cells"]))
            self.assertEqual(table_json["quality"]["confidence"], table["confidence"])
            self.assertEqual(table_json["quality"]["needsReview"], table["needsReview"])
            self.assertEqual(table_json["artifacts"]["csvPath"], table["csvPath"])
            self.assertIn("Table 1", table["caption"])

            figure = next(element for element in saved["elements"] if element["type"] == "figure")
            self.assertEqual(figure["engine"], "pymupdf")
            self.assertGreaterEqual(figure["confidence"], 0.65)
            self.assertFalse(figure["needsReview"])
            self.assertTrue(Path(figure["pngPath"]).exists())
            self.assertGreater(figure["metadata"].get("imageWidth", 0), 0)
            self.assertGreater(figure["metadata"].get("imageHeight", 0), 0)
            self.assertIn("Fig. 1", figure["caption"])
            self.assertGreaterEqual(figure["bbox"][3], figure["captionBBox"][3])
            self.assertIn("imageBBox", figure["metadata"])
            self.assertLess(figure["metadata"]["imageBBox"][3], figure["captionBBox"][1])

            formulas = [element for element in saved["elements"] if element["type"] == "formula"]
            formula = next(element for element in formulas if "E = mc^2" in element["text"])
            self.assertEqual(formula["engine"], "pymupdf")
            self.assertTrue(formula["needsReview"])
            self.assertIn("single_engine_formula", formula["qualityFlags"])
            self.assertIn("E = mc^2", formula["text"])
            self.assertEqual(formula["text"], "E = mc^2 (1)")
            self.assertEqual(formula["latex"], "E = mc^2")
            self.assertEqual(formula["metadata"]["formulaNumber"], "1")
            self.assertTrue(Path(formula["pngPath"]).exists())
            self.assertIn("lineIndex", formula["metadata"])
            self.assertTrue(any("a = b + c d = e + f" in item["text"] for item in formulas))
            self.assertNotIn("fitted value", "\n".join(item["text"] for item in formulas))


if __name__ == "__main__":
    unittest.main()
