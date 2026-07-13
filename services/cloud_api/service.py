from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import socket
import sqlite3
import struct
import smtplib
import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from email.message import EmailMessage

try:  # Production dependency; SQLite remains available for local tests and offline migration.
    import psycopg
    from psycopg.rows import dict_row
except ImportError:  # pragma: no cover - exercised only when PostgreSQL deployment is selected.
    psycopg = None
    dict_row = None

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from omnilit_qt.knowledge_graph_views import make_snapshot, reconcile_snapshot, view_summaries
from omnilit_qt.literature_library_shared import LibraryStateStore, project_library_state
from omnilit_qt.research_business_shared import DEFAULT_BUSINESS_SETTINGS, SETTINGS_FIELDS, project_research_statistics, project_research_workspace
from omnilit_qt.shared_protocol import PROTOCOL_VERSION, validate_cloud_graph_list, validate_cloud_graph_sync_request, validate_cloud_graph_sync_result, validate_cloud_service_metrics, validate_collaboration_event_page, validate_collaboration_mutation_request, validate_collaboration_mutation_result, validate_collaboration_snapshot, validate_diagnostic_receipt, validate_diagnostic_report_create_request, validate_graph_data, validate_graph_neighbor_page, validate_graph_view_list, validate_graph_view_mutation, validate_graph_view_restore, validate_graph_view_save_request, validate_graph_view_state, validate_library_state, validate_library_sync_request, validate_literature_page, validate_resource_permission_mutation, validate_task, validate_team_invite_accept, validate_team_invite_create
from omnilit_qt.version import APP_VERSION


DEFAULT_CONTROLS = {
    "uploadLocalPdfs": False,
    "syncAnnotations": False,
    "syncFullText": False,
    "useCloudAi": False,
    "retainCloudTaskData": False,
    "allowTeamAccess": False,
    "allowShareLinks": False,
    "shareDiagnostics": False,
}
LOGGER = logging.getLogger("omnilit.cloud_api")
ACTIVE_TASK_STATUSES = {"queued", "running", "stopping"}
FINAL_TASK_STATUSES = {"succeeded", "failed", "cancelled"}
CURRENT_SCHEMA_VERSION = 6
DIAGNOSTIC_FIELDS = {"protocolVersion", "occurredAt", "source", "code", "exceptionType", "fingerprint", "severity", "appVersion"}
WORKSPACE_RESOURCE_TYPES = {"literature_record", "library_state", "business_settings", "graph", "graph_view", "annotation"}
SYNC_CATEGORIES = {"literature", "collections", "graphs", "views", "settings", "annotations", "pdfs", "fullText", "extractions"}
PUBLIC_SUBMISSION_STATUSES = {"draft", "pending_review", "changes_requested", "approved", "rejected", "withdrawal_requested", "withdrawn", "takedown"}
PUBLIC_LICENSE_CODES = {"cc-by", "cc-by-sa", "cc0", "public-domain", "publisher-oa", "author-redistribution"}


class CloudApiError(RuntimeError):
    def __init__(self, status: int, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.retryable = retryable


class CloudSchemaVersionError(RuntimeError):
    """Raised when a database was created by a newer, incompatible service."""


class _CompatRow(dict):
    def __getitem__(self, key):
        if isinstance(key, int):
            return tuple(self.values())[key]
        return super().__getitem__(key)


class _PostgresCursor:
    def __init__(self, cursor) -> None:
        self._cursor = cursor

    def fetchone(self):
        row = self._cursor.fetchone()
        return _CompatRow(row) if row is not None else None

    def fetchall(self):
        return [_CompatRow(row) for row in self._cursor.fetchall()]


class _PostgresConnection:
    def __init__(self, connection) -> None:
        self._connection = connection

    @staticmethod
    def _sql(sql: str) -> str:
        statement = sql.replace("?", "%s")
        if statement.lstrip().upper().startswith("INSERT OR IGNORE"):
            statement = statement.replace("INSERT OR IGNORE", "INSERT", 1).rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"
        return statement

    def execute(self, sql: str, parameters: tuple[Any, ...] = ()) -> _PostgresCursor:
        return _PostgresCursor(self._connection.execute(self._sql(sql), parameters))

    def executescript(self, script: str) -> None:
        script = script.replace("cursor INTEGER PRIMARY KEY AUTOINCREMENT", "cursor BIGSERIAL PRIMARY KEY")
        script = script.replace("quota_bytes INTEGER NOT NULL", "quota_bytes BIGINT NOT NULL")
        for raw in script.split(";"):
            statement = raw.strip()
            if not statement or statement.upper() in {"BEGIN IMMEDIATE", "COMMIT"} or statement.upper().startswith("PRAGMA "):
                continue
            if statement.upper().startswith("INSERT OR IGNORE"):
                statement = statement.replace("INSERT OR IGNORE", "INSERT", 1) + " ON CONFLICT DO NOTHING"
            self._connection.execute(statement)

    def commit(self) -> None:
        self._connection.commit()

    def rollback(self) -> None:
        self._connection.rollback()

    def close(self) -> None:
        self._connection.close()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None = None) -> str:
    return (value or _now()).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _is_integrity_error(error: BaseException) -> bool:
    return isinstance(error, sqlite3.IntegrityError) or bool(psycopg is not None and isinstance(error, psycopg.IntegrityError))


def _secret_environment(name: str) -> str:
    direct, filename = os.environ.get(name, ""), os.environ.get(f"{name}_FILE", "")
    if direct and filename:
        raise RuntimeError(f"Set only one of {name} and {name}_FILE")
    if filename:
        return Path(filename).read_text(encoding="utf-8").strip()
    return direct.strip()


class CloudApiService:
    """Tenant-isolated cloud domain service backed by encrypted SQLite records."""

    def __init__(self, database_path: Path | str, encryption_key: bytes, *, public_base_url: str = "https://app.omnilit.invalid", task_workers: int = 2, max_pending_tasks: int = 32, task_timeout: float = 300.0, task_step_delay: float = 0.0, collaboration_event_retention: int = 10_000, diagnostic_retention_days: int = 30, diagnostic_tenant_limit: int = 500, diagnostic_daily_limit: int = 100) -> None:
        if len(encryption_key) != 32:
            raise ValueError("Cloud API encryption key must contain exactly 32 bytes")
        raw_database = str(database_path)
        self.database_url = raw_database if raw_database.startswith(("postgresql://", "postgres://")) else ""
        self.database_path = Path(database_path) if not self.database_url else Path("postgresql")
        if not self.database_url:
            self.database_path.parent.mkdir(parents=True, exist_ok=True)
        elif psycopg is None:
            raise RuntimeError("PostgreSQL deployment requires psycopg[binary]")
        default_object_root = self.database_path.parent / "objects" if not self.database_url else Path("/var/lib/omnilit")
        self.private_object_dir = Path(os.environ.get("OMNILIT_PRIVATE_OBJECT_DIR", str(default_object_root / "private")))
        self.public_object_dir = Path(os.environ.get("OMNILIT_PUBLIC_OBJECT_DIR", str(default_object_root / "public")))
        self.quarantine_object_dir = Path(os.environ.get("OMNILIT_QUARANTINE_OBJECT_DIR", str(default_object_root / "quarantine")))
        for directory in (self.private_object_dir, self.public_object_dir, self.quarantine_object_dir):
            directory.mkdir(parents=True, exist_ok=True)
        self.default_quota_bytes = max(0, int(os.environ.get("OMNILIT_DEFAULT_QUOTA_BYTES", str(5 * 1024**3))))
        self.public_max_file_bytes = max(1024, int(os.environ.get("OMNILIT_PUBLIC_MAX_FILE_BYTES", str(200 * 1024**2))))
        self.clamav_host = os.environ.get("OMNILIT_CLAMAV_HOST", "").strip()
        self.clamav_port = int(os.environ.get("OMNILIT_CLAMAV_PORT", "3310"))
        self.require_email_verification = os.environ.get("OMNILIT_REQUIRE_EMAIL_VERIFICATION", "0") == "1"
        self.turnstile_secret = _secret_environment("OMNILIT_TURNSTILE_SECRET")
        self.smtp_host = os.environ.get("OMNILIT_SMTP_HOST", "").strip()
        self.smtp_port = int(os.environ.get("OMNILIT_SMTP_PORT", "587"))
        self.smtp_user = os.environ.get("OMNILIT_SMTP_USER", "").strip()
        self.smtp_password = _secret_environment("OMNILIT_SMTP_PASSWORD")
        self.smtp_from = os.environ.get("OMNILIT_SMTP_FROM", self.smtp_user).strip()
        self._cipher = AESGCM(encryption_key)
        self.public_base_url = public_base_url.rstrip("/")
        self._lock = threading.RLock()
        self._started = time.monotonic()
        self._task_timeout = max(0.05, float(task_timeout))
        self._task_step_delay = max(0.0, float(task_step_delay))
        self._max_pending_tasks = max(1, int(max_pending_tasks))
        self._collaboration_event_retention = max(100, int(collaboration_event_retention))
        self._diagnostic_retention = timedelta(days=max(1, int(diagnostic_retention_days)))
        self._diagnostic_tenant_limit = max(10, int(diagnostic_tenant_limit))
        self._diagnostic_daily_limit = min(max(1, int(diagnostic_daily_limit)), self._diagnostic_tenant_limit)
        self._task_lock = threading.RLock()
        self._task_cancellations: dict[str, threading.Event] = {}
        self._task_futures: dict[str, Future[None]] = {}
        self._collaboration_condition = threading.Condition()
        self._closed = False
        self._initialize()
        self._recover_cloud_tasks()
        self._task_executor = ThreadPoolExecutor(max_workers=max(1, int(task_workers)), thread_name_prefix="omnilit-cloud-task")

    @contextmanager
    def _connect(self) -> Iterator[Any]:
        if self.database_url:
            raw_connection = psycopg.connect(self.database_url, row_factory=dict_row)
            connection: Any = _PostgresConnection(raw_connection)
        else:
            connection = sqlite3.connect(self.database_path, timeout=5)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA journal_mode=WAL")
        try:
            yield connection
        except BaseException:
            connection.rollback()
            raise
        else:
            connection.commit()
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connect() as db:
            if self.database_url:
                try:
                    version_row = db.execute("SELECT COALESCE(MAX(version),0) AS version FROM schema_migrations").fetchone()
                    schema_version = int(version_row["version"])
                except Exception:
                    db.rollback()
                    schema_version = 0
            else:
                schema_version = int(db.execute("PRAGMA user_version").fetchone()[0])
            if schema_version > CURRENT_SCHEMA_VERSION:
                raise CloudSchemaVersionError(
                    f"Cloud database schema {schema_version} is newer than supported schema {CURRENT_SCHEMA_VERSION}"
                )
            db.executescript(f"""
                BEGIN IMMEDIATE;
                CREATE TABLE IF NOT EXISTS schema_migrations(
                    version INTEGER PRIMARY KEY, description TEXT NOT NULL, applied_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS tenants(id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS users(
                    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                    email TEXT NOT NULL UNIQUE, display_name TEXT NOT NULL, password_hash TEXT NOT NULL,
                    roles_json TEXT NOT NULL, controls_json TEXT NOT NULL, created_at TEXT NOT NULL, deleted_at TEXT
                );
                CREATE TABLE IF NOT EXISTS workspaces(
                    id TEXT PRIMARY KEY, owner_user_id TEXT UNIQUE REFERENCES users(id) ON DELETE CASCADE,
                    kind TEXT NOT NULL CHECK(kind IN ('personal','public')), name TEXT NOT NULL,
                    quota_bytes INTEGER NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS workspace_sync_preferences(
                    workspace_id TEXT PRIMARY KEY REFERENCES workspaces(id) ON DELETE CASCADE,
                    enabled INTEGER NOT NULL, categories_json TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS workspace_resources(
                    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
                    resource_type TEXT NOT NULL, resource_id TEXT NOT NULL, revision INTEGER NOT NULL,
                    deleted INTEGER NOT NULL, encrypted_payload TEXT NOT NULL, payload_hash TEXT NOT NULL,
                    updated_at TEXT NOT NULL, updated_by TEXT NOT NULL,
                    PRIMARY KEY(workspace_id,resource_type,resource_id)
                );
                CREATE TABLE IF NOT EXISTS workspace_changes(
                    cursor INTEGER PRIMARY KEY AUTOINCREMENT,
                    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
                    resource_type TEXT NOT NULL, resource_id TEXT NOT NULL, operation TEXT NOT NULL,
                    resource_revision INTEGER NOT NULL, client_mutation_id TEXT NOT NULL,
                    encrypted_payload TEXT NOT NULL, payload_hash TEXT NOT NULL, occurred_at TEXT NOT NULL,
                    UNIQUE(workspace_id,client_mutation_id)
                );
                CREATE INDEX IF NOT EXISTS workspace_changes_cursor
                    ON workspace_changes(workspace_id,cursor);
                CREATE TABLE IF NOT EXISTS public_submissions(
                    id TEXT PRIMARY KEY, contributor_id TEXT NOT NULL REFERENCES users(id),
                    source_workspace_id TEXT NOT NULL REFERENCES workspaces(id), source_resource_id TEXT NOT NULL,
                    status TEXT NOT NULL, revision INTEGER NOT NULL, encrypted_snapshot TEXT NOT NULL,
                    content_hash TEXT NOT NULL, license_code TEXT NOT NULL, license_url TEXT NOT NULL,
                    rights_statement TEXT NOT NULL, public_display_name TEXT NOT NULL,
                    reviewer_id TEXT, review_note TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS public_submissions_status
                    ON public_submissions(status,updated_at);
                CREATE TABLE IF NOT EXISTS public_library_records(
                    id TEXT PRIMARY KEY, submission_id TEXT NOT NULL UNIQUE REFERENCES public_submissions(id),
                    version INTEGER NOT NULL, content_hash TEXT NOT NULL, doi_key TEXT NOT NULL,
                    encrypted_record TEXT NOT NULL, license_code TEXT NOT NULL, license_url TEXT NOT NULL,
                    rights_statement TEXT NOT NULL, contributor_name TEXT NOT NULL, approved_at TEXT NOT NULL, withdrawn_at TEXT
                );
                CREATE INDEX IF NOT EXISTS public_library_doi ON public_library_records(doi_key);
                CREATE TABLE IF NOT EXISTS public_takedown_requests(
                    id TEXT PRIMARY KEY, record_id TEXT NOT NULL, request_type TEXT NOT NULL,
                    status TEXT NOT NULL, encrypted_request TEXT NOT NULL, requester_hash TEXT NOT NULL,
                    reviewer_id TEXT, decision_note TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS public_takedown_status ON public_takedown_requests(status,created_at);
                CREATE TABLE IF NOT EXISTS system_admins(
                    user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS asset_uploads(
                    id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
                    owner_user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    scope TEXT NOT NULL, submission_id TEXT, filename TEXT NOT NULL, media_type TEXT NOT NULL,
                    expected_bytes INTEGER NOT NULL, expected_sha256 TEXT NOT NULL, received_bytes INTEGER NOT NULL,
                    temporary_path TEXT NOT NULL, created_at TEXT NOT NULL, expires_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS assets(
                    id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
                    owner_user_id TEXT NOT NULL, scope TEXT NOT NULL, submission_id TEXT,
                    filename TEXT NOT NULL, media_type TEXT NOT NULL, size_bytes INTEGER NOT NULL,
                    sha256 TEXT NOT NULL, encrypted_path TEXT NOT NULL, scan_status TEXT NOT NULL,
                    created_at TEXT NOT NULL, UNIQUE(workspace_id,scope,sha256)
                );
                CREATE INDEX IF NOT EXISTS assets_workspace_scope ON assets(workspace_id,scope,created_at);
                CREATE TABLE IF NOT EXISTS account_security(
                    user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                    status TEXT NOT NULL, email_verified_at TEXT, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS account_tokens(
                    token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    purpose TEXT NOT NULL, expires_at TEXT NOT NULL, used_at TEXT, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS persistent_rate_limits(
                    rate_key TEXT PRIMARY KEY, window_started_at TEXT NOT NULL, request_count INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions(
                    token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    expires_at TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS library_snapshots(
                    tenant_id TEXT PRIMARY KEY REFERENCES tenants(id) ON DELETE CASCADE, cloud_revision INTEGER NOT NULL,
                    encrypted_state TEXT NOT NULL, updated_at TEXT NOT NULL, updated_by TEXT NOT NULL, device_id TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS shares(
                    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                    owner_id TEXT NOT NULL, token_hash TEXT NOT NULL UNIQUE, resource_type TEXT NOT NULL,
                    resource_id TEXT NOT NULL, permission TEXT NOT NULL, created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL, revoked_at TEXT
                );
                CREATE TABLE IF NOT EXISTS audits(
                    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, actor_id TEXT NOT NULL, occurred_at TEXT NOT NULL,
                    action TEXT NOT NULL, resource_type TEXT NOT NULL, resource_id TEXT NOT NULL, request_id TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS audits_tenant_time ON audits(tenant_id, occurred_at DESC);
                CREATE TABLE IF NOT EXISTS team_invites(
                    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                    inviter_id TEXT NOT NULL, email TEXT NOT NULL, role TEXT NOT NULL, token_hash TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL, expires_at TEXT NOT NULL, accepted_at TEXT
                );
                CREATE TABLE IF NOT EXISTS resource_permissions(
                    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                    resource_type TEXT NOT NULL, resource_id TEXT NOT NULL, principal_type TEXT NOT NULL,
                    principal_id TEXT NOT NULL, permission TEXT NOT NULL, updated_at TEXT NOT NULL,
                    UNIQUE(tenant_id, resource_type, resource_id, principal_type, principal_id)
                );
                CREATE TABLE IF NOT EXISTS cloud_graphs(
                    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE, record_id TEXT NOT NULL,
                    cloud_revision INTEGER NOT NULL, encrypted_graph TEXT NOT NULL, updated_at TEXT NOT NULL,
                    updated_by TEXT NOT NULL, device_id TEXT NOT NULL, node_count INTEGER NOT NULL, edge_count INTEGER NOT NULL,
                    PRIMARY KEY(tenant_id, record_id)
                );
                CREATE TABLE IF NOT EXISTS cloud_graph_views(
                    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE, record_id TEXT NOT NULL,
                    view_id TEXT NOT NULL, encrypted_view TEXT NOT NULL, name TEXT NOT NULL, created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL, graph_fingerprint TEXT NOT NULL,
                    PRIMARY KEY(tenant_id, record_id, view_id)
                );
                CREATE TABLE IF NOT EXISTS cloud_tasks(
                    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                    actor_id TEXT NOT NULL, type TEXT NOT NULL, record_id TEXT NOT NULL, status TEXT NOT NULL,
                    cancellable INTEGER NOT NULL, progress_json TEXT NOT NULL, message TEXT NOT NULL,
                    created_at TEXT NOT NULL, started_at TEXT, finished_at TEXT, result_encrypted TEXT, error_json TEXT
                );
                CREATE INDEX IF NOT EXISTS cloud_tasks_tenant_created ON cloud_tasks(tenant_id, created_at DESC);
                CREATE TABLE IF NOT EXISTS collaboration_revisions(
                    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE, record_id TEXT NOT NULL,
                    revision INTEGER NOT NULL, PRIMARY KEY(tenant_id, record_id)
                );
                CREATE TABLE IF NOT EXISTS graph_annotations(
                    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE, record_id TEXT NOT NULL,
                    annotation_id TEXT NOT NULL, target_type TEXT NOT NULL, target_id TEXT NOT NULL,
                    encrypted_annotation TEXT NOT NULL, revision INTEGER NOT NULL, deleted INTEGER NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    PRIMARY KEY(tenant_id, record_id, annotation_id)
                );
                CREATE TABLE IF NOT EXISTS collaboration_events(
                    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE, record_id TEXT NOT NULL,
                    revision INTEGER NOT NULL, client_mutation_id TEXT NOT NULL, encrypted_event TEXT NOT NULL,
                    occurred_at TEXT NOT NULL, PRIMARY KEY(tenant_id, record_id, revision),
                    UNIQUE(tenant_id, record_id, client_mutation_id)
                );
                CREATE INDEX IF NOT EXISTS collaboration_events_record_revision ON collaboration_events(tenant_id, record_id, revision);
                CREATE TABLE IF NOT EXISTS diagnostic_reports(
                    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                    occurred_at TEXT NOT NULL, received_at TEXT NOT NULL, source TEXT NOT NULL, code TEXT NOT NULL,
                    exception_type TEXT NOT NULL, fingerprint TEXT NOT NULL, severity TEXT NOT NULL, app_version TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS diagnostic_reports_tenant_received ON diagnostic_reports(tenant_id, received_at DESC);
                INSERT OR IGNORE INTO schema_migrations(version, description, applied_at)
                    VALUES(1, 'Phase 2 cloud schema baseline', '{_iso()}');
                INSERT OR IGNORE INTO schema_migrations(version, description, applied_at)
                    VALUES(2, 'Privacy-safe opt-in diagnostics', '{_iso()}');
                INSERT OR IGNORE INTO schema_migrations(version, description, applied_at)
                    VALUES(3, 'Personal workspaces and moderated public library', '{_iso()}');
                INSERT OR IGNORE INTO schema_migrations(version, description, applied_at)
                    VALUES(4, 'Resumable encrypted workspace attachments', '{_iso()}');
                INSERT OR IGNORE INTO schema_migrations(version, description, applied_at)
                    VALUES(5, 'Email verification and persistent public rate limits', '{_iso()}');
                INSERT OR IGNORE INTO schema_migrations(version, description, applied_at)
                    VALUES(6, 'Public reports takedown and administrator quota controls', '{_iso()}');
                PRAGMA user_version={CURRENT_SCHEMA_VERSION};
                COMMIT;
            """)
            db.execute(
                "INSERT OR IGNORE INTO workspaces(id,owner_user_id,kind,name,quota_bytes,created_at) VALUES(?,?,?,?,?,?)",
                ("public-library", None, "public", "OmniLit Public Library", 0, _iso()),
            )
            users = db.execute("SELECT id,display_name,created_at FROM users").fetchall()
            for user in users:
                existing = db.execute("SELECT id FROM workspaces WHERE owner_user_id=?", (user["id"],)).fetchone()
                if existing is None:
                    db.execute(
                        "INSERT INTO workspaces(id,owner_user_id,kind,name,quota_bytes,created_at) VALUES(?,?,?,?,?,?)",
                        (uuid.uuid4().hex, user["id"], "personal", f"{user['display_name']} Workspace", self.default_quota_bytes, user["created_at"]),
                    )
                db.execute("INSERT OR IGNORE INTO account_security(user_id,status,email_verified_at,updated_at) VALUES(?,?,?,?)", (user["id"], "active", user["created_at"], _iso()))
        self._schema_version = CURRENT_SCHEMA_VERSION

    def operational_health(self) -> dict[str, Any]:
        """Return a non-sensitive readiness result suitable for an orchestrator probe."""
        checks = {"database": "ready", "schema": "ready", "taskService": "ready"}
        try:
            with self._connect() as db:
                db.execute("SELECT 1").fetchone()
                schema_version = int(db.execute("SELECT COALESCE(MAX(version),0) AS version FROM schema_migrations").fetchone()["version"]) if self.database_url else int(db.execute("PRAGMA user_version").fetchone()[0])
        except Exception:
            schema_version = self._schema_version
            checks["database"] = "not_ready"
        if schema_version != CURRENT_SCHEMA_VERSION:
            checks["schema"] = "not_ready"
        with self._task_lock:
            if self._closed:
                checks["taskService"] = "not_ready"
        ready = all(value == "ready" for value in checks.values())
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "appVersion": APP_VERSION,
            "status": "ready" if ready else "not_ready",
            "service": "omnilit-cloud-api",
            "schemaVersion": schema_version,
            "supportedSchemaVersion": CURRENT_SCHEMA_VERSION,
            "checks": checks,
        }

    def _recover_cloud_tasks(self) -> None:
        finished = _iso()
        error = _json({"protocolVersion": PROTOCOL_VERSION, "code": "service_restarted", "message": "Cloud API restarted before the task finished", "retryable": True})
        with self._connect() as db:
            db.execute("UPDATE cloud_tasks SET status='failed',cancellable=0,message='Service restarted',finished_at=?,error_json=? WHERE status IN ('queued','running','stopping')", (finished, error))

    @staticmethod
    def _task_payload(row: sqlite3.Row) -> dict[str, Any]:
        task: dict[str, Any] = {"protocolVersion": PROTOCOL_VERSION, "id": row["id"], "type": row["type"], "status": row["status"], "cancellable": bool(row["cancellable"]), "progress": json.loads(row["progress_json"]), "message": row["message"], "createdAt": row["created_at"]}
        if row["started_at"]:
            task["startedAt"] = row["started_at"]
        if row["finished_at"]:
            task["finishedAt"] = row["finished_at"]
        if row["result_encrypted"]:
            task["resultRef"] = f"/v1/tasks/{row['id']}/result"
        if row["error_json"]:
            task["error"] = json.loads(row["error_json"])
        validate_task(task)
        return task

    def create_cloud_task(self, actor: sqlite3.Row, task_type: str, task_input: dict[str, Any], request_id: str) -> dict[str, Any]:
        if task_type != "graph.audit" or not isinstance(task_input, dict):
            raise CloudApiError(400, "unsupported_task_type", "Only the controlled graph.audit cloud task is supported")
        record_id = str(task_input.get("recordId") or "")
        if not record_id or len(record_id) > 256 or set(task_input) != {"recordId"}:
            raise CloudApiError(400, "invalid_task_input", "graph.audit accepts only a bounded recordId")
        self._require_resource(actor, "graph", record_id, "viewer")
        with self._task_lock:
            if self._closed:
                raise CloudApiError(503, "service_stopping", "Cloud task service is stopping", retryable=True)
            with self._connect() as db:
                global_active = db.execute("SELECT COUNT(*) FROM cloud_tasks WHERE status IN ('queued','running','stopping')").fetchone()[0]
                tenant_active = db.execute("SELECT COUNT(*) FROM cloud_tasks WHERE tenant_id=? AND status IN ('queued','running','stopping')", (actor["tenant_id"],)).fetchone()[0]
                if global_active >= self._max_pending_tasks or tenant_active >= min(16, self._max_pending_tasks):
                    raise CloudApiError(503, "task_queue_full", "Cloud task queue is full", retryable=True)
                task_id, created_at = str(uuid.uuid4()), _iso()
                progress = {"completed": 0, "total": 1, "unit": "task", "message": "Queued"}
                db.execute("INSERT INTO cloud_tasks VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (task_id, actor["tenant_id"], actor["id"], task_type, record_id, "queued", 1, _json(progress), "Queued", created_at, None, None, None, None))
                self._audit(db, actor, "task.create", "cloud_task", task_id, request_id)
                row = db.execute("SELECT * FROM cloud_tasks WHERE id=?", (task_id,)).fetchone()
            cancellation = threading.Event()
            self._task_cancellations[task_id] = cancellation
            future = self._task_executor.submit(self._run_cloud_graph_audit, task_id, actor["tenant_id"], actor["id"], record_id, cancellation)
            self._task_futures[task_id] = future
            future.add_done_callback(lambda completed, key=task_id: self._forget_cloud_future(key, completed))
            return self._task_payload(row)

    def _forget_cloud_future(self, task_id: str, future: Future[None]) -> None:
        with self._task_lock:
            if self._task_futures.get(task_id) is future:
                self._task_futures.pop(task_id, None)

    def _set_cloud_task_progress(self, task_id: str, completed: int, total: int, message: str) -> None:
        progress = {"completed": max(0, min(completed, total)), "total": max(1, total), "unit": "elements", "message": message[:512]}
        with self._connect() as db:
            db.execute("UPDATE cloud_tasks SET progress_json=?,message=? WHERE id=? AND status='running'", (_json(progress), message[:512], task_id))

    def _run_cloud_graph_audit(self, task_id: str, tenant_id: str, actor_id: str, record_id: str, cancellation: threading.Event) -> None:
        started_at, deadline = _iso(), time.monotonic() + self._task_timeout
        try:
            with self._connect() as db:
                row = db.execute("SELECT status FROM cloud_tasks WHERE id=? AND tenant_id=?", (task_id, tenant_id)).fetchone()
                if row is None or row["status"] == "cancelled":
                    return
                if row["status"] == "stopping" or cancellation.is_set():
                    raise InterruptedError("cancelled")
                db.execute("UPDATE cloud_tasks SET status='running',message='Auditing cloud graph',started_at=?,progress_json=? WHERE id=?", (started_at, _json({"completed": 0, "total": 1, "unit": "elements", "message": "Loading encrypted graph"}), task_id))
                graph_row = db.execute("SELECT encrypted_graph FROM cloud_graphs WHERE tenant_id=? AND record_id=?", (tenant_id, record_id)).fetchone()
            if graph_row is None:
                raise CloudApiError(404, "cloud_graph_not_found", "Cloud graph not found")
            graph = self._decrypt(graph_row["encrypted_graph"])
            nodes, edges = list(graph.get("nodes") or []), list(graph.get("edges") or [])
            total, completed = max(1, len(nodes) + len(edges)), 0
            node_types: dict[str, int] = {}
            relation_types: dict[str, int] = {}
            for collection, counts, key in ((nodes, node_types, "type"), (edges, relation_types, "type")):
                for item in collection:
                    if cancellation.is_set():
                        raise InterruptedError("cancelled")
                    if time.monotonic() >= deadline:
                        raise TimeoutError("cloud task timed out")
                    value = str(item.get(key) or "unknown")
                    counts[value] = counts.get(value, 0) + 1
                    completed += 1
                    if completed == total or completed % 25 == 0:
                        self._set_cloud_task_progress(task_id, completed, total, f"Audited {completed} / {total} elements")
                    if self._task_step_delay:
                        time.sleep(self._task_step_delay)
            result = {"protocolVersion": PROTOCOL_VERSION, "recordId": record_id, "nodeCount": len(nodes), "edgeCount": len(edges), "nodeTypes": node_types, "relationTypes": relation_types}
            finished_at = _iso()
            with self._connect() as db:
                db.execute("UPDATE cloud_tasks SET status='succeeded',cancellable=0,message='Succeeded',finished_at=?,progress_json=?,result_encrypted=? WHERE id=?", (finished_at, _json({"completed": total, "total": total, "unit": "elements", "message": "Succeeded"}), self._encrypt(result), task_id))
                actor = db.execute("SELECT * FROM users WHERE id=? AND tenant_id=?", (actor_id, tenant_id)).fetchone()
                if actor is not None:
                    self._audit(db, actor, "task.succeed", "cloud_task", task_id, task_id)
        except InterruptedError:
            with self._connect() as db:
                db.execute("UPDATE cloud_tasks SET status='cancelled',cancellable=0,message='Cancelled',finished_at=? WHERE id=?", (_iso(), task_id))
        except TimeoutError:
            error = {"protocolVersion": PROTOCOL_VERSION, "code": "task_timeout", "message": "Cloud task timed out", "retryable": True}
            with self._connect() as db:
                db.execute("UPDATE cloud_tasks SET status='failed',cancellable=0,message='Task timed out',finished_at=?,error_json=? WHERE id=?", (_iso(), _json(error), task_id))
        except Exception:
            LOGGER.exception("cloud_task_failed task_id=%s type=graph.audit", task_id)
            error = {"protocolVersion": PROTOCOL_VERSION, "code": "task_failed", "message": "Cloud task failed", "retryable": False}
            with self._connect() as db:
                db.execute("UPDATE cloud_tasks SET status='failed',cancellable=0,message='Task failed',finished_at=?,error_json=? WHERE id=?", (_iso(), _json(error), task_id))
        finally:
            with self._task_lock:
                self._task_cancellations.pop(task_id, None)

    def get_cloud_task(self, actor: sqlite3.Row, task_id: str) -> dict[str, Any]:
        try:
            task_id = str(uuid.UUID(task_id))
        except ValueError as exc:
            raise CloudApiError(400, "invalid_task_id", "Task ID is invalid") from exc
        with self._connect() as db:
            row = db.execute("SELECT * FROM cloud_tasks WHERE id=? AND tenant_id=?", (task_id, actor["tenant_id"])).fetchone()
        if row is None:
            raise CloudApiError(404, "task_not_found", "Cloud task not found")
        return self._task_payload(row)

    def cancel_cloud_task(self, actor: sqlite3.Row, task_id: str, request_id: str) -> dict[str, Any]:
        task = self.get_cloud_task(actor, task_id)
        if task["status"] in FINAL_TASK_STATUSES:
            return task
        with self._task_lock:
            cancellation = self._task_cancellations.get(task_id)
            future = self._task_futures.get(task_id)
            cancelled = task["status"] == "queued" and future is not None and future.cancel()
            next_status, message = ("cancelled", "Cancelled") if cancelled else ("stopping", "Stopping")
            with self._connect() as db:
                db.execute("UPDATE cloud_tasks SET status=?,cancellable=0,message=?,finished_at=? WHERE id=? AND tenant_id=? AND status NOT IN ('succeeded','failed','cancelled')", (next_status, message, _iso() if cancelled else None, task_id, actor["tenant_id"]))
                self._audit(db, actor, "task.cancel", "cloud_task", task_id, request_id)
                row = db.execute("SELECT * FROM cloud_tasks WHERE id=?", (task_id,)).fetchone()
            if cancelled:
                self._task_cancellations.pop(task_id, None)
            elif cancellation:
                cancellation.set()
        return self._task_payload(row)

    def cloud_task_result(self, actor: sqlite3.Row, task_id: str) -> dict[str, Any]:
        task = self.get_cloud_task(actor, task_id)
        if task["status"] != "succeeded":
            raise CloudApiError(409, "task_result_unavailable", "Cloud task result is not available")
        with self._connect() as db:
            row = db.execute("SELECT result_encrypted FROM cloud_tasks WHERE id=? AND tenant_id=?", (task_id, actor["tenant_id"])).fetchone()
        if row is None or not row["result_encrypted"]:
            raise CloudApiError(410, "task_result_missing", "Cloud task result is missing")
        return self._decrypt(row["result_encrypted"])

    def cloud_metrics(self, actor: sqlite3.Row) -> dict[str, Any]:
        self._require_team_admin(actor)
        with self._connect() as db:
            users = db.execute("SELECT COUNT(*) FROM users WHERE tenant_id=? AND deleted_at IS NULL", (actor["tenant_id"],)).fetchone()[0]
            graphs = db.execute("SELECT COUNT(*) FROM cloud_graphs WHERE tenant_id=?", (actor["tenant_id"],)).fetchone()[0]
            collaboration_events = db.execute("SELECT COUNT(*) FROM collaboration_events WHERE tenant_id=?", (actor["tenant_id"],)).fetchone()[0]
            audits = db.execute("SELECT COUNT(*) FROM audits WHERE tenant_id=?", (actor["tenant_id"],)).fetchone()[0]
            statuses = db.execute("SELECT status,COUNT(*) AS count FROM cloud_tasks WHERE tenant_id=? GROUP BY status", (actor["tenant_id"],)).fetchall()
        result = {"protocolVersion": PROTOCOL_VERSION, "status": "ready", "uptimeSeconds": max(0.0, time.monotonic() - self._started), "tenantUsers": users, "cloudGraphs": graphs, "collaborationEvents": collaboration_events, "tasksByStatus": {row["status"]: row["count"] for row in statuses}, "auditEvents": audits}
        validate_cloud_service_metrics(result)
        return result

    def shutdown(self, wait: bool = True) -> None:
        with self._task_lock:
            if self._closed:
                return
            self._closed = True
            finished_at = _iso()
            with self._connect() as db:
                db.execute("UPDATE cloud_tasks SET status='cancelled',cancellable=0,message='Service stopped',finished_at=? WHERE status='queued'", (finished_at,))
                db.execute("UPDATE cloud_tasks SET status='stopping',cancellable=0,message='Service stopping' WHERE status='running'")
            for cancellation in self._task_cancellations.values():
                cancellation.set()
        with self._collaboration_condition:
            self._collaboration_condition.notify_all()
        self._task_executor.shutdown(wait=wait, cancel_futures=True)

    @staticmethod
    def _password_hash(password: str, salt: bytes | None = None) -> str:
        salt = salt or secrets.token_bytes(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 600_000)
        return f"pbkdf2_sha256$600000${base64.urlsafe_b64encode(salt).decode()}${base64.urlsafe_b64encode(digest).decode()}"

    @classmethod
    def _password_matches(cls, password: str, encoded: str) -> bool:
        try:
            _, iterations, salt, digest = encoded.split("$", 3)
            candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), base64.urlsafe_b64decode(salt), int(iterations))
            return hmac.compare_digest(candidate, base64.urlsafe_b64decode(digest))
        except (ValueError, TypeError):
            return False

    def _encrypt(self, value: dict[str, Any]) -> str:
        nonce = secrets.token_bytes(12)
        ciphertext = self._cipher.encrypt(nonce, _json(value).encode("utf-8"), b"omnilit-cloud-v1")
        return base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")

    def _decrypt(self, value: str) -> dict[str, Any]:
        raw = base64.urlsafe_b64decode(value)
        return json.loads(self._cipher.decrypt(raw[:12], raw[12:], b"omnilit-cloud-v1"))

    def _workspace_id(self, actor: sqlite3.Row) -> str:
        with self._connect() as db:
            row = db.execute("SELECT id FROM workspaces WHERE owner_user_id=? AND kind='personal'", (actor["id"],)).fetchone()
        if row is None:
            raise CloudApiError(500, "workspace_missing", "The account personal workspace is unavailable")
        return str(row["id"])

    def _account(self, row: sqlite3.Row) -> dict[str, Any]:
        controls = {**DEFAULT_CONTROLS, **json.loads(row["controls_json"])}
        with self._connect() as db:
            security = db.execute("SELECT status FROM account_security WHERE user_id=?", (row["id"],)).fetchone()
        return {
            "protocolVersion": PROTOCOL_VERSION, "id": row["id"], "tenantId": row["tenant_id"],
            "workspaceId": self._workspace_id(row), "accountStatus": security["status"] if security else "active",
            "email": row["email"], "displayName": row["display_name"],
            "roles": json.loads(row["roles_json"]), "dataControls": controls,
            "createdAt": row["created_at"],
        }

    def _audit(self, db: sqlite3.Connection, actor: sqlite3.Row, action: str, resource_type: str, resource_id: str, request_id: str) -> None:
        db.execute("INSERT INTO audits VALUES(?,?,?,?,?,?,?,?)", (uuid.uuid4().hex, actor["tenant_id"], actor["id"], _iso(), action, resource_type, resource_id, request_id))

    @staticmethod
    def _role(actor: sqlite3.Row) -> str:
        roles = json.loads(actor["roles_json"])
        return str(roles[0]) if roles else "member"

    def _require_team_admin(self, actor: sqlite3.Row, *, owner_only: bool = False) -> None:
        role = self._role(actor)
        allowed = role == "owner" if owner_only else role in {"owner", "admin"}
        if not allowed:
            raise CloudApiError(403, "permission_denied", "Team administration permission is required")

    def _require_resource(self, actor: sqlite3.Row, resource_type: str, resource_id: str, required: str) -> None:
        if self._role(actor) == "owner":
            return
        rank = {"viewer": 1, "editor": 2}
        with self._connect() as db:
            owner = db.execute("SELECT controls_json FROM users WHERE tenant_id=? AND roles_json LIKE '%owner%' AND deleted_at IS NULL LIMIT 1", (actor["tenant_id"],)).fetchone()
            if owner is None or not json.loads(owner["controls_json"]).get("allowTeamAccess"):
                raise CloudApiError(403, "team_access_disabled", "The tenant owner has not enabled team access")
            rows = db.execute("SELECT permission FROM resource_permissions WHERE tenant_id=? AND resource_type=? AND resource_id=? AND ((principal_type='user' AND principal_id=?) OR (principal_type='team' AND principal_id=?))", (actor["tenant_id"], resource_type, resource_id, actor["id"], actor["tenant_id"])).fetchall()
        granted = max((rank.get(str(row["permission"]), 0) for row in rows), default=0)
        if granted < rank[required]:
            raise CloudApiError(403, "permission_denied", f"{required.title()} permission is required for this resource")

    def _verify_turnstile(self, token: str, remote_ip: str) -> None:
        if not self.turnstile_secret:
            if self.require_email_verification:
                raise CloudApiError(503, "turnstile_unconfigured", "Public registration verification is unavailable", retryable=True)
            return
        if not token:
            raise CloudApiError(400, "turnstile_required", "Turnstile verification is required")
        payload = urlencode({"secret": self.turnstile_secret, "response": token, "remoteip": remote_ip}).encode("ascii")
        try:
            with urlopen(Request("https://challenges.cloudflare.com/turnstile/v0/siteverify", data=payload, method="POST"), timeout=10) as response:
                result = json.loads(response.read())
        except Exception as exc:
            raise CloudApiError(503, "turnstile_unavailable", "Turnstile verification is unavailable", retryable=True) from exc
        if not result.get("success"):
            raise CloudApiError(400, "turnstile_failed", "Turnstile verification failed")

    def _send_account_email(self, recipient: str, subject: str, body: str) -> None:
        if not self.smtp_host or not self.smtp_from:
            raise CloudApiError(503, "smtp_unconfigured", "Account email delivery is unavailable", retryable=True)
        message = EmailMessage()
        message["From"], message["To"], message["Subject"] = self.smtp_from, recipient, subject
        message.set_content(body)
        try:
            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=15) as client:
                client.starttls()
                if self.smtp_user:
                    client.login(self.smtp_user, self.smtp_password)
                client.send_message(message)
        except (OSError, smtplib.SMTPException) as exc:
            raise CloudApiError(503, "smtp_unavailable", "Account email delivery failed", retryable=True) from exc

    def persistent_rate_allowed(self, key: str, limit: int, window_seconds: int) -> bool:
        now = _now()
        with self._lock, self._connect() as db:
            row = db.execute("SELECT * FROM persistent_rate_limits WHERE rate_key=?", (key[:200],)).fetchone()
            if row is None or datetime.fromisoformat(row["window_started_at"]) + timedelta(seconds=window_seconds) <= now:
                db.execute("INSERT INTO persistent_rate_limits VALUES(?,?,1) ON CONFLICT(rate_key) DO UPDATE SET window_started_at=excluded.window_started_at,request_count=1", (key[:200], _iso(now)))
                return True
            if int(row["request_count"]) >= max(1, limit):
                return False
            db.execute("UPDATE persistent_rate_limits SET request_count=request_count+1 WHERE rate_key=?", (key[:200],))
            return True

    def register(self, email: str, password: str, display_name: str, tenant_name: str, request_id: str, *, turnstile_token: str = "", remote_ip: str = "") -> dict[str, Any]:
        email = email.strip().casefold()
        if "@" not in email or len(email) > 254 or len(password) < 12 or len(display_name.strip()) < 1:
            raise CloudApiError(400, "invalid_registration", "A valid email, display name, and password of at least 12 characters are required")
        self._verify_turnstile(turnstile_token, remote_ip)
        tenant_id, user_id, created = uuid.uuid4().hex, uuid.uuid4().hex, _iso()
        verification_token = secrets.token_urlsafe(32) if self.require_email_verification else ""
        try:
            with self._lock, self._connect() as db:
                db.execute("INSERT INTO tenants VALUES(?,?,?)", (tenant_id, tenant_name.strip()[:120] or display_name.strip()[:120], created))
                db.execute("INSERT INTO users(id,tenant_id,email,display_name,password_hash,roles_json,controls_json,created_at,deleted_at) VALUES(?,?,?,?,?,?,?,?,NULL)", (user_id, tenant_id, email, display_name.strip()[:120], self._password_hash(password), _json(["owner"]), _json(DEFAULT_CONTROLS), created))
                db.execute("INSERT INTO workspaces(id,owner_user_id,kind,name,quota_bytes,created_at) VALUES(?,?,?,?,?,?)", (uuid.uuid4().hex, user_id, "personal", f"{display_name.strip()[:120]} Workspace", self.default_quota_bytes, created))
                db.execute("INSERT INTO account_security VALUES(?,?,?,?)", (user_id, "pending_verification" if self.require_email_verification else "active", None if self.require_email_verification else created, created))
                if verification_token:
                    db.execute("INSERT INTO account_tokens VALUES(?,?,?,?,?,?)", (hashlib.sha256(verification_token.encode()).hexdigest(), user_id, "verify_email", _iso(_now() + timedelta(hours=24)), None, created))
                actor = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
                self._audit(db, actor, "account.register", "tenant", tenant_id, request_id)
        except Exception as exc:
            if _is_integrity_error(exc):
                raise CloudApiError(409, "email_exists", "An account with this email already exists") from exc
            raise
        if verification_token:
            verification_url = f"{self.public_base_url}/#/verify-email/{verification_token}"
            self._send_account_email(email, "Verify your OmniLit account", f"Verify your OmniLit account within 24 hours:\n\n{verification_url}\n")
            return {"protocolVersion": PROTOCOL_VERSION, "verificationRequired": True, "email": email}
        return self.login(email, password, request_id)

    def login(self, email: str, password: str, request_id: str) -> dict[str, Any]:
        with self._lock, self._connect() as db:
            row = db.execute("SELECT * FROM users WHERE email=? AND deleted_at IS NULL", (email.strip().casefold(),)).fetchone()
            if row is None or not self._password_matches(password, row["password_hash"]):
                raise CloudApiError(401, "invalid_credentials", "Email or password is incorrect")
            security = db.execute("SELECT status FROM account_security WHERE user_id=?", (row["id"],)).fetchone()
            if security is not None and security["status"] != "active":
                raise CloudApiError(403, "account_not_active", "Verify the account email before signing in")
            token = secrets.token_urlsafe(32)
            expires = _now() + timedelta(hours=8)
            db.execute("INSERT INTO sessions VALUES(?,?,?,?)", (hashlib.sha256(token.encode()).hexdigest(), row["id"], _iso(expires), _iso()))
            self._audit(db, row, "account.login", "session", "self", request_id)
            return {"protocolVersion": PROTOCOL_VERSION, "accessToken": token, "expiresAt": _iso(expires), "user": self._account(row)}

    def verify_email(self, token: str) -> dict[str, Any]:
        token_hash, now = hashlib.sha256(token.encode()).hexdigest(), _iso()
        with self._lock, self._connect() as db:
            row = db.execute("SELECT * FROM account_tokens WHERE token_hash=? AND purpose='verify_email' AND used_at IS NULL AND expires_at>?", (token_hash, now)).fetchone()
            if row is None:
                raise CloudApiError(404, "verification_token_invalid", "Email verification link is invalid or expired")
            db.execute("UPDATE account_tokens SET used_at=? WHERE token_hash=?", (now, token_hash))
            db.execute("UPDATE account_security SET status='active',email_verified_at=?,updated_at=? WHERE user_id=?", (now, now, row["user_id"]))
        return {"protocolVersion": PROTOCOL_VERSION, "verified": True}

    def resend_verification(self, email: str) -> dict[str, Any]:
        """Issue a fresh verification link without revealing whether an account exists."""
        normalized = email.strip().casefold()
        token = secrets.token_urlsafe(32)
        with self._lock, self._connect() as db:
            row = db.execute(
                "SELECT u.id,u.email FROM users u JOIN account_security s ON s.user_id=u.id "
                "WHERE u.email=? AND u.deleted_at IS NULL AND s.status='pending_verification'",
                (normalized,),
            ).fetchone()
            if row is not None:
                now = _iso()
                db.execute("UPDATE account_tokens SET used_at=? WHERE user_id=? AND purpose='verify_email' AND used_at IS NULL", (now, row["id"]))
                db.execute("INSERT INTO account_tokens VALUES(?,?,?,?,?,?)", (hashlib.sha256(token.encode()).hexdigest(), row["id"], "verify_email", _iso(_now() + timedelta(hours=24)), None, now))
        if row is not None:
            verification_url = f"{self.public_base_url}/#/verify-email/{token}"
            self._send_account_email(str(row["email"]), "Verify your OmniLit account", f"Verify your OmniLit account within 24 hours:\n\n{verification_url}\n")
        return {"protocolVersion": PROTOCOL_VERSION, "accepted": True}

    def request_password_reset(self, email: str) -> dict[str, Any]:
        """Create a one-time reset token while keeping the response enumeration-safe."""
        normalized = email.strip().casefold()
        token = secrets.token_urlsafe(32)
        with self._lock, self._connect() as db:
            row = db.execute("SELECT id,email FROM users WHERE email=? AND deleted_at IS NULL", (normalized,)).fetchone()
            if row is not None:
                now = _iso()
                db.execute("UPDATE account_tokens SET used_at=? WHERE user_id=? AND purpose='reset_password' AND used_at IS NULL", (now, row["id"]))
                db.execute("INSERT INTO account_tokens VALUES(?,?,?,?,?,?)", (hashlib.sha256(token.encode()).hexdigest(), row["id"], "reset_password", _iso(_now() + timedelta(hours=1)), None, now))
        if row is not None:
            reset_url = f"{self.public_base_url}/#/reset-password/{token}"
            self._send_account_email(str(row["email"]), "Reset your OmniLit password", f"Reset your OmniLit password within one hour:\n\n{reset_url}\n")
        return {"protocolVersion": PROTOCOL_VERSION, "accepted": True}

    def reset_password(self, token: str, new_password: str) -> dict[str, Any]:
        if len(new_password) < 12:
            raise CloudApiError(400, "weak_password", "Password must contain at least 12 characters")
        token_hash, now = hashlib.sha256(token.encode()).hexdigest(), _iso()
        with self._lock, self._connect() as db:
            row = db.execute("SELECT * FROM account_tokens WHERE token_hash=? AND purpose='reset_password' AND used_at IS NULL AND expires_at>?", (token_hash, now)).fetchone()
            if row is None:
                raise CloudApiError(404, "reset_token_invalid", "Password reset link is invalid or expired")
            db.execute("UPDATE users SET password_hash=? WHERE id=?", (self._password_hash(new_password), row["user_id"]))
            db.execute("UPDATE account_tokens SET used_at=? WHERE token_hash=?", (now, token_hash))
            db.execute("DELETE FROM sessions WHERE user_id=?", (row["user_id"],))
        return {"protocolVersion": PROTOCOL_VERSION, "reset": True}

    def change_password(self, actor: sqlite3.Row, current_password: str, new_password: str, request_id: str) -> dict[str, Any]:
        if len(new_password) < 12:
            raise CloudApiError(400, "weak_password", "Password must contain at least 12 characters")
        if not self._password_matches(current_password, actor["password_hash"]):
            raise CloudApiError(401, "invalid_credentials", "Current password is incorrect")
        with self._lock, self._connect() as db:
            db.execute("UPDATE users SET password_hash=? WHERE id=?", (self._password_hash(new_password), actor["id"]))
            db.execute("DELETE FROM sessions WHERE user_id=?", (actor["id"],))
            self._audit(db, actor, "account.password.change", "user", actor["id"], request_id)
        return {"protocolVersion": PROTOCOL_VERSION, "changed": True}

    def list_sessions(self, actor: sqlite3.Row) -> dict[str, Any]:
        with self._connect() as db:
            rows = db.execute("SELECT token_hash,created_at,expires_at FROM sessions WHERE user_id=? AND expires_at>? ORDER BY created_at DESC", (actor["id"], _iso())).fetchall()
        return {"protocolVersion": PROTOCOL_VERSION, "devices": [{"id": row["token_hash"], "createdAt": row["created_at"], "expiresAt": row["expires_at"]} for row in rows]}

    def revoke_session(self, actor: sqlite3.Row, session_id: str, request_id: str) -> None:
        with self._lock, self._connect() as db:
            db.execute("DELETE FROM sessions WHERE token_hash=? AND user_id=?", (session_id, actor["id"]))
            self._audit(db, actor, "account.session.revoke", "session", session_id[:16], request_id)

    def logout(self, actor: sqlite3.Row, token: str, request_id: str) -> None:
        self.revoke_session(actor, hashlib.sha256(token.encode()).hexdigest(), request_id)

    def authenticate(self, token: str) -> sqlite3.Row:
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        with self._connect() as db:
            row = db.execute("SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires_at>? AND u.deleted_at IS NULL", (token_hash, _iso())).fetchone()
        if row is None:
            raise CloudApiError(401, "unauthorized", "A valid Cloud API session is required")
        return row

    def account(self, actor: sqlite3.Row) -> dict[str, Any]:
        return self._account(actor)

    def update_controls(self, actor: sqlite3.Row, controls: dict[str, Any], request_id: str) -> dict[str, Any]:
        if set(controls) != set(DEFAULT_CONTROLS) or any(not isinstance(value, bool) for value in controls.values()):
            raise CloudApiError(400, "invalid_data_controls", "All cloud data controls must be explicit booleans")
        with self._lock, self._connect() as db:
            db.execute("UPDATE users SET controls_json=? WHERE id=? AND tenant_id=?", (_json(controls), actor["id"], actor["tenant_id"]))
            self._audit(db, actor, "account.controls.update", "user", actor["id"], request_id)
            row = db.execute("SELECT * FROM users WHERE id=?", (actor["id"],)).fetchone()
        return self._account(row)

    def workspace_summary(self, actor: sqlite3.Row) -> dict[str, Any]:
        workspace_id = self._workspace_id(actor)
        with self._connect() as db:
            workspace = db.execute("SELECT * FROM workspaces WHERE id=?", (workspace_id,)).fetchone()
            used = db.execute("SELECT COUNT(*) FROM workspace_resources WHERE workspace_id=? AND deleted=0", (workspace_id,)).fetchone()[0]
            asset_bytes = db.execute("SELECT COALESCE(SUM(size_bytes),0) FROM assets WHERE workspace_id=?", (workspace_id,)).fetchone()[0]
        return {"protocolVersion": PROTOCOL_VERSION, "id": workspace_id, "kind": "personal", "name": workspace["name"], "quotaBytes": int(workspace["quota_bytes"]), "usedBytes": int(asset_bytes), "resourceCount": int(used), "createdAt": workspace["created_at"]}

    def workspace_sync_preferences(self, actor: sqlite3.Row) -> dict[str, Any]:
        workspace_id = self._workspace_id(actor)
        with self._connect() as db:
            row = db.execute("SELECT * FROM workspace_sync_preferences WHERE workspace_id=?", (workspace_id,)).fetchone()
        categories = {name: False for name in sorted(SYNC_CATEGORIES)}
        if row is not None:
            categories.update(json.loads(row["categories_json"]))
        return {"protocolVersion": PROTOCOL_VERSION, "enabled": bool(row["enabled"]) if row else False, "categories": categories, "updatedAt": row["updated_at"] if row else ""}

    def update_workspace_sync_preferences(self, actor: sqlite3.Row, request: dict[str, Any]) -> dict[str, Any]:
        if not {"protocolVersion", "enabled", "categories"}.issubset(request) or set(request) - {"protocolVersion", "enabled", "categories", "updatedAt"} or request.get("protocolVersion") != PROTOCOL_VERSION:
            raise CloudApiError(400, "invalid_sync_preferences", "Sync preferences must use the current protocol")
        categories = request.get("categories")
        if not isinstance(categories, dict) or set(categories) != SYNC_CATEGORIES or any(not isinstance(value, bool) for value in categories.values()):
            raise CloudApiError(400, "invalid_sync_preferences", "Every sync category must be an explicit boolean")
        workspace_id, updated_at = self._workspace_id(actor), _iso()
        with self._lock, self._connect() as db:
            db.execute("INSERT INTO workspace_sync_preferences VALUES(?,?,?,?) ON CONFLICT(workspace_id) DO UPDATE SET enabled=excluded.enabled,categories_json=excluded.categories_json,updated_at=excluded.updated_at", (workspace_id, int(bool(request["enabled"])), _json(categories), updated_at))
        return self.workspace_sync_preferences(actor)

    def workspace_sync_status(self, actor: sqlite3.Row) -> dict[str, Any]:
        workspace_id = self._workspace_id(actor)
        with self._connect() as db:
            cursor = int(db.execute("SELECT COALESCE(MAX(cursor),0) FROM workspace_changes WHERE workspace_id=?", (workspace_id,)).fetchone()[0])
            resources = int(db.execute("SELECT COUNT(*) FROM workspace_resources WHERE workspace_id=? AND deleted=0", (workspace_id,)).fetchone()[0])
        return {"protocolVersion": PROTOCOL_VERSION, "workspaceId": workspace_id, "enabled": self.workspace_sync_preferences(actor)["enabled"], "cursor": cursor, "resourceCount": resources, "pendingChanges": 0, "conflictCount": 0, "lastSyncedAt": ""}

    @staticmethod
    def _workspace_change_payload(row: sqlite3.Row, decrypt) -> dict[str, Any]:
        payload = decrypt(row["encrypted_payload"]) if row["encrypted_payload"] else {}
        return {"cursor": int(row["cursor"]), "resourceType": row["resource_type"], "resourceId": row["resource_id"], "operation": row["operation"], "revision": int(row["resource_revision"]), "clientMutationId": row["client_mutation_id"], "payloadHash": row["payload_hash"], "payload": payload, "occurredAt": row["occurred_at"]}

    def pull_workspace_changes(self, actor: sqlite3.Row, cursor: int, limit: int = 200) -> dict[str, Any]:
        workspace_id = self._workspace_id(actor)
        with self._connect() as db:
            rows = db.execute("SELECT * FROM workspace_changes WHERE workspace_id=? AND cursor>? ORDER BY cursor LIMIT ?", (workspace_id, max(0, int(cursor)), max(1, min(int(limit), 500)))).fetchall()
        changes = [self._workspace_change_payload(row, self._decrypt) for row in rows]
        return {"protocolVersion": PROTOCOL_VERSION, "workspaceId": workspace_id, "cursor": changes[-1]["cursor"] if changes else max(0, int(cursor)), "changes": changes, "hasMore": len(rows) == max(1, min(int(limit), 500))}

    def push_workspace_changes(self, actor: sqlite3.Row, request: dict[str, Any], request_id: str) -> dict[str, Any]:
        if request.get("protocolVersion") != PROTOCOL_VERSION or not isinstance(request.get("changes"), list) or len(request["changes"]) > 100:
            raise CloudApiError(400, "invalid_workspace_sync", "A current-protocol batch of at most 100 changes is required")
        workspace_id, applied, conflicts = self._workspace_id(actor), [], []
        with self._lock, self._connect() as db:
            for change in request["changes"]:
                if not isinstance(change, dict):
                    raise CloudApiError(400, "invalid_workspace_change", "Workspace changes must be objects")
                resource_type = str(change.get("resourceType") or "")
                resource_id = str(change.get("resourceId") or "")
                mutation_id = str(change.get("clientMutationId") or "")
                operation = str(change.get("operation") or "")
                if resource_type not in WORKSPACE_RESOURCE_TYPES or not resource_id or len(resource_id) > 256 or len(mutation_id) < 8 or operation not in {"upsert", "delete"}:
                    raise CloudApiError(400, "invalid_workspace_change", "Workspace change identity or operation is invalid")
                duplicate = db.execute("SELECT * FROM workspace_changes WHERE workspace_id=? AND client_mutation_id=?", (workspace_id, mutation_id)).fetchone()
                if duplicate is not None:
                    applied.append(self._workspace_change_payload(duplicate, self._decrypt))
                    continue
                current = db.execute("SELECT * FROM workspace_resources WHERE workspace_id=? AND resource_type=? AND resource_id=?", (workspace_id, resource_type, resource_id)).fetchone()
                current_revision = int(current["revision"]) if current else 0
                base_revision = int(change.get("baseRevision") or 0)
                if base_revision != current_revision:
                    conflicts.append({"resourceType": resource_type, "resourceId": resource_id, "localRevision": base_revision, "cloudRevision": current_revision, "cloudPayload": self._decrypt(current["encrypted_payload"]) if current and not current["deleted"] else {}})
                    continue
                payload = change.get("payload") if operation == "upsert" else {}
                if not isinstance(payload, dict):
                    raise CloudApiError(400, "invalid_workspace_change", "Workspace resource payload must be an object")
                canonical = _json(payload)
                if len(canonical.encode("utf-8")) > 16 * 1024 * 1024:
                    raise CloudApiError(413, "workspace_resource_too_large", "Workspace resource exceeds 16 MiB")
                revision, occurred_at = current_revision + 1, _iso()
                encrypted, payload_hash = self._encrypt(payload), hashlib.sha256(canonical.encode("utf-8")).hexdigest()
                db.execute("INSERT INTO workspace_resources VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(workspace_id,resource_type,resource_id) DO UPDATE SET revision=excluded.revision,deleted=excluded.deleted,encrypted_payload=excluded.encrypted_payload,payload_hash=excluded.payload_hash,updated_at=excluded.updated_at,updated_by=excluded.updated_by", (workspace_id, resource_type, resource_id, revision, int(operation == "delete"), encrypted, payload_hash, occurred_at, actor["id"]))
                inserted = db.execute("INSERT INTO workspace_changes(workspace_id,resource_type,resource_id,operation,resource_revision,client_mutation_id,encrypted_payload,payload_hash,occurred_at) VALUES(?,?,?,?,?,?,?,?,?) RETURNING cursor", (workspace_id, resource_type, resource_id, operation, revision, mutation_id, encrypted, payload_hash, occurred_at)).fetchone()
                cursor = int(inserted["cursor"] if isinstance(inserted, dict) else inserted[0])
                applied.append({"cursor": cursor, "resourceType": resource_type, "resourceId": resource_id, "operation": operation, "revision": revision, "clientMutationId": mutation_id, "payloadHash": payload_hash, "payload": payload, "occurredAt": occurred_at})
            latest = int(db.execute("SELECT COALESCE(MAX(cursor),0) FROM workspace_changes WHERE workspace_id=?", (workspace_id,)).fetchone()[0])
            self._audit(db, actor, "workspace.sync.push", "workspace", workspace_id, request_id)
        return {"protocolVersion": PROTOCOL_VERSION, "workspaceId": workspace_id, "cursor": latest, "applied": applied, "conflicts": conflicts}

    def query_private_library(self, actor: sqlite3.Row, request: dict[str, Any]) -> dict[str, Any]:
        workspace_id = self._workspace_id(actor)
        with self._connect() as db:
            rows = db.execute("SELECT encrypted_payload FROM workspace_resources WHERE workspace_id=? AND resource_type='literature_record' AND deleted=0 ORDER BY updated_at DESC", (workspace_id,)).fetchall()
        records = [self._decrypt(row["encrypted_payload"]) for row in rows]
        text = str(request.get("query") or request.get("searchText") or "").casefold()
        if text:
            records = [record for record in records if text in f"{record.get('title','')} {record.get('authorsText','')} {record.get('keywordsText','')}".casefold()]
        offset, limit = max(0, int(request.get("offset") or 0)), max(1, min(int(request.get("limit") or 50), 200))
        page = records[offset:offset + limit]
        return {"protocolVersion": PROTOCOL_VERSION, "status": "ready" if records else "empty", "records": page, "offset": offset, "nextOffset": offset + len(page), "total": len(records), "hasMore": offset + len(page) < len(records), "cacheAvailable": True, "facets": {"years": [], "sources": [], "journalTypes": [], "pdfStatuses": [], "keywordGroups": []}, "message": "" if records else "No private cloud literature records."}

    def private_library_record(self, actor: sqlite3.Row, record_id: str) -> dict[str, Any]:
        with self._connect() as db:
            row = db.execute("SELECT encrypted_payload FROM workspace_resources WHERE workspace_id=? AND resource_type='literature_record' AND resource_id=? AND deleted=0", (self._workspace_id(actor), record_id)).fetchone()
        if row is None:
            raise CloudApiError(404, "library_record_not_found", "Private library record not found")
        return self._decrypt(row["encrypted_payload"])

    def _workspace_payload(self, actor: sqlite3.Row, resource_type: str, resource_id: str, fallback: dict[str, Any]) -> tuple[dict[str, Any], int]:
        with self._connect() as db:
            row = db.execute("SELECT encrypted_payload,revision FROM workspace_resources WHERE workspace_id=? AND resource_type=? AND resource_id=? AND deleted=0", (self._workspace_id(actor), resource_type, resource_id)).fetchone()
        return (self._decrypt(row["encrypted_payload"]), int(row["revision"])) if row else (fallback, 0)

    def _save_workspace_payload(self, actor: sqlite3.Row, resource_type: str, resource_id: str, payload: dict[str, Any], base_revision: int, request_id: str) -> int:
        result = self.push_workspace_changes(actor, {"protocolVersion": PROTOCOL_VERSION, "deviceId": "cloud-web", "cursor": 0, "changes": [{"resourceType": resource_type, "resourceId": resource_id, "operation": "upsert", "baseRevision": base_revision, "clientMutationId": request_id, "payload": payload}]}, request_id)
        if result["conflicts"]:
            raise CloudApiError(409, f"{resource_type}_conflict", "The cloud resource changed; reload before saving")
        return int(result["applied"][0]["revision"])

    def cloud_library_state(self, actor: sqlite3.Row) -> dict[str, Any]:
        fallback = project_library_state(LibraryStateStore.default_state())
        return self._workspace_payload(actor, "library_state", "current", fallback)[0]

    def mutate_cloud_library_state(self, actor: sqlite3.Row, request: dict[str, Any], request_id: str) -> dict[str, Any]:
        state, revision = self._workspace_payload(actor, "library_state", "current", project_library_state(LibraryStateStore.default_state()))
        expected = int(request.get("expectedRevision") or 0)
        if expected != int(state.get("revision") or 0):
            raise CloudApiError(409, "library_state_conflict", "The cloud library state changed; reload before saving")
        favorites = {key: list(value) for key, value in (state.get("favorites") or {}).items()}
        collections = [dict(value) for value in state.get("collections") or []]
        compare = list((state.get("workspace") or {}).get("compareRecordIds") or [])
        action, record_id, collection_id = str(request.get("action") or ""), str(request.get("recordId") or ""), str(request.get("collectionId") or "")
        changed = True
        if action == "toggle_collection_record" and record_id and collection_id:
            values = list(favorites.get(record_id) or [])
            favorites[record_id] = [value for value in values if value != collection_id] if collection_id in values else [*values, collection_id]
            if not favorites[record_id]: favorites.pop(record_id, None)
        elif action == "toggle_compare_record" and record_id:
            if record_id in compare: compare.remove(record_id)
            elif len(compare) < 4: compare.append(record_id)
            else: raise CloudApiError(409, "compare_limit", "The comparison workspace accepts at most four records")
        elif action == "clear_compare": compare.clear()
        elif action == "remove_compare_record" and record_id:
            if record_id in compare: compare.remove(record_id)
            else: changed = False
        elif action == "create_collection" and str(request.get("name") or "").strip():
            collections.append({"id": uuid.uuid4().hex, "name": str(request["name"]).strip()[:120], "builtIn": False, "recordCount": 0})
        elif action == "rename_collection" and collection_id:
            collections = [{**item, "name": str(request.get("name") or item["name"])[:120]} if item["id"] == collection_id and not item.get("builtIn") else item for item in collections]
        elif action == "delete_collection" and collection_id:
            collections = [item for item in collections if item["id"] != collection_id or item.get("builtIn")]
            favorites = {key: [value for value in values if value != collection_id] for key, values in favorites.items()}
            favorites = {key: values for key, values in favorites.items() if values}
        else: changed = False
        counts: dict[str, int] = {}
        for value in favorites.values():
            for item in value: counts[item] = counts.get(item, 0) + 1
        collections = [{**item, "recordCount": counts.get(item["id"], 0)} for item in collections]
        if changed:
            state = {**state, "revision": expected + 1, "updatedAt": _iso(), "syncState": "synced", "collections": collections, "favorites": favorites, "workspace": {"compareRecordIds": compare}}
            self._save_workspace_payload(actor, "library_state", "current", state, revision, request_id)
        return {"protocolVersion": PROTOCOL_VERSION, "changed": changed, "message": "updated" if changed else "unchanged", "state": state}

    def cloud_research_workspace(self, actor: sqlite3.Row) -> dict[str, Any]:
        records = self.query_private_library(actor, {"limit": 200})["records"]
        return project_research_workspace(Path("."), True, records, self.cloud_library_state(actor))

    def cloud_research_statistics(self, actor: sqlite3.Row) -> dict[str, Any]:
        records = self.query_private_library(actor, {"limit": 200})["records"]
        return project_research_statistics(True, records, self.cloud_library_state(actor))

    def cloud_business_settings(self, actor: sqlite3.Row) -> dict[str, Any]:
        fallback = {"protocolVersion": PROTOCOL_VERSION, **DEFAULT_BUSINESS_SETTINGS, "aiCredentialConfigured": False}
        return self._workspace_payload(actor, "business_settings", "current", fallback)[0]

    def update_cloud_business_settings(self, actor: sqlite3.Row, request: dict[str, Any], request_id: str) -> dict[str, Any]:
        current, resource_revision = self._workspace_payload(actor, "business_settings", "current", {"protocolVersion": PROTOCOL_VERSION, **DEFAULT_BUSINESS_SETTINGS, "aiCredentialConfigured": False})
        if int(request.get("expectedRevision") or 0) != int(current.get("revision") or 0):
            raise CloudApiError(409, "business_settings_conflict", "The cloud settings changed; reload before saving")
        payload = dict(DEFAULT_BUSINESS_SETTINGS)
        payload.update({key: request[key] for key in SETTINGS_FIELDS if key in request})
        payload.update({"protocolVersion": PROTOCOL_VERSION, "revision": int(current.get("revision") or 0) + 1, "aiCredentialConfigured": False, "updatedAt": _iso()})
        self._save_workspace_payload(actor, "business_settings", "current", payload, resource_revision, request_id)
        return payload

    def create_public_submission(self, actor: sqlite3.Row, request: dict[str, Any], request_id: str) -> dict[str, Any]:
        record = request.get("record")
        license_info = request.get("license")
        if not isinstance(record, dict) or not str(record.get("title") or "").strip() or not isinstance(license_info, dict):
            raise CloudApiError(400, "invalid_public_submission", "A bounded record and license declaration are required")
        license_code = str(license_info.get("code") or "")
        license_url = str(license_info.get("url") or "")
        rights_statement = str(license_info.get("rightsStatement") or "")
        if license_code not in PUBLIC_LICENSE_CODES or not license_url.startswith("https://") or len(rights_statement.strip()) < 10:
            raise CloudApiError(400, "invalid_public_license", "A supported verifiable public license declaration is required")
        canonical = _json(record)
        if len(canonical.encode("utf-8")) > 2 * 1024 * 1024:
            raise CloudApiError(413, "public_submission_too_large", "Public metadata submission exceeds 2 MiB")
        submission_id, now = uuid.uuid4().hex, _iso()
        with self._lock, self._connect() as db:
            db.execute("INSERT INTO public_submissions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (submission_id, actor["id"], self._workspace_id(actor), str(request.get("sourceResourceId") or record.get("recordId") or submission_id)[:256], "draft", 1, self._encrypt(record), hashlib.sha256(canonical.encode("utf-8")).hexdigest(), license_code, license_url[:1000], rights_statement[:4000], str(request.get("publicDisplayName") or actor["display_name"])[:120], None, "", now, now))
            self._audit(db, actor, "public.submission.create", "public_submission", submission_id, request_id)
        return self.get_public_submission(actor, submission_id)

    def get_public_submission(self, actor: sqlite3.Row, submission_id: str) -> dict[str, Any]:
        with self._connect() as db:
            row = db.execute("SELECT * FROM public_submissions WHERE id=? AND contributor_id=?", (submission_id, actor["id"])).fetchone()
        if row is None:
            raise CloudApiError(404, "public_submission_not_found", "Public submission not found")
        return self._public_submission_payload(row)

    def list_public_submissions(self, actor: sqlite3.Row, *, moderation: bool = False) -> dict[str, Any]:
        if moderation:
            self._require_system_admin(actor)
        with self._connect() as db:
            rows = db.execute("SELECT * FROM public_submissions " + ("ORDER BY updated_at DESC" if moderation else "WHERE contributor_id=? ORDER BY updated_at DESC"), () if moderation else (actor["id"],)).fetchall()
        return {"protocolVersion": PROTOCOL_VERSION, "submissions": [self._public_submission_payload(row) for row in rows]}

    def _public_submission_payload(self, row: sqlite3.Row) -> dict[str, Any]:
        return {"protocolVersion": PROTOCOL_VERSION, "id": row["id"], "status": row["status"], "revision": int(row["revision"]), "sourceResourceId": row["source_resource_id"], "record": self._decrypt(row["encrypted_snapshot"]), "contentHash": row["content_hash"], "license": {"code": row["license_code"], "url": row["license_url"], "rightsStatement": row["rights_statement"]}, "publicDisplayName": row["public_display_name"], "reviewNote": row["review_note"], "createdAt": row["created_at"], "updatedAt": row["updated_at"]}

    def submit_public_submission(self, actor: sqlite3.Row, submission_id: str, request_id: str) -> dict[str, Any]:
        with self._lock, self._connect() as db:
            row = db.execute("SELECT * FROM public_submissions WHERE id=? AND contributor_id=?", (submission_id, actor["id"])).fetchone()
            if row is None:
                raise CloudApiError(404, "public_submission_not_found", "Public submission not found")
            if row["status"] not in {"draft", "changes_requested"}:
                raise CloudApiError(409, "public_submission_state", "Only draft or changes-requested submissions can be submitted")
            db.execute("UPDATE public_submissions SET status='pending_review',revision=revision+1,updated_at=? WHERE id=?", (_iso(), submission_id))
            self._audit(db, actor, "public.submission.submit", "public_submission", submission_id, request_id)
        return self.get_public_submission(actor, submission_id)

    def request_public_withdrawal(self, actor: sqlite3.Row, submission_id: str, request_id: str) -> dict[str, Any]:
        with self._lock, self._connect() as db:
            row = db.execute("SELECT status FROM public_submissions WHERE id=? AND contributor_id=?", (submission_id, actor["id"])).fetchone()
            if row is None:
                raise CloudApiError(404, "public_submission_not_found", "Public submission not found")
            next_status = "withdrawal_requested" if row["status"] == "approved" else "withdrawn"
            db.execute("UPDATE public_submissions SET status=?,revision=revision+1,updated_at=? WHERE id=?", (next_status, _iso(), submission_id))
            self._audit(db, actor, "public.submission.withdraw", "public_submission", submission_id, request_id)
        return self.get_public_submission(actor, submission_id)

    def _require_system_admin(self, actor: sqlite3.Row) -> None:
        with self._connect() as db:
            allowed = db.execute("SELECT 1 FROM system_admins WHERE user_id=?", (actor["id"],)).fetchone() is not None
        if not allowed:
            raise CloudApiError(403, "system_admin_required", "System administrator permission is required")

    def grant_system_admin(self, actor: sqlite3.Row) -> None:
        with self._lock, self._connect() as db:
            db.execute("INSERT OR IGNORE INTO system_admins VALUES(?,?)", (actor["id"], _iso()))

    def bootstrap_system_admin(self, email: str) -> dict[str, Any]:
        """Promote an existing verified account from an operator-only CLI command."""
        with self._lock, self._connect() as db:
            actor = db.execute("SELECT * FROM users WHERE email=? AND deleted_at IS NULL", (email.strip().casefold(),)).fetchone()
            if actor is None:
                raise CloudApiError(404, "account_not_found", "Register and verify the administrator account first")
            security = db.execute("SELECT status FROM account_security WHERE user_id=?", (actor["id"],)).fetchone()
            if security is not None and security["status"] != "active":
                raise CloudApiError(409, "account_not_active", "Verify the administrator account first")
            db.execute("INSERT OR IGNORE INTO system_admins VALUES(?,?)", (actor["id"], _iso()))
        return {"protocolVersion": PROTOCOL_VERSION, "userId": actor["id"], "email": actor["email"], "systemAdmin": True}

    def moderate_public_submission(self, actor: sqlite3.Row, submission_id: str, request: dict[str, Any], request_id: str) -> dict[str, Any]:
        self._require_system_admin(actor)
        decision = str(request.get("decision") or "")
        if decision not in {"approve", "reject", "request_changes", "withdraw", "takedown"}:
            raise CloudApiError(400, "invalid_moderation_decision", "Unsupported moderation decision")
        target_status = {"approve": "approved", "reject": "rejected", "request_changes": "changes_requested", "withdraw": "withdrawn", "takedown": "takedown"}[decision]
        now = _iso()
        with self._lock, self._connect() as db:
            row = db.execute("SELECT * FROM public_submissions WHERE id=?", (submission_id,)).fetchone()
            if row is None:
                raise CloudApiError(404, "public_submission_not_found", "Public submission not found")
            if decision == "approve" and row["status"] != "pending_review":
                raise CloudApiError(409, "public_submission_state", "Only pending submissions can be approved")
            if decision == "approve":
                record = self._decrypt(row["encrypted_snapshot"])
                doi_key = str(record.get("doi") or "").strip().casefold()
                duplicate = db.execute("SELECT id FROM public_library_records WHERE withdrawn_at IS NULL AND ((doi_key<>'' AND doi_key=?) OR content_hash=?)", (doi_key, row["content_hash"])).fetchone()
                if duplicate is not None:
                    raise CloudApiError(409, "public_record_duplicate", "A matching public record already exists")
                db.execute("INSERT INTO public_library_records VALUES(?,?,?,?,?,?,?,?,?,?,?,NULL)", (uuid.uuid4().hex, submission_id, 1, row["content_hash"], doi_key, row["encrypted_snapshot"], row["license_code"], row["license_url"], row["rights_statement"], row["public_display_name"], now))
                self._promote_public_assets(db, submission_id)
            if decision in {"withdraw", "takedown"}:
                db.execute("UPDATE public_library_records SET withdrawn_at=? WHERE submission_id=?", (now, submission_id))
            db.execute("UPDATE public_submissions SET status=?,revision=revision+1,reviewer_id=?,review_note=?,updated_at=? WHERE id=?", (target_status, actor["id"], str(request.get("note") or "")[:2000], now, submission_id))
            self._audit(db, actor, f"public.moderation.{decision}", "public_submission", submission_id, request_id)
        with self._connect() as db:
            result = db.execute("SELECT * FROM public_submissions WHERE id=?", (submission_id,)).fetchone()
        return self._public_submission_payload(result)

    def query_public_library(self, request: dict[str, Any]) -> dict[str, Any]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM public_library_records WHERE withdrawn_at IS NULL ORDER BY approved_at DESC").fetchall()
        records = []
        text = str(request.get("searchText") or "").casefold()
        for row in rows:
            record = self._decrypt(row["encrypted_record"])
            if text and text not in f"{record.get('title','')} {record.get('authorsText','')} {record.get('keywordsText','')}".casefold():
                continue
            records.append({"id": row["id"], "version": int(row["version"]), "record": record, "license": {"code": row["license_code"], "url": row["license_url"], "rightsStatement": row["rights_statement"]}, "contributorName": row["contributor_name"], "approvedAt": row["approved_at"]})
        offset, limit = max(0, int(request.get("offset") or 0)), max(1, min(int(request.get("limit") or 50), 200))
        return {"protocolVersion": PROTOCOL_VERSION, "records": records[offset:offset + limit], "offset": offset, "total": len(records), "hasMore": offset + limit < len(records)}

    def create_public_takedown_request(self, request: dict[str, Any], request_type: str, remote_ip: str) -> dict[str, Any]:
        if request_type not in {"report", "copyright"}:
            raise CloudApiError(400, "invalid_takedown_type", "Unsupported public report type")
        record_id, reason = str(request.get("recordId") or "").strip(), str(request.get("reason") or "").strip()
        if not record_id or len(reason) < 10 or len(reason) > 5000:
            raise CloudApiError(400, "invalid_takedown_request", "A public record and a detailed reason are required")
        with self._connect() as db:
            record = db.execute("SELECT id FROM public_library_records WHERE id=? AND withdrawn_at IS NULL", (record_id,)).fetchone()
        if record is None:
            raise CloudApiError(404, "public_record_not_found", "Public record not found")
        takedown_id, now = uuid.uuid4().hex, _iso()
        safe_request = {"recordId": record_id, "reason": reason, "evidenceUrl": str(request.get("evidenceUrl") or "")[:2000], "contact": str(request.get("contact") or "")[:320]}
        requester_hash = hashlib.sha256(f"{remote_ip}:{safe_request['contact']}".encode()).hexdigest()
        with self._lock, self._connect() as db:
            db.execute("INSERT INTO public_takedown_requests VALUES(?,?,?,?,?,?,?,?,?,?)", (takedown_id, record_id, request_type, "pending", self._encrypt(safe_request), requester_hash, None, "", now, now))
        return {"protocolVersion": PROTOCOL_VERSION, "id": takedown_id, "status": "pending"}

    def list_public_takedown_requests(self, actor: sqlite3.Row) -> dict[str, Any]:
        self._require_system_admin(actor)
        with self._connect() as db:
            rows = db.execute("SELECT * FROM public_takedown_requests ORDER BY created_at").fetchall()
        return {"protocolVersion": PROTOCOL_VERSION, "requests": [{"id": row["id"], "recordId": row["record_id"], "requestType": row["request_type"], "status": row["status"], "request": self._decrypt(row["encrypted_request"]), "decisionNote": row["decision_note"], "createdAt": row["created_at"], "updatedAt": row["updated_at"]} for row in rows]}

    def decide_public_takedown_request(self, actor: sqlite3.Row, takedown_id: str, request: dict[str, Any], request_id: str) -> dict[str, Any]:
        self._require_system_admin(actor)
        decision = str(request.get("decision") or "")
        if decision not in {"dismiss", "hide"}:
            raise CloudApiError(400, "invalid_takedown_decision", "Decision must be dismiss or hide")
        now = _iso()
        with self._lock, self._connect() as db:
            row = db.execute("SELECT * FROM public_takedown_requests WHERE id=?", (takedown_id,)).fetchone()
            if row is None:
                raise CloudApiError(404, "takedown_request_not_found", "Takedown request not found")
            status = "dismissed" if decision == "dismiss" else "actioned"
            db.execute("UPDATE public_takedown_requests SET status=?,reviewer_id=?,decision_note=?,updated_at=? WHERE id=?", (status, actor["id"], str(request.get("note") or "")[:2000], now, takedown_id))
            if decision == "hide":
                public_record = db.execute("SELECT submission_id FROM public_library_records WHERE id=?", (row["record_id"],)).fetchone()
                db.execute("UPDATE public_library_records SET withdrawn_at=? WHERE id=?", (now, row["record_id"]))
                if public_record is not None:
                    db.execute("UPDATE public_submissions SET status='takedown',updated_at=? WHERE id=?", (now, public_record["submission_id"]))
            self._audit(db, actor, f"public.takedown.{decision}", "public_record", row["record_id"], request_id)
        return {"protocolVersion": PROTOCOL_VERSION, "id": takedown_id, "status": status}

    def set_account_quota(self, actor: sqlite3.Row, user_id: str, quota_bytes: int, request_id: str) -> dict[str, Any]:
        self._require_system_admin(actor)
        if quota_bytes < 0 or quota_bytes > 10 * 1024**4:
            raise CloudApiError(400, "invalid_quota", "Quota is outside the supported range")
        with self._lock, self._connect() as db:
            workspace = db.execute("SELECT id FROM workspaces WHERE owner_user_id=? AND kind='personal'", (user_id,)).fetchone()
            if workspace is None:
                raise CloudApiError(404, "workspace_not_found", "Personal workspace not found")
            db.execute("UPDATE workspaces SET quota_bytes=? WHERE id=?", (quota_bytes, workspace["id"]))
            self._audit(db, actor, "account.quota.update", "workspace", workspace["id"], request_id)
        return {"protocolVersion": PROTOCOL_VERSION, "userId": user_id, "workspaceId": workspace["id"], "quotaBytes": quota_bytes}

    @staticmethod
    def _validate_attachment_content(filename: str, media_type: str, content: bytes) -> None:
        suffix = Path(filename).suffix.casefold()
        if media_type == "application/pdf":
            if suffix != ".pdf" or not content.startswith(b"%PDF-"):
                raise CloudApiError(400, "invalid_attachment_type", "PDF extension and file signature must agree")
            return
        if media_type not in {"text/plain", "application/json"} or suffix not in {".txt", ".json"}:
            raise CloudApiError(400, "invalid_attachment_type", "Only PDF, UTF-8 text, and JSON attachments are supported")
        try:
            content.decode("utf-8")
            if media_type == "application/json":
                json.loads(content)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CloudApiError(400, "invalid_attachment_content", "Text attachments must contain valid UTF-8 content") from exc

    def _clamav_scan(self, content: bytes) -> str:
        if not self.clamav_host:
            raise CloudApiError(503, "malware_scanner_unavailable", "Attachment scanning is not configured", retryable=True)
        try:
            with socket.create_connection((self.clamav_host, self.clamav_port), timeout=15) as stream:
                stream.sendall(b"zINSTREAM\0")
                for offset in range(0, len(content), 1024 * 1024):
                    chunk = content[offset:offset + 1024 * 1024]
                    stream.sendall(struct.pack("!I", len(chunk)) + chunk)
                stream.sendall(struct.pack("!I", 0))
                response = stream.recv(4096).decode("utf-8", errors="replace")
        except OSError as exc:
            raise CloudApiError(503, "malware_scanner_unavailable", "Attachment scanner is unavailable", retryable=True) from exc
        if " FOUND" in response:
            raise CloudApiError(422, "malware_detected", "Attachment failed malware scanning")
        if " OK" not in response:
            raise CloudApiError(503, "malware_scan_failed", "Attachment scanner did not return a conclusive result", retryable=True)
        return "clean"

    def initialize_asset_upload(self, actor: sqlite3.Row, request: dict[str, Any]) -> dict[str, Any]:
        scope = str(request.get("scope") or "")
        filename = Path(str(request.get("filename") or "")).name[:240]
        media_type = str(request.get("mediaType") or "")
        expected_bytes = int(request.get("sizeBytes") or 0)
        expected_sha256 = str(request.get("sha256") or "").casefold()
        submission_id = str(request.get("submissionId") or "")
        if scope not in {"private", "public_submission"} or not filename or media_type not in {"application/pdf", "text/plain", "application/json"} or expected_bytes < 1 or expected_bytes > self.public_max_file_bytes or len(expected_sha256) != 64 or any(char not in "0123456789abcdef" for char in expected_sha256):
            raise CloudApiError(400, "invalid_asset_upload", "Attachment metadata, size, or SHA-256 is invalid")
        workspace_id = self._workspace_id(actor)
        with self._lock, self._connect() as db:
            workspace = db.execute("SELECT quota_bytes FROM workspaces WHERE id=?", (workspace_id,)).fetchone()
            used_row = db.execute("SELECT COALESCE(SUM(size_bytes),0) AS value FROM assets WHERE workspace_id=?", (workspace_id,)).fetchone()
            pending_row = db.execute("SELECT COALESCE(SUM(expected_bytes),0) AS value FROM asset_uploads WHERE workspace_id=?", (workspace_id,)).fetchone()
            used = int(used_row["value"] if isinstance(used_row, dict) else used_row[0])
            pending = int(pending_row["value"] if isinstance(pending_row, dict) else pending_row[0])
            if used + pending + expected_bytes > int(workspace["quota_bytes"]):
                raise CloudApiError(413, "workspace_quota_exceeded", "Workspace attachment quota would be exceeded")
            if scope == "public_submission":
                submission = db.execute("SELECT status FROM public_submissions WHERE id=? AND contributor_id=?", (submission_id, actor["id"])).fetchone()
                if submission is None or submission["status"] not in {"draft", "changes_requested"}:
                    raise CloudApiError(409, "public_submission_state", "A draft public submission is required for public attachments")
            upload_id, now = uuid.uuid4().hex, _iso()
            temporary = self.quarantine_object_dir / f"{upload_id}.part"
            temporary.touch(exist_ok=False)
            db.execute("INSERT INTO asset_uploads VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", (upload_id, workspace_id, actor["id"], scope, submission_id or None, filename, media_type, expected_bytes, expected_sha256, 0, str(temporary), now, _iso(_now() + timedelta(hours=24))))
        return {"protocolVersion": PROTOCOL_VERSION, "uploadId": upload_id, "chunkSize": 4 * 1024 * 1024, "receivedBytes": 0, "expiresAt": _iso(_now() + timedelta(hours=24))}

    def append_asset_chunk(self, actor: sqlite3.Row, upload_id: str, offset: int, content: bytes) -> dict[str, Any]:
        if not content or len(content) > 4 * 1024 * 1024:
            raise CloudApiError(413, "invalid_asset_chunk", "Attachment chunks must contain at most 4 MiB")
        with self._lock, self._connect() as db:
            row = db.execute("SELECT * FROM asset_uploads WHERE id=? AND owner_user_id=? AND expires_at>?", (upload_id, actor["id"], _iso())).fetchone()
            if row is None:
                raise CloudApiError(404, "asset_upload_not_found", "Attachment upload is missing or expired")
            if int(offset) != int(row["received_bytes"]) or int(row["received_bytes"]) + len(content) > int(row["expected_bytes"]):
                raise CloudApiError(409, "asset_chunk_offset", "Attachment chunk offset does not match the committed length")
            path = Path(row["temporary_path"])
            with path.open("ab") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            received = int(row["received_bytes"]) + len(content)
            db.execute("UPDATE asset_uploads SET received_bytes=? WHERE id=?", (received, upload_id))
        return {"protocolVersion": PROTOCOL_VERSION, "uploadId": upload_id, "receivedBytes": received, "complete": received == int(row["expected_bytes"])}

    def complete_asset_upload(self, actor: sqlite3.Row, upload_id: str) -> dict[str, Any]:
        with self._lock, self._connect() as db:
            row = db.execute("SELECT * FROM asset_uploads WHERE id=? AND owner_user_id=? AND expires_at>?", (upload_id, actor["id"], _iso())).fetchone()
            if row is None:
                raise CloudApiError(404, "asset_upload_not_found", "Attachment upload is missing or expired")
            if int(row["received_bytes"]) != int(row["expected_bytes"]):
                raise CloudApiError(409, "asset_upload_incomplete", "Attachment upload has not received all bytes")
            temporary = Path(row["temporary_path"])
            content = temporary.read_bytes()
            digest = hashlib.sha256(content).hexdigest()
            if digest != row["expected_sha256"]:
                raise CloudApiError(409, "asset_hash_mismatch", "Attachment SHA-256 does not match the declaration")
            self._validate_attachment_content(row["filename"], row["media_type"], content)
            scan_status = self._clamav_scan(content)
            asset_id = uuid.uuid4().hex
            target_root = self.quarantine_object_dir if row["scope"] == "public_submission" else self.private_object_dir
            target_dir = target_root / row["workspace_id"]
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / f"{digest}.omnilit"
            encrypted = self._encrypt({"filename": row["filename"], "mediaType": row["media_type"], "contentBase64": base64.b64encode(content).decode("ascii")})
            if not target.exists():
                temporary_target = target.with_suffix(".tmp")
                temporary_target.write_text(encrypted, encoding="ascii")
                os.replace(temporary_target, target)
            db.execute("INSERT INTO assets VALUES(?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(workspace_id,scope,sha256) DO NOTHING", (asset_id, row["workspace_id"], actor["id"], row["scope"], row["submission_id"], row["filename"], row["media_type"], len(content), digest, str(target), scan_status, _iso()))
            saved = db.execute("SELECT * FROM assets WHERE workspace_id=? AND scope=? AND sha256=?", (row["workspace_id"], row["scope"], digest)).fetchone()
            db.execute("DELETE FROM asset_uploads WHERE id=?", (upload_id,))
            temporary.unlink(missing_ok=True)
        return {"protocolVersion": PROTOCOL_VERSION, "id": saved["id"], "scope": saved["scope"], "filename": saved["filename"], "mediaType": saved["media_type"], "sizeBytes": int(saved["size_bytes"]), "sha256": saved["sha256"], "scanStatus": saved["scan_status"], "createdAt": saved["created_at"]}

    def read_asset(self, actor: sqlite3.Row, asset_id: str) -> tuple[dict[str, Any], bytes]:
        with self._connect() as db:
            row = db.execute("SELECT * FROM assets WHERE id=?", (asset_id,)).fetchone()
        if row is None or (row["scope"] == "private" and row["owner_user_id"] != actor["id"]) or row["scope"] == "public_submission":
            raise CloudApiError(404, "asset_not_found", "Attachment is unavailable")
        payload = self._decrypt(Path(row["encrypted_path"]).read_text(encoding="ascii"))
        return {"filename": row["filename"], "mediaType": row["media_type"], "sizeBytes": int(row["size_bytes"])}, base64.b64decode(payload["contentBase64"])

    def _promote_public_assets(self, db: Any, submission_id: str) -> None:
        rows = db.execute("SELECT * FROM assets WHERE submission_id=? AND scope='public_submission'", (submission_id,)).fetchall()
        for row in rows:
            target_dir = self.public_object_dir / "public-library"
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / f"{row['sha256']}.omnilit"
            source = Path(row["encrypted_path"])
            if not target.exists():
                os.replace(source, target)
            else:
                source.unlink(missing_ok=True)
            db.execute("UPDATE assets SET workspace_id='public-library',scope='public',encrypted_path=? WHERE id=?", (str(target), row["id"]))

    def submit_diagnostic(self, actor: sqlite3.Row, report: dict[str, Any]) -> dict[str, Any]:
        """Accept a bounded diagnostic classification only after explicit per-user consent."""
        controls = {**DEFAULT_CONTROLS, **json.loads(actor["controls_json"])}
        if not controls["shareDiagnostics"]:
            raise CloudApiError(403, "diagnostic_sharing_disabled", "Diagnostic sharing is disabled for this account")
        if set(report) != DIAGNOSTIC_FIELDS:
            raise CloudApiError(400, "invalid_diagnostic_report", "Diagnostic reports must contain only the fixed privacy-safe fields")
        validate_diagnostic_report_create_request(report)
        try:
            occurred_at = datetime.fromisoformat(str(report["occurredAt"]).replace("Z", "+00:00"))
        except ValueError as exc:
            raise CloudApiError(400, "invalid_diagnostic_time", "Diagnostic occurredAt must be an ISO-8601 timestamp") from exc
        if occurred_at.tzinfo is None:
            raise CloudApiError(400, "invalid_diagnostic_time", "Diagnostic occurredAt must include a timezone")
        received = _now()
        if occurred_at > received + timedelta(minutes=5) or occurred_at < received - self._diagnostic_retention:
            raise CloudApiError(400, "invalid_diagnostic_time", "Diagnostic timestamp is outside the accepted retention window")
        report_id = uuid.uuid4().hex
        cutoff = received - self._diagnostic_retention
        daily_cutoff = received - timedelta(hours=24)
        with self._lock, self._connect() as db:
            db.execute("DELETE FROM diagnostic_reports WHERE tenant_id=? AND received_at<?", (actor["tenant_id"], _iso(cutoff)))
            recent = int(db.execute("SELECT COUNT(*) FROM diagnostic_reports WHERE tenant_id=? AND received_at>=?", (actor["tenant_id"], _iso(daily_cutoff))).fetchone()[0])
            if recent >= self._diagnostic_daily_limit:
                raise CloudApiError(429, "diagnostic_quota_exceeded", "The tenant diagnostic quota has been reached", retryable=True)
            db.execute(
                "INSERT INTO diagnostic_reports VALUES(?,?,?,?,?,?,?,?,?,?)",
                (report_id, actor["tenant_id"], _iso(occurred_at.astimezone(timezone.utc)), _iso(received), report["source"], report["code"], report["exceptionType"], report["fingerprint"], report["severity"], report["appVersion"]),
            )
            db.execute(
                "DELETE FROM diagnostic_reports WHERE tenant_id=? AND id NOT IN (SELECT id FROM diagnostic_reports WHERE tenant_id=? ORDER BY received_at DESC,id DESC LIMIT ?)",
                (actor["tenant_id"], actor["tenant_id"], self._diagnostic_tenant_limit),
            )
        receipt = {"protocolVersion": PROTOCOL_VERSION, "accepted": True, "reportId": report_id, "retainedUntil": _iso(received + self._diagnostic_retention)}
        validate_diagnostic_receipt(receipt)
        return receipt

    def sync_library(self, actor: sqlite3.Row, request: dict[str, Any], request_id: str) -> dict[str, Any]:
        self._require_resource(actor, "library_state", "current", "editor")
        validate_library_sync_request(request)
        state = dict(request["state"])
        validate_library_state(state)
        with self._lock, self._connect() as db:
            row = db.execute("SELECT * FROM library_snapshots WHERE tenant_id=?", (actor["tenant_id"],)).fetchone()
            current_revision = int(row["cloud_revision"]) if row else 0
            if int(request["baseCloudRevision"]) != current_revision:
                server_state = self._decrypt(row["encrypted_state"]) if row else LibraryStateStore.default_state()
                if "protocolVersion" not in server_state:
                    from omnilit_qt.literature_library_shared import project_library_state
                    server_state = project_library_state(server_state)
                conflict_id = uuid.uuid4().hex
                self._audit(db, actor, "library.sync.conflict", "library_state", conflict_id, request_id)
                return {"protocolVersion": PROTOCOL_VERSION, "status": "conflict", "cloudRevision": current_revision, "syncedAt": row["updated_at"] if row else "", "serverState": server_state, "conflictId": conflict_id}
            cloud_revision, synced_at = current_revision + 1, _iso()
            state["syncState"] = "synced"
            encrypted = self._encrypt(state)
            db.execute("INSERT INTO library_snapshots VALUES(?,?,?,?,?,?) ON CONFLICT(tenant_id) DO UPDATE SET cloud_revision=excluded.cloud_revision, encrypted_state=excluded.encrypted_state, updated_at=excluded.updated_at, updated_by=excluded.updated_by, device_id=excluded.device_id", (actor["tenant_id"], cloud_revision, encrypted, synced_at, actor["id"], request["deviceId"]))
            self._audit(db, actor, "library.sync", "library_state", str(cloud_revision), request_id)
        return {"protocolVersion": PROTOCOL_VERSION, "status": "synced", "cloudRevision": cloud_revision, "syncedAt": synced_at, "serverState": state}

    def get_library(self, actor: sqlite3.Row) -> dict[str, Any]:
        self._require_resource(actor, "library_state", "current", "viewer")
        with self._connect() as db:
            row = db.execute("SELECT * FROM library_snapshots WHERE tenant_id=?", (actor["tenant_id"],)).fetchone()
        if row is None:
            raise CloudApiError(404, "cloud_library_not_found", "No cloud library snapshot exists")
        return {"protocolVersion": PROTOCOL_VERSION, "status": "synced", "cloudRevision": row["cloud_revision"], "syncedAt": row["updated_at"], "serverState": self._decrypt(row["encrypted_state"])}

    def sync_graph(self, actor: sqlite3.Row, request: dict[str, Any], request_id: str, *, expected_record_id: str = "") -> dict[str, Any]:
        validate_cloud_graph_sync_request(request)
        graph = dict(request["graph"])
        validate_graph_data(graph)
        record_id = str(graph.get("recordId") or "")
        if expected_record_id and record_id != expected_record_id:
            raise CloudApiError(409, "graph_record_mismatch", "GraphData recordId must match the sync resource path")
        nodes, edges = list(graph.get("nodes") or []), list(graph.get("edges") or [])
        if not record_id or len(record_id) > 256 or len(nodes) > 10_000 or len(edges) > 40_000:
            raise CloudApiError(413, "graph_too_large", "Cloud graph exceeds the record, node, or edge limit")
        self._require_resource(actor, "graph", record_id, "editor")
        encrypted = self._encrypt(graph)
        if len(encrypted) > 24 * 1024 * 1024:
            raise CloudApiError(413, "graph_too_large", "Encrypted cloud graph exceeds 24 MiB")
        with self._lock, self._connect() as db:
            row = db.execute("SELECT * FROM cloud_graphs WHERE tenant_id=? AND record_id=?", (actor["tenant_id"], record_id)).fetchone()
            current_revision = int(row["cloud_revision"]) if row else 0
            if int(request["baseCloudRevision"]) != current_revision:
                server_graph = self._decrypt(row["encrypted_graph"]) if row else graph
                result = {"protocolVersion": PROTOCOL_VERSION, "status": "conflict", "recordId": record_id, "cloudRevision": current_revision, "syncedAt": row["updated_at"] if row else "", "serverGraph": server_graph, "conflictId": uuid.uuid4().hex}
                self._audit(db, actor, "graph.sync.conflict", "graph", record_id, request_id)
                validate_cloud_graph_sync_result(result)
                return result
            cloud_revision, synced_at = current_revision + 1, _iso()
            db.execute("INSERT INTO cloud_graphs VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(tenant_id,record_id) DO UPDATE SET cloud_revision=excluded.cloud_revision,encrypted_graph=excluded.encrypted_graph,updated_at=excluded.updated_at,updated_by=excluded.updated_by,device_id=excluded.device_id,node_count=excluded.node_count,edge_count=excluded.edge_count", (actor["tenant_id"], record_id, cloud_revision, encrypted, synced_at, actor["id"], str(request["deviceId"]), len(nodes), len(edges)))
            self._audit(db, actor, "graph.sync", "graph", record_id, request_id)
        result = {"protocolVersion": PROTOCOL_VERSION, "status": "synced", "recordId": record_id, "cloudRevision": cloud_revision, "syncedAt": synced_at, "serverGraph": graph}
        validate_cloud_graph_sync_result(result)
        return result

    def get_cloud_graph(self, actor: sqlite3.Row, record_id: str) -> dict[str, Any]:
        if not record_id or len(record_id) > 256:
            raise CloudApiError(400, "invalid_graph_id", "A bounded graph record ID is required")
        self._require_resource(actor, "graph", record_id, "viewer")
        with self._connect() as db:
            row = db.execute("SELECT * FROM cloud_graphs WHERE tenant_id=? AND record_id=?", (actor["tenant_id"], record_id)).fetchone()
        if row is None:
            raise CloudApiError(404, "cloud_graph_not_found", "Cloud graph not found")
        graph = self._decrypt(row["encrypted_graph"])
        validate_graph_data(graph)
        return graph

    @staticmethod
    def _collaboration_revision(db: sqlite3.Connection, tenant_id: str, record_id: str) -> int:
        row = db.execute("SELECT revision FROM collaboration_revisions WHERE tenant_id=? AND record_id=?", (tenant_id, record_id)).fetchone()
        return int(row["revision"]) if row else 0

    def _collaboration_sync_enabled(self, actor: sqlite3.Row) -> bool:
        with self._connect() as db:
            owner = db.execute("SELECT controls_json FROM users WHERE tenant_id=? AND roles_json LIKE '%owner%' AND deleted_at IS NULL LIMIT 1", (actor["tenant_id"],)).fetchone()
        return bool(owner is not None and json.loads(owner["controls_json"]).get("syncAnnotations"))

    def collaboration_snapshot(self, actor: sqlite3.Row, record_id: str) -> dict[str, Any]:
        self._require_resource(actor, "graph", record_id, "viewer")
        can_edit = True
        try:
            self._require_resource(actor, "graph", record_id, "editor")
        except CloudApiError:
            can_edit = False
        with self._connect() as db:
            graph = db.execute("SELECT 1 FROM cloud_graphs WHERE tenant_id=? AND record_id=?", (actor["tenant_id"], record_id)).fetchone()
            if graph is None:
                raise CloudApiError(404, "cloud_graph_not_found", "Cloud graph not found")
            revision = self._collaboration_revision(db, actor["tenant_id"], record_id)
            rows = db.execute("SELECT encrypted_annotation FROM graph_annotations WHERE tenant_id=? AND record_id=? AND deleted=0 ORDER BY revision,annotation_id LIMIT 500", (actor["tenant_id"], record_id)).fetchall()
        result = {"protocolVersion": PROTOCOL_VERSION, "recordId": record_id, "revision": revision, "canEdit": can_edit, "syncEnabled": self._collaboration_sync_enabled(actor), "annotations": [self._decrypt(row["encrypted_annotation"]) for row in rows]}
        validate_collaboration_snapshot(result)
        return result

    def _collaboration_event_page(self, tenant_id: str, record_id: str, after_revision: int, limit: int) -> dict[str, Any]:
        with self._connect() as db:
            current_revision = self._collaboration_revision(db, tenant_id, record_id)
            oldest = db.execute("SELECT MIN(revision) FROM collaboration_events WHERE tenant_id=? AND record_id=?", (tenant_id, record_id)).fetchone()[0]
            rows = db.execute("SELECT encrypted_event FROM collaboration_events WHERE tenant_id=? AND record_id=? AND revision>? ORDER BY revision LIMIT ?", (tenant_id, record_id, after_revision, limit + 1)).fetchall()
        has_more = len(rows) > limit
        result = {"protocolVersion": PROTOCOL_VERSION, "recordId": record_id, "afterRevision": after_revision, "currentRevision": current_revision, "events": [self._decrypt(row["encrypted_event"]) for row in rows[:limit]], "hasMore": has_more, "resetRequired": bool(after_revision > 0 and oldest is not None and int(oldest) > after_revision + 1)}
        validate_collaboration_event_page(result)
        return result

    def collaboration_events(self, actor: sqlite3.Row, record_id: str, after_revision: int, *, limit: int = 100, wait_seconds: float = 0.0) -> dict[str, Any]:
        if after_revision < 0 or limit < 1 or limit > 200 or wait_seconds < 0 or wait_seconds > 25:
            raise CloudApiError(400, "invalid_collaboration_query", "Collaboration revision, limit, or wait duration is invalid")
        self._require_resource(actor, "graph", record_id, "viewer")
        with self._connect() as db:
            if db.execute("SELECT 1 FROM cloud_graphs WHERE tenant_id=? AND record_id=?", (actor["tenant_id"], record_id)).fetchone() is None:
                raise CloudApiError(404, "cloud_graph_not_found", "Cloud graph not found")
        page = self._collaboration_event_page(actor["tenant_id"], record_id, after_revision, limit)
        if page["events"] or page["resetRequired"] or wait_seconds <= 0:
            return page
        with self._collaboration_condition:
            page = self._collaboration_event_page(actor["tenant_id"], record_id, after_revision, limit)
            if not page["events"] and not page["resetRequired"]:
                self._collaboration_condition.wait(wait_seconds)
        return self._collaboration_event_page(actor["tenant_id"], record_id, after_revision, limit)

    def mutate_collaboration(self, actor: sqlite3.Row, record_id: str, request: dict[str, Any], request_id: str) -> dict[str, Any]:
        validate_collaboration_mutation_request(request)
        self._require_resource(actor, "graph", record_id, "editor")
        try:
            client_mutation_id = str(uuid.UUID(str(request["clientMutationId"])))
        except ValueError as exc:
            raise CloudApiError(400, "invalid_client_mutation_id", "clientMutationId must be a UUID") from exc
        action = str(request["action"])
        target_type, target_id = str(request["targetType"]), str(request["targetId"])
        body = str(request.get("body") or "").strip()
        requested_annotation_id = str(request.get("annotationId") or "")
        if requested_annotation_id:
            try:
                requested_annotation_id = str(uuid.UUID(requested_annotation_id))
            except ValueError as exc:
                raise CloudApiError(400, "invalid_annotation_id", "annotationId must be a UUID") from exc
        if action == "upsert" and not body:
            raise CloudApiError(400, "empty_annotation", "Annotation body cannot be empty")
        if action == "upsert" and not self._collaboration_sync_enabled(actor):
            raise CloudApiError(403, "annotation_sync_disabled", "The tenant owner has not enabled annotation sync")
        if action == "delete" and not requested_annotation_id:
            raise CloudApiError(400, "annotation_id_required", "Deleting an annotation requires annotationId")
        graph = self.get_cloud_graph(actor, record_id)
        if target_type == "graph":
            target_exists = target_id == record_id
        elif target_type == "node":
            target_exists = any(str(node.get("id")) == target_id for node in graph["nodes"])
        else:
            target_exists = any(str(edge.get("id")) == target_id for edge in graph["edges"])
        if action == "upsert" and not target_exists:
            raise CloudApiError(404, "collaboration_target_not_found", "Annotation target does not exist in the current cloud graph")

        with self._lock, self._connect() as db:
            duplicate = db.execute("SELECT encrypted_event FROM collaboration_events WHERE tenant_id=? AND record_id=? AND client_mutation_id=?", (actor["tenant_id"], record_id, client_mutation_id)).fetchone()
            if duplicate is not None:
                event = self._decrypt(duplicate["encrypted_event"])
                result = {"protocolVersion": PROTOCOL_VERSION, "recordId": record_id, "revision": event["revision"], "event": event}
                validate_collaboration_mutation_result(result)
                return result
            current_revision = self._collaboration_revision(db, actor["tenant_id"], record_id)
            if int(request["baseRevision"]) != current_revision:
                self._audit(db, actor, "collaboration.conflict", "graph", record_id, request_id)
                db.commit()
                raise CloudApiError(409, "collaboration_conflict", "Collaboration revision is stale; reload the snapshot before retrying")
            annotation_id = requested_annotation_id or str(uuid.uuid4())
            existing_row = db.execute("SELECT * FROM graph_annotations WHERE tenant_id=? AND record_id=? AND annotation_id=?", (actor["tenant_id"], record_id, annotation_id)).fetchone()
            existing = self._decrypt(existing_row["encrypted_annotation"]) if existing_row is not None else None
            if action == "delete" and (existing_row is None or bool(existing_row["deleted"])):
                raise CloudApiError(404, "annotation_not_found", "Collaboration annotation not found")
            if existing is not None and (existing["targetType"] != target_type or existing["targetId"] != target_id):
                raise CloudApiError(409, "annotation_target_mismatch", "An existing annotation cannot be moved to another target")
            if action == "upsert" and existing_row is None:
                count = db.execute("SELECT COUNT(*) FROM graph_annotations WHERE tenant_id=? AND record_id=? AND deleted=0", (actor["tenant_id"], record_id)).fetchone()[0]
                if count >= 500:
                    raise CloudApiError(409, "annotation_limit_reached", "At most 500 active annotations are allowed per graph")
            revision, occurred_at = current_revision + 1, _iso()
            annotation = None
            if action == "upsert":
                annotation = {"protocolVersion": PROTOCOL_VERSION, "id": annotation_id, "recordId": record_id, "targetType": target_type, "targetId": target_id, "body": body, "authorId": actor["id"], "authorDisplayName": actor["display_name"], "revision": revision, "createdAt": existing["createdAt"] if existing else occurred_at, "updatedAt": occurred_at}
                db.execute("INSERT INTO graph_annotations VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(tenant_id,record_id,annotation_id) DO UPDATE SET encrypted_annotation=excluded.encrypted_annotation,revision=excluded.revision,deleted=0,updated_at=excluded.updated_at", (actor["tenant_id"], record_id, annotation_id, target_type, target_id, self._encrypt(annotation), revision, 0, annotation["createdAt"], occurred_at))
                event_action = "annotation.upserted"
            else:
                db.execute("UPDATE graph_annotations SET encrypted_annotation=?,revision=?,deleted=1,updated_at=? WHERE tenant_id=? AND record_id=? AND annotation_id=?", (self._encrypt({"deleted": True}), revision, occurred_at, actor["tenant_id"], record_id, annotation_id))
                historical_rows = db.execute("SELECT revision,encrypted_event FROM collaboration_events WHERE tenant_id=? AND record_id=?", (actor["tenant_id"], record_id)).fetchall()
                for historical_row in historical_rows:
                    historical_event = self._decrypt(historical_row["encrypted_event"])
                    if historical_event.get("annotationId") == annotation_id and "annotation" in historical_event:
                        historical_event.pop("annotation", None)
                        db.execute("UPDATE collaboration_events SET encrypted_event=? WHERE tenant_id=? AND record_id=? AND revision=?", (self._encrypt(historical_event), actor["tenant_id"], record_id, historical_row["revision"]))
                event_action = "annotation.deleted"
            event = {"protocolVersion": PROTOCOL_VERSION, "recordId": record_id, "revision": revision, "clientMutationId": client_mutation_id, "action": event_action, "annotationId": annotation_id, "actorId": actor["id"], "occurredAt": occurred_at}
            if annotation is not None:
                event["annotation"] = annotation
            db.execute("INSERT INTO collaboration_revisions VALUES(?,?,?) ON CONFLICT(tenant_id,record_id) DO UPDATE SET revision=excluded.revision", (actor["tenant_id"], record_id, revision))
            db.execute("INSERT INTO collaboration_events VALUES(?,?,?,?,?,?)", (actor["tenant_id"], record_id, revision, client_mutation_id, self._encrypt(event), occurred_at))
            db.execute("DELETE FROM collaboration_events WHERE tenant_id=? AND record_id=? AND revision<=?", (actor["tenant_id"], record_id, max(0, revision - self._collaboration_event_retention)))
            self._audit(db, actor, event_action, "graph_annotation", annotation_id, request_id)
        with self._collaboration_condition:
            self._collaboration_condition.notify_all()
        result = {"protocolVersion": PROTOCOL_VERSION, "recordId": record_id, "revision": revision, "event": event}
        validate_collaboration_mutation_result(result)
        return result

    def list_cloud_graphs(self, actor: sqlite3.Row) -> dict[str, Any]:
        with self._connect() as db:
            rows = db.execute("SELECT record_id,cloud_revision,updated_at,node_count,edge_count FROM cloud_graphs WHERE tenant_id=? ORDER BY updated_at DESC", (actor["tenant_id"],)).fetchall()
        graphs = []
        for row in rows:
            try:
                self._require_resource(actor, "graph", row["record_id"], "viewer")
            except CloudApiError:
                continue
            graphs.append({"recordId": row["record_id"], "cloudRevision": row["cloud_revision"], "updatedAt": row["updated_at"], "nodeCount": row["node_count"], "edgeCount": row["edge_count"]})
        result = {"protocolVersion": PROTOCOL_VERSION, "graphs": graphs}
        validate_cloud_graph_list(result)
        return result

    def cloud_graph_neighbors(self, actor: sqlite3.Row, record_id: str, node_id: str, mode: str, offset: int, limit: int) -> dict[str, Any]:
        graph = self.get_cloud_graph(actor, record_id)
        if mode not in {"all", "references", "cited_by", "authors", "institutions", "topics", "venues"}:
            raise CloudApiError(400, "invalid_relation_mode", "Unsupported graph relation mode")
        offset, limit = max(0, int(offset)), max(1, min(int(limit), 100))
        relation_types = {"authors": {"AUTHOR_OF", "WRITTEN_BY"}, "institutions": {"AFFILIATED_WITH"}, "topics": {"HAS_TOPIC", "MENTIONS", "HAS_KEYWORD"}, "venues": {"PUBLISHED_IN"}}
        incident = []
        for edge in graph["edges"]:
            if edge["source"] != node_id and edge["target"] != node_id:
                continue
            edge_type = str(edge["type"]).upper()
            if mode == "references" and not (edge["source"] == node_id and edge_type == "CITES"):
                continue
            if mode == "cited_by" and not (edge["target"] == node_id and edge_type == "CITES"):
                continue
            if mode in relation_types and edge_type not in relation_types[mode]:
                continue
            incident.append(edge)
        neighbor_ids = list(dict.fromkeys(edge["target"] if edge["source"] == node_id else edge["source"] for edge in incident))
        page_ids = set(neighbor_ids[offset:offset + limit])
        nodes = [node for node in graph["nodes"] if node["id"] in page_ids]
        edges = [edge for edge in incident if (edge["target"] if edge["source"] == node_id else edge["source"]) in page_ids]
        result = {"protocolVersion": PROTOCOL_VERSION, "schemaVersion": 1, "recordId": record_id, "nodeId": node_id, "relationMode": mode, "status": "ready" if nodes else "empty", "nodes": nodes, "edges": edges, "offset": offset, "nextOffset": offset + len(nodes), "revealed": len(nodes), "total": len(neighbor_ids), "hasMore": offset + len(nodes) < len(neighbor_ids)}
        validate_graph_neighbor_page(result)
        return result

    def cloud_graph_literature(self, actor: sqlite3.Row, record_id: str, request: dict[str, Any]) -> dict[str, Any]:
        graph = self.get_cloud_graph(actor, record_id)
        visible_values = request.get("visibleNodeIds") or []
        if not isinstance(visible_values, list) or len(visible_values) > 5_000:
            raise CloudApiError(400, "invalid_visible_nodes", "visibleNodeIds must be an array of at most 5000 IDs")
        visible = {str(value) for value in visible_values}
        selected, hovered = str(request.get("selectedNodeId") or ""), str(request.get("hoveredNodeId") or "")
        paper = dict(graph.get("paper") or {})
        rows = []
        for node in graph["nodes"]:
            if node["id"] not in visible or node["type"] not in {"paper", "citation"}:
                continue
            attributes, metrics = dict(node.get("attributes") or {}), dict(node.get("metrics") or {})
            authors_value = attributes.get("authors", paper.get("authors", []))
            authors = ", ".join(str(item.get("name") if isinstance(item, dict) else item) for item in authors_value) if isinstance(authors_value, list) else str(authors_value or "")
            title = str(attributes.get("title") or node.get("label") or "")
            importance, confidence = float(metrics.get("importance", 0.5)), float(metrics.get("confidence", 1.0))
            rows.append({"nodeId": node["id"], "recordId": str(attributes.get("recordId") or record_id), "kind": node["type"], "title": title, "year": str(attributes.get("year") or paper.get("year") or ""), "authors": authors, "venue": str(attributes.get("venue") or ""), "citations": max(0, int(attributes.get("citations") or 0)), "importance": importance, "confidence": confidence, "evidenceCount": len(node.get("evidence") or []), "selected": selected == node["id"], "hovered": hovered == node["id"], "searchText": f"{title} {authors}".strip(), "relevance": importance})
        result = {"protocolVersion": PROTOCOL_VERSION, "recordId": record_id, "rows": rows, "offset": 0, "nextOffset": len(rows), "total": len(rows), "hasMore": False}
        validate_literature_page(result)
        return result

    def list_cloud_views(self, actor: sqlite3.Row, record_id: str) -> dict[str, Any]:
        self._require_resource(actor, "graph", record_id, "viewer")
        with self._connect() as db:
            rows = db.execute("SELECT encrypted_view FROM cloud_graph_views WHERE tenant_id=? AND record_id=?", (actor["tenant_id"], record_id)).fetchall()
        result = {"protocolVersion": PROTOCOL_VERSION, "recordId": record_id, "views": view_summaries([self._decrypt(row["encrypted_view"]) for row in rows])}
        validate_graph_view_list(result)
        return result

    def save_cloud_view(self, actor: sqlite3.Row, record_id: str, request: dict[str, Any], request_id: str) -> dict[str, Any]:
        validate_graph_view_save_request(request)
        self._require_resource(actor, "graph", record_id, "editor")
        graph = self.get_cloud_graph(actor, record_id)
        with self._lock, self._connect() as db:
            rows = db.execute("SELECT * FROM cloud_graph_views WHERE tenant_id=? AND record_id=?", (actor["tenant_id"], record_id)).fetchall()
            views = [self._decrypt(row["encrypted_view"]) for row in rows]
            requested_id, name = str(request.get("id") or ""), str(request.get("name") or "").strip()[:80]
            existing = next((item for item in views if requested_id and item["id"] == requested_id), None) or next((item for item in views if str(item.get("name") or "").casefold() == name.casefold()), None)
            snapshot = make_snapshot(record_id, name, str(request.get("graphFingerprint") or (graph.get("metadata") or {}).get("source_fingerprint") or ""), dict(request.get("exploration") or {}), dict(request.get("filters") or {}), dict(request.get("selection") or {}), dict(request.get("viewport") or {}), existing, path=dict(request.get("path") or {}))
            if existing is None and len(views) >= 100:
                raise CloudApiError(409, "view_limit_reached", "At most 100 cloud graph views can be saved")
            db.execute("INSERT INTO cloud_graph_views VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(tenant_id,record_id,view_id) DO UPDATE SET encrypted_view=excluded.encrypted_view,name=excluded.name,updated_at=excluded.updated_at,graph_fingerprint=excluded.graph_fingerprint", (actor["tenant_id"], record_id, snapshot["id"], self._encrypt(snapshot), snapshot["name"], snapshot["createdAt"], snapshot["updatedAt"], snapshot["graphFingerprint"]))
            self._audit(db, actor, "graph_view.save", "graph_view", snapshot["id"], request_id)
        validate_graph_view_state(snapshot)
        return snapshot

    def restore_cloud_view(self, actor: sqlite3.Row, record_id: str, view_id: str) -> dict[str, Any]:
        graph = self.get_cloud_graph(actor, record_id)
        with self._connect() as db:
            row = db.execute("SELECT encrypted_view FROM cloud_graph_views WHERE tenant_id=? AND record_id=? AND view_id=?", (actor["tenant_id"], record_id, view_id)).fetchone()
        if row is None:
            raise CloudApiError(404, "view_not_found", "Cloud graph view not found")
        restored, report = reconcile_snapshot(self._decrypt(row["encrypted_view"]), graph)
        node_ids = set(restored["exploration"]["nodeIds"])
        edge_ids = set(restored["exploration"]["edgeIds"])
        if node_ids:
            nodes = [node for node in graph["nodes"] if node["id"] in node_ids]
            visible = {node["id"] for node in nodes}
            edges = [edge for edge in graph["edges"] if edge["source"] in visible and edge["target"] in visible and (not edge_ids or edge["id"] in edge_ids)]
            restored_graph = {**graph, "nodes": nodes, "edges": edges, "viewState": restored, "metadata": {**graph["metadata"], "projection": "saved-view"}}
        else:
            restored_graph = {**graph, "viewState": restored}
        result = {"protocolVersion": PROTOCOL_VERSION, "recordId": record_id, "view": restored, "graph": restored_graph, "reconciliation": report}
        validate_graph_view_restore(result)
        return result

    def delete_cloud_view(self, actor: sqlite3.Row, record_id: str, view_id: str, request_id: str) -> dict[str, Any]:
        self._require_resource(actor, "graph", record_id, "editor")
        with self._lock, self._connect() as db:
            cursor = db.execute("DELETE FROM cloud_graph_views WHERE tenant_id=? AND record_id=? AND view_id=?", (actor["tenant_id"], record_id, view_id))
            if cursor.rowcount == 0:
                raise CloudApiError(404, "view_not_found", "Cloud graph view not found")
            self._audit(db, actor, "graph_view.delete", "graph_view", view_id, request_id)
        result = {"protocolVersion": PROTOCOL_VERSION, "recordId": record_id, "viewId": view_id, "deleted": True}
        validate_graph_view_mutation(result)
        return result

    def create_share(self, actor: sqlite3.Row, request: dict[str, Any], request_id: str) -> dict[str, Any]:
        controls = json.loads(actor["controls_json"])
        if not controls.get("allowShareLinks"):
            raise CloudApiError(403, "sharing_disabled", "Enable share links in cloud data controls first")
        resource_type, resource_id = str(request.get("resourceType") or ""), str(request.get("resourceId") or "")
        permission = str(request.get("permission") or "")
        if resource_type not in {"library_state", "collection", "graph", "graph_view"} or not resource_id or permission not in {"viewer", "editor"}:
            raise CloudApiError(400, "invalid_share", "A supported resource and permission are required")
        if resource_type == "graph_view":
            with self._connect() as db:
                view = db.execute("SELECT record_id FROM cloud_graph_views WHERE tenant_id=? AND view_id=?", (actor["tenant_id"], resource_id)).fetchone()
            if view is None:
                raise CloudApiError(404, "view_not_found", "Cloud graph view not found")
            self._require_resource(actor, "graph", view["record_id"], "editor")
        else:
            self._require_resource(actor, resource_type, resource_id, "editor")
        share_id, token = uuid.uuid4().hex, secrets.token_urlsafe(32)
        expires_at = str(request.get("expiresAt") or _iso(_now() + timedelta(days=7)))
        created_at = _iso()
        with self._lock, self._connect() as db:
            db.execute("INSERT INTO shares VALUES(?,?,?,?,?,?,?,?,?,NULL)", (share_id, actor["tenant_id"], actor["id"], hashlib.sha256(token.encode()).hexdigest(), resource_type, resource_id[:256], permission, created_at, expires_at))
            self._audit(db, actor, "share.create", resource_type, resource_id, request_id)
        return {"protocolVersion": PROTOCOL_VERSION, "id": share_id, "resourceType": resource_type, "resourceId": resource_id, "permission": permission, "createdAt": created_at, "expiresAt": expires_at, "revoked": False, "url": f"{self.public_base_url}/#/share/{token}"}

    def revoke_share(self, actor: sqlite3.Row, share_id: str, request_id: str) -> None:
        with self._lock, self._connect() as db:
            row = db.execute("SELECT * FROM shares WHERE id=? AND tenant_id=?", (share_id, actor["tenant_id"])).fetchone()
            if row is None:
                raise CloudApiError(404, "share_not_found", "Share link not found")
            db.execute("UPDATE shares SET revoked_at=? WHERE id=? AND tenant_id=?", (_iso(), share_id, actor["tenant_id"]))
            self._audit(db, actor, "share.revoke", row["resource_type"], row["resource_id"], request_id)

    def resolve_share(self, token: str) -> dict[str, Any]:
        with self._connect() as db:
            share = db.execute("SELECT * FROM shares WHERE token_hash=? AND revoked_at IS NULL AND expires_at>?", (hashlib.sha256(token.encode()).hexdigest(), _iso())).fetchone()
            if share is None:
                raise CloudApiError(404, "share_not_found", "Share link is invalid, expired, or revoked")
            if share["resource_type"] in {"library_state", "collection"}:
                snapshot = db.execute("SELECT * FROM library_snapshots WHERE tenant_id=?", (share["tenant_id"],)).fetchone()
                if snapshot is None:
                    raise CloudApiError(404, "shared_resource_not_found", "Shared resource is unavailable")
                state = self._decrypt(snapshot["encrypted_state"])
            elif share["resource_type"] == "graph":
                row = db.execute("SELECT encrypted_graph FROM cloud_graphs WHERE tenant_id=? AND record_id=?", (share["tenant_id"], share["resource_id"])).fetchone()
                if row is None:
                    raise CloudApiError(404, "shared_resource_not_found", "Shared graph is unavailable")
                return {"protocolVersion": PROTOCOL_VERSION, "resourceType": "graph", "resourceId": share["resource_id"], "permission": share["permission"], "graph": self._decrypt(row["encrypted_graph"])}
            else:
                row = db.execute("SELECT encrypted_view,record_id FROM cloud_graph_views WHERE tenant_id=? AND view_id=?", (share["tenant_id"], share["resource_id"])).fetchone()
                if row is None:
                    raise CloudApiError(404, "shared_resource_not_found", "Shared graph view is unavailable")
                graph_row = db.execute("SELECT encrypted_graph FROM cloud_graphs WHERE tenant_id=? AND record_id=?", (share["tenant_id"], row["record_id"])).fetchone()
                if graph_row is None:
                    raise CloudApiError(404, "shared_resource_not_found", "Shared graph is unavailable")
                return {"protocolVersion": PROTOCOL_VERSION, "resourceType": "graph_view", "resourceId": share["resource_id"], "permission": share["permission"], "view": self._decrypt(row["encrypted_view"]), "graph": self._decrypt(graph_row["encrypted_graph"])}
        if share["resource_type"] == "collection":
            collection_id = share["resource_id"]
            state = {**state, "collections": [item for item in state["collections"] if item["id"] == collection_id], "favorites": {record_id: [collection_id] for record_id, ids in state["favorites"].items() if collection_id in ids}, "workspace": {"compareRecordIds": []}}
        return {"protocolVersion": PROTOCOL_VERSION, "resourceType": share["resource_type"], "resourceId": share["resource_id"], "permission": share["permission"], "state": state}

    def audit_events(self, actor: sqlite3.Row, limit: int = 100) -> dict[str, Any]:
        self._require_team_admin(actor)
        with self._connect() as db:
            rows = db.execute("SELECT * FROM audits WHERE tenant_id=? ORDER BY occurred_at DESC LIMIT ?", (actor["tenant_id"], max(1, min(limit, 200)))).fetchall()
        events = [{"id": row["id"], "occurredAt": row["occurred_at"], "actorId": row["actor_id"], "action": row["action"], "resourceType": row["resource_type"], "resourceId": row["resource_id"], "requestId": row["request_id"]} for row in rows]
        return {"protocolVersion": PROTOCOL_VERSION, "events": events}

    def export_account(self, actor: sqlite3.Row, request_id: str) -> dict[str, Any]:
        self._require_team_admin(actor, owner_only=True)
        with self._lock, self._connect() as db:
            snapshot = db.execute("SELECT * FROM library_snapshots WHERE tenant_id=?", (actor["tenant_id"],)).fetchone()
            shares = db.execute("SELECT id,resource_type,resource_id,permission,created_at,expires_at,revoked_at FROM shares WHERE tenant_id=?", (actor["tenant_id"],)).fetchall()
            annotation_rows = db.execute("SELECT record_id,encrypted_annotation FROM graph_annotations WHERE tenant_id=? AND deleted=0 ORDER BY record_id,revision", (actor["tenant_id"],)).fetchall()
            revisions = db.execute("SELECT record_id,revision FROM collaboration_revisions WHERE tenant_id=?", (actor["tenant_id"],)).fetchall()
            diagnostics = db.execute("SELECT id,occurred_at,received_at,source,code,exception_type,fingerprint,severity,app_version FROM diagnostic_reports WHERE tenant_id=? ORDER BY received_at,id", (actor["tenant_id"],)).fetchall()
            self._audit(db, actor, "account.export", "user", actor["id"], request_id)
        annotations_by_graph: dict[str, list[dict[str, Any]]] = {}
        for row in annotation_rows:
            annotations_by_graph.setdefault(row["record_id"], []).append(self._decrypt(row["encrypted_annotation"]))
        collaboration = [{"recordId": row["record_id"], "revision": row["revision"], "annotations": annotations_by_graph.get(row["record_id"], [])} for row in revisions]
        diagnostic_export = [{"id": row["id"], "occurredAt": row["occurred_at"], "receivedAt": row["received_at"], "source": row["source"], "code": row["code"], "exceptionType": row["exception_type"], "fingerprint": row["fingerprint"], "severity": row["severity"], "appVersion": row["app_version"]} for row in diagnostics]
        return {"protocolVersion": PROTOCOL_VERSION, "account": self._account(actor), "library": self._decrypt(snapshot["encrypted_state"]) if snapshot else None, "shares": [dict(row) for row in shares], "collaboration": collaboration, "diagnostics": diagnostic_export}

    def delete_account(self, actor: sqlite3.Row, confirmation: str, request_id: str) -> None:
        if confirmation != actor["email"]:
            raise CloudApiError(400, "deletion_confirmation_required", "Confirm account deletion with the account email")
        with self._lock, self._connect() as db:
            self._audit(db, actor, "account.delete", "user", actor["id"], request_id)
            if "owner" in json.loads(actor["roles_json"]):
                db.execute("DELETE FROM audits WHERE tenant_id=?", (actor["tenant_id"],))
                db.execute("DELETE FROM tenants WHERE id=?", (actor["tenant_id"],))
            else:
                db.execute("DELETE FROM users WHERE id=? AND tenant_id=?", (actor["id"], actor["tenant_id"]))

    def list_team_members(self, actor: sqlite3.Row) -> dict[str, Any]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM users WHERE tenant_id=? AND deleted_at IS NULL ORDER BY created_at,id", (actor["tenant_id"],)).fetchall()
        members = [{"id": row["id"], "email": row["email"], "displayName": row["display_name"], "role": self._role(row), "joinedAt": row["created_at"]} for row in rows]
        return {"protocolVersion": PROTOCOL_VERSION, "tenantId": actor["tenant_id"], "members": members}

    def create_team_invite(self, actor: sqlite3.Row, request: dict[str, Any], request_id: str) -> dict[str, Any]:
        validate_team_invite_create(request)
        self._require_team_admin(actor)
        email, role = str(request["email"]).strip().casefold(), str(request["role"])
        if "@" not in email or role not in {"admin", "member"}:
            raise CloudApiError(400, "invalid_invite", "A valid invitation email and supported role are required")
        if role == "admin" and self._role(actor) != "owner":
            raise CloudApiError(403, "permission_denied", "Only the tenant owner can invite administrators")
        token, invite_id = secrets.token_urlsafe(32), uuid.uuid4().hex
        created_at = _iso()
        expires_at = _iso(_now() + timedelta(hours=int(request.get("expiresInHours") or 72)))
        with self._lock, self._connect() as db:
            if db.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone():
                raise CloudApiError(409, "email_exists", "This email already belongs to an OmniLit account")
            db.execute("UPDATE team_invites SET accepted_at=? WHERE tenant_id=? AND email=? AND accepted_at IS NULL", (_iso(), actor["tenant_id"], email))
            db.execute("INSERT INTO team_invites VALUES(?,?,?,?,?,?,?,?,NULL)", (invite_id, actor["tenant_id"], actor["id"], email, role, hashlib.sha256(token.encode()).hexdigest(), created_at, expires_at))
            self._audit(db, actor, "team.invite.create", "team_invite", invite_id, request_id)
        return {"protocolVersion": PROTOCOL_VERSION, "id": invite_id, "tenantId": actor["tenant_id"], "email": email, "role": role, "createdAt": created_at, "expiresAt": expires_at, "accepted": False, "url": f"{self.public_base_url}/#/invite/{token}"}

    def accept_team_invite(self, request: dict[str, Any], request_id: str) -> dict[str, Any]:
        validate_team_invite_accept(request)
        if len(str(request["password"])) < 12 or not str(request["displayName"]).strip():
            raise CloudApiError(400, "invalid_invite_account", "A display name and password of at least 12 characters are required")
        token_hash = hashlib.sha256(str(request["token"]).encode()).hexdigest()
        with self._lock, self._connect() as db:
            invite = db.execute("SELECT * FROM team_invites WHERE token_hash=? AND accepted_at IS NULL AND expires_at>?", (token_hash, _iso())).fetchone()
            if invite is None:
                raise CloudApiError(404, "invite_not_found", "Invitation is invalid, expired, replaced, or already used")
            if db.execute("SELECT 1 FROM users WHERE email=?", (invite["email"],)).fetchone():
                raise CloudApiError(409, "email_exists", "This email already belongs to an OmniLit account")
            user_id, created_at = uuid.uuid4().hex, _iso()
            display_name = str(request["displayName"]).strip()
            db.execute("INSERT INTO users(id,tenant_id,email,display_name,password_hash,roles_json,controls_json,created_at,deleted_at) VALUES(?,?,?,?,?,?,?,?,NULL)", (user_id, invite["tenant_id"], invite["email"], display_name, self._password_hash(str(request["password"])), _json([invite["role"]]), _json(DEFAULT_CONTROLS), created_at))
            db.execute("INSERT INTO workspaces(id,owner_user_id,kind,name,quota_bytes,created_at) VALUES(?,?,?,?,?,?)", (uuid.uuid4().hex, user_id, "personal", f"{display_name} Workspace", self.default_quota_bytes, created_at))
            db.execute("UPDATE team_invites SET accepted_at=? WHERE id=?", (created_at, invite["id"]))
            actor = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
            self._audit(db, actor, "team.invite.accept", "team_invite", invite["id"], request_id)
        return self.login(invite["email"], str(request["password"]), request_id)

    def update_member_role(self, actor: sqlite3.Row, member_id: str, role: str, request_id: str) -> dict[str, Any]:
        self._require_team_admin(actor, owner_only=True)
        if role not in {"admin", "member"}:
            raise CloudApiError(400, "invalid_role", "Member role must be admin or member")
        with self._lock, self._connect() as db:
            member = db.execute("SELECT * FROM users WHERE id=? AND tenant_id=? AND deleted_at IS NULL", (member_id, actor["tenant_id"])).fetchone()
            if member is None or self._role(member) == "owner":
                raise CloudApiError(404, "member_not_found", "Team member not found")
            db.execute("UPDATE users SET roles_json=? WHERE id=? AND tenant_id=?", (_json([role]), member_id, actor["tenant_id"]))
            self._audit(db, actor, "team.member.role", "user", member_id, request_id)
        return self.list_team_members(actor)

    def remove_team_member(self, actor: sqlite3.Row, member_id: str, request_id: str) -> None:
        self._require_team_admin(actor)
        with self._lock, self._connect() as db:
            member = db.execute("SELECT * FROM users WHERE id=? AND tenant_id=? AND deleted_at IS NULL", (member_id, actor["tenant_id"])).fetchone()
            if member is None or self._role(member) == "owner" or member_id == actor["id"]:
                raise CloudApiError(404, "member_not_found", "Removable team member not found")
            if self._role(actor) == "admin" and self._role(member) != "member":
                raise CloudApiError(403, "permission_denied", "Administrators can remove members only")
            db.execute("DELETE FROM resource_permissions WHERE tenant_id=? AND principal_type='user' AND principal_id=?", (actor["tenant_id"], member_id))
            db.execute("DELETE FROM users WHERE id=? AND tenant_id=?", (member_id, actor["tenant_id"]))
            self._audit(db, actor, "team.member.remove", "user", member_id, request_id)

    def list_resource_permissions(self, actor: sqlite3.Row, resource_type: str, resource_id: str) -> dict[str, Any]:
        self._require_team_admin(actor, owner_only=True)
        if resource_type not in {"library_state", "collection", "graph", "graph_view"} or not resource_id or len(resource_id) > 256:
            raise CloudApiError(400, "invalid_resource", "A supported bounded resource is required")
        with self._connect() as db:
            rows = db.execute("SELECT * FROM resource_permissions WHERE tenant_id=? AND resource_type=? AND resource_id=? ORDER BY principal_type,principal_id", (actor["tenant_id"], resource_type, resource_id)).fetchall()
        permissions = [{"id": row["id"], "resourceType": row["resource_type"], "resourceId": row["resource_id"], "principalType": row["principal_type"], "principalId": row["principal_id"], "permission": row["permission"], "updatedAt": row["updated_at"]} for row in rows]
        return {"protocolVersion": PROTOCOL_VERSION, "resourceType": resource_type, "resourceId": resource_id, "permissions": permissions}

    def set_resource_permission(self, actor: sqlite3.Row, request: dict[str, Any], request_id: str) -> dict[str, Any]:
        validate_resource_permission_mutation(request)
        self._require_team_admin(actor, owner_only=True)
        resource_type, resource_id = str(request["resourceType"]), str(request["resourceId"])
        principal_type, principal_id, permission = str(request["principalType"]), str(request["principalId"]), str(request["permission"])
        if resource_type not in {"library_state", "collection", "graph", "graph_view"} or not resource_id or len(resource_id) > 256 or principal_type not in {"user", "team"} or permission not in {"none", "viewer", "editor"}:
            raise CloudApiError(400, "invalid_permission", "A supported bounded resource, principal, and permission are required")
        with self._lock, self._connect() as db:
            if principal_type == "team":
                valid = principal_id == actor["tenant_id"]
            else:
                valid = db.execute("SELECT 1 FROM users WHERE id=? AND tenant_id=? AND deleted_at IS NULL", (principal_id, actor["tenant_id"])).fetchone() is not None
            if not valid:
                raise CloudApiError(404, "principal_not_found", "Permission principal is outside this tenant")
            if permission == "none":
                db.execute("DELETE FROM resource_permissions WHERE tenant_id=? AND resource_type=? AND resource_id=? AND principal_type=? AND principal_id=?", (actor["tenant_id"], resource_type, resource_id, principal_type, principal_id))
            else:
                permission_id, updated_at = uuid.uuid4().hex, _iso()
                db.execute("INSERT INTO resource_permissions VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(tenant_id,resource_type,resource_id,principal_type,principal_id) DO UPDATE SET permission=excluded.permission,updated_at=excluded.updated_at", (permission_id, actor["tenant_id"], resource_type, resource_id, principal_type, principal_id, permission, updated_at))
            self._audit(db, actor, "permission.update", resource_type, resource_id, request_id)
        return self.list_resource_permissions(actor, resource_type, resource_id)
