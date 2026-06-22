from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from omnilit_qt.pdf_cloud_client import CloudAPIClient, CloudAPIError
from omnilit_qt.pdf_extraction_paddleocr_vl import (
    PaddleOCRVLConfig,
    PaddleOCRVLExtractionEngine,
    _parse_paddle_jsonl,
    html_table_to_rows,
    markdown_table_to_rows,
)


def _jsonl_payload(image_path: str = "assets/figure.png") -> str:
    return json.dumps(
        {
            "result": {
                "layoutParsingResults": [
                    {
                        "page": 0,
                        "prunedResult": {
                            "blocks": [
                                {"label": "table", "coordinate": [1, 2, 30, 40], "markdown": "|A|B|\n|---|---|\n|1|2|"},
                                {"label": "formula", "coordinate": [5, 50, 60, 70], "latex": "x+y"},
                                {"label": "figure", "coordinate": [10, 75, 80, 100], "caption": "Figure 1"},
                            ]
                        },
                        "markdown": {"text": "# Paper", "images": {image_path: "https://assets.example/figure.png"}},
                        "outputImages": {"layout": "https://assets.example/layout.jpg"},
                    }
                ]
            }
        }
    )


class PaddleOCRVLExtractionEngineTests(unittest.TestCase):
    def _config(self, *, timeout: float = 30, poll_interval: float = 0) -> PaddleOCRVLConfig:
        return PaddleOCRVLConfig(
            enabled=True,
            job_url="https://paddleocr.aistudio-app.com/api/v2/ocr/jobs",
            model="PaddleOCR-VL-1.6",
            timeout=timeout,
            api_token="token-value",
            poll_interval=poll_interval,
        )

    def test_cloud_api_submits_multipart_polls_jsonl_and_downloads_images(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pdf_path = root / "sample.pdf"
            pdf_path.write_bytes(b"%PDF-1.4 mocked")
            responses = [
                {"data": {"jobId": "job-1"}},
                {"data": {"state": "running", "extractProgress": {"totalPages": 1, "extractedPages": 0}}},
                {"data": {"state": "done", "resultUrl": {"jsonUrl": "https://assets.example/result.jsonl"}}},
            ]

            def fake_download(client: CloudAPIClient, url: str, target: Path) -> Path:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(_jsonl_payload(), encoding="utf-8") if target.suffix == ".jsonl" else target.write_bytes(b"image")
                return target

            with patch.object(CloudAPIClient, "request_json", side_effect=responses) as request_mock, patch.object(
                CloudAPIClient, "download", autospec=True, side_effect=fake_download
            ) as download_mock:
                index = PaddleOCRVLExtractionEngine(self._config()).analyze(pdf_path, root / "out")

            submit = request_mock.call_args_list[0]
            self.assertEqual(submit.args[:2], ("POST", "https://paddleocr.aistudio-app.com/api/v2/ocr/jobs"))
            self.assertEqual(submit.kwargs["headers"]["Authorization"], "bearer token-value")
            self.assertEqual(submit.kwargs["data"]["model"], "PaddleOCR-VL-1.6")
            self.assertEqual(json.loads(submit.kwargs["data"]["optionalPayload"])["useChartRecognition"], False)
            self.assertEqual(submit.kwargs["files"]["file"][0], "sample.pdf")
            self.assertEqual(request_mock.call_args_list[1].args[1], "https://paddleocr.aistudio-app.com/api/v2/ocr/jobs/job-1")
            self.assertGreaterEqual(download_mock.call_count, 3)
            self.assertEqual(index["parserConfigVersion"], "cloud-api-v2")
            self.assertEqual(index["providerMode"], "cloud-api")
            self.assertEqual({item["type"] for item in index["elements"]}, {"table", "formula", "figure"})
            self.assertEqual(Path(index["markdownPath"]).read_text(encoding="utf-8"), "# Paper")
            self.assertTrue((root / "out" / "paddleocr_vl" / "assets" / "figure.png").exists())

    def test_failed_job_raises_task_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            pdf_path = Path(temp) / "sample.pdf"
            pdf_path.write_bytes(b"pdf")
            responses = [{"data": {"jobId": "job-1"}}, {"data": {"state": "failed", "errorMsg": "bad document"}}]
            with patch.object(CloudAPIClient, "request_json", side_effect=responses):
                with self.assertRaisesRegex(CloudAPIError, "bad document") as raised:
                    PaddleOCRVLExtractionEngine(self._config()).analyze(pdf_path, Path(temp) / "out")
            self.assertEqual(raised.exception.code, "TASK_FAILED")

    def test_unknown_job_state_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            pdf_path = Path(temp) / "sample.pdf"
            pdf_path.write_bytes(b"pdf")
            responses = [{"data": {"jobId": "job-1"}}, {"data": {"state": "mystery"}}]
            with patch.object(CloudAPIClient, "request_json", side_effect=responses):
                with self.assertRaises(CloudAPIError) as raised:
                    PaddleOCRVLExtractionEngine(self._config()).analyze(pdf_path, Path(temp) / "out")
            self.assertEqual(raised.exception.code, "INVALID_RESPONSE")

    def test_invalid_jsonl_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "bad.jsonl"
            path.write_text("not-json", encoding="utf-8")
            with self.assertRaises(CloudAPIError) as raised:
                _parse_paddle_jsonl(path)
            self.assertEqual(raised.exception.code, "INVALID_RESPONSE")

    def test_unsafe_remote_image_path_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pdf_path = root / "sample.pdf"
            pdf_path.write_bytes(b"pdf")

            def fake_download(client: CloudAPIClient, url: str, target: Path) -> Path:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(_jsonl_payload("../escape.png"), encoding="utf-8")
                return target

            responses = [{"data": {"jobId": "job-1"}}, {"data": {"state": "done", "resultUrl": {"jsonUrl": "https://assets.example/result.jsonl"}}}]
            with patch.object(CloudAPIClient, "request_json", side_effect=responses), patch.object(
                CloudAPIClient, "download", autospec=True, side_effect=fake_download
            ):
                with self.assertRaises(CloudAPIError) as raised:
                    PaddleOCRVLExtractionEngine(self._config()).analyze(pdf_path, root / "out")
            self.assertEqual(raised.exception.code, "UNSAFE_ASSET_PATH")

    def test_markdown_and_html_tables_parse_without_bs4(self) -> None:
        self.assertEqual(markdown_table_to_rows("| A | B |\n|---|---|\n| 1 | 2 |"), [["A", "B"], ["1", "2"]])
        self.assertEqual(
            html_table_to_rows("<table><tr><th>A</th><th>B</th></tr><tr><td>1</td><td>2</td></tr></table>"),
            [["A", "B"], ["1", "2"]],
        )


if __name__ == "__main__":
    unittest.main()
