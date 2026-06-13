from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any

from omnilit_qt.pdf_extraction_engines import HybridExtractionPipeline
from omnilit_qt.pdf_extraction_schema import make_base_index, make_element
from omnilit_qt.pdf_extraction_settings import normalize_engine_id


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
        return index


class PdfExtractionAutoRuntimeTests(unittest.TestCase):
    def test_engine_id_normalization_handles_reported_paddle_typo(self) -> None:
        self.assertEqual(normalize_engine_id("paddleocr_vI"), "paddleocr_vl")
        self.assertEqual(normalize_engine_id("paddleocr_vl"), "paddleocr_vl")
        self.assertEqual(normalize_engine_id("paddleocr-vl"), "paddleocr_vl")
        self.assertEqual(normalize_engine_id("hybrid"), "auto")

    def test_auto_pipeline_uses_mineru_after_paddle_not_initialized(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pdf_path = root / "sample.pdf"
            pdf_path.write_bytes(b"%PDF-1.4 mocked")
            mineru_element = make_element("m1", "formula", 0, [1, 2, 3, 4], [100, 120], engine="mineru", text="x")
            pipeline = HybridExtractionPipeline(
                engines=[
                    FakeEngine("paddleocr_vl", available=False),
                    FakeEngine("mineru", available=False, elements=[mineru_element]),
                ],
                fallback_engine=FakeEngine("pymupdf"),
            )

            index = pipeline.analyze(pdf_path, root / "out", {"engine": "auto"})

        self.assertIn("pymupdf", index["engineChain"])
        self.assertIn("mineru", index["engineChain"])
        self.assertEqual(index["engineErrors"][0]["engine"], "paddleocr_vl")
        self.assertEqual(index["engineErrors"][0]["level"], "info")
        self.assertTrue(any(element["engine"] == "mineru" for element in index["elements"]))

    def test_mineru_auto_initialization_failure_keeps_pymupdf(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pdf_path = root / "sample.pdf"
            pdf_path.write_bytes(b"%PDF-1.4 mocked")
            pymupdf_element = make_element("p1", "figure", 0, [1, 2, 3, 4], [100, 120], engine="pymupdf")
            pipeline = HybridExtractionPipeline(
                engines=[
                    FakeEngine("paddleocr_vl", available=False),
                    FakeEngine("mineru", available=False, fail=RuntimeError("MinerU 自动初始化失败，已回退到 PyMuPDF。")),
                ],
                fallback_engine=FakeEngine("pymupdf", elements=[pymupdf_element]),
            )

            index = pipeline.analyze(pdf_path, root / "out", {"engine": "auto"})

        self.assertEqual(index["engine"], "pymupdf")
        self.assertEqual(index["engineChain"], ["pymupdf"])
        self.assertEqual([error["engine"] for error in index["engineErrors"]], ["paddleocr_vl", "mineru"])
        self.assertEqual(index["engineErrors"][1]["level"], "warning")
        self.assertTrue(index["elements"][0]["needsReview"])


if __name__ == "__main__":
    unittest.main()
