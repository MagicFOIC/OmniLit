from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import secrets
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


LOGGER = logging.getLogger("omnilit.cloud_api.backup")
MAGIC = b"OMNILIT-CLOUD-BACKUP\x00\x01"
MAX_HEADER_BYTES = 64 * 1024


class CloudBackupError(RuntimeError):
    pass


def _iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class CloudBackupManager:
    """Creates encrypted, consistent SQLite snapshots and restores them offline."""

    def __init__(self, backup_key: bytes) -> None:
        if len(backup_key) != 32:
            raise ValueError("Cloud backup key must contain exactly 32 bytes")
        self._cipher = AESGCM(backup_key)

    @staticmethod
    def _database_bytes(database_path: Path) -> bytes:
        database_path = Path(database_path)
        if not database_path.is_file():
            raise CloudBackupError("Cloud database does not exist")
        source = sqlite3.connect(f"{database_path.resolve().as_uri()}?mode=ro", uri=True, timeout=5)
        snapshot = sqlite3.connect(":memory:")
        try:
            source.backup(snapshot)
            snapshot.execute("PRAGMA journal_mode=MEMORY")
            integrity = snapshot.execute("PRAGMA integrity_check").fetchone()
            if integrity is None or integrity[0] != "ok":
                raise CloudBackupError("Cloud database failed integrity_check")
            payload = bytearray(snapshot.serialize())
            if payload[:16] != b"SQLite format 3\x00" or len(payload) < 20:
                raise CloudBackupError("Cloud database snapshot format is invalid")
            # sqlite3_backup preserves the source WAL header flags even though the
            # destination is now a self-contained snapshot. Normalize the copy to
            # rollback-journal format so deserialize/offline restore never seeks a
            # stale sidecar file.
            payload[18] = 1
            payload[19] = 1
            return bytes(payload)
        finally:
            snapshot.close()
            source.close()

    @staticmethod
    def _validate_database_bytes(payload: bytes) -> None:
        database = sqlite3.connect(":memory:")
        try:
            database.deserialize(payload)
            integrity = database.execute("PRAGMA integrity_check").fetchone()
            if integrity is None or integrity[0] != "ok":
                raise CloudBackupError("Backup database failed integrity_check")
        except sqlite3.DatabaseError as exc:
            raise CloudBackupError("Backup does not contain a valid SQLite database") from exc
        finally:
            database.close()

    def _encode(self, database_bytes: bytes, created_at: str) -> bytes:
        nonce = secrets.token_bytes(12)
        header = json.dumps({
            "formatVersion": 1,
            "createdAt": created_at,
            "plaintextBytes": len(database_bytes),
            "plaintextSha256": hashlib.sha256(database_bytes).hexdigest(),
            "nonce": base64.urlsafe_b64encode(nonce).decode("ascii"),
        }, separators=(",", ":"), sort_keys=True).encode("utf-8")
        ciphertext = self._cipher.encrypt(nonce, database_bytes, MAGIC + header)
        return MAGIC + len(header).to_bytes(4, "big") + header + ciphertext

    def _decode(self, backup_path: Path) -> tuple[dict[str, Any], bytes]:
        try:
            blob = Path(backup_path).read_bytes()
        except OSError as exc:
            raise CloudBackupError("Backup file cannot be read") from exc
        prefix = len(MAGIC)
        if len(blob) < prefix + 4 or blob[:prefix] != MAGIC:
            raise CloudBackupError("Backup format is not recognized")
        header_length = int.from_bytes(blob[prefix:prefix + 4], "big")
        if header_length <= 0 or header_length > MAX_HEADER_BYTES or len(blob) <= prefix + 4 + header_length:
            raise CloudBackupError("Backup header is invalid")
        header_bytes = blob[prefix + 4:prefix + 4 + header_length]
        try:
            header = json.loads(header_bytes)
            nonce = base64.urlsafe_b64decode(header["nonce"])
            expected_size = int(header["plaintextBytes"])
            expected_hash = str(header["plaintextSha256"])
            if header.get("formatVersion") != 1 or len(nonce) != 12 or expected_size < 0:
                raise ValueError("invalid backup metadata")
            plaintext = self._cipher.decrypt(nonce, blob[prefix + 4 + header_length:], MAGIC + header_bytes)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise CloudBackupError("Backup header is invalid") from exc
        except Exception as exc:
            raise CloudBackupError("Backup authentication failed") from exc
        if len(plaintext) != expected_size or not secrets.compare_digest(hashlib.sha256(plaintext).hexdigest(), expected_hash):
            raise CloudBackupError("Backup checksum does not match")
        self._validate_database_bytes(plaintext)
        return header, plaintext

    def create_backup(self, database_path: Path, backup_directory: Path, *, retention: int = 14) -> dict[str, Any]:
        backup_directory = Path(backup_directory)
        backup_directory.mkdir(parents=True, exist_ok=True)
        database_bytes = self._database_bytes(database_path)
        created_at = _iso()
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        target = backup_directory / f"omnilit-cloud-{timestamp}-{secrets.token_hex(4)}.backup"
        temporary = backup_directory / f".{target.name}.{secrets.token_hex(4)}.tmp"
        blob = self._encode(database_bytes, created_at)
        try:
            with temporary.open("xb") as stream:
                stream.write(blob)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
        finally:
            if temporary.exists():
                temporary.unlink()
        deleted = self.prune_backups(backup_directory, retention=max(1, int(retention)))
        result = {"formatVersion": 1, "createdAt": created_at, "path": str(target.resolve()), "encryptedBytes": len(blob), "plaintextBytes": len(database_bytes), "pruned": deleted}
        LOGGER.info(json.dumps({"event": "cloud_backup_created", "createdAt": created_at, "encryptedBytes": len(blob), "pruned": deleted}, separators=(",", ":")))
        return result

    @staticmethod
    def prune_backups(backup_directory: Path, *, retention: int) -> int:
        files = sorted(Path(backup_directory).glob("omnilit-cloud-*.backup"), key=lambda item: item.stat().st_mtime_ns, reverse=True)
        deleted = 0
        for path in files[max(1, int(retention)):]:
            path.unlink()
            deleted += 1
        return deleted

    def verify_backup(self, backup_path: Path) -> dict[str, Any]:
        header, plaintext = self._decode(backup_path)
        return {"formatVersion": 1, "createdAt": header["createdAt"], "plaintextBytes": len(plaintext), "plaintextSha256": header["plaintextSha256"], "valid": True}

    def restore_backup(self, backup_path: Path, target_database: Path, *, force: bool = False) -> dict[str, Any]:
        header, plaintext = self._decode(backup_path)
        target = Path(target_database)
        target.parent.mkdir(parents=True, exist_ok=True)
        for suffix in ("-wal", "-shm"):
            if Path(f"{target}{suffix}").exists():
                raise CloudBackupError("Target has SQLite sidecar files; stop the service and checkpoint it before restore")
        if target.exists() and not force:
            raise CloudBackupError("Target database already exists; offline restore requires --force")
        temporary = target.parent / f".{target.name}.{secrets.token_hex(4)}.restore.tmp"
        safety_copy: Path | None = None
        source = sqlite3.connect(":memory:")
        destination: sqlite3.Connection | None = None
        try:
            source.deserialize(plaintext)
            destination = sqlite3.connect(temporary)
            source.backup(destination)
            destination.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            integrity = destination.execute("PRAGMA integrity_check").fetchone()
            if integrity is None or integrity[0] != "ok":
                raise CloudBackupError("Restored database failed integrity_check")
            destination.close()
            destination = None
            with temporary.open("rb+") as stream:
                os.fsync(stream.fileno())
            if target.exists():
                timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
                safety_copy = target.with_name(f"{target.name}.pre-restore-{timestamp}-{secrets.token_hex(4)}")
                os.replace(target, safety_copy)
            try:
                os.replace(temporary, target)
            except BaseException:
                if safety_copy is not None and safety_copy.exists() and not target.exists():
                    os.replace(safety_copy, target)
                raise
        except OSError as exc:
            raise CloudBackupError("Backup restore could not replace the target database") from exc
        finally:
            if destination is not None:
                destination.close()
            source.close()
            if temporary.exists():
                temporary.unlink()
        result = {"formatVersion": 1, "createdAt": header["createdAt"], "target": str(target.resolve()), "safetyCopy": str(safety_copy.resolve()) if safety_copy else "", "restored": True}
        LOGGER.info(json.dumps({"event": "cloud_backup_restored", "createdAt": header["createdAt"], "safetyCopyCreated": safety_copy is not None}, separators=(",", ":")))
        return result


class CloudBackupScheduler:
    def __init__(self, manager: CloudBackupManager, database_path: Path, backup_directory: Path, *, interval_seconds: float = 86400, retention: int = 14) -> None:
        self.manager = manager
        self.database_path = Path(database_path)
        self.backup_directory = Path(backup_directory)
        self.interval_seconds = max(0.05, float(interval_seconds))
        self.retention = max(1, int(retention))
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._status_lock = threading.Lock()
        self._last_success = 0.0
        self._last_failure = 0.0
        self._consecutive_failures = 0

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="omnilit-cloud-backup", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.manager.create_backup(self.database_path, self.backup_directory, retention=self.retention)
            except Exception as exc:
                with self._status_lock:
                    self._last_failure = time.time()
                    self._consecutive_failures += 1
                LOGGER.error(json.dumps({"event": "cloud_backup_failed", "errorType": type(exc).__name__}, separators=(",", ":")))
            else:
                with self._status_lock:
                    self._last_success = time.time()
                    self._consecutive_failures = 0
            if self._stop.wait(self.interval_seconds):
                return

    def stop(self, timeout: float = 30.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=max(0.0, timeout))
            if self._thread.is_alive():
                raise CloudBackupError("Cloud backup worker did not stop before timeout")
            self._thread = None

    def status_snapshot(self) -> dict[str, float | int]:
        with self._status_lock:
            return {
                "lastSuccessUnixTime": self._last_success,
                "lastFailureUnixTime": self._last_failure,
                "consecutiveFailures": self._consecutive_failures,
            }
