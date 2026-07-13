from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from omnilit_qt.shared_protocol import PROTOCOL_VERSION


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


DEFAULT_CATEGORIES = {
    "literature": True,
    "collections": True,
    "graphs": True,
    "views": True,
    "settings": True,
    "annotations": False,
    "pdfs": False,
    "fullText": False,
    "extractions": False,
}


class WorkspaceSyncStore:
    """Persistent local sync journal. It never stores credentials or absolute paths."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._initialize()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA journal_mode=WAL")
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def _initialize(self) -> None:
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS sync_profile(
                    id INTEGER PRIMARY KEY CHECK(id=1), device_id TEXT NOT NULL,
                    cloud_account_id TEXT NOT NULL, cloud_workspace_id TEXT NOT NULL,
                    enabled INTEGER NOT NULL, cursor INTEGER NOT NULL,
                    categories_json TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS outbox(
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT, client_mutation_id TEXT NOT NULL UNIQUE,
                    resource_type TEXT NOT NULL, resource_id TEXT NOT NULL, operation TEXT NOT NULL,
                    base_revision INTEGER NOT NULL, payload_json TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS tombstones(
                    resource_type TEXT NOT NULL, resource_id TEXT NOT NULL, revision INTEGER NOT NULL,
                    deleted_at TEXT NOT NULL, PRIMARY KEY(resource_type,resource_id)
                );
                CREATE TABLE IF NOT EXISTS conflicts(
                    id TEXT PRIMARY KEY, resource_type TEXT NOT NULL, resource_id TEXT NOT NULL,
                    local_json TEXT NOT NULL, cloud_json TEXT NOT NULL, cloud_revision INTEGER NOT NULL,
                    created_at TEXT NOT NULL, resolved_at TEXT, resolution TEXT
                );
            """)
            db.execute(
                "INSERT OR IGNORE INTO sync_profile VALUES(1,?,?,?,?,?,?,?)",
                (uuid.uuid4().hex, "", "", 0, 0, json.dumps(DEFAULT_CATEGORIES, separators=(",", ":")), _now()),
            )

    def preferences(self) -> dict[str, Any]:
        with self._connect() as db:
            row = db.execute("SELECT * FROM sync_profile WHERE id=1").fetchone()
        return {"protocolVersion": PROTOCOL_VERSION, "enabled": bool(row["enabled"]), "categories": json.loads(row["categories_json"]), "updatedAt": row["updated_at"]}

    def update_preferences(self, enabled: bool, categories: dict[str, Any], *, cloud_account_id: str = "", cloud_workspace_id: str = "") -> dict[str, Any]:
        if set(categories) != set(DEFAULT_CATEGORIES) or any(not isinstance(value, bool) for value in categories.values()):
            raise ValueError("Every sync category must be an explicit boolean")
        now = _now()
        with self._lock, self._connect() as db:
            db.execute(
                "UPDATE sync_profile SET enabled=?,categories_json=?,cloud_account_id=?,cloud_workspace_id=?,updated_at=? WHERE id=1",
                (int(enabled), json.dumps(categories, separators=(",", ":")), cloud_account_id[:128], cloud_workspace_id[:128], now),
            )
        return self.preferences()

    def status(self) -> dict[str, Any]:
        with self._connect() as db:
            profile = db.execute("SELECT * FROM sync_profile WHERE id=1").fetchone()
            outbox_count = int(db.execute("SELECT COUNT(*) FROM outbox").fetchone()[0])
            conflict_count = int(db.execute("SELECT COUNT(*) FROM conflicts WHERE resolved_at IS NULL").fetchone()[0])
        return {"protocolVersion": PROTOCOL_VERSION, "enabled": bool(profile["enabled"]), "deviceId": profile["device_id"], "cursor": int(profile["cursor"]), "outboxCount": outbox_count, "conflictCount": conflict_count, "lastSyncAt": profile["updated_at"]}

    def enqueue(self, change: dict[str, Any]) -> dict[str, Any]:
        resource_type = str(change.get("resourceType") or "")
        resource_id = str(change.get("resourceId") or "")
        operation = str(change.get("operation") or "")
        if not resource_type or not resource_id or operation not in {"upsert", "delete"}:
            raise ValueError("Invalid workspace change")
        mutation_id = str(change.get("clientMutationId") or uuid.uuid4().hex)
        payload = change.get("payload") if isinstance(change.get("payload"), dict) else {}
        with self._lock, self._connect() as db:
            db.execute(
                "INSERT OR IGNORE INTO outbox(client_mutation_id,resource_type,resource_id,operation,base_revision,payload_json,created_at) VALUES(?,?,?,?,?,?,?)",
                (mutation_id, resource_type, resource_id, operation, max(0, int(change.get("baseRevision") or 0)), json.dumps(payload, ensure_ascii=False, separators=(",", ":")), _now()),
            )
            if operation == "delete":
                db.execute("INSERT INTO tombstones VALUES(?,?,?,?) ON CONFLICT(resource_type,resource_id) DO UPDATE SET revision=excluded.revision,deleted_at=excluded.deleted_at", (resource_type, resource_id, max(0, int(change.get("baseRevision") or 0)), _now()))
        return {"protocolVersion": PROTOCOL_VERSION, "clientMutationId": mutation_id, "queued": True}

    def batch(self, limit: int = 200) -> dict[str, Any]:
        with self._connect() as db:
            profile = db.execute("SELECT * FROM sync_profile WHERE id=1").fetchone()
            rows = db.execute("SELECT * FROM outbox ORDER BY sequence LIMIT ?", (min(max(1, limit), 500),)).fetchall()
        changes = [{"resourceType": row["resource_type"], "resourceId": row["resource_id"], "operation": row["operation"], "baseRevision": row["base_revision"], "clientMutationId": row["client_mutation_id"], "payload": json.loads(row["payload_json"])} for row in rows]
        return {"protocolVersion": PROTOCOL_VERSION, "deviceId": profile["device_id"], "cursor": int(profile["cursor"]), "changes": changes}

    def apply_result(self, result: dict[str, Any]) -> dict[str, Any]:
        applied_ids = [str(item.get("clientMutationId") or "") for item in result.get("applied", []) if isinstance(item, dict)]
        conflicts = [item for item in result.get("conflicts", []) if isinstance(item, dict)]
        with self._lock, self._connect() as db:
            for mutation_id in applied_ids:
                db.execute("DELETE FROM outbox WHERE client_mutation_id=?", (mutation_id,))
            for item in conflicts:
                pending = db.execute("SELECT payload_json FROM outbox WHERE client_mutation_id=?", (str(item.get("clientMutationId") or ""),)).fetchone()
                db.execute("INSERT OR REPLACE INTO conflicts VALUES(?,?,?,?,?,?,?,?,NULL)", (str(item.get("id") or uuid.uuid4().hex), str(item.get("resourceType") or ""), str(item.get("resourceId") or ""), pending["payload_json"] if pending else "{}", json.dumps(item.get("cloudPayload") or {}, ensure_ascii=False, separators=(",", ":")), int(item.get("cloudRevision") or 0), _now(), None))
            db.execute("UPDATE sync_profile SET cursor=?,updated_at=? WHERE id=1", (max(0, int(result.get("nextCursor") or result.get("cursor") or 0)), _now()))
        return self.status()

    def resolve_conflict(self, conflict_id: str, resolution: str) -> dict[str, Any]:
        if resolution not in {"keep_local", "keep_cloud", "copy_local"}:
            raise ValueError("Invalid conflict resolution")
        with self._lock, self._connect() as db:
            row = db.execute("SELECT * FROM conflicts WHERE id=? AND resolved_at IS NULL", (conflict_id,)).fetchone()
            if row is None:
                raise ValueError("Conflict not found")
            if resolution in {"keep_local", "copy_local"}:
                resource_id = row["resource_id"] if resolution == "keep_local" else f"{row['resource_id']}-copy-{uuid.uuid4().hex[:8]}"
                db.execute("INSERT INTO outbox(client_mutation_id,resource_type,resource_id,operation,base_revision,payload_json,created_at) VALUES(?,?,?,?,?,?,?)", (uuid.uuid4().hex, row["resource_type"], resource_id, "upsert", row["cloud_revision"], row["local_json"], _now()))
            db.execute("UPDATE conflicts SET resolved_at=?,resolution=? WHERE id=?", (_now(), resolution, conflict_id))
        return self.status()
