from __future__ import annotations

import http.client
import json
import tempfile
import threading
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from omnilit_qt.shared_protocol import PROTOCOL_VERSION
from services.cloud_api import CloudApiService
from services.cloud_api.http_server import make_server


class CloudApiHttpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        service = CloudApiService(Path(self.temp.name) / "cloud.sqlite3", b"k" * 32, public_base_url="https://cloud.example")
        self.server = make_server("127.0.0.1", 0, service=service, allowed_origins={"https://app.example"}, metrics_token="operations-metrics-token-value-123456")
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_address[1]

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temp.cleanup()

    def request(self, method: str, path: str, body: dict | None = None, token: str = "", origin: str = "https://app.example") -> tuple[int, dict, dict]:
        status, raw, response_headers = self.request_raw(method, path, body, token, origin)
        return status, json.loads(raw) if raw else {}, response_headers

    def request_raw(self, method: str, path: str, body: dict | None = None, token: str = "", origin: str = "https://app.example") -> tuple[int, bytes, dict]:
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
        headers = {"Origin": origin, "Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        connection.request(method, path, body=json.dumps(body).encode() if body is not None else None, headers=headers)
        response = connection.getresponse()
        raw = response.read()
        response_headers = dict(response.getheaders())
        connection.close()
        return response.status, raw, response_headers

    def test_account_sync_conflict_and_security_headers(self) -> None:
        status, session, headers = self.request("POST", "/v1/auth/register", {"email": "owner@example.com", "password": "correct-horse-battery", "displayName": "Owner", "tenantName": "Lab"})
        self.assertEqual(status, 201)
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(headers["Access-Control-Allow-Origin"], "https://app.example")
        token = session["accessToken"]
        status, account, _ = self.request("GET", "/v1/account/me", token=token)
        self.assertEqual((status, account["email"]), (200, "owner@example.com"))
        state = {"protocolVersion": PROTOCOL_VERSION, "revision": 0, "updatedAt": "", "syncState": "local_only", "collections": [], "favorites": {}, "workspace": {"compareRecordIds": []}}
        sync = {"protocolVersion": PROTOCOL_VERSION, "deviceId": "web", "baseCloudRevision": 0, "state": state}
        self.assertEqual(self.request("POST", "/v1/sync/library", sync, token)[0], 200)
        status, conflict, _ = self.request("POST", "/v1/sync/library", sync, token)
        self.assertEqual((status, conflict["status"], conflict["cloudRevision"]), (409, "conflict", 1))

    def test_account_devices_password_change_and_logout(self) -> None:
        _, session, _ = self.request("POST", "/v1/auth/register", {"email": "security@example.com", "password": "correct-horse-battery", "displayName": "Owner", "tenantName": "Lab"})
        token = session["accessToken"]
        status, devices, _ = self.request("GET", "/v1/account/devices", token=token)
        self.assertEqual((status, len(devices["devices"])), (200, 1))
        status, changed, _ = self.request("POST", "/v1/account/password", {"currentPassword": "correct-horse-battery", "newPassword": "new-correct-horse-battery"}, token)
        self.assertEqual((status, changed["changed"]), (200, True))
        self.assertEqual(self.request("GET", "/v1/account/me", token=token)[0], 401)
        _, next_session, _ = self.request("POST", "/v1/auth/login", {"email": "security@example.com", "password": "new-correct-horse-battery"})
        next_token = next_session["accessToken"]
        self.assertEqual(self.request("POST", "/v1/auth/logout", token=next_token)[0], 200)
        self.assertEqual(self.request("GET", "/v1/account/me", token=next_token)[0], 401)

    def test_origin_auth_and_tls_guards(self) -> None:
        self.assertEqual(self.request("GET", "/v1/account/me")[0], 401)
        self.assertEqual(self.request("GET", "/v1/health", origin="https://evil.example")[0], 403)
        status, readiness, _ = self.request("GET", "/v1/health/ready")
        self.assertEqual((status, readiness["status"], readiness["checks"]["database"]), (200, "ready", "ready"))
        status, liveness, _ = self.request("GET", "/v1/health/live")
        self.assertEqual((status, liveness["status"]), (200, "alive"))
        service = CloudApiService(Path(self.temp.name) / "second.sqlite3", b"z" * 32)
        with self.assertRaises(ValueError):
            make_server("0.0.0.0", 0, service=service, allowed_origins=set(), tls_terminated=False)

    def test_operations_metrics_use_a_separate_credential_and_templated_labels(self) -> None:
        self.assertEqual(self.request("GET", "/internal/metrics")[0], 401)
        _, session, _ = self.request("POST", "/v1/auth/register", {"email": "metrics-owner@example.com", "password": "correct-horse-battery", "displayName": "Owner", "tenantName": "Lab"})
        self.assertEqual(self.request("GET", "/internal/metrics", token=session["accessToken"])[0], 401)
        status, body, headers = self.request_raw("GET", "/internal/metrics", token="operations-metrics-token-value-123456")
        text = body.decode("utf-8")
        self.assertEqual(status, 200)
        self.assertIn("text/plain; version=0.0.4", headers["Content-Type"])
        self.assertIn("omnilit_cloud_ready 1", text)
        self.assertIn('route="/v1/auth/register"', text)
        self.assertIn("omnilit_cloud_http_request_duration_seconds_bucket", text)
        self.assertNotIn("metrics-owner@example.com", text)
        self.assertNotIn(session["accessToken"], text)

    def test_browser_preflight_is_exact_origin_and_bounded(self) -> None:
        status, _, headers = self.request("OPTIONS", "/v1/account/data-controls")
        self.assertEqual(status, 204)
        self.assertEqual(headers["Access-Control-Allow-Origin"], "https://app.example")
        self.assertIn("PATCH", headers["Access-Control-Allow-Methods"])
        self.assertIn("Authorization", headers["Access-Control-Allow-Headers"])

    def test_diagnostic_upload_is_authenticated_opt_in_and_content_bounded(self) -> None:
        _, session, _ = self.request("POST", "/v1/auth/register", {"email": "diagnostic@example.com", "password": "correct-horse-battery", "displayName": "Owner", "tenantName": "Lab"})
        token = session["accessToken"]
        report = {"protocolVersion": PROTOCOL_VERSION, "occurredAt": datetime.now(timezone.utc).isoformat(), "source": "react", "code": "render_error", "exceptionType": "TypeError", "fingerprint": "01234567", "severity": "error", "appVersion": "0.1.0"}
        self.assertEqual(self.request("POST", "/v1/diagnostics", report)[0], 401)
        status, disabled, _ = self.request("POST", "/v1/diagnostics", report, token)
        self.assertEqual((status, disabled["code"]), (403, "diagnostic_sharing_disabled"))
        _, account, _ = self.request("GET", "/v1/account/me", token=token)
        updated = {**account["dataControls"], "shareDiagnostics": True}
        self.assertEqual(self.request("PATCH", "/v1/account/data-controls", updated, token)[0], 200)
        status, receipt, _ = self.request("POST", "/v1/diagnostics", report, token)
        self.assertEqual((status, receipt["accepted"]), (202, True))
        status, invalid, _ = self.request("POST", "/v1/diagnostics", {**report, "stack": "C:/private/paper.pdf"}, token)
        self.assertEqual((status, invalid["code"]), (400, "invalid_diagnostic_report"))

    def test_team_invite_and_resource_permission_http_contract(self) -> None:
        _, owner_session, _ = self.request("POST", "/v1/auth/register", {"email": "owner@example.com", "password": "correct-horse-battery", "displayName": "Owner", "tenantName": "Lab"})
        owner_token = owner_session["accessToken"]
        status, invite, _ = self.request("POST", "/v1/team/invites", {"protocolVersion": PROTOCOL_VERSION, "email": "member@example.com", "role": "member"}, owner_token)
        self.assertEqual(status, 201)
        invite_token = invite["url"].rsplit("/", 1)[-1]
        status, member_session, _ = self.request("POST", "/v1/team/invites:accept", {"protocolVersion": PROTOCOL_VERSION, "token": invite_token, "displayName": "Member", "password": "member-password-value"})
        self.assertEqual(status, 200)
        status, members, _ = self.request("GET", "/v1/team/members", token=owner_token)
        self.assertEqual((status, len(members["members"])), (200, 2))
        member = next(item for item in members["members"] if item["email"] == "member@example.com")
        status, permissions, _ = self.request("POST", "/v1/permissions", {"protocolVersion": PROTOCOL_VERSION, "resourceType": "library_state", "resourceId": "current", "principalType": "user", "principalId": member["id"], "permission": "viewer"}, owner_token)
        self.assertEqual((status, permissions["permissions"][0]["permission"]), (200, "viewer"))
        self.assertEqual(self.request("GET", "/v1/permissions/library_state/current", token=owner_token)[0], 200)
        self.assertEqual(self.request("GET", "/v1/audit/events", token=member_session["accessToken"])[0], 403)

    def test_public_invite_acceptance_uses_auth_rate_limit(self) -> None:
        body = {"protocolVersion": PROTOCOL_VERSION, "token": "x" * 32, "displayName": "Member", "password": "member-password-value"}
        statuses = [self.request("POST", "/v1/team/invites:accept", body)[0] for _ in range(11)]
        self.assertEqual(statuses[:10], [404] * 10)
        self.assertEqual(statuses[10], 429)

    def test_cloud_graph_query_sync_neighbors_and_views_contract(self) -> None:
        _, session, _ = self.request("POST", "/v1/auth/register", {"email": "owner@example.com", "password": "correct-horse-battery", "displayName": "Owner", "tenantName": "Lab"})
        token = session["accessToken"]
        graph = json.loads((Path(__file__).parents[1] / "packages" / "shared-schema" / "fixtures" / "shared-graph-v1.json").read_text(encoding="utf-8"))
        record_id = quote(graph["recordId"], safe="")
        status, synced, _ = self.request("POST", f"/v1/graphs/{record_id}/sync", {"protocolVersion": PROTOCOL_VERSION, "deviceId": "desktop", "baseCloudRevision": 0, "graph": graph}, token)
        self.assertEqual((status, synced["cloudRevision"]), (200, 1))
        status, mismatch, _ = self.request("POST", "/v1/graphs/other-record/sync", {"protocolVersion": PROTOCOL_VERSION, "deviceId": "desktop", "baseCloudRevision": 0, "graph": graph}, token)
        self.assertEqual((status, mismatch["code"]), (409, "graph_record_mismatch"))
        self.assertEqual(self.request("GET", f"/v1/graphs/{record_id}", token=token)[1]["recordId"], graph["recordId"])
        self.assertEqual(self.request("GET", "/v1/graphs", token=token)[1]["graphs"][0]["nodeCount"], len(graph["nodes"]))
        seed = graph["nodes"][0]["id"]
        status, neighbors, _ = self.request("GET", f"/v1/graphs/{record_id}/nodes/{quote(seed, safe='')}:neighbors?limit=5", token=token)
        self.assertEqual(status, 200)
        self.assertEqual(neighbors["nodeId"], seed)
        self.assertEqual(self.request("GET", f"/v1/graphs/{record_id}/nodes/{quote(seed, safe='')}:neighbors?offset=invalid", token=token)[0], 400)
        status, literature, _ = self.request("POST", f"/v1/graphs/{record_id}/literature/query", {"visibleNodeIds": [node["id"] for node in graph["nodes"]]}, token)
        self.assertEqual(status, 200)
        self.assertEqual(literature["recordId"], graph["recordId"])
        view = CloudApiServiceTestsView.value()
        status, saved, _ = self.request("POST", f"/v1/graphs/{record_id}/views", view, token)
        self.assertEqual(status, 200)
        self.assertEqual(self.request("GET", f"/v1/graphs/{record_id}/views", token=token)[1]["views"][0]["id"], saved["id"])
        self.assertEqual(self.request("GET", f"/v1/graphs/{record_id}/views/{saved['id']}", token=token)[0], 200)
        self.assertEqual(self.request("DELETE", f"/v1/graphs/{record_id}/views/{saved['id']}", token=token)[1]["deleted"], True)

    def test_cloud_task_result_metrics_and_redacted_request_log_contract(self) -> None:
        _, session, _ = self.request("POST", "/v1/auth/register", {"email": "owner@example.com", "password": "correct-horse-battery", "displayName": "Owner", "tenantName": "Lab"})
        token = session["accessToken"]
        graph = json.loads((Path(__file__).parents[1] / "packages" / "shared-schema" / "fixtures" / "shared-graph-v1.json").read_text(encoding="utf-8"))
        record_id = quote(graph["recordId"], safe="")
        self.assertEqual(self.request("POST", f"/v1/graphs/{record_id}/sync", {"protocolVersion": PROTOCOL_VERSION, "deviceId": "desktop", "baseCloudRevision": 0, "graph": graph}, token)[0], 200)
        status, task, _ = self.request("POST", "/v1/tasks", {"type": "graph.audit", "input": {"recordId": graph["recordId"]}}, token)
        self.assertEqual(status, 202)
        deadline = time.monotonic() + 3
        while task["status"] not in {"succeeded", "failed", "cancelled"} and time.monotonic() < deadline:
            time.sleep(0.01)
            status, task, _ = self.request("GET", f"/v1/tasks/{task['id']}", token=token)
            self.assertEqual(status, 200)
        self.assertEqual(task["status"], "succeeded")
        status, result, _ = self.request("GET", f"/v1/tasks/{task['id']}/result", token=token)
        self.assertEqual((status, result["nodeCount"], result["edgeCount"]), (200, len(graph["nodes"]), len(graph["edges"])))
        status, metrics, _ = self.request("GET", "/v1/metrics", token=token)
        self.assertEqual((status, metrics["cloudGraphs"], metrics["tasksByStatus"]["succeeded"]), (200, 1, 1))
        self.assertEqual(self.request("POST", "/v1/tasks", {"type": "unknown", "input": {}}, token)[0], 400)

        secret = "secret-share-token-that-must-not-be-logged"
        with self.assertLogs("omnilit.cloud_api.http", level="INFO") as captured:
            self.assertEqual(self.request("GET", f"/v1/public/shares/{secret}")[0], 404)
        logged = "\n".join(captured.output)
        self.assertNotIn(secret, logged)
        self.assertIn('"route":"/v1/public/shares/{token}"', logged)
        self.assertIn('"requestId":', logged)

    def test_graph_collaboration_snapshot_mutation_events_and_sse_contract(self) -> None:
        _, session, _ = self.request("POST", "/v1/auth/register", {"email": "owner@example.com", "password": "correct-horse-battery", "displayName": "Owner", "tenantName": "Lab"})
        token = session["accessToken"]
        status, account, _ = self.request("GET", "/v1/account/me", token=token)
        self.assertEqual(status, 200)
        self.assertEqual(self.request("PATCH", "/v1/account/data-controls", {**account["dataControls"], "syncAnnotations": True}, token)[0], 200)
        graph = json.loads((Path(__file__).parents[1] / "packages" / "shared-schema" / "fixtures" / "shared-graph-v1.json").read_text(encoding="utf-8"))
        record_id = quote(graph["recordId"], safe="")
        self.assertEqual(self.request("POST", f"/v1/graphs/{record_id}/sync", {"protocolVersion": PROTOCOL_VERSION, "deviceId": "desktop", "baseCloudRevision": 0, "graph": graph}, token)[0], 200)
        mutation = {"protocolVersion": PROTOCOL_VERSION, "baseRevision": 0, "clientMutationId": "11111111-1111-4111-8111-111111111111", "action": "upsert", "targetType": "node", "targetId": graph["nodes"][0]["id"], "body": "Team annotation"}
        with self.assertLogs("omnilit.cloud_api.http", level="INFO") as captured:
            status, result, _ = self.request("POST", f"/v1/graphs/{record_id}/collaboration", mutation, token)
        self.assertEqual((status, result["revision"]), (200, 1))
        logged = "\n".join(captured.output)
        self.assertNotIn(mutation["body"], logged)
        self.assertNotIn(graph["recordId"], logged)
        self.assertIn('"route":"/v1/graphs/{recordId}/collaboration"', logged)
        status, snapshot, _ = self.request("GET", f"/v1/graphs/{record_id}/collaboration", token=token)
        self.assertEqual((status, snapshot["annotations"][0]["body"]), (200, "Team annotation"))
        status, events, _ = self.request("GET", f"/v1/graphs/{record_id}/collaboration/events?afterRevision=0&limit=10", token=token)
        self.assertEqual((status, events["events"][0]["revision"]), (200, 1))
        status, raw, headers = self.request_raw("GET", f"/v1/graphs/{record_id}/collaboration/events/stream?afterRevision=0&waitSeconds=0", token=token)
        self.assertEqual(status, 200)
        self.assertTrue(headers["Content-Type"].startswith("text/event-stream"))
        self.assertIn(b"event: collaboration", raw)
        self.assertIn(b"id: 1", raw)
        deadline = time.monotonic() + 1
        while self.server._collaboration_stream_active and time.monotonic() < deadline:
            time.sleep(0.01)
        acquired = 0
        while self.server.acquire_collaboration_stream():
            acquired += 1
        try:
            status, capacity, _ = self.request("GET", f"/v1/graphs/{record_id}/collaboration/events/stream?afterRevision=1&waitSeconds=0", token=token)
            self.assertEqual((status, capacity["code"]), (503, "collaboration_stream_capacity"))
        finally:
            for _ in range(acquired):
                self.server.release_collaboration_stream()
        stale = {**mutation, "clientMutationId": "22222222-2222-4222-8222-222222222222", "body": "Stale"}
        status, conflict, _ = self.request("POST", f"/v1/graphs/{record_id}/collaboration", stale, token)
        self.assertEqual((status, conflict["code"]), (409, "collaboration_conflict"))


class CloudApiServiceTestsView:
    @staticmethod
    def value() -> dict:
        return {"protocolVersion": PROTOCOL_VERSION, "name": "Cloud view", "exploration": {"nodeIds": [], "edgeIds": [], "pages": {}}, "filters": {"mode": "all", "searchText": "", "density": "normal", "literatureSortKey": "relevance", "literatureSortDescending": True, "facets": {}, "nodeTypes": [], "needsReviewOnly": False}, "selection": {"nodeId": "", "edgeId": ""}, "viewport": {"displayStyle": "academic", "focusDepth": 0, "reviewMode": False, "graphScale": 1, "panX": 0, "panY": 0, "showArrows": True, "showLabels": True, "dimUnrelated": True, "textFadeThreshold": 1.15, "nodeSizeScale": 1, "linkThickness": 1, "animateLayout": False}}


if __name__ == "__main__":
    unittest.main()
