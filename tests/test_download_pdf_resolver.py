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

    def test_pdf_url_detection_accepts_common_pdf_query_parameters(self) -> None:
        self.assertTrue(core.looks_like_pdf_url("https://publisher.test/article?format=pdf"))
        self.assertTrue(core.looks_like_pdf_url("https://publisher.test/article?download=1"))
        self.assertFalse(core.looks_like_pdf_url("https://publisher.test/article?download=metadata"))

    def test_publisher_rules_derive_common_official_pdf_urls(self) -> None:
        self.assertEqual(
            core.candidate_urls_from_landing_url("https://pubs.acs.org/doi/10.1021/example.paper"),
            ["https://pubs.acs.org/doi/pdf/10.1021/example.paper"],
        )
        self.assertEqual(
            core.candidate_urls_from_landing_url("https://onlinelibrary.wiley.com/doi/full/10.1002/example"),
            ["https://onlinelibrary.wiley.com/doi/pdf/10.1002/example"],
        )
        self.assertEqual(
            core.candidate_urls_from_landing_url("https://link.springer.com/article/10.1007/s12345-026-0001"),
            ["https://link.springer.com/content/pdf/10.1007/s12345-026-0001.pdf"],
        )
        self.assertEqual(
            core.candidate_urls_from_landing_url("https://www.nature.com/articles/s41598-026-00001-1"),
            ["https://www.nature.com/articles/s41598-026-00001-1.pdf"],
        )

    def test_oa_landing_page_adds_publisher_rule_candidate(self) -> None:
        record = {
            "open_access": {"is_oa": True},
            "primary_location": {
                "is_oa": True,
                "landing_page_url": "https://pubs.acs.org/doi/full/10.1021/example.paper",
            },
        }

        self.assertEqual(
            core.iter_pdf_candidates(record, None),
            ["https://pubs.acs.org/doi/pdf/10.1021/example.paper"],
        )
        self.assertEqual(core.iter_pdf_candidate_details(record, None)[0].candidate_source, "publisher_rule")

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
                "https://www.osti.gov/servlets/purl/2529405",
                "https://repo.test/location.pdf",
                "https://europepmc.test/fulltext.pdf",
                "https://doaj.test/article.pdf",
                "https://unpaywall.test/best.pdf",
                "https://unpaywall.test/location.pdf",
                "https://www.publisher.test/primary.pdf",
                "https://publisher.test/oa.pdf",
            ],
        )

    def test_oa_pdf_resolver_prefers_repository_before_publisher_links(self) -> None:
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
        self.assertEqual(resolved.url, "https://repo.test/unpaywall.pdf")

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
        self.assertEqual(resolved.url, "https://repo.test/unpaywall.pdf")

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

    def test_shadow_library_candidate_is_rejected(self) -> None:
        record = {
            "open_access": {"is_oa": True},
            "pdf_candidates": [
                "https://sci-hub.example/paper.pdf",
                "https://repo.test/open.pdf",
            ],
        }

        self.assertEqual(core.iter_pdf_candidates(record, None), ["https://repo.test/open.pdf"])

    def test_resolver_adds_openalex_content_api_candidate(self) -> None:
        record = {
            "id": "https://openalex.org/W123456789",
            "open_access": {"is_oa": True},
        }

        self.assertEqual(
            core.iter_pdf_candidates(record, None),
            ["https://content.openalex.org/works/W123456789.pdf"],
        )
        self.assertEqual(
            core.iter_pdf_candidate_details(record, None)[0].candidate_source,
            "openalex_content_api",
        )

    def test_record_ids_add_arxiv_and_pmc_direct_candidates(self) -> None:
        arxiv_record = {
            "ids": {"arxiv": "https://arxiv.org/abs/2601.00001v1"},
            "open_access": {"is_oa": True},
        }
        pmc_record = {
            "ids": {"pmcid": "https://pmc.ncbi.nlm.nih.gov/articles/PMC1234567/"},
            "open_access": {"is_oa": True},
        }

        self.assertEqual(core.iter_pdf_candidates(arxiv_record, None), ["https://arxiv.org/pdf/2601.00001"])
        self.assertEqual(
            core.iter_pdf_candidates(pmc_record, None),
            ["https://pmc.ncbi.nlm.nih.gov/articles/PMC1234567/pdf/"],
        )

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

    def test_download_retries_earlier_candidate_when_head_html_but_later_head_ok(self) -> None:
        import fitz

        document = fitz.open()
        document.new_page()
        try:
            payload = document.tobytes()
        finally:
            document.close()

        class HeadResponse:
            def __init__(self, content_type: str) -> None:
                self.status_code = 200
                self.headers = {"content-type": content_type}

        class PdfResponse:
            status_code = 200
            url = "https://publisher.test/first.pdf"
            headers = {"content-type": "application/pdf"}

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            @staticmethod
            def iter_content(chunk_size):
                del chunk_size
                yield payload

        class BrokenResponse:
            status_code = 500
            url = "https://repo.test/second.pdf"
            headers = {"content-type": "text/plain"}

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

        class Session:
            def __init__(self) -> None:
                self.get_urls: list[str] = []

            @staticmethod
            def head(url, **_kwargs):
                if url == "https://publisher.test/first.pdf":
                    return HeadResponse("text/html")
                return HeadResponse("application/pdf")

            def get(self, url, **_kwargs):
                self.get_urls.append(url)
                return PdfResponse() if url == "https://publisher.test/first.pdf" else BrokenResponse()

        item = {
            "pdf_url": "https://publisher.test/first.pdf",
            "open_access": {"is_oa": True, "oa_url": "https://repo.test/second.pdf"},
        }

        with tempfile.TemporaryDirectory() as temp:
            session = Session()
            result, candidates = core.download_first_available_pdf(
                session,
                item,
                None,
                "10.1/head-html-priority",
                core.CrawlConfig(out_dir=Path(temp), min_pdf_bytes=8),
            )

        self.assertEqual(result.status, "downloaded")
        self.assertEqual(result.source_url, "https://publisher.test/first.pdf")
        self.assertEqual(candidates, ["https://repo.test/second.pdf", "https://publisher.test/first.pdf"])
        self.assertEqual(session.get_urls, ["https://repo.test/second.pdf", "https://publisher.test/first.pdf"])

    def test_download_get_validates_pdf_when_head_returns_403(self) -> None:
        import fitz

        document = fitz.open()
        document.new_page()
        try:
            payload = document.tobytes()
        finally:
            document.close()

        class HeadResponse:
            status_code = 403
            headers = {"content-type": "text/html"}

        class Response:
            status_code = 200
            url = "https://publisher.test/open.pdf"
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
            "title": "Publisher blocks HEAD with 403 but serves PDF",
            "open_access": {"is_oa": True, "oa_url": "https://publisher.test/open.pdf"},
        }

        with tempfile.TemporaryDirectory() as temp:
            session = Session()
            result, candidates = core.download_first_available_pdf(
                session,
                item,
                None,
                "10.1/head-403",
                core.CrawlConfig(out_dir=Path(temp), min_pdf_bytes=8),
            )

        self.assertEqual(result.status, "downloaded")
        self.assertEqual(candidates, ["https://publisher.test/open.pdf"])
        self.assertEqual(session.get_calls, 1)

    def test_download_get_403_is_blocked_or_login(self) -> None:
        class HeadResponse:
            status_code = 403
            headers = {"content-type": "text/html"}

        class Response:
            status_code = 403
            url = "https://publisher.test/login.pdf"
            headers = {"content-type": "text/html"}

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

        class Session:
            @staticmethod
            def head(*_args, **_kwargs):
                return HeadResponse()

            @staticmethod
            def get(*_args, **_kwargs):
                return Response()

        item = {
            "title": "Publisher requires login",
            "open_access": {"is_oa": True, "oa_url": "https://publisher.test/login.pdf"},
        }

        with tempfile.TemporaryDirectory() as temp:
            result, candidates = core.download_first_available_pdf(
                Session(),
                item,
                None,
                "10.1/login",
                core.CrawlConfig(out_dir=Path(temp), min_pdf_bytes=8),
            )

        self.assertEqual(result.status, "blocked_or_login")
        self.assertEqual(result.http_status, 403)
        self.assertEqual(result.failure_reason, "blocked_or_login")
        self.assertEqual(candidates, ["https://publisher.test/login.pdf"])

    def test_download_emits_fine_grained_pdf_progress(self) -> None:
        import fitz

        document = fitz.open()
        document.new_page()
        try:
            payload = document.tobytes()
        finally:
            document.close()

        class HeadResponse:
            status_code = 200
            headers = {"content-type": "application/pdf"}

        class Response:
            status_code = 200
            url = "https://repo.test/open.pdf"
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
            @staticmethod
            def head(*_args, **_kwargs):
                return HeadResponse()

            @staticmethod
            def get(*_args, **_kwargs):
                return Response()

        messages: list[str] = []
        with tempfile.TemporaryDirectory() as temp:
            config = core.CrawlConfig(
                out_dir=Path(temp),
                min_pdf_bytes=8,
                language="en",
                progress_callback=lambda _stats, message: messages.append(message),
            )
            stats = core.CrawlStats()
            result, _candidates = core.download_first_available_pdf(
                Session(),
                {"open_access": {"is_oa": True, "oa_url": "https://repo.test/open.pdf"}},
                None,
                "10.1/progress",
                config,
                stats=stats,
            )

        self.assertEqual(result.status, "downloaded")
        self.assertTrue(any("Found 1 legal OA PDF candidate" in message for message in messages))
        self.assertTrue(any("Checking PDF candidate" in message for message in messages))
        self.assertTrue(any("Trying PDF candidate" in message for message in messages))
        self.assertTrue(any("Downloading PDF candidate" in message for message in messages))

    def test_pdf_network_steps_use_bounded_timeouts(self) -> None:
        import fitz

        document = fitz.open()
        document.new_page()
        try:
            payload = document.tobytes()
        finally:
            document.close()

        class HeadResponse:
            status_code = 200
            headers = {"content-type": "application/pdf"}

        class Response:
            status_code = 200
            url = "https://repo.test/open.pdf"
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
                self.head_timeout = None
                self.get_timeout = None

            def head(self, *_args, **kwargs):
                self.head_timeout = kwargs.get("timeout")
                return HeadResponse()

            def get(self, *_args, **kwargs):
                self.get_timeout = kwargs.get("timeout")
                return Response()

        with tempfile.TemporaryDirectory() as temp:
            session = Session()
            result, _candidates = core.download_first_available_pdf(
                session,
                {"open_access": {"is_oa": True, "oa_url": "https://repo.test/open.pdf"}},
                None,
                "10.1/timeouts",
                core.CrawlConfig(out_dir=Path(temp), min_pdf_bytes=8),
            )

        self.assertEqual(result.status, "downloaded")
        self.assertEqual(session.head_timeout, core.PDF_HEAD_TIMEOUT)
        self.assertEqual(session.get_timeout, core.PDF_DOWNLOAD_TIMEOUT)

    def test_resolver_extracts_pdf_from_oa_landing_page_metadata(self) -> None:
        class Response:
            status_code = 200

            def __init__(self, text: str = "", content_type: str = "text/html") -> None:
                self.text = text
                self.headers = {"content-type": content_type}
                self.url = "https://publisher.test/article"

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

    def test_resolver_uses_doi_landing_redirect_final_url_as_html_base(self) -> None:
        class Response:
            status_code = 200
            headers = {"content-type": "text/html"}
            text = '<meta name="citation_pdf_url" content="/downloads/open.pdf">'
            url = "https://publisher.test/article/123"

        class HeadResponse:
            status_code = 200
            headers = {"content-type": "application/pdf"}

        class Session:
            def __init__(self) -> None:
                self.get_urls: list[str] = []

            @staticmethod
            def head(*_args, **_kwargs):
                return HeadResponse()

            def get(self, url, **_kwargs):
                self.get_urls.append(url)
                return Response()

        session = Session()
        item = {
            "doi": "10.1234/doi-only",
            "open_access": {"is_oa": True},
        }

        resolved = core.resolve_open_access_pdf(item, session, core.CrawlConfig(oa_only=True, request_delay=0))

        self.assertEqual(resolved.url, "https://publisher.test/downloads/open.pdf")
        self.assertIn("https://doi.org/10.1234/doi-only", session.get_urls)

    def test_resolver_uses_doi_redirect_final_url_for_publisher_rule(self) -> None:
        class Response:
            status_code = 200
            headers = {"content-type": "text/html"}
            text = "<html><body>Open access article</body></html>"
            url = "https://pubs.acs.org/doi/full/10.1021/example.paper"

        class HeadResponse:
            status_code = 200
            headers = {"content-type": "application/pdf"}

        class Session:
            @staticmethod
            def head(*_args, **_kwargs):
                return HeadResponse()

            @staticmethod
            def get(*_args, **_kwargs):
                return Response()

        item = {
            "doi": "10.1021/example.paper",
            "open_access": {"is_oa": True},
        }

        resolved = core.resolve_open_access_pdf(item, Session(), core.CrawlConfig(oa_only=True, request_delay=0))

        self.assertEqual(resolved.url, "https://pubs.acs.org/doi/pdf/10.1021/example.paper")
        self.assertEqual(resolved.candidate_details[0]["candidate_source"], "publisher_rule")

    def test_resolver_adds_semantic_scholar_open_access_pdf(self) -> None:
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

        resolved = core.resolve_open_access_pdf(item, session, core.CrawlConfig(oa_only=True, request_delay=0))

        self.assertEqual(resolved.url, "https://s2.test/open.pdf")
        self.assertIn("/DOI:10.1234%2Fsemantic", session.api_url)
        self.assertEqual(session.params["fields"], "paperId,title,isOpenAccess,openAccessPdf,externalIds,url")
        self.assertEqual(resolved.candidate_details[0]["candidate_source"], "semantic_scholar_openAccessPdf")

    def test_html_response_enqueues_pdf_candidate(self) -> None:
        import fitz

        document = fitz.open()
        document.new_page()
        try:
            payload = document.tobytes()
        finally:
            document.close()

        class HtmlResponse:
            status_code = 200
            url = "https://publisher.test/article.pdf"
            headers = {"content-type": "text/html"}

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            @staticmethod
            def iter_content(chunk_size):
                del chunk_size
                yield b'<html><meta name="citation_pdf_url" content="/open.pdf"></html>'

        class PdfResponse:
            status_code = 200
            url = "https://publisher.test/open.pdf"
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
                self.get_urls: list[str] = []

            def get(self, url, **_kwargs):
                self.get_urls.append(url)
                return HtmlResponse() if len(self.get_urls) == 1 else PdfResponse()

        item = {
            "id": "https://openalex.org/W-html-queue",
            "title": "HTML candidate reveals PDF",
            "pdf_url": "https://publisher.test/article.pdf",
            "open_access": {"is_oa": True},
        }

        with tempfile.TemporaryDirectory() as temp:
            session = Session()
            result, candidates = core.download_first_available_pdf(
                session,
                item,
                None,
                "10.1/html-queue",
                core.CrawlConfig(out_dir=Path(temp), min_pdf_bytes=8, request_delay=0),
            )

            self.assertEqual(result.status, "downloaded")
            self.assertEqual(
                candidates,
                ["https://publisher.test/open.pdf", "https://publisher.test/article.pdf"],
            )
            self.assertEqual(session.get_urls, ["https://publisher.test/article.pdf", "https://publisher.test/open.pdf"])

    def test_mislabeled_pdf_html_response_enqueues_pdf_candidate(self) -> None:
        import fitz

        document = fitz.open()
        document.new_page()
        try:
            payload = document.tobytes()
        finally:
            document.close()

        class HtmlResponse:
            status_code = 200
            url = "https://publisher.test/article.pdf"
            headers = {"content-type": "application/pdf"}

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            @staticmethod
            def iter_content(chunk_size):
                del chunk_size
                yield b'<html><body><iframe src="/reader/open.pdf"></iframe></body></html>'

        class PdfResponse:
            status_code = 200
            url = "https://publisher.test/reader/open.pdf"
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
                self.get_urls: list[str] = []

            def get(self, url, **_kwargs):
                self.get_urls.append(url)
                return HtmlResponse() if len(self.get_urls) == 1 else PdfResponse()

        item = {
            "pdf_url": "https://publisher.test/article.pdf",
            "open_access": {"is_oa": True},
        }

        with tempfile.TemporaryDirectory() as temp:
            session = Session()
            result, candidates = core.download_first_available_pdf(
                session,
                item,
                None,
                "10.1/mislabeled-html",
                core.CrawlConfig(out_dir=Path(temp), min_pdf_bytes=8, request_delay=0),
            )

            self.assertEqual(result.status, "downloaded")
            self.assertEqual(
                candidates,
                ["https://publisher.test/reader/open.pdf", "https://publisher.test/article.pdf"],
            )
            self.assertEqual(session.get_urls, ["https://publisher.test/article.pdf", "https://publisher.test/reader/open.pdf"])

    def test_semantic_scholar_fallback_runs_after_direct_get_failure(self) -> None:
        import fitz

        document = fitz.open()
        document.new_page()
        try:
            payload = document.tobytes()
        finally:
            document.close()

        class HeadResponse:
            status_code = 200
            headers = {"content-type": "application/pdf"}

        class HtmlResponse:
            status_code = 200
            url = "https://publisher.test/broken.pdf"
            headers = {"content-type": "text/html"}

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            @staticmethod
            def iter_content(chunk_size):
                del chunk_size
                yield b"<html>temporary publisher placeholder</html>"

        class ApiResponse:
            status_code = 200

            @staticmethod
            def json():
                return {"isOpenAccess": True, "openAccessPdf": {"url": "https://s2.test/open.pdf"}}

        class PdfResponse:
            status_code = 200
            url = "https://s2.test/open.pdf"
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
                self.get_urls: list[str] = []

            @staticmethod
            def head(*_args, **_kwargs):
                return HeadResponse()

            def get(self, url, **_kwargs):
                self.get_urls.append(url)
                if "semanticscholar.org" in url:
                    return ApiResponse()
                if url == "https://s2.test/open.pdf":
                    return PdfResponse()
                return HtmlResponse()

        item = {
            "doi": "10.1234/fallback",
            "pdf_url": "https://publisher.test/broken.pdf",
            "open_access": {"is_oa": True},
        }

        with tempfile.TemporaryDirectory() as temp:
            session = Session()
            result, candidates = core.download_first_available_pdf(
                session,
                item,
                None,
                "10.1234/fallback",
                core.CrawlConfig(out_dir=Path(temp), min_pdf_bytes=8, request_delay=0),
            )

        self.assertEqual(result.status, "downloaded")
        self.assertEqual(result.source_url, "https://s2.test/open.pdf")
        self.assertEqual(result.candidate_source, "semantic_scholar_openAccessPdf")
        self.assertEqual(
            candidates,
            ["https://s2.test/open.pdf", "https://publisher.test/broken.pdf"],
        )

    def test_landing_page_fallback_runs_after_direct_get_failure(self) -> None:
        import fitz

        document = fitz.open()
        document.new_page()
        try:
            payload = document.tobytes()
        finally:
            document.close()

        class HeadResponse:
            status_code = 200
            headers = {"content-type": "application/pdf"}

        class BrokenResponse:
            status_code = 200
            url = "https://publisher.test/broken.pdf"
            headers = {"content-type": "text/plain"}

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            @staticmethod
            def iter_content(chunk_size):
                del chunk_size
                yield b"temporary placeholder"

        class LandingResponse:
            status_code = 200
            headers = {"content-type": "text/html"}
            text = '<meta name="citation_pdf_url" content="/files/open.pdf">'

        class PdfResponse:
            status_code = 200
            url = "https://publisher.test/files/open.pdf"
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
                self.get_urls: list[str] = []

            @staticmethod
            def head(*_args, **_kwargs):
                return HeadResponse()

            def get(self, url, **_kwargs):
                self.get_urls.append(url)
                if url == "https://publisher.test/article":
                    return LandingResponse()
                if url == "https://publisher.test/files/open.pdf":
                    return PdfResponse()
                return BrokenResponse()

        item = {
            "pdf_url": "https://publisher.test/broken.pdf",
            "open_access": {"is_oa": True, "oa_url": "https://publisher.test/article"},
        }

        with tempfile.TemporaryDirectory() as temp:
            session = Session()
            result, candidates = core.download_first_available_pdf(
                session,
                item,
                None,
                "landing-fallback",
                core.CrawlConfig(out_dir=Path(temp), min_pdf_bytes=8, request_delay=0),
            )

        self.assertEqual(result.status, "downloaded")
        self.assertEqual(result.source_url, "https://publisher.test/files/open.pdf")
        self.assertEqual(
            candidates,
            ["https://publisher.test/files/open.pdf", "https://publisher.test/broken.pdf"],
        )
        self.assertIn("https://publisher.test/article", session.get_urls)

    def test_pdf_magic_bytes_accepts_octet_stream_pdf(self) -> None:
        import fitz

        document = fitz.open()
        document.new_page()
        try:
            payload = document.tobytes()
        finally:
            document.close()

        class Response:
            status_code = 200
            url = "https://repo.test/open.bin"
            headers = {"content-type": "application/octet-stream"}

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            @staticmethod
            def iter_content(chunk_size):
                del chunk_size
                yield payload

        class Session:
            @staticmethod
            def get(*_args, **_kwargs):
                return Response()

        with tempfile.TemporaryDirectory() as temp:
            result = core.download_pdf(
                Session(),
                "https://repo.test/open.pdf",
                "10.1/octet",
                core.CrawlConfig(out_dir=Path(temp), min_pdf_bytes=8, request_delay=0),
                candidate_source="unpaywall_url_for_pdf",
            )

            self.assertEqual(result.status, "downloaded")
            self.assertEqual(result.candidate_source, "unpaywall_url_for_pdf")

    def test_download_accepts_206_partial_content_pdf_when_file_is_complete(self) -> None:
        import fitz

        document = fitz.open()
        document.new_page()
        try:
            payload = document.tobytes()
        finally:
            document.close()

        class Response:
            status_code = 206
            url = "https://repo.test/open.pdf"
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
            @staticmethod
            def get(*_args, **_kwargs):
                return Response()

        with tempfile.TemporaryDirectory() as temp:
            result = core.download_pdf(
                Session(),
                "https://repo.test/open.pdf",
                "10.1/partial-content",
                core.CrawlConfig(out_dir=Path(temp), min_pdf_bytes=8, request_delay=0),
                candidate_source="unpaywall_url_for_pdf",
            )

        self.assertEqual(result.status, "downloaded")

    def test_download_accepts_pdf_named_by_content_disposition(self) -> None:
        import fitz

        document = fitz.open()
        document.new_page()
        try:
            payload = document.tobytes()
        finally:
            document.close()

        class Response:
            status_code = 200
            url = "https://repo.test/download?format=pdf"
            headers = {
                "content-type": "text/plain",
                "content-disposition": 'attachment; filename="article.pdf"',
            }

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            @staticmethod
            def iter_content(chunk_size):
                del chunk_size
                yield payload

        class Session:
            @staticmethod
            def get(*_args, **_kwargs):
                return Response()

        with tempfile.TemporaryDirectory() as temp:
            result = core.download_pdf(
                Session(),
                "https://repo.test/download?format=pdf",
                "10.1/content-disposition",
                core.CrawlConfig(out_dir=Path(temp), min_pdf_bytes=8, request_delay=0),
                candidate_source="publisher_rule",
            )

        self.assertEqual(result.status, "downloaded")

    def test_arxiv_delay_is_at_least_3_seconds(self) -> None:
        class Response:
            status_code = 200
            url = "https://arxiv.org/pdf/2601.00001v1"
            headers = {"content-type": "application/pdf"}

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            @staticmethod
            def iter_content(chunk_size):
                del chunk_size
                yield b"%PDF-1.4\n%%EOF\n"

        class Session:
            @staticmethod
            def get(*_args, **_kwargs):
                return Response()

        sleeps: list[float] = []
        setattr(core.enforce_arxiv_download_delay, "_last_download_at", core.time.monotonic())
        with tempfile.TemporaryDirectory() as temp, patch.object(
            core,
            "sleep_or_stop",
            side_effect=lambda seconds, _config: sleeps.append(seconds) and False,
        ):
            core.download_pdf(
                Session(),
                "https://arxiv.org/pdf/2601.00001v1",
                "2601.00001v1",
                core.CrawlConfig(out_dir=Path(temp), min_pdf_bytes=8),
                candidate_source="arxiv_pdf",
            )

        self.assertTrue(sleeps)
        self.assertGreaterEqual(sleeps[0], 2.9)

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
