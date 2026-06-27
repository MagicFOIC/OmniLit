from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from SourceProxy.source_api_proxy import SourceApiProxy, resolve_route


class Response:
    status_code = 200
    headers = {"content-type": "application/json"}
    content = b'{"ok":true}'


class RecordingSession:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def get(self, url: str, **kwargs):
        self.calls.append({"url": url, **kwargs})
        return Response()


class SourceApiProxyTests(unittest.TestCase):
    def test_openalex_route_maps_to_works_and_injects_server_key(self) -> None:
        route, params = resolve_route("/search/openalex/W123", "select=id&api_key=client-secret")
        session = RecordingSession()
        proxy = SourceApiProxy(session=session)

        with patch.dict(os.environ, {"OPENALEX_API_KEY": "server-openalex"}, clear=False):
            status, _headers, body = proxy.handle_get("/search/openalex/W123", "select=id&api_key=client-secret")

        self.assertEqual(status, 200)
        self.assertEqual(body, b'{"ok":true}')
        self.assertTrue(route.upstream_url.endswith("/works/W123"))
        self.assertEqual(params["api_key"], "client-secret")
        self.assertEqual(session.calls[0]["params"]["api_key"], "server-openalex")
        self.assertNotIn("client-secret", str(session.calls))

    def test_semantic_scholar_route_uses_header_key(self) -> None:
        session = RecordingSession()
        proxy = SourceApiProxy(session=session)

        with patch.dict(os.environ, {"SEMANTIC_SCHOLAR_API_KEY": "server-s2"}, clear=False):
            proxy.handle_get("/lookup/semantic-scholar/DOI:10.1234/example", "fields=paperId")

        self.assertTrue(session.calls[0]["url"].endswith("/paper/DOI:10.1234/example"))
        self.assertEqual(session.calls[0]["headers"]["x-api-key"], "server-s2")

    def test_doaj_route_maps_to_search_articles(self) -> None:
        session = RecordingSession()
        proxy = SourceApiProxy(session=session)

        with patch.dict(os.environ, {"DOAJ_API_KEY": "server-doaj"}, clear=False):
            proxy.handle_get("/search/doaj-premium/battery", "page=1")

        self.assertTrue(session.calls[0]["url"].endswith("/search/articles/battery"))
        self.assertEqual(session.calls[0]["params"]["api_key"], "server-doaj")

    def test_cache_reuses_successful_response_without_second_upstream_call(self) -> None:
        session = RecordingSession()
        proxy = SourceApiProxy(session=session, cache_ttl=60)

        proxy.handle_get("/search/openalex", "search=battery")
        proxy.handle_get("/search/openalex", "search=battery")

        self.assertEqual(len(session.calls), 1)


if __name__ == "__main__":
    unittest.main()
