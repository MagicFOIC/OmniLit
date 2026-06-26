from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from Download import literature_download_core as core


class PdfResolverTests(unittest.TestCase):
    def test_candidate_url_normalization_adds_https_and_filters_non_http(self) -> None:
        self.assertEqual(core.normalize_candidate_url("www.osti.gov/servlets/purl/2529405"), "https://www.osti.gov/servlets/purl/2529405")
        self.assertEqual(core.normalize_candidate_url("doi.org/10.1234/example"), "https://doi.org/10.1234/example")
        self.assertEqual(core.normalize_candidate_url("http://Repo.TEST/paper.pdf"), "https://repo.test/paper.pdf")
        self.assertIsNone(core.normalize_candidate_url("mailto:author@example.com"))

    def test_pdf_candidates_cover_openalex_unpaywall_europe_pmc_and_doaj_links(self) -> None:
        record = {
            "open_access": {"is_oa": True, "oa_url": "publisher.test/oa.pdf"},
            "primary_location": {"pdf_url": "www.publisher.test/primary.pdf"},
            "best_oa_location": {"landing_page_url": "https://www.osti.gov/biblio/2529405", "is_oa": True},
            "locations": [{"pdf_url": "//repo.test/location.pdf"}],
            "fullTextUrlList": {
                "fullTextUrl": [{
                    "availabilityCode": "OA",
                    "documentStyle": "pdf",
                    "url": "europepmc.test/fulltext.pdf",
                }]
            },
            "doaj_fulltext_links": ["doaj.test/article.pdf"],
            "unpaywall": {
                "is_oa": True,
                "best_oa_location": {"url_for_pdf": "unpaywall.test/best.pdf"},
                "oa_locations": [{"url_for_pdf": "https://unpaywall.test/location.pdf"}],
            },
        }

        self.assertEqual(
            core.iter_pdf_candidates(record, record["unpaywall"]),
            [
                "https://www.publisher.test/primary.pdf",
                "https://www.osti.gov/servlets/purl/2529405",
                "https://repo.test/location.pdf",
                "https://publisher.test/oa.pdf",
                "https://unpaywall.test/best.pdf",
                "https://unpaywall.test/location.pdf",
                "https://europepmc.test/fulltext.pdf",
                "https://doaj.test/article.pdf",
            ],
        )

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

    def test_download_get_sniffs_pdf_when_head_reports_html(self) -> None:
        import fitz

        document = fitz.open()
        document.new_page()
        try:
            payload = document.tobytes()
        finally:
            document.close()

        class HeadResponse:
            status_code = 200
            headers = {"content-type": "text/html"}

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
                self.get_calls = 0

            @staticmethod
            def head(*_args, **_kwargs):
                return HeadResponse()

            def get(self, *_args, **_kwargs):
                self.get_calls += 1
                return Response()

        item = {
            "id": "https://openalex.org/W-head-html",
            "title": "Publisher HEAD says HTML but GET serves PDF",
            "open_access": {"is_oa": True, "oa_url": "https://publisher.test/paper.pdf"},
        }

        with tempfile.TemporaryDirectory() as temp:
            session = Session()
            result, candidates = core.download_first_available_pdf(
                session,
                item,
                None,
                "10.1/head-html",
                core.CrawlConfig(out_dir=Path(temp), min_pdf_bytes=8),
            )

            self.assertEqual(result.status, "downloaded")
            self.assertEqual(candidates, ["https://publisher.test/paper.pdf"])
            self.assertEqual(session.get_calls, 1)

    def test_resolver_extracts_pdf_from_oa_landing_page_metadata(self) -> None:
        class Response:
            status_code = 200

            def __init__(self, text: str = "", content_type: str = "text/html") -> None:
                self.text = text
                self.headers = {"content-type": content_type}

        class Session:
            @staticmethod
            def head(url, **_kwargs):
                del url
                return Response(content_type="application/pdf")

            @staticmethod
            def get(url, **_kwargs):
                self_url = "https://repo.test/open.pdf"
                return Response(f'<html><meta name="citation_pdf_url" content="{self_url}"></html>')

        item = {
            "id": "https://openalex.org/W-landing",
            "title": "OA landing page advertises a PDF",
            "open_access": {"is_oa": True, "oa_url": "https://publisher.test/article"},
        }

        resolved = core.resolve_open_access_pdf(item, Session(), core.CrawlConfig(oa_only=True))

        self.assertEqual(resolved.url, "https://repo.test/open.pdf")
        self.assertEqual(resolved.candidates, ["https://repo.test/open.pdf"])

    def test_resolver_uses_semantic_scholar_open_access_pdf_as_second_layer(self) -> None:
        class HeadResponse:
            status_code = 200
            headers = {"content-type": "application/pdf"}

        class ApiResponse:
            status_code = 200

            @staticmethod
            def json():
                return {"isOpenAccess": True, "openAccessPdf": {"url": "https://s2.test/open.pdf"}}

        class Session:
            def __init__(self) -> None:
                self.api_url = ""
                self.params = {}

            @staticmethod
            def head(*_args, **_kwargs):
                return HeadResponse()

            def get(self, url, params=None, **_kwargs):
                self.api_url = url
                self.params = params or {}
                return ApiResponse()

        session = Session()
        item = {
            "doi": "10.1234/semantic",
            "title": "Semantic Scholar has an OA PDF",
            "open_access": {"is_oa": True, "oa_url": "https://publisher.test/article"},
        }

        resolved = core.resolve_open_access_pdf(item, session, core.CrawlConfig(oa_only=True))

        self.assertEqual(resolved.url, "https://s2.test/open.pdf")
        self.assertIn("/DOI:10.1234%2Fsemantic", session.api_url)
        self.assertEqual(session.params["fields"], "isOpenAccess,openAccessPdf,externalIds")

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
