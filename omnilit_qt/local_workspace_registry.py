from __future__ import annotations

import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class LocalWorkspaceRegistry:
    """Local-only mapping between desktop profiles, workspace paths, and optional cloud accounts."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS local_profiles(
                    id TEXT PRIMARY KEY, display_name TEXT NOT NULL, workspace_path TEXT NOT NULL UNIQUE,
                    cloud_account_id TEXT NOT NULL, cloud_base_url TEXT NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
            """)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def _project(row: sqlite3.Row) -> dict[str, str]:
        return {"id": row["id"], "displayName": row["display_name"], "workspacePath": row["workspace_path"], "cloudAccountId": row["cloud_account_id"], "cloudBaseUrl": row["cloud_base_url"], "createdAt": row["created_at"], "updatedAt": row["updated_at"]}

    def profiles(self) -> list[dict[str, str]]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM local_profiles ORDER BY created_at,id").fetchall()
        return [self._project(row) for row in rows]

    def add(self, display_name: str, workspace_path: Path, *, cloud_account_id: str = "", cloud_base_url: str = "") -> dict[str, str]:
        resolved = str(Path(workspace_path).expanduser().resolve())
        name = display_name.strip()
        if not name:
            raise ValueError("Profile display name is required")
        profile_id, now = uuid.uuid4().hex, _now()
        try:
            with self._lock, self._connect() as db:
                db.execute("INSERT INTO local_profiles VALUES(?,?,?,?,?,?,?)", (profile_id, name[:120], resolved, cloud_account_id[:128], cloud_base_url[:512], now, now))
                row = db.execute("SELECT * FROM local_profiles WHERE id=?", (profile_id,)).fetchone()
        except sqlite3.IntegrityError as exc:
            raise ValueError("This workspace path already belongs to another local profile") from exc
        return self._project(row)

    def bind_cloud_account(self, profile_id: str, cloud_account_id: str, cloud_base_url: str) -> dict[str, str]:
        with self._lock, self._connect() as db:
            db.execute("UPDATE local_profiles SET cloud_account_id=?,cloud_base_url=?,updated_at=? WHERE id=?", (cloud_account_id[:128], cloud_base_url[:512], _now(), profile_id))
            row = db.execute("SELECT * FROM local_profiles WHERE id=?", (profile_id,)).fetchone()
        if row is None:
            raise ValueError("Local profile not found")
        return self._project(row)
