from __future__ import annotations

import tempfile
import threading
import unittest
import zipfile
from pathlib import Path
from unittest.mock import Mock

import requests

from omnilit_qt.pdf_cloud_client import CloudAPIClient, CloudAPICancelled, CloudAPIError, safe_extract_zip, sanitize_url


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

    def test_authentication_and_quota_errors_have_stable_codes(self) -> None:
        for status, code in ((401, "AUTH_FAILED"), (403, "AUTH_FAILED"), (429, "QUOTA_EXCEEDED")):
            response = requests.Response()
            response.status_code = status
            response._content = b"{}"
            session = Mock()
            session.request.return_value = response

            with self.assertRaises(CloudAPIError) as raised:
                CloudAPIClient("test", retries=0, session=session).request("GET", "https://api.example/test")

            self.assertEqual(raised.exception.code, code)

    def test_timeout_and_network_errors_have_stable_codes(self) -> None:
        for error, code in ((requests.Timeout(), "TIMEOUT"), (requests.ConnectionError("offline"), "NETWORK_ERROR")):
            session = Mock()
            session.request.side_effect = error

            with self.assertRaises(CloudAPIError) as raised:
                CloudAPIClient("test", retries=0, session=session).request("GET", "https://api.example/test")

            self.assertEqual(raised.exception.code, code)

    def test_cancelled_request_never_reaches_network(self) -> None:
        cancel_event = threading.Event()
        cancel_event.set()
        session = Mock()

        with self.assertRaises(CloudAPICancelled):
            CloudAPIClient("test", cancel_event=cancel_event, session=session).request("GET", "https://api.example/test")

        session.request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
