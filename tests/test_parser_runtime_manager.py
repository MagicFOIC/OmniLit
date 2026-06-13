from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

from omnilit_qt.parser_runtime_manager import ParserRuntimeManager


class ParserRuntimeManagerTests(unittest.TestCase):
    def test_default_optional_statuses_are_soft_not_hard_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            manager = ParserRuntimeManager(Path(temp))
            with patch("shutil.which", return_value=None), patch("socket.create_connection", side_effect=OSError):
                mineru = manager.check_mineru_available()
                paddle = manager.check_paddleocr_vl_available()

        self.assertFalse(mineru["available"])
        self.assertTrue(mineru["installable"])
        self.assertEqual(mineru["status"], "installable")
        self.assertFalse(paddle["available"])
        self.assertEqual(paddle["status"], "not_initialized")

    def test_ensure_mineru_runtime_success_uses_managed_venv(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manager = ParserRuntimeManager(root)
            venv_python = root / "mineru" / ".venv" / ("Scripts/python.exe" if sys.platform.startswith("win") else "bin/python")

            def fake_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
                commands.append(list(cmd))
                if cmd[:3] == [sys.executable, "-m", "venv"]:
                    venv_python.parent.mkdir(parents=True, exist_ok=True)
                    venv_python.write_text("", encoding="utf-8")
                return subprocess.CompletedProcess(cmd, 0, "ok", "")

            commands: list[list[str]] = []
            with patch.dict("os.environ", {}, clear=True), patch("subprocess.run", side_effect=fake_run), patch("shutil.which", return_value=None):
                status = manager.ensure_mineru_runtime()

        self.assertTrue(status["available"])
        self.assertEqual(status["status"], "ready")
        self.assertTrue(status["python"])
        self.assertIn([str(venv_python), "-m", "pip", "install", "uv"], commands)
        self.assertIn([str(venv_python), "-m", "uv", "pip", "install", "-U", "mineru[all]"], commands)

    def test_ensure_mineru_runtime_failure_is_recorded(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            manager = ParserRuntimeManager(Path(temp))

            def fake_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
                return subprocess.CompletedProcess(cmd, 1, "", "token=secret-value")

            with patch.dict("os.environ", {}, clear=True), patch("subprocess.run", side_effect=fake_run), patch("shutil.which", return_value=None):
                status = manager.ensure_mineru_runtime()

        self.assertFalse(status["available"])
        self.assertTrue(status["installable"])
        self.assertEqual(status["status"], "failed")
        self.assertNotIn("secret-value", status.get("lastError", ""))

    def test_sanitize_log_masks_sensitive_values(self) -> None:
        manager = ParserRuntimeManager(Path(tempfile.mkdtemp()))

        text = manager.sanitize_log("api_key=abc token:xyz password = hunter2")

        self.assertIn("api_key=***", text)
        self.assertIn("token:***", text)
        self.assertIn("password = ***", text)
        self.assertNotIn("hunter2", text)


if __name__ == "__main__":
    unittest.main()
