from __future__ import annotations

import hmac
import ipaddress
import json
import logging
import mimetypes
import secrets
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

from omnilit_qt.shared_protocol import PROTOCOL_VERSION, SharedProtocolError

from .graph_service import GraphService, GraphServiceError
from .task_registry import TaskRegistry, TaskRegistryError


LOGGER = logging.getLogger("omnilit.local_agent")
MAX_REQUEST_BYTES = 64 * 1024
MAX_WEB_ASSET_BYTES = 32 * 1024 * 1024
WEB_ASSET_SUFFIXES = {".html", ".js", ".css", ".json", ".png", ".svg", ".ico", ".woff", ".woff2"}


class LocalAgentServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], handler: type[BaseHTTPRequestHandler], *, service: GraphService, tasks: TaskRegistry, token: str, allowed_origins: set[str], max_concurrency: int = 8, web_root: Path | None = None) -> None:
        host = address[0]
        try:
            if not ipaddress.ip_address(host).is_loopback:
                raise ValueError("Local Agent must bind to a loopback address")
        except ValueError as exc:
            if str(exc) == "Local Agent must bind to a loopback address":
                raise
            raise ValueError("Local Agent host must be an IP loopback address") from exc
        self.service = service
        self.tasks = tasks
        self.access_token = token
        configured_origins = set(allowed_origins)
        self.request_slots = threading.BoundedSemaphore(max(1, max_concurrency))
        candidate = Path(web_root).resolve() if web_root else None
        self.web_root = candidate if candidate and (candidate / "index.html").is_file() else None
        super().__init__(address, handler)
        own_origin = f"http://{self.server_address[0]}:{self.server_address[1]}"
        self.allowed_origins = frozenset({*configured_origins, own_origin})

    def server_close(self) -> None:
        self.tasks.shutdown(wait=True)
        super().server_close()


class _Handler(BaseHTTPRequestHandler):
    server: LocalAgentServer
    protocol_version = "HTTP/1.1"

    def log_message(self, _format: str, *args: object) -> None:
        return

    def _origin(self) -> str:
        return self.headers.get("Origin", "")

    def _origin_allowed(self) -> bool:
        origin = self._origin()
        return not origin or origin in self.server.allowed_origins

    def _headers(self, status: int, length: int, request_id: str, content_type: str = "application/json; charset=utf-8") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self' qrc:; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' blob: data:; connect-src 'self' ws: http://127.0.0.1:* http://localhost:* http://[::1]:*; object-src 'none'; "
            "base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
        )
        self.send_header("X-OmniLit-Protocol-Version", PROTOCOL_VERSION)
        self.send_header("X-Request-Id", request_id)
        origin = self._origin()
        if origin and origin in self.server.allowed_origins:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.end_headers()

    def _json(self, status: int, payload: dict[str, Any], request_id: str) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self._headers(status, len(body), request_id)
        self.wfile.write(body)

    def _web_asset(self, parts: list[str], request_id: str) -> bool:
        root = self.server.web_root
        if root is None or not parts or parts[0] != "app":
            return False
        relative = Path(*parts[1:]) if len(parts) > 1 else Path("index.html")
        if relative.suffix.casefold() not in WEB_ASSET_SUFFIXES:
            self._error(404, "web_asset_not_found", "Embedded web asset not found", request_id)
            return True
        target = (root / relative).resolve()
        if not target.is_relative_to(root) or not target.is_file():
            self._error(404, "web_asset_not_found", "Embedded web asset not found", request_id)
            return True
        size = target.stat().st_size
        if size > MAX_WEB_ASSET_BYTES:
            self._error(413, "web_asset_too_large", "Embedded web asset is too large", request_id)
            return True
        body = target.read_bytes()
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type in {"application/javascript", "application/json"}:
            content_type += "; charset=utf-8"
        self._headers(200, len(body), request_id, content_type)
        self.wfile.write(body)
        return True

    def _error(self, status: int, code: str, message: str, request_id: str, *, retryable: bool = False) -> None:
        self._json(status, {"protocolVersion": PROTOCOL_VERSION, "code": code, "message": message, "retryable": retryable, "requestId": request_id}, request_id)

    def _authorized(self) -> bool:
        expected = f"Bearer {self.server.access_token}"
        return hmac.compare_digest(self.headers.get("Authorization", ""), expected)

    def _guard(self, request_id: str) -> bool:
        if not self._origin_allowed():
            self._error(403, "origin_forbidden", "Origin is not allowed", request_id)
            return False
        if not self._authorized():
            self._error(401, "unauthorized", "A valid Local Agent token is required", request_id)
            return False
        return True

    def _body(self, request_id: str) -> dict[str, Any] | None:
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length < 0 or length > MAX_REQUEST_BYTES:
            self._error(413, "request_too_large", "Request body is too large", request_id)
            return None
        body = json.loads(self.rfile.read(length) or b"{}")
        if not isinstance(body, dict):
            raise GraphServiceError("invalid_input", "Request body must be an object")
        return body

    def _dispatch(self, method: str) -> None:
        request_id = uuid.uuid4().hex
        if not self.server.request_slots.acquire(blocking=False):
            self._error(503, "agent_busy", "Local Agent concurrency limit reached", request_id, retryable=True)
            return
        try:
            if not self._guard(request_id):
                return
            parsed = urlsplit(self.path)
            parts = [unquote(part) for part in parsed.path.split("/") if part]
            if method == "GET" and self._web_asset(parts, request_id):
                return
            if method == "GET" and parts == ["v1", "health"]:
                self._json(200, {"protocolVersion": PROTOCOL_VERSION, "status": "ready", "service": "omnilit-local-agent"}, request_id)
                return
            if parts == ["v1", "sync", "local", "preferences"]:
                if method == "GET":
                    self._json(200, self.server.service.local_sync_preferences(), request_id)
                    return
                if method == "POST":
                    body = self._body(request_id)
                    if body is None: return
                    self._json(200, self.server.service.update_local_sync_preferences(body), request_id)
                    return
            if method == "GET" and parts == ["v1", "sync", "local", "status"]:
                self._json(200, self.server.service.local_sync_status(), request_id)
                return
            if parts == ["v1", "sync", "local", "outbox"]:
                if method == "GET":
                    self._json(200, self.server.service.local_sync_batch(), request_id)
                    return
                if method == "POST":
                    body = self._body(request_id)
                    if body is None: return
                    self._json(202, self.server.service.enqueue_local_sync_change(body), request_id)
                    return
            if method == "POST" and parts == ["v1", "sync", "local", "results"]:
                body = self._body(request_id)
                if body is None: return
                self._json(200, self.server.service.apply_local_sync_result(body), request_id)
                return
            if method == "POST" and len(parts) == 5 and parts[:4] == ["v1", "sync", "local", "conflicts"]:
                body = self._body(request_id)
                if body is None: return
                self._json(200, self.server.service.resolve_local_sync_conflict(parts[4], body), request_id)
                return
            if method == "POST" and parts == ["v1", "library", "query"]:
                body = self._body(request_id)
                if body is None:
                    return
                self._json(200, self.server.service.library(body), request_id)
                return
            if method == "GET" and parts == ["v1", "library", "state"]:
                self._json(200, self.server.service.library_state(), request_id)
                return
            if method == "GET" and parts == ["v1", "workspace"]:
                self._json(200, self.server.service.research_workspace(), request_id)
                return
            if method == "GET" and parts == ["v1", "statistics"]:
                self._json(200, self.server.service.research_statistics(), request_id)
                return
            if parts == ["v1", "settings", "business"]:
                if method == "GET":
                    self._json(200, self.server.service.business_settings(), request_id)
                    return
                if method == "POST":
                    body = self._body(request_id)
                    if body is None:
                        return
                    self._json(200, self.server.service.update_business_settings(body), request_id)
                    return
            if method == "POST" and parts == ["v1", "library", "state", "mutations"]:
                body = self._body(request_id)
                if body is None:
                    return
                self._json(200, self.server.service.mutate_library_state(body), request_id)
                return
            if method == "GET" and len(parts) == 4 and parts[:3] == ["v1", "library", "records"]:
                self._json(200, self.server.service.library_detail(parts[3]), request_id)
                return
            if len(parts) >= 2 and parts[:2] == ["v1", "tasks"]:
                if method == "POST" and len(parts) == 2:
                    body = self._body(request_id)
                    if body is None:
                        return
                    task_input = body["input"] if "input" in body else {}
                    self._json(202, self.server.tasks.create(str(body.get("type") or ""), task_input), request_id)
                    return
                if method == "GET" and len(parts) == 3:
                    self._json(200, self.server.tasks.get(parts[2]), request_id)
                    return
                if method == "POST" and len(parts) == 3 and parts[2].endswith(":cancel"):
                    self._json(200, self.server.tasks.cancel(parts[2][:-7]), request_id)
                    return
                if method == "GET" and len(parts) == 4 and parts[3] == "result":
                    self._json(200, self.server.tasks.result(parts[2]), request_id)
                    return
            if method == "POST" and len(parts) == 4 and parts[:2] == ["v1", "timelines"] and parts[3] == "query":
                body = self._body(request_id)
                if body is None:
                    return
                self._json(200, self.server.service.timeline(parts[2], body), request_id)
                return
            if method == "GET" and parts == ["v1", "graphs"]:
                self._json(200, self.server.service.list_graphs(), request_id)
                return
            if len(parts) >= 3 and parts[:2] == ["v1", "graphs"]:
                record_id = parts[2]
                query = parse_qs(parsed.query)
                if method == "GET" and len(parts) == 3:
                    self._json(200, self.server.service.initial_graph(record_id), request_id)
                    return
                if method == "GET" and len(parts) == 5 and parts[3] == "nodes" and parts[4].endswith(":neighbors"):
                    node_id = parts[4][:-10]
                    payload = self.server.service.neighbors(record_id, node_id, (query.get("mode") or ["all"])[0], int((query.get("offset") or [0])[0]), int((query.get("limit") or [12])[0]))
                    self._json(200, payload, request_id)
                    return
                if method == "POST" and len(parts) == 4 and parts[3] == "projection":
                    body = self._body(request_id)
                    if body is None:
                        return
                    self._json(200, self.server.service.projection(record_id, body), request_id)
                    return
                if len(parts) == 4 and parts[3] == "views":
                    if method == "GET":
                        self._json(200, self.server.service.list_views(record_id), request_id)
                        return
                    if method == "POST":
                        body = self._body(request_id)
                        if body is None:
                            return
                        self._json(200, self.server.service.save_view(record_id, body), request_id)
                        return
                if len(parts) == 5 and parts[3] == "views":
                    if method == "GET":
                        self._json(200, self.server.service.restore_view(record_id, parts[4]), request_id)
                        return
                    if method == "DELETE":
                        self._json(200, self.server.service.delete_view(record_id, parts[4]), request_id)
                        return
                if method == "POST" and len(parts) == 5 and parts[3:] == ["literature", "query"]:
                    body = self._body(request_id)
                    if body is None:
                        return
                    self._json(200, self.server.service.literature(record_id, body), request_id)
                    return
            self._error(404, "not_found", "Local Agent route not found", request_id)
        except GraphServiceError as exc:
            self._error(exc.status, exc.code, str(exc), request_id)
        except SharedProtocolError as exc:
            self._error(400, exc.code, str(exc), request_id)
        except TaskRegistryError as exc:
            self._error(exc.status, exc.code, str(exc), request_id, retryable=exc.status >= 500)
        except (ValueError, TypeError, json.JSONDecodeError):
            self._error(400, "invalid_input", "Request parameters are invalid", request_id)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            LOGGER.exception("local_agent_request_failed request_id=%s", request_id)
            self._error(500, "internal_error", "Local Agent request failed", request_id, retryable=True)
        finally:
            self.server.request_slots.release()

    def do_OPTIONS(self) -> None:
        LOGGER.info(
            "local_agent_preflight origin=%s private_network=%s",
            self._origin() or "none",
            self.headers.get("Access-Control-Request-Private-Network", "false"),
        )
        request_id = uuid.uuid4().hex
        if not self._origin_allowed():
            self._error(403, "origin_forbidden", "Origin is not allowed", request_id)
            return
        self.send_response(204)
        origin = self._origin()
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type, X-OmniLit-Protocol-Version")
        if self.headers.get("Access-Control-Request-Private-Network", "").casefold() == "true":
            self.send_header("Access-Control-Allow-Private-Network", "true")
        self.send_header("Access-Control-Max-Age", "600")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:
        self._dispatch("GET")

    def do_POST(self) -> None:
        self._dispatch("POST")

    def do_DELETE(self) -> None:
        self._dispatch("DELETE")


def create_local_agent_server(*, data_root: Path, host: str = "127.0.0.1", port: int = 0, token: str | None = None, allowed_origins: set[str] | None = None, max_concurrency: int = 8, web_root: Path | None = None) -> LocalAgentServer:
    access_token = token or secrets.token_urlsafe(32)
    if len(access_token) < 24:
        raise ValueError("Local Agent token must contain at least 24 characters")
    service = GraphService(data_root)
    tasks = TaskRegistry(Path(data_root).resolve() / "runtime" / "local_agent" / "tasks", {"graph.audit": service.audit_task, "research.brief": service.research_brief_task})
    return LocalAgentServer((host, port), _Handler, service=service, tasks=tasks, token=access_token, allowed_origins=allowed_origins or set(), max_concurrency=max_concurrency, web_root=web_root)
