from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

from omnilit_qt.pdf_cloud_client import CloudAPIClient
from omnilit_qt.pdf_extraction_engines import HybridExtractionPipeline
from omnilit_qt.pdf_extraction_mineru import (
    EngineUnavailable,
    MinerUConfig,
    MinerUExtractionEngine,
    discover_mineru_outputs,
    parse_mineru_json_files,
)
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
    def test_cloud_api_uploads_polls_and_normalizes_archive(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pdf_path = root / "sample.pdf"
            write_blank_pdf(pdf_path)
            config = MinerUConfig(True, "api", "", "", "https://mineru.example/api/v4", 30, "pipeline", "token-value", 0)
            responses = [
                {"code": 0, "data": {"batch_id": "batch-1", "file_urls": ["https://upload.example/file?sig=secret"]}},
                {"code": 0, "data": {"extract_result": [{"status": "done", "full_zip_url": "https://download.example/result.zip?sig=secret"}]}},
            ]

            def fake_download(client: CloudAPIClient, url: str, target: Path) -> Path:
                with zipfile.ZipFile(target, "w") as bundle:
                    bundle.writestr(
                        "paper_content_list.json",
                        json.dumps([{"type": "formula", "page_idx": 0, "bbox": [100, 100, 500, 200], "latex_text": "$a+b$"}]),
                    )
                return target

            with patch.object(CloudAPIClient, "request_json", side_effect=responses), patch.object(CloudAPIClient, "request") as request_mock, patch.object(CloudAPIClient, "download", autospec=True, side_effect=fake_download):
                index = MinerUExtractionEngine(config).analyze(pdf_path, root / "out")

            self.assertTrue(request_mock.called)
            self.assertEqual(index["parserConfigVersion"], "cloud-api-v1")
            self.assertEqual(index["providerMode"], "cloud-api")
            self.assertEqual(index["elements"][0]["latex"], "a+b")

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

    def test_parse_mineru_json_accepts_common_labels_and_one_based_page_numbers(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            raw_dir = root / "mineru_raw"
            image_dir = raw_dir / "images"
            image_dir.mkdir(parents=True)
            (image_dir / "figure-1.png").write_bytes(b"png")
            json_path = raw_dir / "layout.json"
            json_path.write_text(
                json.dumps(
                    {
                        "pages": [
                            {
                                "page_no": 1,
                                "page_width": 2000,
                                "page_height": 1000,
                                "blocks": [
                                    {
                                        "type": "isolate_formula",
                                        "bbox": [100, 100, 500, 200],
                                        "latex_text": "$a+b$",
                                    },
                                    {
                                        "type": "image_body",
                                        "bbox": [600, 200, 900, 600],
                                        "image": {"path": "images/figure-1.png"},
                                        "caption": "Nested image path",
                                    },
                                ],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            pages = [{"page": 0, "width": 200.0, "height": 100.0, "rect": [0, 0, 200, 100]}]

            elements = parse_mineru_json_files([json_path], pages, root, raw_dir)

            self.assertEqual([element["page"] for element in elements], [0, 0])
            self.assertEqual({element["type"] for element in elements}, {"formula", "figure"})
            formula = next(element for element in elements if element["type"] == "formula")
            self.assertEqual(formula["latex"], "a+b")
            self.assertEqual(formula["bbox"], [10.0, 10.0, 50.0, 20.0])
            figure = next(element for element in elements if element["type"] == "figure")
            self.assertEqual(figure["caption"], "Nested image path")
            self.assertTrue(figure["pngPath"].endswith("figure-1.png"))
            self.assertTrue(Path(figure["pngPath"]).exists())

    def test_discover_mineru_outputs_accepts_variant_layout_pdf_names(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            raw_dir = Path(temp)
            layout_pdf = raw_dir / "sample_layout.pdf"
            layout_pdf.write_bytes(b"%PDF-1.4")

            discovered = discover_mineru_outputs(raw_dir)

            self.assertEqual(discovered["layout_pdf"], layout_pdf)

    def test_content_list_table_body_is_preferred_scaled_and_not_duplicated(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            content_path = root / "paper_content_list.json"
            middle_path = root / "paper_middle.json"
            table = {
                "type": "table",
                "page_idx": 0,
                "bbox": [65, 80, 931, 268],
                "table_caption": ["Table 1 Results"],
                "table_body": "<table><tr><th>A</th><th>B</th></tr><tr><td>1</td><td>2</td></tr></table>",
            }
            content_path.write_text(json.dumps([table]), encoding="utf-8")
            middle_path.write_text(json.dumps({"pages": [{"page": 0, "blocks": [table, table]}]}), encoding="utf-8")
            pages = [{"page": 0, "width": 595.0, "height": 779.0, "rect": [0, 0, 595, 779]}]

            elements = parse_mineru_json_files([middle_path, content_path], pages, root, root)

            self.assertEqual(len(elements), 1)
            self.assertEqual(elements[0]["table"], [["A", "B"], ["1", "2"]])
            self.assertEqual(elements[0]["caption"], "Table 1 Results")
            self.assertEqual(elements[0]["bbox"], [38.675, 62.32, 553.945, 208.772])
            self.assertEqual(elements[0]["metadata"]["tableSourceFormat"], "content_list")

    def test_nonzero_cli_with_parseable_output_is_recovered_with_warning(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pdf_path = root / "sample.pdf"
            write_blank_pdf(pdf_path)
            config = MinerUConfig(True, "cli", "mineru", sys.executable, "", 900, "pipeline")

            def fake_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
                engine_dir = Path(cmd[cmd.index("--output") + 1])
                raw_dir = engine_dir / "mineru_raw"
                raw_dir.mkdir(parents=True, exist_ok=True)
                (raw_dir / "sample_content_list.json").write_text(
                    json.dumps([{"type": "table", "page_idx": 0, "bbox": [100, 100, 900, 500], "table_body": "<table><tr><td>A</td><td>B</td></tr></table>"}]),
                    encoding="utf-8",
                )
                return subprocess.CompletedProcess(cmd, 1, "service shutdown warning", "")

            with patch("subprocess.run", side_effect=fake_run):
                index = MinerUExtractionEngine(config).analyze(pdf_path, root / "out")

            self.assertEqual(index["engine"], "mineru")
            self.assertEqual(len(index["elements"]), 1)
            self.assertEqual(index["engineErrors"][0]["code"], "NONZERO_WITH_OUTPUT")

    def test_timeout_with_parseable_output_is_recovered_with_warning(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pdf_path = root / "sample.pdf"
            write_blank_pdf(pdf_path)
            config = MinerUConfig(True, "cli", "mineru", sys.executable, "", 1, "pipeline")

            def fake_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
                engine_dir = Path(cmd[cmd.index("--output") + 1])
                raw_dir = engine_dir / "mineru_raw"
                raw_dir.mkdir(parents=True, exist_ok=True)
                (raw_dir / "sample_content_list.json").write_text(
                    json.dumps([{"type": "table", "page_idx": 0, "bbox": [100, 100, 900, 500], "table_body": "<table><tr><td>A</td><td>B</td></tr></table>"}]),
                    encoding="utf-8",
                )
                raise subprocess.TimeoutExpired(cmd, 1)

            with patch("subprocess.run", side_effect=fake_run):
                index = MinerUExtractionEngine(config).analyze(pdf_path, root / "out")

            self.assertEqual(len(index["elements"]), 1)
            self.assertEqual(index["engineErrors"][0]["code"], "TIMEOUT_WITH_OUTPUT")

    def test_explicit_mineru_pipeline_runs_only_mineru(self) -> None:
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
                (raw_dir / "sample.md").write_text("MinerU result", encoding="utf-8")
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
                engines=[FakeEngine("paddleocr_vl", RuntimeError("paddle must not run")), MinerUExtractionEngine(config)],
                fallback_engine=FakeEngine("pymupdf"),
            )
            with patch("subprocess.run", side_effect=fake_run):
                index = pipeline.analyze(pdf_path, root / "out", {"engine": "mineru"})

            self.assertEqual(index["engine"], "fusion")
            self.assertFalse(any(error["engine"] == "paddleocr_vl" for error in index["engineErrors"]))
            self.assertTrue(any("mineru" in element.get("sourceEngines", []) for element in index["elements"]))


if __name__ == "__main__":
    unittest.main()
