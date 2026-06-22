from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

from omnilit_qt.pdf_cloud_client import CloudAPIClient, CloudAPIError
from omnilit_qt.pdf_extraction_engines import HybridExtractionPipeline
from omnilit_qt.pdf_extraction_mineru import MinerUConfig, MinerUExtractionEngine, parse_mineru_json_files
from omnilit_qt.pdf_extraction_schema import make_base_index


def write_blank_pdf(path: Path, width: float = 200.0, height: float = 100.0) -> None:
    try:
        import fitz
    except ModuleNotFoundError as exc:
        raise unittest.SkipTest("PyMuPDF is not installed in this environment") from exc
    doc = fitz.open()
    doc.new_page(width=width, height=height)
    doc.save(str(path))
    doc.close()


class FakeEngine:
    def __init__(self, name: str, fail: Exception | None = None) -> None:
        self.name = name
        self.fail = fail
        self.calls = 0

    def is_available(self) -> bool:
        return True

    def analyze(self, pdf_path: Path, output_dir: Path, options: dict[str, Any] | None = None) -> dict[str, Any]:
        self.calls += 1
        if self.fail:
            raise self.fail
        index = make_base_index(pdf_path, output_dir, self.name, page_count=1)
        index["pages"] = [{"page": 0, "width": 200.0, "height": 100.0, "rect": [0.0, 0.0, 200.0, 100.0]}]
        return index


class MinerUExtractionEngineTests(unittest.TestCase):
    def _config(self, poll_interval: float = 0) -> MinerUConfig:
        return MinerUConfig(True, "https://mineru.example/api/v4", 30, "pipeline", "token-value", poll_interval)

    def test_cloud_api_uploads_polls_and_normalizes_archive(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pdf_path = root / "sample.pdf"
            write_blank_pdf(pdf_path)
            responses = [
                {"code": 0, "data": {"batch_id": "batch-1", "file_urls": ["https://upload.example/file?sig=secret"]}},
                {"code": 0, "data": {"extract_result": [{"status": "running"}]}},
                {"code": 0, "data": {"extract_result": [{"status": "done", "full_zip_url": "https://download.example/result.zip?sig=secret"}]}},
            ]

            def fake_download(client: CloudAPIClient, url: str, target: Path) -> Path:
                with zipfile.ZipFile(target, "w") as bundle:
                    bundle.writestr(
                        "paper_content_list.json",
                        json.dumps([{"type": "formula", "page_idx": 0, "bbox": [100, 100, 500, 200], "latex_text": "$a+b$"}]),
                    )
                return target

            with patch.object(CloudAPIClient, "request_json", side_effect=responses) as request_json, patch.object(
                CloudAPIClient, "request"
            ) as upload, patch.object(CloudAPIClient, "download", autospec=True, side_effect=fake_download):
                index = MinerUExtractionEngine(self._config()).analyze(pdf_path, root / "out")

            create = request_json.call_args_list[0]
            self.assertEqual(create.args[:2], ("POST", "https://mineru.example/api/v4/file-urls/batch"))
            self.assertEqual(create.kwargs["headers"]["Authorization"], "Bearer token-value")
            self.assertEqual(create.kwargs["json"]["model_version"], "pipeline")
            self.assertEqual(upload.call_args.args[:2], ("PUT", "https://upload.example/file?sig=secret"))
            self.assertEqual(index["parserConfigVersion"], "cloud-api-v2")
            self.assertEqual(index["providerMode"], "cloud-api")
            self.assertEqual(index["elements"][0]["latex"], "a+b")

    def test_failed_cloud_task_raises_task_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            pdf_path = Path(temp) / "sample.pdf"
            write_blank_pdf(pdf_path)
            responses = [
                {"code": 0, "data": {"batch_id": "batch-1", "file_urls": ["https://upload.example/file"]}},
                {"code": 0, "data": {"extract_result": [{"status": "failed", "err_msg": "quota exhausted"}]}},
            ]
            with patch.object(CloudAPIClient, "request_json", side_effect=responses), patch.object(CloudAPIClient, "request"):
                with self.assertRaisesRegex(CloudAPIError, "quota exhausted") as raised:
                    MinerUExtractionEngine(self._config()).analyze(pdf_path, Path(temp) / "out")
            self.assertEqual(raised.exception.code, "TASK_FAILED")

    def test_parse_mineru_json_accepts_common_labels_and_one_based_pages(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            image_dir = root / "images"
            image_dir.mkdir()
            (image_dir / "figure.png").write_bytes(b"png")
            payload = root / "layout.json"
            payload.write_text(
                json.dumps(
                    {
                        "pages": [
                            {
                                "page_no": 1,
                                "page_width": 2000,
                                "page_height": 1000,
                                "blocks": [
                                    {"type": "isolate_formula", "bbox": [100, 100, 500, 200], "latex_text": "$a+b$"},
                                    {"type": "image_body", "bbox": [600, 200, 900, 600], "image": {"path": "images/figure.png"}},
                                ],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            pages = [{"page": 0, "width": 200.0, "height": 100.0, "rect": [0, 0, 200, 100]}]

            elements = parse_mineru_json_files([payload], pages, root, root)

            self.assertEqual([item["page"] for item in elements], [0, 0])
            self.assertEqual({item["type"] for item in elements}, {"formula", "figure"})
            self.assertEqual(next(item for item in elements if item["type"] == "formula")["latex"], "a+b")

    def test_explicit_mineru_pipeline_never_calls_paddleocr(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pdf_path = root / "sample.pdf"
            write_blank_pdf(pdf_path)
            paddle = FakeEngine("paddleocr_vl", RuntimeError("paddle must not run"))
            mineru = FakeEngine("mineru")
            pipeline = HybridExtractionPipeline(engines=[paddle, mineru], fallback_engine=FakeEngine("pymupdf"))

            index = pipeline.analyze(pdf_path, root / "out", {"engine": "mineru"})

            self.assertEqual(paddle.calls, 0)
            self.assertEqual(mineru.calls, 1)
            self.assertFalse(any(error["engine"] == "paddleocr_vl" for error in index["engineErrors"]))


if __name__ == "__main__":
    unittest.main()
