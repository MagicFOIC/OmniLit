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
from omnilit_qt.pdf_extraction_mineru import EngineUnavailable, MinerUConfig, MinerUExtractionEngine
from omnilit_qt.pdf_extraction_schema import make_base_index


def write_blank_pdf(path: Path, width: float = 200.0, height: float = 100.0) -> None:
    try:
        import fitz
    except ModuleNotFoundError as exc:  # pragma: no cover - depends on local test runtime.
        raise unittest.SkipTest("PyMuPDF is not installed in this environment") from exc
    doc = fitz.open()
    doc.new_page(width=width, height=height)
    doc.save(str(path))
    doc.close()


class FakeEngine:
    def __init__(self, name: str, fail: Exception | None = None) -> None:
        self.name = name
        self.fail = fail

    def is_available(self) -> bool:
        return True

    def analyze(self, pdf_path: Path, output_dir: Path, options: dict[str, Any] | None = None) -> dict[str, Any]:
        if self.fail:
            raise self.fail
        index = make_base_index(pdf_path, output_dir, self.name, page_count=1)
        index["pages"] = [{"page": 0, "width": 200.0, "height": 100.0, "rect": [0.0, 0.0, 200.0, 100.0]}]
        return index


class MinerUExtractionEngineTests(unittest.TestCase):
    def test_analyze_normalizes_table_formula_and_figure(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pdf_path = root / "sample.pdf"
            write_blank_pdf(pdf_path)
            config = MinerUConfig(
                enabled=True,
                mode="cli",
                command="mineru",
                python=sys.executable,
                api_url="http://127.0.0.1:8000",
                timeout=900,
                backend="pipeline",
            )

            def fake_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
                engine_dir = Path(cmd[cmd.index("--output") + 1])
                raw_dir = engine_dir / "mineru_raw"
                image_dir = raw_dir / "images"
                image_dir.mkdir(parents=True, exist_ok=True)
                (raw_dir / "sample.md").write_text("# MinerU result", encoding="utf-8")
                (image_dir / "fig.png").write_bytes(b"png")
                (raw_dir / "sample.json").write_text(
                    json.dumps(
                        {
                            "pages": [
                                {
                                    "page": 0,
                                    "page_width": 2000,
                                    "page_height": 1000,
                                    "blocks": [
                                        {
                                            "type": "table",
                                            "bbox": [100, 100, 900, 300],
                                            "html": "<table><tr><th>A</th><th>B</th></tr><tr><td>1</td><td>2</td></tr></table>",
                                        },
                                        {
                                            "type": "interline_equation",
                                            "bbox": [100, 400, 500, 500],
                                            "latex": "E = mc^2",
                                        },
                                        {
                                            "type": "image",
                                            "bbox": [600, 400, 1000, 800],
                                            "image_path": "images/fig.png",
                                            "caption": "Figure 1",
                                        },
                                    ],
                                }
                            ]
                        }
                    ),
                    encoding="utf-8",
                )
                return subprocess.CompletedProcess(cmd, 0, "mineru ok", "")

            with patch("subprocess.run", side_effect=fake_run):
                index = MinerUExtractionEngine(config).analyze(pdf_path, root / "out")

            self.assertEqual(index["version"], 3)
            self.assertEqual(index["engine"], "mineru")
            self.assertEqual(index["engineChain"], ["mineru"])
            self.assertEqual(index["markdownPath"], str(root / "out" / "mineru" / "mineru.md"))
            self.assertEqual({element["type"] for element in index["elements"]}, {"table", "formula", "figure"})

            table = next(element for element in index["elements"] if element["type"] == "table")
            self.assertEqual(table["engine"], "mineru")
            self.assertEqual(table["confidence"], 0.82)
            self.assertEqual(table["bbox"], [10.0, 10.0, 90.0, 30.0])
            self.assertEqual(table["table"], [["A", "B"], ["1", "2"]])
            self.assertTrue(Path(table["csvPath"]).exists())
            self.assertTrue(Path(table["jsonPath"]).exists())

            formula = next(element for element in index["elements"] if element["type"] == "formula")
            self.assertEqual(formula["confidence"], 0.84)
            self.assertEqual(formula["latex"], "E = mc^2")
            self.assertEqual(formula["text"], "E = mc^2")

            figure = next(element for element in index["elements"] if element["type"] == "figure")
            self.assertEqual(figure["confidence"], 0.78)
            self.assertEqual(figure["caption"], "Figure 1")
            self.assertTrue(figure["pngPath"].endswith("fig.png"))
            self.assertTrue(Path(figure["pngPath"]).exists())

    def test_cli_not_found_is_unavailable_and_analyze_raises(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pdf_path = root / "sample.pdf"
            pdf_path.write_bytes(b"%PDF-1.4 mocked")
            config = MinerUConfig(
                enabled=True,
                mode="cli",
                command="definitely_missing_mineru_command",
                python="",
                api_url="http://127.0.0.1:8000",
                timeout=900,
                backend="pipeline",
            )
            engine = MinerUExtractionEngine(config)

            self.assertFalse(engine.is_available())
            with self.assertRaises(EngineUnavailable):
                engine.analyze(pdf_path, root / "out")

    def test_hybrid_pipeline_uses_mineru_after_paddle_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pdf_path = root / "sample.pdf"
            write_blank_pdf(pdf_path)
            config = MinerUConfig(
                enabled=True,
                mode="cli",
                command="mineru",
                python=sys.executable,
                api_url="http://127.0.0.1:8000",
                timeout=900,
                backend="pipeline",
            )

            def fake_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
                engine_dir = Path(cmd[cmd.index("--output") + 1])
                raw_dir = engine_dir / "mineru_raw"
                raw_dir.mkdir(parents=True, exist_ok=True)
                (raw_dir / "sample.md").write_text("MinerU fallback", encoding="utf-8")
                (raw_dir / "sample.json").write_text(
                    json.dumps(
                        {
                            "pages": [
                                {
                                    "page": 0,
                                    "page_width": 2000,
                                    "page_height": 1000,
                                    "blocks": [{"type": "formula", "bbox": [100, 100, 500, 200], "latex": "a+b"}],
                                }
                            ]
                        }
                    ),
                    encoding="utf-8",
                )
                return subprocess.CompletedProcess(cmd, 0, "", "")

            pipeline = HybridExtractionPipeline(
                engines=[FakeEngine("paddleocr_vl", RuntimeError("paddle failed")), MinerUExtractionEngine(config)],
                fallback_engine=FakeEngine("pymupdf"),
            )
            with patch("subprocess.run", side_effect=fake_run):
                index = pipeline.analyze(pdf_path, root / "out", {"engine": "hybrid"})

            self.assertEqual(index["engine"], "fusion")
            self.assertEqual(index["engineErrors"][0]["engine"], "paddleocr_vl")
            self.assertTrue(any("mineru" in element.get("sourceEngines", []) for element in index["elements"]))


if __name__ == "__main__":
    unittest.main()
