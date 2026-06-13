from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

from omnilit_qt.pdf_extraction_engines import HybridExtractionPipeline
from omnilit_qt.pdf_extraction_paddleocr_vl import (
    EngineUnavailable,
    PaddleOCRVLConfig,
    PaddleOCRVLExtractionEngine,
    html_table_to_rows,
    markdown_table_to_rows,
)
from omnilit_qt.pdf_extraction_schema import make_base_index


class FakeFallbackEngine:
    name = "pymupdf"

    def is_available(self) -> bool:
        return True

    def analyze(self, pdf_path: Path, output_dir: Path, options: dict[str, Any] | None = None) -> dict[str, Any]:
        index = make_base_index(pdf_path, output_dir, self.name, page_count=1)
        index["pages"] = [{"page": 0, "width": 100.0, "height": 120.0, "rect": [0.0, 0.0, 100.0, 120.0]}]
        return index


class PaddleOCRVLExtractionEngineTests(unittest.TestCase):
    def test_is_available_false_when_mode_off(self) -> None:
        with patch.dict("os.environ", {"OMNILIT_PADDLEOCR_VL_MODE": "off"}, clear=True):
            engine = PaddleOCRVLExtractionEngine()
            self.assertFalse(engine.is_available())

    def test_markdown_and_html_tables_parse_without_bs4(self) -> None:
        self.assertEqual(
            markdown_table_to_rows("| A | B |\n|---|---|\n| 1 | 2 |"),
            [["A", "B"], ["1", "2"]],
        )
        self.assertEqual(
            html_table_to_rows("<table><tr><th>A</th><th>B</th></tr><tr><td>1</td><td>2</td></tr></table>"),
            [["A", "B"], ["1", "2"]],
        )

    def test_analyze_normalizes_table_formula_and_figure(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pdf_path = root / "sample.pdf"
            pdf_path.write_bytes(b"%PDF-1.4 mocked")
            config = PaddleOCRVLConfig(
                enabled=True,
                mode="service",
                server_url="http://127.0.0.1:8118/v1",
                model="PaddlePaddle/PaddleOCR-VL-1.6",
                pipeline_version="v1.6",
                python=sys.executable,
                timeout=900,
            )

            def fake_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
                output_dir = Path(cmd[cmd.index("--output") + 1])
                output_dir.mkdir(parents=True, exist_ok=True)
                (output_dir / "paddleocr_vl_result.json").write_text(
                    json.dumps(
                        {
                            "pages": [
                                {
                                    "page": 0,
                                    "blocks": [
                                        {
                                            "block_label": "table",
                                            "page": 0,
                                            "bbox": [10, 20, 70, 80],
                                            "markdown": "| A | B |\n|---|---|\n| 1 | 2 |",
                                        },
                                        {
                                            "block_label": "formula",
                                            "page": 0,
                                            "bbox": [15, 90, 85, 104],
                                            "markdown": "E = mc^2",
                                        },
                                        {
                                            "block_label": "figure",
                                            "page": 0,
                                            "caption": "Figure 1. Architecture",
                                        },
                                    ],
                                }
                            ]
                        }
                    ),
                    encoding="utf-8",
                )
                (output_dir / "paddleocr_vl.md").write_text("# Parsed paper", encoding="utf-8")
                return subprocess.CompletedProcess(cmd, 0, "", "")

            with patch("subprocess.run", side_effect=fake_run) as run_mock:
                index = PaddleOCRVLExtractionEngine(config).analyze(pdf_path, root / "out")

            self.assertTrue(run_mock.called)
            self.assertEqual(index["version"], 3)
            self.assertEqual(index["engine"], "paddleocr_vl")
            self.assertEqual(index["engineChain"], ["paddleocr_vl"])
            self.assertEqual(index["markdownPath"], str(root / "out" / "paddleocr_vl" / "paddleocr_vl.md"))
            self.assertEqual({element["type"] for element in index["elements"]}, {"table", "formula", "figure"})

            table = next(element for element in index["elements"] if element["type"] == "table")
            self.assertEqual(table["engine"], "paddleocr_vl")
            self.assertEqual(table["confidence"], 0.88)
            self.assertEqual(table["table"], [["A", "B"], ["1", "2"]])
            self.assertTrue(Path(table["csvPath"]).exists())
            self.assertTrue(Path(table["jsonPath"]).exists())

            formula = next(element for element in index["elements"] if element["type"] == "formula")
            self.assertEqual(formula["latex"], "E = mc^2")
            self.assertFalse(formula["needsReview"])

            figure = next(element for element in index["elements"] if element["type"] == "figure")
            self.assertEqual(figure["bbox"], [])
            self.assertEqual(figure["confidence"], 0.65)
            self.assertTrue(figure["needsReview"])

    def test_subprocess_timeout_records_engine_error_in_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pdf_path = root / "sample.pdf"
            pdf_path.write_bytes(b"%PDF-1.4 mocked")
            config = PaddleOCRVLConfig(
                enabled=True,
                mode="service",
                server_url="http://127.0.0.1:8118/v1",
                model="PaddlePaddle/PaddleOCR-VL-1.6",
                pipeline_version="v1.6",
                python=sys.executable,
                timeout=1,
            )
            pipeline = HybridExtractionPipeline(
                engines=[PaddleOCRVLExtractionEngine(config)],
                fallback_engine=FakeFallbackEngine(),
            )

            with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=["python"], timeout=1)):
                index = pipeline.analyze(pdf_path, root / "out", {"engine": "paddleocr_vl"})

            self.assertEqual(index["engine"], "pymupdf")
            self.assertIn("engineErrors", index)
            self.assertEqual(index["engineErrors"][0]["engine"], "paddleocr_vl")
            self.assertEqual(index["engineErrors"][0]["type"], "EngineUnavailable")
            self.assertIn("timed out", index["engineErrors"][0]["message"])

    def test_subprocess_timeout_raises_from_engine(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pdf_path = root / "sample.pdf"
            pdf_path.write_bytes(b"%PDF-1.4 mocked")
            config = PaddleOCRVLConfig(
                enabled=True,
                mode="subprocess",
                server_url="",
                model="PaddlePaddle/PaddleOCR-VL-1.6",
                pipeline_version="v1.6",
                python=sys.executable,
                timeout=1,
            )

            with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=["python"], timeout=1)):
                with self.assertRaises(EngineUnavailable):
                    PaddleOCRVLExtractionEngine(config).analyze(pdf_path, root / "out")


if __name__ == "__main__":
    unittest.main()
