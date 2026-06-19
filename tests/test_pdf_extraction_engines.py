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
        index["rawOutputs"][self.name] = str(output_dir / self.name)
        if self.name == "mineru":
            index["markdownPath"] = str(output_dir / "mineru.md")
        return index


class PdfExtractionEngineTests(unittest.TestCase):
    def test_cloud_cache_marker_survives_merge(self) -> None:
        class CloudEngine(FakeEngine):
            def analyze(self, pdf_path: Path, output_dir: Path, options: dict[str, Any] | None = None) -> dict[str, Any]:
                index = super().analyze(pdf_path, output_dir, options)
                index["parserConfigVersion"] = "cloud-api-v1"
                index["providerMode"] = "cloud-api"
                return index

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pdf_path = root / "sample.pdf"
            pdf_path.write_bytes(b"%PDF-1.4 mocked")
            pipeline = HybridExtractionPipeline([CloudEngine("paddleocr_vl")], FakeEngine("pymupdf"))

            index = pipeline.analyze(pdf_path, root / "out", {"engine": "paddleocr_vl"})

            self.assertEqual(index["parserConfigVersion"], "cloud-api-v1")
            self.assertEqual(index["providerMode"], "cloud-api")

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

    def test_paddle_failure_keeps_pymupdf_without_running_mineru(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pdf_path = root / "sample.pdf"
            pdf_path.write_bytes(b"%PDF-1.4 fake for mocked engines")
            paddle = FakeEngine("paddleocr_vl", fail=RuntimeError("paddle unavailable"))
            mineru = FakeEngine("mineru")
            pipeline = HybridExtractionPipeline(
                engines=[paddle, mineru],
                fallback_engine=FakeEngine("pymupdf"),
            )

            index = pipeline.analyze(pdf_path, root / "out", {"engine": "paddleocr_vl"})

            self.assertEqual(index["engine"], "pymupdf")
            self.assertEqual(index["engineChain"], ["pymupdf"])
            self.assertEqual(index["engineErrors"][0]["engine"], "paddleocr_vl")
            self.assertEqual(paddle.calls, 1)
            self.assertEqual(mineru.calls, 0)
            saved = json.loads((root / "out" / "extraction_index.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["version"], 3)

    def test_retired_hybrid_engine_is_unsupported(self) -> None:
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
            self.assertEqual([error["engine"] for error in index["engineErrors"]], ["hybrid"])
            self.assertEqual(index["engineErrors"][0]["code"], "UNSUPPORTED_ENGINE")
            self.assertEqual(index["elements"][0]["engine"], "pymupdf")


if __name__ == "__main__":
    unittest.main()
