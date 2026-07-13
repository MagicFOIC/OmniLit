from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from omnilit_qt.crash_reporting import MAX_REPORTS, write_diagnostic_event
from omnilit_qt.startup_diagnostics import write_startup_log


class CrashReportingTests(unittest.TestCase):
    @staticmethod
    def sensitive_exception() -> BaseException:
        try:
            raise RuntimeError("token=cloud-secret C:/Users/researcher/private-paper.pdf")
        except RuntimeError as exc:
            return exc

    def test_report_contains_classification_and_fingerprint_but_no_sensitive_details(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            path = write_diagnostic_event("qt_main", "unhandled exception", exc=self.sensitive_exception(), fatal=True, directory=directory)
            self.assertIsNotNone(path)
            raw = path.read_text(encoding="utf-8")
            report = json.loads(raw)
            self.assertEqual((report["source"], report["code"], report["fatal"]), ("qt_main", "unhandled_exception", True))
            self.assertEqual(len(report["fingerprint"]), 64)
            self.assertEqual(report["exceptionType"], "builtins.RuntimeError")
            for sensitive in ("cloud-secret", "private-paper", "researcher", "traceback", "argv", "cwd"):
                self.assertNotIn(sensitive, raw.casefold())

    def test_startup_compatibility_writer_hashes_lines_instead_of_persisting_them(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {"OMNILIT_CRASH_DIR": temporary}, clear=False):
            path = write_startup_log("QML load failed", ["qml_path=C:/Users/name/research.qml", "token=secret"])
            self.assertIsNotNone(path)
            raw = path.read_text(encoding="utf-8")
            self.assertNotIn("research.qml", raw)
            self.assertNotIn("secret", raw)
            self.assertEqual(json.loads(raw)["source"], "startup")

    def test_local_spool_has_a_hard_retention_limit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            for index in range(MAX_REPORTS + 5):
                self.assertIsNotNone(write_diagnostic_event("local_agent", f"failure_{index}", directory=directory))
            reports = list(directory.glob("*.json"))
            self.assertEqual(len(reports), MAX_REPORTS)


if __name__ == "__main__":
    unittest.main()
