from __future__ import annotations

import unittest

from Download import literature_download_core as core


class PdfResolverPriorityTests(unittest.TestCase):
    class Response:
        def __init__(self, status_code: int, content_type: str) -> None:
            self.status_code = status_code
            self.headers = {"content-type": content_type}

    class Session:
        def __init__(self, responses: dict[str, tuple[int, str]]) -> None:
            self.responses = responses
            self.head_calls: list[str] = []

        def head(self, url, **_kwargs):
            self.head_calls.append(url)
            status, content_type = self.responses[url]
            return PdfResolverPriorityTests.Response(status, content_type)

    def test_priority_primary_then_oa_url_then_unpaywall_then_doaj(self) -> None:
        record = {
            "primary_location": {"pdf_url": "https://publisher.test/primary.pdf"},
            "open_access": {"is_oa": True, "oa_url": "https://publisher.test/oa.pdf"},
            "unpaywall": {"is_oa": True, "pdf_url": "https://repo.test/unpaywall.pdf"},
            "doaj_fulltext_links": ["https://doaj.test/fulltext.pdf"],
        }
        config = core.CrawlConfig(oa_only=True)

        self.assertEqual(
            core.resolve_open_access_pdf(
                record,
                self.Session({
                    "https://publisher.test/primary.pdf": (200, "application/pdf"),
                    "https://publisher.test/oa.pdf": (200, "application/pdf"),
                    "https://repo.test/unpaywall.pdf": (200, "application/pdf"),
                    "https://doaj.test/fulltext.pdf": (200, "application/pdf"),
                }),
                config,
            ).url,
            "https://publisher.test/primary.pdf",
        )
        self.assertEqual(
            core.resolve_open_access_pdf(
                record,
                self.Session({
                    "https://publisher.test/primary.pdf": (200, "text/html"),
                    "https://publisher.test/oa.pdf": (200, "application/pdf"),
                    "https://repo.test/unpaywall.pdf": (200, "application/pdf"),
                    "https://doaj.test/fulltext.pdf": (200, "application/pdf"),
                }),
                config,
            ).url,
            "https://publisher.test/oa.pdf",
        )
        self.assertEqual(
            core.resolve_open_access_pdf(
                record,
                self.Session({
                    "https://publisher.test/primary.pdf": (200, "text/html"),
                    "https://publisher.test/oa.pdf": (200, "text/html"),
                    "https://repo.test/unpaywall.pdf": (200, "application/pdf"),
                    "https://doaj.test/fulltext.pdf": (200, "application/pdf"),
                }),
                config,
            ).url,
            "https://repo.test/unpaywall.pdf",
        )
        self.assertEqual(
            core.resolve_open_access_pdf(
                record,
                self.Session({
                    "https://publisher.test/primary.pdf": (200, "text/html"),
                    "https://publisher.test/oa.pdf": (200, "text/html"),
                    "https://repo.test/unpaywall.pdf": (403, "text/html"),
                    "https://doaj.test/fulltext.pdf": (200, "application/pdf"),
                }),
                config,
            ).url,
            "https://doaj.test/fulltext.pdf",
        )


if __name__ == "__main__":
    unittest.main()
