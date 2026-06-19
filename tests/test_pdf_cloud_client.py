from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from omnilit_qt.pdf_cloud_client import CloudAPIError, safe_extract_zip, sanitize_url


class PdfCloudClientTests(unittest.TestCase):
    def test_safe_extract_zip_extracts_regular_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "result.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("paper/result.json", "{}")

            safe_extract_zip(archive, root / "out")

            self.assertEqual((root / "out" / "paper" / "result.json").read_text(), "{}")

    def test_safe_extract_zip_rejects_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "unsafe.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("../escaped.txt", "bad")

            with self.assertRaises(CloudAPIError) as raised:
                safe_extract_zip(archive, root / "out")

            self.assertEqual(raised.exception.code, "UNSAFE_ARCHIVE")
            self.assertFalse((root / "escaped.txt").exists())

    def test_sanitize_url_removes_signed_query(self) -> None:
        self.assertEqual(sanitize_url("https://files.example/a.zip?signature=secret"), "https://files.example/a.zip")


if __name__ == "__main__":
    unittest.main()
