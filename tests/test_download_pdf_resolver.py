from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from Download import literature_download_core as core


class PdfResolverTests(unittest.TestCase):
    def test_oa_pdf_resolver_prefers_openalex_then_unpaywall_then_doaj(self) -> None:
        class HeadResponse:
            def __init__(self, status_code: int, content_type: str) -> None:
                self.status_code = status_code
                self.headers = {"content-type": content_type}

        class Session:
            def __init__(self, content_types: dict[str, tuple[int, str]]) -> None:
                self.content_types = content_types

            def head(self, url, **_kwargs):
                status, content_type = self.content_types[url]
                return HeadResponse(status, content_type)

        record = {
            "primary_location": {"pdf_url": "https://publisher.test/openalex.pdf"},
            "open_access": {"is_oa": True, "oa_url": "https://publisher.test/oa.pdf"},
            "unpaywall": {
                "is_oa": True,
                "pdf_url": "https://repo.test/unpaywall.pdf",
                "pdf_urls": ["https://repo.test/unpaywall.pdf"],
            },
            "doaj_fulltext_links": ["https://doaj.test/fulltext.pdf"],
        }
        config = core.CrawlConfig(oa_only=True)

        resolved = core.resolve_open_access_pdf(
            record,
            Session({
                "https://publisher.test/openalex.pdf": (200, "application/pdf"),
                "https://publisher.test/oa.pdf": (200, "application/pdf"),
                "https://repo.test/unpaywall.pdf": (200, "application/pdf"),
                "https://doaj.test/fulltext.pdf": (200, "application/pdf"),
            }),
            config,
        )
        self.assertEqual(resolved.url, "https://publisher.test/openalex.pdf")

        resolved = core.resolve_open_access_pdf(
            record,
            Session({
                "https://publisher.test/openalex.pdf": (200, "text/html"),
                "https://publisher.test/oa.pdf": (200, "text/html"),
                "https://repo.test/unpaywall.pdf": (200, "application/pdf"),
                "https://doaj.test/fulltext.pdf": (200, "application/pdf"),
            }),
            config,
        )
        self.assertEqual(resolved.url, "https://repo.test/unpaywall.pdf")

        resolved = core.resolve_open_access_pdf(
            record,
            Session({
                "https://publisher.test/openalex.pdf": (200, "text/html"),
                "https://publisher.test/oa.pdf": (200, "text/html"),
                "https://repo.test/unpaywall.pdf": (403, "text/html"),
                "https://doaj.test/fulltext.pdf": (200, "application/pdf"),
            }),
            config,
        )
        self.assertEqual(resolved.url, "https://doaj.test/fulltext.pdf")

    def test_oa_pdf_resolver_rejects_shadow_library(self) -> None:
        class Session:
            def head(self, *_args, **_kwargs):
                raise AssertionError("shadow library URL should be rejected before HEAD")

        record = {
            "primary_location": {"pdf_url": "https://sci-hub.example/10.1/paper.pdf"},
            "open_access": {"is_oa": True},
        }

        resolved = core.resolve_open_access_pdf(record, Session(), core.CrawlConfig(oa_only=True))

        self.assertIsNone(resolved.url)
        self.assertEqual(resolved.candidates, [])
        self.assertEqual(resolved.reason, "no_oa_pdf")

    def test_download_get_validates_pdf_when_head_is_unavailable(self) -> None:
        import fitz

        document = fitz.open()
        document.new_page()
        try:
            payload = document.tobytes()
        finally:
            document.close()

        class Response:
            status_code = 200
            headers = {"content-type": "application/pdf"}

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            @staticmethod
            def iter_content(chunk_size):
                del chunk_size
                yield payload

        class Session:
            def __init__(self) -> None:
                self.head_calls = 0
                self.get_calls = 0

            def head(self, *_args, **_kwargs):
                self.head_calls += 1
                raise core.requests.RequestException("HEAD blocked")

            def get(self, *_args, **_kwargs):
                self.get_calls += 1
                return Response()

        item = {
            "id": "https://openalex.org/W-head-blocked",
            "title": "Publisher blocks HEAD but serves PDF",
            "open_access": {"is_oa": True, "oa_url": "https://publisher.test/paper.pdf"},
        }

        with tempfile.TemporaryDirectory() as temp:
            session = Session()
            config = core.CrawlConfig(out_dir=Path(temp), min_pdf_bytes=8)
            result, candidates = core.download_first_available_pdf(session, item, None, "10.1/head", config)

            self.assertEqual(result.status, "downloaded")
            self.assertEqual(candidates, ["https://publisher.test/paper.pdf"])
            self.assertEqual(session.head_calls, 1)
            self.assertEqual(session.get_calls, 1)
            self.assertTrue(Path(result.path).read_bytes().startswith(b"%PDF"))

    def test_no_download_when_oa_only_and_no_pdf(self) -> None:
        item = {
            "id": "https://openalex.org/W-no-pdf",
            "title": "Lithium-sulfur batteries without a PDF link",
            "abstract": "Polysulfide shuttle and sulfur cathode.",
            "open_access": {"is_oa": True, "oa_url": "https://publisher.test/article"},
        }
        config = core.CrawlConfig(
            out_dir=Path("unused"),
            keywords=["lithium-sulfur batteries"],
            oa_only=True,
            request_delay=0,
            page_delay=0,
            strict_keyword_match=False,
            resume=False,
        )
        stats = core.CrawlStats()
        output = io.StringIO()

        with patch.object(
            core,
            "search_literature_source",
            return_value={"results": [item], "meta": {"next_cursor": None}},
        ):
            core.crawl_keyword(
                object(),
                core.SOURCE_OPENALEX,
                "lithium-sulfur batteries",
                core.ExistingIndex(set(), set(), set()),
                output,
                config,
                stats,
                {},
            )

        record = json.loads(output.getvalue())
        self.assertEqual(record["download_status"], "failed")
        self.assertEqual(record["download_reason"], "no_oa_pdf")
        self.assertEqual(record["pdf_candidates"], [])
        self.assertIsNone(record["local_pdf_path"])


if __name__ == "__main__":
    unittest.main()
