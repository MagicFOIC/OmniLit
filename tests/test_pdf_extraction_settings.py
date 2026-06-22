from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from omnilit_qt.pdf_extraction_settings import (
    MINERU_API_URL_DEFAULT,
    PADDLEOCR_API_URL_DEFAULT,
    engine_status,
    normalize_parser_api_url,
    parser_api_token,
    parser_api_url,
    redact_sensitive_text,
    save_parser_service,
)


class Store:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def setting(self, key: str, default: str = "") -> str:
        return self.values.get(key, default)

    def set_setting(self, key: str, value: str) -> None:
        self.values[key] = value


class PdfExtractionSettingsTests(unittest.TestCase):
    def test_official_api_urls_are_the_defaults(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(parser_api_url(None, "mineru"), MINERU_API_URL_DEFAULT)
            self.assertEqual(parser_api_url(None, "paddleocr_vl"), PADDLEOCR_API_URL_DEFAULT)
        self.assertEqual(PADDLEOCR_API_URL_DEFAULT, "https://paddleocr.aistudio-app.com/api/v2/ocr/jobs")

    def test_mineru_endpoint_is_normalized_to_batch_api_root(self) -> None:
        self.assertEqual(
            normalize_parser_api_url("mineru", "https://mineru.net/api/v4/extract/task"),
            "https://mineru.net/api/v4",
        )
        self.assertEqual(
            normalize_parser_api_url("mineru", "https://mineru.net/api/v4/file-urls/batch"),
            "https://mineru.net/api/v4",
        )

    def test_environment_values_override_encrypted_saved_settings(self) -> None:
        store = Store()
        save_parser_service(store, "mineru", "https://saved.example/api/v4", "saved-token", True)

        with patch.dict(
            os.environ,
            {
                "OMNILIT_MINERU_API_URL": "https://env.example/api/v4",
                "OMNILIT_MINERU_API_TOKEN": "env-token",
            },
            clear=True,
        ):
            self.assertEqual(parser_api_url(store, "mineru"), "https://env.example/api/v4")
            self.assertEqual(parser_api_token(store, "mineru"), "env-token")

        self.assertNotIn("saved-token", store.values["pdf_parser/mineru/token"])
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(parser_api_token(store, "mineru"), "saved-token")

    def test_engine_status_reports_cloud_configuration_without_exposing_tokens(self) -> None:
        with patch.dict(
            os.environ,
            {
                "OMNILIT_MINERU_API_TOKEN": "mineru-secret",
                "OMNILIT_PADDLEOCR_VL_API_KEY": "paddle-secret",
            },
            clear=True,
        ):
            status = engine_status()

        self.assertTrue(status["mineru"]["available"])
        self.assertTrue(status["paddleocr_vl"]["available"])
        self.assertNotIn("installable", status["mineru"])
        self.assertNotIn("mineru-secret", str(status))
        self.assertNotIn("paddle-secret", str(status))

    def test_engine_status_requires_tokens(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            status = engine_status()

        self.assertFalse(status["mineru"]["available"])
        self.assertFalse(status["paddleocr_vl"]["available"])
        self.assertEqual(status["mineru"]["status"], "not_configured")
        self.assertEqual(status["paddleocr_vl"]["status"], "not_configured")

    def test_redact_sensitive_text_masks_common_secret_fields(self) -> None:
        text = "api_key=abc token:xyz password = hunter2 Authorization: Bearer eyJheader.payload.signature https://files.test/a.zip?signature=secret normal=value"

        redacted = redact_sensitive_text(text)

        self.assertIn("api_key=***", redacted)
        self.assertIn("token:***", redacted)
        self.assertIn("password = ***", redacted)
        self.assertNotIn("abc", redacted)
        self.assertNotIn("xyz", redacted)
        self.assertNotIn("hunter2", redacted)
        self.assertNotIn("eyJheader", redacted)
        self.assertNotIn("signature=secret", redacted)


if __name__ == "__main__":
    unittest.main()
