from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from omnilit_qt.pdf_extraction_core import sha256_file
from omnilit_qt.pdf_extraction_engines import HybridExtractionPipeline, PyMuPDFExtractionEngine
from omnilit_qt.pdf_extraction_schema import make_base_index, make_element


class FakeEngine:
    def __init__(
        self,
        name: str,
        *,
        available: bool = True,
        fail: Exception | None = None,
        elements: list[dict[str, Any]] | None = None,
    ) -> None:
        self.name = name
        self.available = available
        self.fail = fail
        self.elements = elements or []

    def is_available(self) -> bool:
        return self.available

    def analyze(self, pdf_path: Path, output_dir: Path, options: dict[str, Any] | None = None) -> dict[str, Any]:
        if self.fail is not None:
            raise self.fail
        index = make_base_index(pdf_path, output_dir, self.name, page_count=1)
        index["pages"] = [{"page": 0, "width": 100.0, "height": 120.0, "rect": [0.0, 0.0, 100.0, 120.0]}]
        index["elements"] = list(self.elements)
        index["rawOutputs"][self.name] = str(output_dir / self.name)
        if self.name == "mineru":
            index["markdownPath"] = str(output_dir / "mineru.md")
        return index


class PdfExtractionEngineTests(unittest.TestCase):
    def test_pymupdf_engine_outputs_version_3(self) -> None:
        engine = PyMuPDFExtractionEngine()
        if not engine.is_available():
            self.skipTest("PyMuPDF is not installed in this environment")

        import fitz

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pdf_path = root / "sample.pdf"
            doc = fitz.open()
            page = doc.new_page()
            page.insert_text((72, 72), "PyMuPDF engine smoke test")
            doc.save(str(pdf_path))
            doc.close()

            index = engine.analyze(pdf_path, root / "out")

            self.assertEqual(index["version"], 3)
            self.assertEqual(index["engine"], "pymupdf")
            self.assertEqual(index["engineChain"], ["pymupdf"])
            self.assertEqual(index["sourceSha256"], sha256_file(pdf_path))

    def test_hybrid_pipeline_falls_back_to_mineru_when_paddle_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pdf_path = root / "sample.pdf"
            pdf_path.write_bytes(b"%PDF-1.4 fake for mocked engines")
            mineru_element = make_element(
                "mineru-table-1",
                "table",
                0,
                [1, 2, 30, 40],
                [100, 120],
                engine="mineru",
                confidence=0.91,
                text="deep table",
            )
            pipeline = HybridExtractionPipeline(
                engines=[
                    FakeEngine("paddleocr_vl", fail=RuntimeError("paddle unavailable")),
                    FakeEngine("mineru", elements=[mineru_element]),
                ],
                fallback_engine=FakeEngine("pymupdf"),
            )

            index = pipeline.analyze(pdf_path, root / "out", {"engine": "paddleocr_vl"})

            self.assertEqual(index["engine"], "fusion")
            self.assertIn("pymupdf", index["engineChain"])
            self.assertIn("mineru", index["engineChain"])
            self.assertTrue(any(element["engine"] == "mineru" for element in index["elements"]))
            self.assertEqual(index["engineErrors"][0]["engine"], "paddleocr_vl")
            saved = json.loads((root / "out" / "extraction_index.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["version"], 3)

    def test_hybrid_pipeline_keeps_pymupdf_when_deep_engines_fail(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pdf_path = root / "sample.pdf"
            pdf_path.write_bytes(b"%PDF-1.4 fake for mocked engines")
            base_element = make_element(
                "pymupdf-figure-1",
                "figure",
                0,
                [1, 2, 30, 40],
                [100, 120],
                engine="pymupdf",
                confidence=0.65,
            )
            pipeline = HybridExtractionPipeline(
                engines=[
                    FakeEngine("paddleocr_vl", fail=RuntimeError("paddle exploded")),
                    FakeEngine("mineru", fail=RuntimeError("mineru exploded")),
                ],
                fallback_engine=FakeEngine("pymupdf", elements=[base_element]),
            )

            index = pipeline.analyze(pdf_path, root / "out", {"engine": "hybrid"})

            self.assertEqual(index["engine"], "pymupdf")
            self.assertEqual(index["engineChain"], ["pymupdf"])
            self.assertEqual([error["engine"] for error in index["engineErrors"]], ["paddleocr_vl", "mineru"])
            self.assertEqual(index["elements"][0]["engine"], "pymupdf")


if __name__ == "__main__":
    unittest.main()
