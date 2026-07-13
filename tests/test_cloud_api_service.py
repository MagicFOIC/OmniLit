from __future__ import annotations

import sqlite3
import hashlib
import json
import tempfile
import threading
import time
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path

from omnilit_qt.literature_library_shared import LibraryStateStore, project_library_state
from omnilit_qt.shared_protocol import PROTOCOL_VERSION, validate_auth_session, validate_library_sync_result, validate_share_link, validate_user_account
from services.cloud_api import CURRENT_SCHEMA_VERSION, CloudApiError, CloudApiService, CloudSchemaVersionError


class CloudApiServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp.name) / "cloud.sqlite3"
        self.service = CloudApiService(self.db_path, bytes(range(32)), public_base_url="https://cloud.example")

    def tearDown(self) -> None:
        self.service.shutdown()
        self.temp.cleanup()

    def register(self, email: str = "owner@example.com") -> tuple[dict, sqlite3.Row]:
        session = self.service.register(email, "correct-horse-battery", "Owner", "Research Lab", "register-request")
        validate_auth_session(session)
        actor = self.service.authenticate(session["accessToken"])
        validate_user_account(self.service.account(actor))
        return session, actor

    @staticmethod
    def state() -> dict:
        raw = LibraryStateStore.default_state()
        raw["favorites"] = {"paper-001": ["core"]}
        return project_library_state(raw)

    @staticmethod
    def graph() -> dict:
        return json.loads((Path(__file__).parents[1] / "packages" / "shared-schema" / "fixtures" / "shared-graph-v1.json").read_text(encoding="utf-8"))

    @staticmethod
    def view(name: str = "Cloud view") -> dict:
        return {"protocolVersion": PROTOCOL_VERSION, "name": name, "exploration": {"nodeIds": [], "edgeIds": [], "pages": {}}, "filters": {"mode": "all", "searchText": "", "density": "normal", "literatureSortKey": "relevance", "literatureSortDescending": True, "facets": {}, "nodeTypes": [], "needsReviewOnly": False}, "selection": {"nodeId": "", "edgeId": ""}, "viewport": {"displayStyle": "academic", "focusDepth": 0, "reviewMode": False, "graphScale": 1, "panX": 0, "panY": 0, "showArrows": True, "showLabels": True, "dimUnrelated": True, "textFadeThreshold": 1.15, "nodeSizeScale": 1, "linkThickness": 1, "animateLayout": False}}

    def test_registration_hashes_credentials_and_sessions(self) -> None:
        session, _ = self.register()
        raw = self.db_path.read_bytes()
        self.assertNotIn(b"correct-horse-battery", raw)
        self.assertNotIn(session["accessToken"].encode(), raw)
        with self.assertRaises(CloudApiError) as error:
            self.service.login("owner@example.com", "wrong-password", "bad-login")
        self.assertEqual(error.exception.status, 401)

    def test_password_change_device_revocation_and_admin_bootstrap(self) -> None:
        first_session, actor = self.register("security@example.com")
        second_session = self.service.login("security@example.com", "correct-horse-battery", "second-login")
        devices = self.service.list_sessions(actor)["devices"]
        self.assertEqual(len(devices), 2)
        second_hash = next(item["id"] for item in devices if item["id"] == hashlib.sha256(second_session["accessToken"].encode()).hexdigest())
        self.service.revoke_session(actor, second_hash, "revoke-device")
        with self.assertRaises(CloudApiError):
            self.service.authenticate(second_session["accessToken"])
        promoted = self.service.bootstrap_system_admin("security@example.com")
        self.assertTrue(promoted["systemAdmin"])
        changed = self.service.change_password(actor, "correct-horse-battery", "new-correct-horse-battery", "change-password")
        self.assertTrue(changed["changed"])
        with self.assertRaises(CloudApiError):
            self.service.authenticate(first_session["accessToken"])
        self.assertIn("accessToken", self.service.login("security@example.com", "new-correct-horse-battery", "login-new"))

    def test_schema_baseline_and_operational_health_are_persisted(self) -> None:
        health = self.service.operational_health()
        self.assertEqual((health["status"], health["schemaVersion"]), ("ready", CURRENT_SCHEMA_VERSION))
        self.assertEqual(set(health["checks"].values()), {"ready"})
        db = sqlite3.connect(self.db_path)
        try:
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], CURRENT_SCHEMA_VERSION)
            migration = db.execute("SELECT description FROM schema_migrations WHERE version=?", (CURRENT_SCHEMA_VERSION,)).fetchone()
        finally:
            db.close()
        self.assertEqual(migration[0], "Public reports takedown and administrator quota controls")

    def test_every_account_gets_an_independent_personal_workspace(self) -> None:
        first_session, first = self.register("workspace-one@example.com")
        second_session, second = self.register("workspace-two@example.com")
        first_account = self.service.account(first)
        second_account = self.service.account(second)
        self.assertNotEqual(first_account["workspaceId"], second_account["workspaceId"])
        self.assertEqual(self.service.workspace_summary(first)["quotaBytes"], 5 * 1024**3)
        change = {"resourceType": "literature_record", "resourceId": "paper-001", "operation": "upsert", "baseRevision": 0, "clientMutationId": "workspace-one-mutation", "payload": {"recordId": "paper-001", "title": "Private One"}}
        pushed = self.service.push_workspace_changes(first, {"protocolVersion": PROTOCOL_VERSION, "deviceId": "desktop-one", "cursor": 0, "changes": [change]}, "push")
        self.assertEqual(pushed["applied"][0]["revision"], 1)
        self.assertEqual(self.service.query_private_library(first, {})["total"], 1)
        self.assertEqual(self.service.query_private_library(second, {})["total"], 0)
        self.assertEqual(self.service.authenticate(first_session["accessToken"])["id"], first["id"])
        self.assertEqual(self.service.authenticate(second_session["accessToken"])["id"], second["id"])

    def test_workspace_sync_is_idempotent_and_reports_revision_conflicts(self) -> None:
        _, actor = self.register("workspace-sync@example.com")
        change = {"resourceType": "literature_record", "resourceId": "paper-001", "operation": "upsert", "baseRevision": 0, "clientMutationId": "stable-mutation-0001", "payload": {"recordId": "paper-001", "title": "First"}}
        request = {"protocolVersion": PROTOCOL_VERSION, "deviceId": "desktop", "cursor": 0, "changes": [change]}
        first = self.service.push_workspace_changes(actor, request, "push-one")
        duplicate = self.service.push_workspace_changes(actor, request, "push-duplicate")
        self.assertEqual(first["applied"][0]["cursor"], duplicate["applied"][0]["cursor"])
        stale = self.service.push_workspace_changes(actor, {**request, "changes": [{**change, "clientMutationId": "stable-mutation-0002", "payload": {"recordId": "paper-001", "title": "Stale"}}]}, "push-stale")
        self.assertEqual(stale["conflicts"][0]["cloudRevision"], 1)
        self.assertEqual(self.service.pull_workspace_changes(actor, 0)["changes"][0]["payload"]["title"], "First")

    def test_hosted_business_pages_are_workspace_scoped(self) -> None:
        _, first = self.register("hosted-one@example.com")
        _, second = self.register("hosted-two@example.com")
        initial = self.service.cloud_library_state(first)
        result = self.service.mutate_cloud_library_state(first, {"protocolVersion": PROTOCOL_VERSION, "expectedRevision": initial["revision"], "action": "create_collection", "name": "Private collection"}, "library-mutation")
        self.assertTrue(result["changed"])
        self.assertTrue(any(item["name"] == "Private collection" for item in self.service.cloud_library_state(first)["collections"]))
        self.assertFalse(any(item["name"] == "Private collection" for item in self.service.cloud_library_state(second)["collections"]))
        settings = self.service.cloud_business_settings(first)
        updated = self.service.update_cloud_business_settings(first, {**{key: settings[key] for key in ("themeMode", "density", "reduceMotion", "highContrast", "startPage", "defaultLibrarySort", "aiEvidenceLimit", "aiEndpoint", "aiModel", "allowRemoteResearchContent")}, "expectedRevision": settings["revision"], "themeMode": "dark"}, "settings")
        self.assertEqual(updated["themeMode"], "dark")
        self.assertNotEqual(self.service.cloud_business_settings(second)["themeMode"], "dark")
        self.assertEqual(self.service.cloud_research_workspace(second)["status"], "empty")

    def test_public_submission_is_an_independent_moderated_copy(self) -> None:
        _, contributor = self.register("contributor@example.com")
        _, administrator = self.register("administrator@example.com")
        self.service.grant_system_admin(administrator)
        source = {"recordId": "paper-public", "title": "Public Evidence", "authorsText": "Ada", "doi": "10.1000/public"}
        submission = self.service.create_public_submission(contributor, {"protocolVersion": PROTOCOL_VERSION, "sourceResourceId": "paper-public", "record": source, "license": {"code": "cc-by", "url": "https://creativecommons.org/licenses/by/4.0/", "rightsStatement": "The contributor confirms this open license."}, "publicDisplayName": "Contributor"}, "create-public")
        self.assertEqual(submission["status"], "draft")
        submitted = self.service.submit_public_submission(contributor, submission["id"], "submit-public")
        self.assertEqual(submitted["status"], "pending_review")
        approved = self.service.moderate_public_submission(administrator, submission["id"], {"decision": "approve", "note": "License verified"}, "approve-public")
        self.assertEqual(approved["status"], "approved")
        public = self.service.query_public_library({"searchText": "Evidence"})
        self.assertEqual(public["records"][0]["record"]["title"], "Public Evidence")
        report = self.service.create_public_takedown_request({"recordId": public["records"][0]["id"], "reason": "The license evidence should be reviewed again."}, "report", "127.0.0.1")
        self.assertEqual(self.service.list_public_takedown_requests(administrator)["requests"][0]["status"], "pending")
        decision = self.service.decide_public_takedown_request(administrator, report["id"], {"decision": "hide", "note": "Hidden pending review"}, "hide-public")
        self.assertEqual(decision["status"], "actioned")
        self.assertEqual(self.service.query_public_library({})["total"], 0)
        source["title"] = "Private title changed"
        self.assertEqual(public["records"][0]["record"]["title"], "Public Evidence")
        quota = self.service.set_account_quota(administrator, contributor["id"], 7 * 1024**3, "quota")
        self.assertEqual(quota["quotaBytes"], 7 * 1024**3)

    def test_chunked_assets_are_hashed_scanned_isolated_and_promoted(self) -> None:
        owner_session, owner = self.register("asset-owner@example.com")
        _, outsider = self.register("asset-outsider@example.com")
        self.service._clamav_scan = lambda _content: "clean"
        content = b"%PDF-1.7\nprivate evidence\n%%EOF"
        digest = hashlib.sha256(content).hexdigest()
        upload = self.service.initialize_asset_upload(owner, {"scope": "private", "filename": "evidence.pdf", "mediaType": "application/pdf", "sizeBytes": len(content), "sha256": digest})
        self.service.append_asset_chunk(owner, upload["uploadId"], 0, content[:10])
        with self.assertRaises(CloudApiError) as offset:
            self.service.append_asset_chunk(owner, upload["uploadId"], 0, content[10:])
        self.assertEqual(offset.exception.code, "asset_chunk_offset")
        self.service.append_asset_chunk(owner, upload["uploadId"], 10, content[10:])
        asset = self.service.complete_asset_upload(owner, upload["uploadId"])
        self.assertEqual(self.service.read_asset(owner, asset["id"])[1], content)
        with self.assertRaises(CloudApiError):
            self.service.read_asset(outsider, asset["id"])
        self.assertNotIn(content, self.db_path.read_bytes())

        submission = self.service.create_public_submission(owner, {"sourceResourceId": "paper-asset", "record": {"recordId": "paper-asset", "title": "Open attachment"}, "license": {"code": "cc-by", "url": "https://creativecommons.org/licenses/by/4.0/", "rightsStatement": "This PDF is licensed for redistribution."}, "publicDisplayName": "Contributor"}, "submission")
        public_upload = self.service.initialize_asset_upload(owner, {"scope": "public_submission", "submissionId": submission["id"], "filename": "open.pdf", "mediaType": "application/pdf", "sizeBytes": len(content), "sha256": digest})
        self.service.append_asset_chunk(owner, public_upload["uploadId"], 0, content)
        pending_asset = self.service.complete_asset_upload(owner, public_upload["uploadId"])
        with self.assertRaises(CloudApiError):
            self.service.read_asset(owner, pending_asset["id"])
        self.service.submit_public_submission(owner, submission["id"], "submit")
        _, administrator = self.register("asset-admin@example.com")
        self.service.grant_system_admin(administrator)
        self.service.moderate_public_submission(administrator, submission["id"], {"decision": "approve", "note": "Rights and scan verified"}, "approve")
        self.assertEqual(self.service.read_asset(outsider, pending_asset["id"])[1], content)
        self.assertEqual(self.service.workspace_summary(owner)["usedBytes"], len(content))
        self.assertEqual(self.service.authenticate(owner_session["accessToken"])["id"], owner["id"])

    def test_schema_one_database_is_upgraded_transactionally(self) -> None:
        legacy_path = Path(self.temp.name) / "legacy.sqlite3"
        db = sqlite3.connect(legacy_path)
        try:
            db.execute("CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY, description TEXT NOT NULL, applied_at TEXT NOT NULL)")
            db.execute("INSERT INTO schema_migrations VALUES(1, 'legacy', '2026-01-01T00:00:00Z')")
            db.execute("PRAGMA user_version=1")
            db.commit()
        finally:
            db.close()
        upgraded = CloudApiService(legacy_path, b"u" * 32)
        try:
            db = sqlite3.connect(legacy_path)
            try:
                self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], CURRENT_SCHEMA_VERSION)
                self.assertIsNotNone(db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='diagnostic_reports'").fetchone())
            finally:
                db.close()
        finally:
            upgraded.shutdown()

    def test_newer_cloud_database_schema_is_rejected(self) -> None:
        future_path = Path(self.temp.name) / "future.sqlite3"
        db = sqlite3.connect(future_path)
        try:
            db.execute(f"PRAGMA user_version={CURRENT_SCHEMA_VERSION + 1}")
            db.commit()
        finally:
            db.close()
        with self.assertRaisesRegex(CloudSchemaVersionError, "newer than supported"):
            CloudApiService(future_path, bytes(range(32)))

    def test_stopping_service_fails_readiness_but_remains_live_at_process_boundary(self) -> None:
        self.service.shutdown()
        health = self.service.operational_health()
        self.assertEqual(health["status"], "not_ready")
        self.assertEqual(health["checks"]["taskService"], "not_ready")

    def test_sync_is_encrypted_and_rejects_stale_revision(self) -> None:
        _, actor = self.register()
        request = {"protocolVersion": PROTOCOL_VERSION, "deviceId": "desktop-a", "baseCloudRevision": 0, "state": self.state()}
        result = self.service.sync_library(actor, request, "sync-1")
        validate_library_sync_result(result)
        self.assertEqual(result["cloudRevision"], 1)
        self.assertNotIn(b"paper-001", self.db_path.read_bytes())
        conflict = self.service.sync_library(actor, request, "sync-stale")
        validate_library_sync_result(conflict)
        self.assertEqual(conflict["status"], "conflict")
        self.assertEqual(conflict["cloudRevision"], 1)
        self.assertEqual(conflict["serverState"]["favorites"], {"paper-001": ["core"]})

    def test_tenant_isolation_prevents_cross_tenant_reads_and_revocation(self) -> None:
        first_session, first = self.register("first@example.com")
        _, second = self.register("second@example.com")
        self.service.sync_library(first, {"protocolVersion": PROTOCOL_VERSION, "deviceId": "a", "baseCloudRevision": 0, "state": self.state()}, "sync")
        with self.assertRaises(CloudApiError) as missing:
            self.service.get_library(second)
        self.assertEqual(missing.exception.status, 404)
        controls = {"uploadLocalPdfs": False, "syncAnnotations": False, "syncFullText": False, "useCloudAi": False, "retainCloudTaskData": False, "allowTeamAccess": False, "allowShareLinks": True, "shareDiagnostics": False}
        self.service.update_controls(first, controls, "controls")
        first = self.service.authenticate(first_session["accessToken"])
        share = self.service.create_share(first, {"resourceType": "collection", "resourceId": "core", "permission": "viewer"}, "share")
        validate_share_link(share)
        with self.assertRaises(CloudApiError) as forbidden:
            self.service.revoke_share(second, share["id"], "cross-tenant")
        self.assertEqual(forbidden.exception.status, 404)
        token = share["url"].rsplit("/", 1)[-1]
        shared = self.service.resolve_share(token)
        self.assertEqual([item["id"] for item in shared["state"]["collections"]], ["core"])
        self.service.revoke_share(first, share["id"], "revoke")
        with self.assertRaises(CloudApiError):
            self.service.resolve_share(token)

    def test_sharing_requires_explicit_user_control_and_audit_is_tenant_scoped(self) -> None:
        _, actor = self.register()
        with self.assertRaises(CloudApiError) as disabled:
            self.service.create_share(actor, {"resourceType": "library_state", "resourceId": "current", "permission": "viewer"}, "share")
        self.assertEqual(disabled.exception.code, "sharing_disabled")
        events = self.service.audit_events(actor)["events"]
        self.assertTrue(any(event["action"] == "account.register" for event in events))
        self.assertTrue(all(event["actorId"] == actor["id"] for event in events))

    def test_export_and_confirmed_account_deletion(self) -> None:
        session, actor = self.register()
        exported = self.service.export_account(actor, "export")
        self.assertEqual(exported["account"]["email"], "owner@example.com")
        with self.assertRaises(CloudApiError):
            self.service.delete_account(actor, "wrong@example.com", "delete")
        self.service.delete_account(actor, "owner@example.com", "delete")
        with self.assertRaises(CloudApiError):
            self.service.authenticate(session["accessToken"])

    def test_diagnostics_require_opt_in_and_reject_arbitrary_content(self) -> None:
        session, actor = self.register()
        report = {"protocolVersion": PROTOCOL_VERSION, "occurredAt": datetime.now(timezone.utc).isoformat(), "source": "react", "code": "render_error", "exceptionType": "TypeError", "fingerprint": "01234567", "severity": "error", "appVersion": "0.1.0"}
        with self.assertRaises(CloudApiError) as disabled:
            self.service.submit_diagnostic(actor, report)
        self.assertEqual(disabled.exception.code, "diagnostic_sharing_disabled")
        self.service.update_controls(actor, {**self.service.account(actor)["dataControls"], "shareDiagnostics": True}, "opt-in")
        actor = self.service.authenticate(session["accessToken"])
        receipt = self.service.submit_diagnostic(actor, report)
        self.assertTrue(receipt["accepted"])
        with self.assertRaises(CloudApiError) as unsafe:
            self.service.submit_diagnostic(actor, {**report, "message": "token=secret private-paper.pdf"})
        self.assertEqual(unsafe.exception.code, "invalid_diagnostic_report")
        exported = self.service.export_account(actor, "diagnostic-export")
        self.assertEqual(exported["diagnostics"][0]["code"], "render_error")
        self.assertNotIn("actorId", exported["diagnostics"][0])

    def test_diagnostic_daily_quota_and_tenant_retention_are_bounded(self) -> None:
        limited_path = Path(self.temp.name) / "limited.sqlite3"
        limited = CloudApiService(limited_path, b"d" * 32, diagnostic_daily_limit=12, diagnostic_tenant_limit=10)
        try:
            session = limited.register("diagnostic@example.com", "correct-horse-battery", "Owner", "Lab", "register")
            actor = limited.authenticate(session["accessToken"])
            limited.update_controls(actor, {**limited.account(actor)["dataControls"], "shareDiagnostics": True}, "opt-in")
            actor = limited.authenticate(session["accessToken"])
            base = {"protocolVersion": PROTOCOL_VERSION, "occurredAt": datetime.now(timezone.utc).isoformat(), "source": "window", "code": "uncaught_error", "exceptionType": "Error", "severity": "error", "appVersion": "0.1.0"}
            for index in range(10):
                limited.submit_diagnostic(actor, {**base, "fingerprint": f"{index:08x}"})
            db = sqlite3.connect(limited_path)
            try:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM diagnostic_reports").fetchone()[0], 10)
            finally:
                db.close()
            with self.assertRaises(CloudApiError) as quota:
                limited.submit_diagnostic(actor, {**base, "fingerprint": "ffffffff"})
            self.assertEqual((quota.exception.status, quota.exception.code), (429, "diagnostic_quota_exceeded"))
        finally:
            limited.shutdown()

    def test_invite_is_single_use_and_member_access_requires_explicit_acl(self) -> None:
        owner_session, owner = self.register()
        self.service.sync_library(owner, {"protocolVersion": PROTOCOL_VERSION, "deviceId": "owner", "baseCloudRevision": 0, "state": self.state()}, "sync")
        owner_controls = {**self.service.account(owner)["dataControls"], "allowTeamAccess": True, "syncAnnotations": True}
        self.service.update_controls(owner, owner_controls, "team-access")
        owner = self.service.authenticate(owner_session["accessToken"])
        invite = self.service.create_team_invite(owner, {"protocolVersion": PROTOCOL_VERSION, "email": "member@example.com", "role": "member", "expiresInHours": 24}, "invite")
        token = invite["url"].rsplit("/", 1)[-1]
        self.assertNotIn(token.encode(), self.db_path.read_bytes())
        member_session = self.service.accept_team_invite({"protocolVersion": PROTOCOL_VERSION, "token": token, "displayName": "Member", "password": "member-password-value"}, "accept")
        member = self.service.authenticate(member_session["accessToken"])
        with self.assertRaises(CloudApiError) as denied:
            self.service.get_library(member)
        self.assertEqual(denied.exception.code, "permission_denied")
        permissions = self.service.set_resource_permission(owner, {"protocolVersion": PROTOCOL_VERSION, "resourceType": "library_state", "resourceId": "current", "principalType": "user", "principalId": member["id"], "permission": "viewer"}, "grant-viewer")
        self.assertEqual(permissions["permissions"][0]["permission"], "viewer")
        self.assertEqual(self.service.get_library(member)["cloudRevision"], 1)
        with self.assertRaises(CloudApiError):
            self.service.sync_library(member, {"protocolVersion": PROTOCOL_VERSION, "deviceId": "member", "baseCloudRevision": 1, "state": self.state()}, "member-write")
        self.service.set_resource_permission(owner, {"protocolVersion": PROTOCOL_VERSION, "resourceType": "library_state", "resourceId": "current", "principalType": "user", "principalId": member["id"], "permission": "editor"}, "grant-editor")
        self.assertEqual(self.service.sync_library(member, {"protocolVersion": PROTOCOL_VERSION, "deviceId": "member", "baseCloudRevision": 1, "state": self.state()}, "member-write")["cloudRevision"], 2)
        graph = self.graph()
        self.service.sync_graph(owner, {"protocolVersion": PROTOCOL_VERSION, "deviceId": "owner", "baseCloudRevision": 0, "graph": graph}, "graph-sync")
        self.service.set_resource_permission(owner, {"protocolVersion": PROTOCOL_VERSION, "resourceType": "graph", "resourceId": graph["recordId"], "principalType": "user", "principalId": member["id"], "permission": "viewer"}, "graph-viewer")
        self.assertEqual(self.service.get_cloud_graph(member, graph["recordId"])["recordId"], graph["recordId"])
        self.assertEqual(self.service.collaboration_snapshot(member, graph["recordId"])["revision"], 0)
        collaboration = {"protocolVersion": PROTOCOL_VERSION, "baseRevision": 0, "clientMutationId": str(uuid.uuid4()), "action": "upsert", "targetType": "graph", "targetId": graph["recordId"], "body": "Shared review note"}
        with self.assertRaises(CloudApiError) as collaboration_denied:
            self.service.mutate_collaboration(member, graph["recordId"], collaboration, "member-note-denied")
        self.assertEqual(collaboration_denied.exception.status, 403)
        self.assertEqual(self.service.create_cloud_task(member, "graph.audit", {"recordId": graph["recordId"]}, "member-audit")["type"], "graph.audit")
        with self.assertRaises(CloudApiError) as metrics_denied:
            self.service.cloud_metrics(member)
        self.assertEqual(metrics_denied.exception.status, 403)
        with self.assertRaises(CloudApiError):
            self.service.save_cloud_view(member, graph["recordId"], self.view("Member view"), "member-view-denied")
        self.service.set_resource_permission(owner, {"protocolVersion": PROTOCOL_VERSION, "resourceType": "graph", "resourceId": graph["recordId"], "principalType": "user", "principalId": member["id"], "permission": "editor"}, "graph-editor")
        self.assertEqual(self.service.mutate_collaboration(member, graph["recordId"], collaboration, "member-note")["revision"], 1)
        self.assertEqual(self.service.save_cloud_view(member, graph["recordId"], self.view("Member view"), "member-view-save")["recordId"], graph["recordId"])
        with self.assertRaises(CloudApiError) as reused:
            self.service.accept_team_invite({"protocolVersion": PROTOCOL_VERSION, "token": token, "displayName": "Again", "password": "another-password-value"}, "reuse")
        self.assertEqual(reused.exception.code, "invite_not_found")

    def test_team_role_and_cross_tenant_permission_boundaries(self) -> None:
        _, owner = self.register("owner@example.com")
        _, outsider = self.register("outside@example.com")
        invite = self.service.create_team_invite(owner, {"protocolVersion": PROTOCOL_VERSION, "email": "admin@example.com", "role": "admin"}, "invite-admin")
        admin_session = self.service.accept_team_invite({"protocolVersion": PROTOCOL_VERSION, "token": invite["url"].rsplit("/", 1)[-1], "displayName": "Admin", "password": "admin-password-value"}, "accept-admin")
        admin = self.service.authenticate(admin_session["accessToken"])
        with self.assertRaises(CloudApiError):
            self.service.create_team_invite(admin, {"protocolVersion": PROTOCOL_VERSION, "email": "other-admin@example.com", "role": "admin"}, "admin-invite-admin")
        with self.assertRaises(CloudApiError):
            self.service.set_resource_permission(admin, {"protocolVersion": PROTOCOL_VERSION, "resourceType": "library_state", "resourceId": "current", "principalType": "team", "principalId": owner["tenant_id"], "permission": "viewer"}, "admin-acl")
        with self.assertRaises(CloudApiError) as cross_tenant:
            self.service.set_resource_permission(owner, {"protocolVersion": PROTOCOL_VERSION, "resourceType": "library_state", "resourceId": "current", "principalType": "user", "principalId": outsider["id"], "permission": "viewer"}, "cross-tenant")
        self.assertEqual(cross_tenant.exception.code, "principal_not_found")
        members = self.service.update_member_role(owner, admin["id"], "member", "demote")
        self.assertEqual(next(item for item in members["members"] if item["id"] == admin["id"])["role"], "member")
        self.service.remove_team_member(owner, admin["id"], "remove")
        with self.assertRaises(CloudApiError):
            self.service.authenticate(admin_session["accessToken"])

    def test_cloud_graph_sync_is_encrypted_versioned_and_restores_views(self) -> None:
        owner_session, owner = self.register()
        graph = self.graph()
        request = {"protocolVersion": PROTOCOL_VERSION, "deviceId": "desktop", "baseCloudRevision": 0, "graph": graph}
        synced = self.service.sync_graph(owner, request, "graph-sync")
        self.assertEqual((synced["status"], synced["cloudRevision"]), ("synced", 1))
        self.assertNotIn(graph["paper"]["title"].encode("utf-8"), self.db_path.read_bytes())
        self.assertEqual(self.service.get_cloud_graph(owner, graph["recordId"])["nodes"], graph["nodes"])
        self.assertEqual(self.service.list_cloud_graphs(owner)["graphs"][0]["nodeCount"], len(graph["nodes"]))
        conflict = self.service.sync_graph(owner, request, "graph-conflict")
        self.assertEqual((conflict["status"], conflict["cloudRevision"]), ("conflict", 1))
        saved = self.service.save_cloud_view(owner, graph["recordId"], self.view(), "view-save")
        self.assertEqual(self.service.list_cloud_views(owner, graph["recordId"])["views"][0]["id"], saved["id"])
        restored = self.service.restore_cloud_view(owner, graph["recordId"], saved["id"])
        self.assertEqual(restored["graph"]["recordId"], graph["recordId"])
        controls = {**self.service.account(owner)["dataControls"], "allowShareLinks": True}
        self.service.update_controls(owner, controls, "share-controls")
        owner = self.service.authenticate(owner_session["accessToken"])
        share = self.service.create_share(owner, {"resourceType": "graph", "resourceId": graph["recordId"], "permission": "viewer"}, "graph-share")
        self.assertEqual(self.service.resolve_share(share["url"].rsplit("/", 1)[-1])["graph"]["recordId"], graph["recordId"])
        self.assertTrue(self.service.delete_cloud_view(owner, graph["recordId"], saved["id"], "view-delete")["deleted"])
        with self.assertRaises(CloudApiError):
            self.service.restore_cloud_view(owner, graph["recordId"], saved["id"])

    def test_cloud_graph_audit_task_is_persistent_encrypted_and_tenant_isolated(self) -> None:
        _, owner = self.register("task-owner@example.com")
        _, outsider = self.register("task-outsider@example.com")
        graph = self.graph()
        self.service.sync_graph(owner, {"protocolVersion": PROTOCOL_VERSION, "deviceId": "desktop", "baseCloudRevision": 0, "graph": graph}, "graph-sync")
        task = self.service.create_cloud_task(owner, "graph.audit", {"recordId": graph["recordId"]}, "task-create")
        deadline = time.monotonic() + 3
        while task["status"] not in {"succeeded", "failed", "cancelled"} and time.monotonic() < deadline:
            time.sleep(0.01)
            task = self.service.get_cloud_task(owner, task["id"])
        self.assertEqual(task["status"], "succeeded")
        result = self.service.cloud_task_result(owner, task["id"])
        self.assertEqual((result["recordId"], result["nodeCount"], result["edgeCount"]), (graph["recordId"], len(graph["nodes"]), len(graph["edges"])))
        db = sqlite3.connect(self.db_path)
        try:
            encrypted_result = db.execute("SELECT result_encrypted FROM cloud_tasks WHERE id=?", (task["id"],)).fetchone()[0]
        finally:
            db.close()
        self.assertNotIn("nodeCount", encrypted_result)
        metrics = self.service.cloud_metrics(owner)
        self.assertEqual((metrics["cloudGraphs"], metrics["tasksByStatus"]["succeeded"]), (1, 1))
        actions = {event["action"] for event in self.service.audit_events(owner)["events"]}
        self.assertTrue({"task.create", "task.succeed"}.issubset(actions))
        for operation in (
            lambda: self.service.get_cloud_task(outsider, task["id"]),
            lambda: self.service.cancel_cloud_task(outsider, task["id"], "cross-tenant-cancel"),
            lambda: self.service.cloud_task_result(outsider, task["id"]),
        ):
            with self.assertRaises(CloudApiError) as missing:
                operation()
            self.assertEqual(missing.exception.status, 404)

    def test_cloud_task_cancellation_queue_bound_and_restart_recovery(self) -> None:
        session, owner = self.register("lifecycle-owner@example.com")
        graph = self.graph()
        self.service.sync_graph(owner, {"protocolVersion": PROTOCOL_VERSION, "deviceId": "desktop", "baseCloudRevision": 0, "graph": graph}, "graph-sync")
        self.service._task_step_delay = 0.05
        self.service._max_pending_tasks = 1
        task = self.service.create_cloud_task(owner, "graph.audit", {"recordId": graph["recordId"]}, "task-create")
        with self.assertRaises(CloudApiError) as full:
            self.service.create_cloud_task(owner, "graph.audit", {"recordId": graph["recordId"]}, "task-overflow")
        self.assertEqual((full.exception.status, full.exception.code), (503, "task_queue_full"))
        cancelled = self.service.cancel_cloud_task(owner, task["id"], "task-cancel")
        deadline = time.monotonic() + 3
        while cancelled["status"] not in {"succeeded", "failed", "cancelled"} and time.monotonic() < deadline:
            time.sleep(0.01)
            cancelled = self.service.get_cloud_task(owner, task["id"])
        self.assertEqual(cancelled["status"], "cancelled")

        self.service.shutdown()
        recovered_id = str(uuid.uuid4())
        db = sqlite3.connect(self.db_path)
        try:
            db.execute(
                "INSERT INTO cloud_tasks VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (recovered_id, owner["tenant_id"], owner["id"], "graph.audit", graph["recordId"], "running", 1, json.dumps({"completed": 0, "total": 1, "unit": "task", "message": "Running"}), "Running", "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:01+00:00", None, None, None),
            )
            db.commit()
        finally:
            db.close()
        self.service = CloudApiService(self.db_path, bytes(range(32)), public_base_url="https://cloud.example")
        recovered_owner = self.service.authenticate(session["accessToken"])
        recovered = self.service.get_cloud_task(recovered_owner, recovered_id)
        self.assertEqual((recovered["status"], recovered["error"]["code"]), ("failed", "service_restarted"))

    def test_graph_collaboration_is_encrypted_idempotent_conflict_safe_and_live(self) -> None:
        _, owner = self.register("collaboration-owner@example.com")
        _, outsider = self.register("collaboration-outsider@example.com")
        graph = self.graph()
        self.service.sync_graph(owner, {"protocolVersion": PROTOCOL_VERSION, "deviceId": "desktop", "baseCloudRevision": 0, "graph": graph}, "graph-sync")
        target = graph["nodes"][0]["id"]
        mutation = {"protocolVersion": PROTOCOL_VERSION, "baseRevision": 0, "clientMutationId": str(uuid.uuid4()), "action": "upsert", "targetType": "node", "targetId": target, "body": "Review this evidence with the methods team."}
        self.assertFalse(self.service.collaboration_snapshot(owner, graph["recordId"])["syncEnabled"])
        with self.assertRaises(CloudApiError) as disabled:
            self.service.mutate_collaboration(owner, graph["recordId"], mutation, "annotation-disabled")
        self.assertEqual(disabled.exception.code, "annotation_sync_disabled")
        self.service.update_controls(owner, {**self.service.account(owner)["dataControls"], "syncAnnotations": True}, "enable-annotations")
        created = self.service.mutate_collaboration(owner, graph["recordId"], mutation, "annotation-create")
        self.assertEqual((created["revision"], created["event"]["action"]), (1, "annotation.upserted"))
        annotation_id = created["event"]["annotationId"]
        self.assertEqual(self.service.mutate_collaboration(owner, graph["recordId"], mutation, "annotation-replay"), created)
        snapshot = self.service.collaboration_snapshot(owner, graph["recordId"])
        self.assertEqual((snapshot["revision"], snapshot["annotations"][0]["body"]), (1, mutation["body"]))
        self.assertNotIn(mutation["body"].encode(), self.db_path.read_bytes())
        with self.assertRaises(CloudApiError) as conflict:
            self.service.mutate_collaboration(owner, graph["recordId"], {**mutation, "clientMutationId": str(uuid.uuid4()), "body": "stale"}, "annotation-conflict")
        self.assertEqual((conflict.exception.status, conflict.exception.code), (409, "collaboration_conflict"))

        received: list[dict] = []
        waiter = threading.Thread(target=lambda: received.append(self.service.collaboration_events(owner, graph["recordId"], 1, wait_seconds=2)))
        waiter.start()
        time.sleep(0.05)
        updated = self.service.mutate_collaboration(owner, graph["recordId"], {**mutation, "baseRevision": 1, "clientMutationId": str(uuid.uuid4()), "annotationId": annotation_id, "body": "Reviewed and accepted."}, "annotation-update")
        waiter.join(timeout=2)
        self.assertFalse(waiter.is_alive())
        self.assertEqual((updated["revision"], received[0]["events"][0]["revision"]), (2, 2))
        deleted = self.service.mutate_collaboration(owner, graph["recordId"], {"protocolVersion": PROTOCOL_VERSION, "baseRevision": 2, "clientMutationId": str(uuid.uuid4()), "action": "delete", "annotationId": annotation_id, "targetType": "node", "targetId": target}, "annotation-delete")
        self.assertEqual(deleted["event"]["action"], "annotation.deleted")
        self.assertEqual(self.service.collaboration_snapshot(owner, graph["recordId"])["annotations"], [])
        retained_events = self.service.collaboration_events(owner, graph["recordId"], 0, limit=10)["events"]
        self.assertNotIn(mutation["body"], json.dumps(retained_events))
        self.assertEqual(self.service.export_account(owner, "export-after-delete")["collaboration"][0]["annotations"], [])
        page = self.service.collaboration_events(owner, graph["recordId"], 0, limit=2)
        self.assertEqual(([event["revision"] for event in page["events"]], page["hasMore"]), ([1, 2], True))
        with self.service._connect() as db:
            db.execute("DELETE FROM collaboration_events WHERE tenant_id=? AND record_id=? AND revision<=2", (owner["tenant_id"], graph["recordId"]))
        self.assertTrue(self.service.collaboration_events(owner, graph["recordId"], 1)["resetRequired"])
        with self.assertRaises(CloudApiError) as isolated:
            self.service.collaboration_snapshot(outsider, graph["recordId"])
        self.assertEqual(isolated.exception.status, 404)


if __name__ == "__main__":
    unittest.main()
