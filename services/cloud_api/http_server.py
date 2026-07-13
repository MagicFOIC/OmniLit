from __future__ import annotations

import ipaddress
import json
import logging
import threading
import time
import uuid
from collections import defaultdict, deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

from omnilit_qt.shared_protocol import PROTOCOL_VERSION, SharedProtocolError

from .service import CloudApiError, CloudApiService
from .operations import OperationsMetrics


MAX_REQUEST_BYTES = 128 * 1024
MAX_GRAPH_REQUEST_BYTES = 16 * 1024 * 1024
LOGGER = logging.getLogger("omnilit.cloud_api.http")


class CloudApiServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], handler: type[BaseHTTPRequestHandler], *, service: CloudApiService, allowed_origins: set[str], tls_terminated: bool = False, rate_limit_per_minute: int = 120, max_collaboration_streams: int = 64, metrics_token: str | None = None) -> None:
        if not tls_terminated and not ipaddress.ip_address(address[0]).is_loopback:
            raise ValueError("Cloud API requires TLS termination when binding outside loopback")
        self.service = service
        self.allowed_origins = frozenset(allowed_origins)
        self.rate_limit_per_minute = max(1, rate_limit_per_minute)
        self._rate_lock = threading.Lock()
        self._rate_windows: dict[str, deque[float]] = defaultdict(deque)
        self._collaboration_stream_capacity = max(1, int(max_collaboration_streams))
        self._collaboration_stream_slots = threading.BoundedSemaphore(self._collaboration_stream_capacity)
        self._collaboration_stream_lock = threading.Lock()
        self._collaboration_stream_active = 0
        self.operations = OperationsMetrics(metrics_token)
        self.operations.set_collaboration_streams(0, self._collaboration_stream_capacity)
        super().__init__(address, handler)

    def rate_allowed(self, key: str, limit: int | None = None) -> bool:
        now = time.monotonic()
        with self._rate_lock:
            window = self._rate_windows[key]
            while window and window[0] <= now - 60:
                window.popleft()
            if len(window) >= (limit or self.rate_limit_per_minute):
                return False
            window.append(now)
            return True

    def server_close(self) -> None:
        self.service.shutdown(wait=True)
        super().server_close()

    def acquire_collaboration_stream(self) -> bool:
        acquired = self._collaboration_stream_slots.acquire(blocking=False)
        if acquired:
            with self._collaboration_stream_lock:
                self._collaboration_stream_active += 1
                self.operations.set_collaboration_streams(self._collaboration_stream_active, self._collaboration_stream_capacity)
        return acquired

    def release_collaboration_stream(self) -> None:
        self._collaboration_stream_slots.release()
        with self._collaboration_stream_lock:
            self._collaboration_stream_active = max(0, self._collaboration_stream_active - 1)
            self.operations.set_collaboration_streams(self._collaboration_stream_active, self._collaboration_stream_capacity)

    def set_backup_status(self, snapshot) -> None:
        self.operations.set_backup_snapshot(snapshot)


class CloudApiHandler(BaseHTTPRequestHandler):
    server: CloudApiServer
    protocol_version = "HTTP/1.1"

    def log_message(self, _format: str, *args: object) -> None:
        return

    def _headers(self, status: int, length: int, request_id: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
        self.send_header("X-OmniLit-Protocol-Version", PROTOCOL_VERSION)
        self.send_header("X-Request-Id", request_id)
        origin = self.headers.get("Origin", "")
        if origin and origin in self.server.allowed_origins:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.end_headers()

    def _json(self, status: int, payload: dict[str, Any], request_id: str) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self._headers(status, len(body), request_id)
        self.wfile.write(body)
        self.server.operations.request_completed(self.command, self._route_label(), status, time.monotonic() - getattr(self, "_request_started", time.monotonic()))
        LOGGER.info(json.dumps({"event": "cloud_request_complete", "requestId": request_id, "method": self.command, "route": self._route_label(), "status": status, "elapsedMs": round((time.monotonic() - getattr(self, "_request_started", time.monotonic())) * 1000, 2)}, separators=(",", ":")))

    def _text(self, status: int, body: str, request_id: str, content_type: str) -> None:
        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Request-Id", request_id)
        self.end_headers()
        self.wfile.write(encoded)
        self.server.operations.request_completed(self.command, self._route_label(), status, time.monotonic() - self._request_started)

    def _binary(self, status: int, body: bytes, request_id: str, content_type: str, filename: str) -> None:
        safe_name = "".join(char for char in filename if char.isalnum() or char in "._- ")[:180] or "attachment"
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Disposition", f'attachment; filename="{safe_name}"')
        self.send_header("Cache-Control", "private, no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Request-Id", request_id)
        self.end_headers()
        self.wfile.write(body)
        self.server.operations.request_completed(self.command, self._route_label(), status, time.monotonic() - self._request_started)

    def _event_stream(self, payload: dict[str, Any], request_id: str) -> None:
        frames: list[str] = []
        if payload["resetRequired"]:
            frames.append(f"event: reset\ndata: {json.dumps({'protocolVersion': PROTOCOL_VERSION, 'recordId': payload['recordId'], 'currentRevision': payload['currentRevision']}, separators=(',', ':'))}\n\n")
        for event in payload["events"]:
            frames.append(f"id: {event['revision']}\nevent: collaboration\ndata: {json.dumps(event, ensure_ascii=False, separators=(',', ':'))}\n\n")
        if not frames:
            frames.append(f"event: heartbeat\ndata: {json.dumps({'protocolVersion': PROTOCOL_VERSION, 'recordId': payload['recordId'], 'currentRevision': payload['currentRevision']}, separators=(',', ':'))}\n\n")
        body = "".join(frames).encode("utf-8")
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-cache, no-store")
            self.send_header("X-Accel-Buffering", "no")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
            self.send_header("X-OmniLit-Protocol-Version", PROTOCOL_VERSION)
            self.send_header("X-Request-Id", request_id)
            origin = self.headers.get("Origin", "")
            if origin and origin in self.server.allowed_origins:
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Vary", "Origin")
            self.end_headers()
            self.wfile.write(body)
            status = 200
        except OSError:
            status = 499
        self.server.operations.request_completed(self.command, self._route_label(), status, time.monotonic() - getattr(self, "_request_started", time.monotonic()))
        LOGGER.info(json.dumps({"event": "cloud_request_complete", "requestId": request_id, "method": self.command, "route": self._route_label(), "status": status, "elapsedMs": round((time.monotonic() - getattr(self, "_request_started", time.monotonic())) * 1000, 2)}, separators=(",", ":")))

    def _route_label(self) -> str:
        parts = [part for part in urlsplit(self.path).path.split("/") if part]
        if parts[:3] == ["v1", "public", "shares"]:
            return "/v1/public/shares/{token}"
        if parts[:2] == ["v1", "shares"] and len(parts) == 3:
            return "/v1/shares/{shareId}"
        if parts[:2] == ["v1", "graphs"] and len(parts) >= 3:
            suffix_parts = parts[3:]
            if len(suffix_parts) == 2 and suffix_parts[0] == "nodes":
                suffix_parts[1] = "{nodeId}:neighbors" if suffix_parts[1].endswith(":neighbors") else "{nodeId}"
            elif len(suffix_parts) == 2 and suffix_parts[0] == "views":
                suffix_parts[1] = "{viewId}"
            suffix = "/".join(suffix_parts)
            return f"/v1/graphs/{{recordId}}/{suffix}".rstrip("/")
        if parts[:2] == ["v1", "tasks"] and len(parts) >= 3:
            return "/v1/tasks/{taskId}" + ("/result" if len(parts) == 4 else (":cancel" if parts[2].endswith(":cancel") else ""))
        if parts[:3] == ["v1", "team", "members"] and len(parts) == 4:
            return "/v1/team/members/{memberId}"
        if parts[:2] == ["v1", "permissions"] and len(parts) > 2:
            return "/v1/permissions/{resourceType}/{resourceId}"
        return "/" + "/".join(parts[:3])

    def _error(self, error: CloudApiError, request_id: str) -> None:
        self._json(error.status, {"protocolVersion": PROTOCOL_VERSION, "code": error.code, "message": str(error), "retryable": error.retryable, "requestId": request_id}, request_id)

    def _body(self, max_bytes: int = MAX_REQUEST_BYTES) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0") or 0)
        except ValueError as exc:
            raise CloudApiError(400, "invalid_content_length", "Content-Length must be an integer") from exc
        if length < 0 or length > max_bytes:
            raise CloudApiError(413, "request_too_large", "Request body is too large")
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError as exc:
            raise CloudApiError(400, "invalid_json", "Request body must be valid JSON") from exc
        if not isinstance(payload, dict):
            raise CloudApiError(400, "invalid_input", "Request body must be an object")
        return payload

    def _body_bytes(self, max_bytes: int) -> bytes:
        try:
            length = int(self.headers.get("Content-Length", "0") or 0)
        except ValueError as exc:
            raise CloudApiError(400, "invalid_content_length", "Content-Length must be an integer") from exc
        if length < 1 or length > max_bytes:
            raise CloudApiError(413, "request_too_large", "Binary request body is too large")
        return self.rfile.read(length)

    def _actor(self):
        authorization = self.headers.get("Authorization", "")
        if not authorization.startswith("Bearer "):
            raise CloudApiError(401, "unauthorized", "A valid Cloud API session is required")
        return self.server.service.authenticate(authorization[7:])

    def _dispatch(self, method: str) -> None:
        self._request_started = time.monotonic()
        self.server.operations.request_started()
        request_id = uuid.uuid4().hex
        origin = self.headers.get("Origin", "")
        if origin and origin not in self.server.allowed_origins:
            self._error(CloudApiError(403, "origin_forbidden", "Origin is not allowed"), request_id)
            return
        parsed = urlsplit(self.path)
        parts = [unquote(value) for value in parsed.path.split("/") if value]
        if method == "GET" and parts == ["internal", "metrics"]:
            if not self.server.operations.configured:
                self._error(CloudApiError(404, "not_found", "Cloud API route not found"), request_id)
                return
            authorization = self.headers.get("Authorization", "")
            if not authorization.startswith("Bearer ") or not self.server.operations.authorized(authorization[7:]):
                self._error(CloudApiError(401, "unauthorized", "A valid operations credential is required"), request_id)
                return
            self._text(200, self.server.operations.render(self.server.service.operational_health()), request_id, "text/plain; version=0.0.4; charset=utf-8")
            return
        client = self.client_address[0]
        auth_route = len(parts) >= 2 and parts[:2] == ["v1", "auth"]
        public_account_route = auth_route or parts == ["v1", "team", "invites:accept"]
        if not self.server.rate_allowed(f"{client}:{'/'.join(parts[:3])}", 10 if public_account_route else None):
            self._error(CloudApiError(429, "rate_limited", "Too many requests", retryable=True), request_id)
            return
        try:
            if method == "GET" and parts == ["v1", "health", "live"]:
                self._json(200, {"protocolVersion": PROTOCOL_VERSION, "status": "alive", "service": "omnilit-cloud-api"}, request_id)
                return
            if method == "GET" and parts in (["v1", "health"], ["v1", "health", "ready"]):
                health = self.server.service.operational_health()
                self._json(200 if health["status"] == "ready" else 503, health, request_id)
                return
            if method == "POST" and parts == ["v1", "auth", "register"]:
                body = self._body()
                email = str(body.get("email") or "").strip().casefold()
                if not self.server.service.persistent_rate_allowed(f"register:ip:{client}", 10, 3600) or not self.server.service.persistent_rate_allowed(f"register:email:{email}", 3, 3600):
                    raise CloudApiError(429, "registration_rate_limited", "Too many registration attempts", retryable=True)
                result = self.server.service.register(email, str(body.get("password") or ""), str(body.get("displayName") or ""), str(body.get("tenantName") or ""), request_id, turnstile_token=str(body.get("turnstileToken") or ""), remote_ip=client)
                self._json(201, result, request_id)
                return
            if method == "POST" and parts == ["v1", "auth", "login"]:
                body = self._body()
                email = str(body.get("email") or "").strip().casefold()
                if not self.server.service.persistent_rate_allowed(f"login:ip:{client}", 30, 900) or not self.server.service.persistent_rate_allowed(f"login:email:{email}", 10, 900):
                    raise CloudApiError(429, "login_rate_limited", "Too many login attempts", retryable=True)
                self._json(200, self.server.service.login(str(body.get("email") or ""), str(body.get("password") or ""), request_id), request_id)
                return
            if method == "POST" and parts == ["v1", "team", "invites:accept"]:
                self._json(200, self.server.service.accept_team_invite(self._body(), request_id), request_id)
                return
            if method == "POST" and parts == ["v1", "auth", "verify-email"]:
                self._json(200, self.server.service.verify_email(str(self._body().get("token") or "")), request_id)
                return
            if method == "POST" and parts == ["v1", "auth", "resend-verification"]:
                body = self._body()
                email = str(body.get("email") or "").strip().casefold()
                if not self.server.service.persistent_rate_allowed(f"verify-resend:ip:{client}", 10, 3600) or not self.server.service.persistent_rate_allowed(f"verify-resend:email:{email}", 3, 3600):
                    raise CloudApiError(429, "verification_rate_limited", "Too many verification email requests", retryable=True)
                self._json(202, self.server.service.resend_verification(email), request_id)
                return
            if method == "POST" and parts == ["v1", "auth", "forgot-password"]:
                body = self._body()
                email = str(body.get("email") or "").strip().casefold()
                if not self.server.service.persistent_rate_allowed(f"password-reset:ip:{client}", 10, 3600) or not self.server.service.persistent_rate_allowed(f"password-reset:email:{email}", 3, 3600):
                    raise CloudApiError(429, "password_reset_rate_limited", "Too many password reset requests", retryable=True)
                self._json(202, self.server.service.request_password_reset(email), request_id)
                return
            if method == "POST" and parts == ["v1", "auth", "reset-password"]:
                body = self._body()
                self._json(200, self.server.service.reset_password(str(body.get("token") or ""), str(body.get("newPassword") or "")), request_id)
                return
            if method == "GET" and len(parts) == 4 and parts[:3] == ["v1", "public", "shares"]:
                self._json(200, self.server.service.resolve_share(parts[3]), request_id)
                return
            if method == "POST" and parts == ["v1", "public", "library", "query"]:
                self._json(200, self.server.service.query_public_library(self._body()), request_id)
                return
            if method == "POST" and parts in (["v1", "public", "reports"], ["v1", "public", "takedown-requests"]):
                request_type = "report" if parts[-1] == "reports" else "copyright"
                if not self.server.service.persistent_rate_allowed(f"public-{request_type}:ip:{client}", 10, 3600):
                    raise CloudApiError(429, "public_report_rate_limited", "Too many public report requests", retryable=True)
                self._json(202, self.server.service.create_public_takedown_request(self._body(), request_type, client), request_id)
                return
            actor = self._actor()
            if method == "GET" and parts == ["v1", "account", "me"]:
                self._json(200, self.server.service.account(actor), request_id)
                return
            if method == "POST" and parts == ["v1", "auth", "logout"]:
                self.server.service.logout(actor, self.headers.get("Authorization", "")[7:], request_id)
                self._json(200, {"protocolVersion": PROTOCOL_VERSION, "loggedOut": True}, request_id)
                return
            if method == "POST" and parts == ["v1", "account", "password"]:
                body = self._body()
                self._json(200, self.server.service.change_password(actor, str(body.get("currentPassword") or ""), str(body.get("newPassword") or ""), request_id), request_id)
                return
            if method == "GET" and parts == ["v1", "account", "devices"]:
                self._json(200, self.server.service.list_sessions(actor), request_id)
                return
            if method == "DELETE" and len(parts) == 4 and parts[:3] == ["v1", "account", "devices"]:
                self.server.service.revoke_session(actor, parts[3], request_id)
                self._json(200, {"protocolVersion": PROTOCOL_VERSION, "revoked": True}, request_id)
                return
            if method == "PATCH" and parts == ["v1", "account", "data-controls"]:
                self._json(200, self.server.service.update_controls(actor, self._body(), request_id), request_id)
                return
            if method == "GET" and parts == ["v1", "workspaces", "me"]:
                self._json(200, self.server.service.workspace_summary(actor), request_id)
                return
            if parts == ["v1", "sync", "workspace", "preferences"]:
                if method == "GET":
                    self._json(200, self.server.service.workspace_sync_preferences(actor), request_id)
                    return
                if method == "PATCH":
                    self._json(200, self.server.service.update_workspace_sync_preferences(actor, self._body()), request_id)
                    return
            if method == "GET" and parts == ["v1", "sync", "workspace", "status"]:
                self._json(200, self.server.service.workspace_sync_status(actor), request_id)
                return
            if method == "GET" and parts == ["v1", "sync", "workspace", "changes"]:
                query = parse_qs(parsed.query)
                self._json(200, self.server.service.pull_workspace_changes(actor, int((query.get("cursor") or [0])[0]), int((query.get("limit") or [200])[0])), request_id)
                return
            if method == "POST" and parts == ["v1", "sync", "workspace", "push"]:
                self._json(200, self.server.service.push_workspace_changes(actor, self._body(MAX_GRAPH_REQUEST_BYTES), request_id), request_id)
                return
            if method == "POST" and parts == ["v1", "library", "query"]:
                self._json(200, self.server.service.query_private_library(actor, self._body()), request_id)
                return
            if method == "GET" and parts == ["v1", "library", "state"]:
                self._json(200, self.server.service.cloud_library_state(actor), request_id)
                return
            if method == "POST" and parts == ["v1", "library", "state", "mutations"]:
                self._json(200, self.server.service.mutate_cloud_library_state(actor, self._body(), request_id), request_id)
                return
            if method == "GET" and parts == ["v1", "workspace"]:
                self._json(200, self.server.service.cloud_research_workspace(actor), request_id)
                return
            if method == "GET" and parts == ["v1", "statistics"]:
                self._json(200, self.server.service.cloud_research_statistics(actor), request_id)
                return
            if parts == ["v1", "settings", "business"]:
                if method == "GET":
                    self._json(200, self.server.service.cloud_business_settings(actor), request_id)
                    return
                if method == "POST":
                    self._json(200, self.server.service.update_cloud_business_settings(actor, self._body(), request_id), request_id)
                    return
            if method == "POST" and parts == ["v1", "assets", "uploads"]:
                self._json(201, self.server.service.initialize_asset_upload(actor, self._body()), request_id)
                return
            if method == "PUT" and len(parts) == 6 and parts[:3] == ["v1", "assets", "uploads"] and parts[4] == "chunks":
                self._json(200, self.server.service.append_asset_chunk(actor, parts[3], int(parts[5]), self._body_bytes(4 * 1024 * 1024)), request_id)
                return
            if method == "POST" and len(parts) == 4 and parts[:3] == ["v1", "assets", "uploads"] and parts[3].endswith(":complete"):
                self._json(200, self.server.service.complete_asset_upload(actor, parts[3][:-9]), request_id)
                return
            if method == "GET" and len(parts) == 4 and parts[:2] == ["v1", "assets"] and parts[3] == "content":
                metadata, content = self.server.service.read_asset(actor, parts[2])
                self._binary(200, content, request_id, metadata["mediaType"], metadata["filename"])
                return
            if method == "GET" and len(parts) == 4 and parts[:3] == ["v1", "library", "records"]:
                self._json(200, self.server.service.private_library_record(actor, parts[3]), request_id)
                return
            if parts == ["v1", "public", "submissions"]:
                if method == "GET":
                    self._json(200, self.server.service.list_public_submissions(actor), request_id)
                    return
                if method == "POST":
                    self._json(201, self.server.service.create_public_submission(actor, self._body(MAX_GRAPH_REQUEST_BYTES), request_id), request_id)
                    return
            if len(parts) == 4 and parts[:3] == ["v1", "public", "submissions"]:
                if method == "GET":
                    self._json(200, self.server.service.get_public_submission(actor, parts[3]), request_id)
                    return
            if method == "POST" and len(parts) == 4 and parts[:3] == ["v1", "public", "submissions"] and parts[3].endswith(":submit"):
                self._json(200, self.server.service.submit_public_submission(actor, parts[3][:-7], request_id), request_id)
                return
            if method == "POST" and len(parts) == 4 and parts[:3] == ["v1", "public", "submissions"] and parts[3].endswith(":withdraw"):
                self._json(200, self.server.service.request_public_withdrawal(actor, parts[3][:-9], request_id), request_id)
                return
            if method == "GET" and parts == ["v1", "admin", "public-submissions"]:
                self._json(200, self.server.service.list_public_submissions(actor, moderation=True), request_id)
                return
            if method == "POST" and len(parts) == 4 and parts[:3] == ["v1", "admin", "public-submissions"]:
                self._json(200, self.server.service.moderate_public_submission(actor, parts[3], self._body(), request_id), request_id)
                return
            if method == "GET" and parts == ["v1", "admin", "takedown-requests"]:
                self._json(200, self.server.service.list_public_takedown_requests(actor), request_id)
                return
            if method == "POST" and len(parts) == 4 and parts[:3] == ["v1", "admin", "takedown-requests"]:
                self._json(200, self.server.service.decide_public_takedown_request(actor, parts[3], self._body(), request_id), request_id)
                return
            if method == "PATCH" and len(parts) == 5 and parts[:3] == ["v1", "admin", "accounts"] and parts[4] == "quota":
                body = self._body()
                self._json(200, self.server.service.set_account_quota(actor, parts[3], int(body.get("quotaBytes") or 0), request_id), request_id)
                return
            if method == "POST" and parts == ["v1", "diagnostics"]:
                self._json(202, self.server.service.submit_diagnostic(actor, self._body()), request_id)
                return
            if method == "GET" and parts == ["v1", "account", "export"]:
                self._json(200, self.server.service.export_account(actor, request_id), request_id)
                return
            if method == "DELETE" and parts == ["v1", "account"]:
                self.server.service.delete_account(actor, str(self._body().get("confirmation") or ""), request_id)
                self._json(200, {"protocolVersion": PROTOCOL_VERSION, "deleted": True}, request_id)
                return
            if method == "GET" and parts == ["v1", "sync", "library"]:
                self._json(200, self.server.service.get_library(actor), request_id)
                return
            if method == "POST" and parts == ["v1", "sync", "library"]:
                result = self.server.service.sync_library(actor, self._body(), request_id)
                self._json(409 if result["status"] == "conflict" else 200, result, request_id)
                return
            if method == "POST" and parts == ["v1", "shares"]:
                self._json(201, self.server.service.create_share(actor, self._body(), request_id), request_id)
                return
            if method == "DELETE" and len(parts) == 3 and parts[:2] == ["v1", "shares"]:
                self.server.service.revoke_share(actor, parts[2], request_id)
                self._json(200, {"protocolVersion": PROTOCOL_VERSION, "revoked": True}, request_id)
                return
            if method == "GET" and parts == ["v1", "audit", "events"]:
                self._json(200, self.server.service.audit_events(actor), request_id)
                return
            if method == "GET" and parts == ["v1", "metrics"]:
                self._json(200, self.server.service.cloud_metrics(actor), request_id)
                return
            if len(parts) >= 2 and parts[:2] == ["v1", "tasks"]:
                if method == "POST" and len(parts) == 2:
                    body = self._body()
                    self._json(202, self.server.service.create_cloud_task(actor, str(body.get("type") or ""), body.get("input") if isinstance(body.get("input"), dict) else {}, request_id), request_id)
                    return
                if method == "GET" and len(parts) == 3:
                    self._json(200, self.server.service.get_cloud_task(actor, parts[2]), request_id)
                    return
                if method == "POST" and len(parts) == 3 and parts[2].endswith(":cancel"):
                    self._json(200, self.server.service.cancel_cloud_task(actor, parts[2][:-7], request_id), request_id)
                    return
                if method == "GET" and len(parts) == 4 and parts[3] == "result":
                    self._json(200, self.server.service.cloud_task_result(actor, parts[2]), request_id)
                    return
            if method == "GET" and parts == ["v1", "team", "members"]:
                self._json(200, self.server.service.list_team_members(actor), request_id)
                return
            if method == "POST" and parts == ["v1", "team", "invites"]:
                self._json(201, self.server.service.create_team_invite(actor, self._body(), request_id), request_id)
                return
            if len(parts) == 4 and parts[:3] == ["v1", "team", "members"]:
                if method == "PATCH":
                    self._json(200, self.server.service.update_member_role(actor, parts[3], str(self._body().get("role") or ""), request_id), request_id)
                    return
                if method == "DELETE":
                    self.server.service.remove_team_member(actor, parts[3], request_id)
                    self._json(200, {"protocolVersion": PROTOCOL_VERSION, "removed": True}, request_id)
                    return
            if method == "GET" and len(parts) == 4 and parts[:2] == ["v1", "permissions"]:
                self._json(200, self.server.service.list_resource_permissions(actor, parts[2], parts[3]), request_id)
                return
            if method == "POST" and parts == ["v1", "permissions"]:
                self._json(200, self.server.service.set_resource_permission(actor, self._body(), request_id), request_id)
                return
            if method == "GET" and parts == ["v1", "graphs"]:
                self._json(200, self.server.service.list_cloud_graphs(actor), request_id)
                return
            if len(parts) >= 3 and parts[:2] == ["v1", "graphs"]:
                record_id = parts[2]
                query = parse_qs(parsed.query)
                if method == "GET" and len(parts) == 3:
                    self._json(200, self.server.service.get_cloud_graph(actor, record_id), request_id)
                    return
                if method == "POST" and len(parts) == 4 and parts[3] == "sync":
                    result = self.server.service.sync_graph(actor, self._body(MAX_GRAPH_REQUEST_BYTES), request_id, expected_record_id=record_id)
                    self._json(409 if result["status"] == "conflict" else 200, result, request_id)
                    return
                if len(parts) == 4 and parts[3] == "collaboration":
                    if method == "GET":
                        self._json(200, self.server.service.collaboration_snapshot(actor, record_id), request_id)
                        return
                    if method == "POST":
                        self._json(200, self.server.service.mutate_collaboration(actor, record_id, self._body(), request_id), request_id)
                        return
                if method == "GET" and len(parts) in {5, 6} and parts[3:5] == ["collaboration", "events"]:
                    try:
                        default_after = self.headers.get("Last-Event-ID", "0") or "0"
                        after_revision = int((query.get("afterRevision") or [default_after])[0])
                        limit = int((query.get("limit") or [100])[0])
                        wait_seconds = float((query.get("waitSeconds") or [0])[0])
                    except ValueError as exc:
                        raise CloudApiError(400, "invalid_collaboration_query", "Collaboration query values must be numeric") from exc
                    needs_slot = wait_seconds > 0 or len(parts) == 6
                    if needs_slot and not self.server.acquire_collaboration_stream():
                        raise CloudApiError(503, "collaboration_stream_capacity", "Collaboration stream capacity is full", retryable=True)
                    try:
                        page = self.server.service.collaboration_events(actor, record_id, after_revision, limit=limit, wait_seconds=wait_seconds)
                        if len(parts) == 6 and parts[5] == "stream":
                            self._event_stream(page, request_id)
                        elif len(parts) == 5:
                            self._json(200, page, request_id)
                        else:
                            raise CloudApiError(404, "not_found", "Cloud API route not found")
                    finally:
                        if needs_slot:
                            self.server.release_collaboration_stream()
                    return
                if method == "GET" and len(parts) == 5 and parts[3] == "nodes" and parts[4].endswith(":neighbors"):
                    try:
                        offset, limit = int((query.get("offset") or [0])[0]), int((query.get("limit") or [12])[0])
                    except ValueError as exc:
                        raise CloudApiError(400, "invalid_pagination", "Graph pagination values must be integers") from exc
                    self._json(200, self.server.service.cloud_graph_neighbors(actor, record_id, parts[4][:-10], (query.get("mode") or ["all"])[0], offset, limit), request_id)
                    return
                if method == "POST" and len(parts) == 5 and parts[3:] == ["literature", "query"]:
                    self._json(200, self.server.service.cloud_graph_literature(actor, record_id, self._body(),), request_id)
                    return
                if len(parts) == 4 and parts[3] == "views":
                    if method == "GET":
                        self._json(200, self.server.service.list_cloud_views(actor, record_id), request_id)
                        return
                    if method == "POST":
                        self._json(200, self.server.service.save_cloud_view(actor, record_id, self._body(), request_id), request_id)
                        return
                if len(parts) == 5 and parts[3] == "views":
                    if method == "GET":
                        self._json(200, self.server.service.restore_cloud_view(actor, record_id, parts[4]), request_id)
                        return
                    if method == "DELETE":
                        self._json(200, self.server.service.delete_cloud_view(actor, record_id, parts[4], request_id), request_id)
                        return
            raise CloudApiError(404, "not_found", "Cloud API route not found")
        except SharedProtocolError as exc:
            self._error(CloudApiError(400, exc.code, str(exc)), request_id)
        except CloudApiError as exc:
            self._error(exc, request_id)
        except Exception:
            self._error(CloudApiError(500, "internal_error", "Cloud API request failed", retryable=True), request_id)

    def do_GET(self) -> None:
        self._dispatch("GET")

    def do_POST(self) -> None:
        self._dispatch("POST")

    def do_PATCH(self) -> None:
        self._dispatch("PATCH")

    def do_DELETE(self) -> None:
        self._dispatch("DELETE")

    def do_PUT(self) -> None:
        self._dispatch("PUT")

    def do_OPTIONS(self) -> None:
        request_id = uuid.uuid4().hex
        origin = self.headers.get("Origin", "")
        if not origin or origin not in self.server.allowed_origins:
            self._error(CloudApiError(403, "origin_forbidden", "Origin is not allowed"), request_id)
            return
        self.send_response(204)
        self.send_header("Content-Length", "0")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, PATCH, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type, X-OmniLit-Protocol-Version")
        self.send_header("Access-Control-Max-Age", "600")
        self.send_header("Vary", "Origin")
        self.send_header("X-Request-Id", request_id)
        self.end_headers()


def make_server(host: str, port: int, *, service: CloudApiService, allowed_origins: set[str], tls_terminated: bool = False, rate_limit_per_minute: int = 120, max_collaboration_streams: int = 64, metrics_token: str | None = None) -> CloudApiServer:
    return CloudApiServer((host, port), CloudApiHandler, service=service, allowed_origins=allowed_origins, tls_terminated=tls_terminated, rate_limit_per_minute=rate_limit_per_minute, max_collaboration_streams=max_collaboration_streams, metrics_token=metrics_token)
