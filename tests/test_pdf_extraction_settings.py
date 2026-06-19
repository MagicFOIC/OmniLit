from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from omnilit_qt.pdf_extraction_settings import (
    import_legacy_parser_tokens,
    parser_api_token,
    engine_status,
    redact_sensitive_text,
)


class FakeRuntimeStatus:
    def __init__(self, paddle: dict | None = None, mineru: dict | None = None) -> None:
        self.paddle = paddle or {"available": False, "installable": False, "status": "not_initialized", "message": "not initialized"}
        self.mineru = mineru or {"available": False, "installable": True, "status": "installable", "message": "installable"}

    def check_paddleocr_vl_available(self) -> dict:
        return dict(self.paddle)

    def check_mineru_available(self) -> dict:
        return dict(self.mineru)


class PdfExtractionSettingsTests(unittest.TestCase):
    def test_legacy_tokens_are_imported_once_and_encrypted(self) -> None:
        class Store:
            def __init__(self) -> None:
                self.values: dict[str, str] = {}

            def setting(self, key: str, default: str = "") -> str:
                return self.values.get(key, default)

            def set_setting(self, key: str, value: str) -> None:
                self.values[key] = value

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            mineru = root / "Mineru.txt"
            paddle = root / "PaddleOCR.txt"
            mineru.write_text("mineru-secret", encoding="utf-8")
            paddle.write_text("paddle-secret", encoding="utf-8")
            store = Store()
            with patch("omnilit_qt.pdf_extraction_settings.LEGACY_TOKEN_PATHS", {"mineru": mineru, "paddleocr_vl": paddle}), patch.dict(os.environ, {}, clear=True):
                imported = import_legacy_parser_tokens(store)
                mineru.write_text("changed", encoding="utf-8")
                second = import_legacy_parser_tokens(store)

            self.assertEqual(imported, {"mineru": True, "paddleocr_vl": True})
            self.assertEqual(second, {"mineru": False, "paddleocr_vl": False})
            self.assertNotIn("mineru-secret", store.values["pdf_parser/mineru/token"])
            self.assertEqual(parser_api_token(store, "mineru"), "mineru-secret")

    def test_engine_status_defaults_keep_optional_engines_soft_available(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            status = engine_status(FakeRuntimeStatus())

        self.assertIn("pymupdf", status)
        self.assertFalse(status["paddleocr_vl"]["available"])
        self.assertEqual(status["paddleocr_vl"]["status"], "not_configured")
        self.assertFalse(status["mineru"]["available"])
        self.assertFalse(status["mineru"]["installable"])

    def test_paddleocr_status_uses_env_api_key_without_exposing_value(self) -> None:
        runtime = FakeRuntimeStatus(
            paddle={"available": True, "installable": False, "status": "service", "message": "service available with API Key from env"}
        )
        with patch.dict(
            "os.environ",
            {
                "OMNILIT_PADDLEOCR_VL_ENABLED": "1",
                "OMNILIT_PADDLEOCR_VL_MODE": "service",
                "OMNILIT_PADDLEOCR_VL_PYTHON": sys.executable,
                "OMNILIT_PADDLEOCR_VL_URL": "http://127.0.0.1:8118/v1",
                "OMNILIT_PADDLEOCR_VL_API_KEY": "secret-value",
            },
            clear=True,
        ):
            status = engine_status(runtime)

        self.assertTrue(status["paddleocr_vl"]["available"])
        self.assertIn("configured", status["paddleocr_vl"]["message"])
        self.assertNotIn("secret-value", status["paddleocr_vl"]["message"])

    def test_mineru_cloud_api_requires_token(self) -> None:
        runtime = FakeRuntimeStatus(mineru={"available": False, "installable": False, "status": "missing", "message": "找不到 mineru 命令"})
        with patch.dict(
            "os.environ",
            {
                "OMNILIT_MINERU_ENABLED": "1",
                "OMNILIT_MINERU_MODE": "api",
            },
            clear=True,
        ):
            status = engine_status(runtime)

        self.assertFalse(status["mineru"]["available"])
        self.assertIn("MinerU", status["mineru"]["message"])

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
