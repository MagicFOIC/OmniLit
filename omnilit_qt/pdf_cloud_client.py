from __future__ import annotations

import json
import shutil
import threading
import time
import zipfile
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit, urlunsplit

import requests

from .pdf_extraction_settings import redact_sensitive_text


ProgressCallback = Callable[[str, int, str], None]


class CloudAPIError(RuntimeError):
    def __init__(self, message: str, *, code: str = "API_FAILED") -> None:
        super().__init__(redact_sensitive_text(message))
        self.code = code


class CloudAPICancelled(CloudAPIError):
    def __init__(self) -> None:
        super().__init__("Cloud parsing was cancelled.", code="CANCELLED")


class CloudAPIClient:
    def __init__(
        self,
        engine: str,
        *,
        timeout: float = 900.0,
        retries: int = 2,
        cancel_event: threading.Event | None = None,
        progress: ProgressCallback | None = None,
        session: requests.Session | None = None,
    ) -> None:
        self.engine = str(engine)
        self.timeout = max(1.0, float(timeout))
        self.retries = max(0, int(retries))
        self.cancel_event = cancel_event
        self.progress = progress
        self.session = session or requests.Session()

    def notify(self, percent: int, message: str) -> None:
        if callable(self.progress):
            self.progress(self.engine, max(0, min(100, int(percent))), str(message))

    def check_cancelled(self) -> None:
        if self.cancel_event is not None and self.cancel_event.is_set():
            raise CloudAPICancelled()

    def wait(self, seconds: float) -> None:
        deadline = time.monotonic() + max(0.0, float(seconds))
        while time.monotonic() < deadline:
            self.check_cancelled()
            time.sleep(min(0.2, deadline - time.monotonic()))

    def request(
        self,
        method: str,
        url: str,
        *,
        expected: tuple[int, ...] = (200,),
        request_timeout: float | None = None,
        **kwargs: Any,
    ) -> requests.Response:
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            self.check_cancelled()
            try:
                response = self.session.request(
                    method,
                    url,
                    timeout=min(self.timeout, request_timeout or 60.0),
                    **kwargs,
                )
                if response.status_code in expected:
                    return response
                if response.status_code in {401, 403}:
                    raise CloudAPIError("API authentication failed. Check the configured token.", code="AUTH_FAILED")
                if response.status_code == 429:
                    raise CloudAPIError("API quota or rate limit was reached.", code="QUOTA_EXCEEDED")
                detail = _response_detail(response)
                if response.status_code < 500 or attempt >= self.retries:
                    raise CloudAPIError(
                        f"API request failed with HTTP {response.status_code}: {detail}",
                        code="HTTP_ERROR",
                    )
                last_error = CloudAPIError(detail, code="HTTP_ERROR")
            except CloudAPIError:
                raise
            except requests.Timeout as exc:
                last_error = exc
                if attempt >= self.retries:
                    raise CloudAPIError("API request timed out.", code="TIMEOUT") from exc
            except requests.RequestException as exc:
                last_error = exc
                if attempt >= self.retries:
                    raise CloudAPIError(f"Unable to reach API service: {exc}", code="NETWORK_ERROR") from exc
            self.wait(min(2.0, 0.5 * (2**attempt)))
        raise CloudAPIError(f"API request failed: {last_error}", code="API_FAILED")

    def request_json(self, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        response = self.request(method, url, **kwargs)
        try:
            value = response.json()
        except (ValueError, json.JSONDecodeError) as exc:
            raise CloudAPIError("API returned invalid JSON.", code="INVALID_RESPONSE") from exc
        if not isinstance(value, dict):
            raise CloudAPIError("API returned an unexpected JSON value.", code="INVALID_RESPONSE")
        return value

    def download(self, url: str, target: Path) -> Path:
        response = self.request("GET", url, expected=(200,), request_timeout=self.timeout, stream=True)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                self.check_cancelled()
                if chunk:
                    handle.write(chunk)
        return target


def safe_extract_zip(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    with zipfile.ZipFile(archive) as bundle:
        for info in bundle.infolist():
            target = (root / info.filename).resolve()
            try:
                target.relative_to(root)
            except ValueError as exc:
                raise CloudAPIError("Parser archive contains an unsafe path.", code="UNSAFE_ARCHIVE") from exc
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with bundle.open(info) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)


def join_api_url(base_url: str, suffix: str) -> str:
    return str(base_url or "").rstrip("/") + "/" + str(suffix or "").lstrip("/")


def sanitize_url(url: str) -> str:
    try:
        parts = urlsplit(str(url or ""))
        return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
    except ValueError:
        return ""


def _response_detail(response: requests.Response) -> str:
    try:
        value = response.json()
        detail = json.dumps(value, ensure_ascii=False)
    except (ValueError, json.JSONDecodeError):
        detail = str(response.text or "")
    return redact_sensitive_text(detail[:1000])
