from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import threading
import time
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse

import requests


OPENALEX_WORKS_URL = "https://api.openalex.org/works"
SEMANTIC_SCHOLAR_PAPER_URL = "https://api.semanticscholar.org/graph/v1/paper"
DOAJ_SEARCH_ARTICLES_URL = "https://doaj.org/api/v4/search/articles"
DEFAULT_TIMEOUT = (8, 45)
DEFAULT_CACHE_TTL = 300
DEFAULT_MAX_CACHE_ITEMS = 512
DEFAULT_RATE_LIMITS = {
    "openalex": 0.1,
    "semantic_scholar": 1.0,
    "doaj": 0.5,
}
SECRET_QUERY_KEYS = {"api_key", "apikey", "key", "token"}


@dataclass(frozen=True)
class ProxyRoute:
    source: str
    upstream_url: str
    api_key_env: str
    key_location: str


@dataclass
class CacheEntry:
    status_code: int
    headers: dict[str, str]
    body: bytes
    expires_at: float


class RateLimiter:
    def __init__(self, limits: dict[str, float] | None = None) -> None:
        self.limits = dict(limits or DEFAULT_RATE_LIMITS)
        self._last_request: dict[str, float] = {}
        self._locks: dict[str, threading.Lock] = {}

    def wait(self, source: str) -> None:
        delay = max(0.0, float(self.limits.get(source, 0.0)))
        if delay <= 0:
            return
        lock = self._locks.setdefault(source, threading.Lock())
        with lock:
            last = self._last_request.get(source)
            if last is not None:
                remaining = delay - (time.monotonic() - last)
                if remaining > 0:
                    time.sleep(remaining)
            self._last_request[source] = time.monotonic()


class ResponseCache:
    def __init__(self, ttl: int = DEFAULT_CACHE_TTL, max_items: int = DEFAULT_MAX_CACHE_ITEMS) -> None:
        self.ttl = max(0, int(ttl))
        self.max_items = max(1, int(max_items))
        self._lock = threading.Lock()
        self._items: dict[str, CacheEntry] = {}

    def get(self, key: str) -> CacheEntry | None:
        if self.ttl <= 0:
            return None
        with self._lock:
            item = self._items.get(key)
            if not item:
                return None
            if item.expires_at <= time.monotonic():
                self._items.pop(key, None)
                return None
            return item

    def set(self, key: str, entry: CacheEntry) -> None:
        if self.ttl <= 0 or entry.status_code >= 500:
            return
        with self._lock:
            if len(self._items) >= self.max_items:
                oldest = min(self._items.items(), key=lambda item: item[1].expires_at)[0]
                self._items.pop(oldest, None)
            self._items[key] = entry


class SourceApiProxy:
    def __init__(
        self,
        *,
        cache_ttl: int = DEFAULT_CACHE_TTL,
        max_cache_items: int = DEFAULT_MAX_CACHE_ITEMS,
        session: requests.Session | None = None,
    ) -> None:
        self.cache = ResponseCache(cache_ttl, max_cache_items)
        self.rate_limiter = RateLimiter()
        self.session = session or requests.Session()

    def handle_get(self, path: str, query: str) -> tuple[int, dict[str, str], bytes]:
        if path.rstrip("/") == "/health":
            return HTTPStatus.OK, {"content-type": "application/json"}, b'{"ok":true}\n'
        route, params = resolve_route(path, query)
        cache_key = cache_key_for(route, params)
        cached = self.cache.get(cache_key)
        if cached:
            return cached.status_code, dict(cached.headers), cached.body

        started = time.monotonic()
        self.rate_limiter.wait(route.source)
        response = self._fetch_with_retry(route, params)
        headers = response_headers(response)
        body = response.content
        status_code = int(response.status_code)
        self.cache.set(
            cache_key,
            CacheEntry(
                status_code=status_code,
                headers=headers,
                body=body,
                expires_at=time.monotonic() + self.cache.ttl,
            ),
        )
        logging.info(
            "source_proxy source=%s status=%s elapsed_ms=%s",
            route.source,
            status_code,
            int((time.monotonic() - started) * 1000),
        )
        return status_code, headers, body

    def _fetch_with_retry(self, route: ProxyRoute, params: dict[str, str]) -> requests.Response:
        last_response: requests.Response | None = None
        for attempt in range(3):
            response = self._fetch_once(route, params)
            last_response = response
            if response.status_code not in {429, 500, 502, 503, 504} or attempt >= 2:
                return response
            retry_after = response.headers.get("Retry-After")
            try:
                delay = float(retry_after) if retry_after else 2.0 ** attempt
            except (TypeError, ValueError):
                delay = 2.0 ** attempt
            time.sleep(max(0.0, min(30.0, delay)))
        return last_response if last_response is not None else self._fetch_once(route, params)

    def _fetch_once(self, route: ProxyRoute, params: dict[str, str]) -> requests.Response:
        outbound_params = {key: value for key, value in params.items() if key.lower() not in SECRET_QUERY_KEYS}
        headers = {"User-Agent": "OmniLitSourceProxy/1.0 (+https://github.com/MagicFOIC/OmniLit)"}
        api_key = os.getenv(route.api_key_env, "").strip()
        if api_key:
            if route.key_location == "query":
                outbound_params.setdefault("api_key", api_key)
            elif route.key_location == "header":
                headers["x-api-key"] = api_key
        return self.session.get(route.upstream_url, params=outbound_params, headers=headers, timeout=DEFAULT_TIMEOUT)


def resolve_route(path: str, query: str) -> tuple[ProxyRoute, dict[str, str]]:
    clean_path = "/" + path.strip("/")
    params = dict(parse_qsl(query, keep_blank_values=True))
    if clean_path == "/search/openalex":
        return ProxyRoute("openalex", OPENALEX_WORKS_URL, "OPENALEX_API_KEY", "query"), params
    if clean_path.startswith("/search/openalex/"):
        suffix = clean_path.removeprefix("/search/openalex")
        return ProxyRoute("openalex", OPENALEX_WORKS_URL + suffix, "OPENALEX_API_KEY", "query"), params
    if clean_path == "/lookup/semantic-scholar":
        return ProxyRoute("semantic_scholar", SEMANTIC_SCHOLAR_PAPER_URL, "SEMANTIC_SCHOLAR_API_KEY", "header"), params
    if clean_path.startswith("/lookup/semantic-scholar/"):
        suffix = clean_path.removeprefix("/lookup/semantic-scholar")
        return ProxyRoute("semantic_scholar", SEMANTIC_SCHOLAR_PAPER_URL + suffix, "SEMANTIC_SCHOLAR_API_KEY", "header"), params
    if clean_path == "/search/doaj-premium":
        return ProxyRoute("doaj", DOAJ_SEARCH_ARTICLES_URL, "DOAJ_API_KEY", "query"), params
    if clean_path.startswith("/search/doaj-premium/"):
        suffix = clean_path.removeprefix("/search/doaj-premium")
        return ProxyRoute("doaj", DOAJ_SEARCH_ARTICLES_URL + suffix, "DOAJ_API_KEY", "query"), params
    raise ValueError("unsupported route")


def cache_key_for(route: ProxyRoute, params: dict[str, str]) -> str:
    safe_params = sorted((key, value) for key, value in params.items() if key.lower() not in SECRET_QUERY_KEYS)
    raw = json.dumps([route.source, route.upstream_url, safe_params], sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def response_headers(response: requests.Response) -> dict[str, str]:
    headers = {
        "content-type": response.headers.get("content-type", "application/json"),
        "cache-control": "public, max-age=300",
    }
    retry_after = response.headers.get("Retry-After")
    if retry_after:
        headers["retry-after"] = retry_after
    return headers


class ProxyHandler(BaseHTTPRequestHandler):
    proxy = SourceApiProxy(
        cache_ttl=int(os.getenv("OMNILIT_SOURCE_PROXY_CACHE_TTL", str(DEFAULT_CACHE_TTL))),
        max_cache_items=int(os.getenv("OMNILIT_SOURCE_PROXY_CACHE_ITEMS", str(DEFAULT_MAX_CACHE_ITEMS))),
    )

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        try:
            status_code, headers, body = self.proxy.handle_get(parsed.path, parsed.query)
        except ValueError:
            status_code, headers, body = HTTPStatus.NOT_FOUND, {"content-type": "application/json"}, b'{"error":"not_found"}\n'
        except requests.RequestException:
            logging.exception("source_proxy upstream_error path=%s", parsed.path)
            status_code, headers, body = HTTPStatus.BAD_GATEWAY, {"content-type": "application/json"}, b'{"error":"upstream_error"}\n'
        self.send_response(int(status_code))
        for key, value in headers.items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        logging.info("source_proxy client=%s message=%s", self.client_address[0], format % args)


def make_server(host: str, port: int) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), ProxyHandler)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the OmniLit source API proxy.")
    parser.add_argument("--host", default=os.getenv("OMNILIT_SOURCE_PROXY_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("OMNILIT_SOURCE_PROXY_PORT", "8765")))
    parser.add_argument("--log-level", default=os.getenv("OMNILIT_SOURCE_PROXY_LOG_LEVEL", "INFO"))
    args = parser.parse_args(argv)
    logging.basicConfig(level=getattr(logging, str(args.log_level).upper(), logging.INFO), format="%(asctime)s %(levelname)s %(message)s")
    server = make_server(args.host, args.port)
    logging.info("source_proxy listening host=%s port=%s", args.host, args.port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logging.info("source_proxy stopping")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
