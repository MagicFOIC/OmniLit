from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any

from omnilit_qt.pdf_extraction_engines import HybridExtractionPipeline
from omnilit_qt.pdf_extraction_schema import make_base_index
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
        self.calls = 0

    def is_available(self) -> bool:
        return self.available

    def analyze(self, pdf_path: Path, output_dir: Path, options: dict[str, Any] | None = None) -> dict[str, Any]:
        self.calls += 1
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
        self.assertEqual(normalize_engine_id("auto"), "auto")
        self.assertEqual(normalize_engine_id("hybrid"), "hybrid")
        self.assertEqual(normalize_engine_id("deep"), "deep")

    def test_retired_engine_ids_do_not_start_optional_engines(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pdf_path = root / "sample.pdf"
            pdf_path.write_bytes(b"%PDF-1.4 mocked")
            paddle = FakeEngine("paddleocr_vl")
            mineru = FakeEngine("mineru")
            pipeline = HybridExtractionPipeline(
                engines=[paddle, mineru],
                fallback_engine=FakeEngine("pymupdf"),
            )

            for engine_id in ("auto", "hybrid", "deep"):
                index = pipeline.analyze(pdf_path, root / engine_id, {"engine": engine_id})
                self.assertEqual(index["engine"], "pymupdf")
                self.assertEqual(index["engineChain"], ["pymupdf"])
                self.assertEqual(index["engineErrors"][0]["engine"], engine_id)
                self.assertEqual(index["engineErrors"][0]["code"], "UNSUPPORTED_ENGINE")

        self.assertEqual(paddle.calls, 0)
        self.assertEqual(mineru.calls, 0)

    def test_missing_engine_option_defaults_to_fast(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pdf_path = root / "sample.pdf"
            pdf_path.write_bytes(b"%PDF-1.4 mocked")
            paddle = FakeEngine("paddleocr_vl")
            mineru = FakeEngine("mineru")
            pipeline = HybridExtractionPipeline(
                engines=[paddle, mineru],
                fallback_engine=FakeEngine("pymupdf"),
            )

            index = pipeline.analyze(pdf_path, root / "out", {})

        self.assertEqual(index["engine"], "pymupdf")
        self.assertEqual(index["engineChain"], ["pymupdf"])
        self.assertEqual(index["engineErrors"], [])
        self.assertEqual(paddle.calls, 0)
        self.assertEqual(mineru.calls, 0)


if __name__ == "__main__":
    unittest.main()
