from __future__ import annotations

import base64
import io
import json
import os
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from omnilit_qt.shared_protocol import PROTOCOL_VERSION
from services.cloud_api import CloudApiService, CloudBackupError, CloudBackupManager, CloudBackupScheduler
from services.cloud_api.__main__ import main as cloud_main


class CloudBackupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.database = self.root / "cloud.sqlite3"
        self.data_key = bytes(range(32))
        self.backup_key = bytes(range(32, 64))
        self.service = CloudApiService(self.database, self.data_key, public_base_url="https://cloud.example")
        self.session = self.service.register("backup-owner@example.com", "correct-horse-battery", "Backup Owner", "Recovery Lab", "register")
        self.actor = self.service.authenticate(self.session["accessToken"])
        graph = json.loads((Path(__file__).parents[1] / "packages" / "shared-schema" / "fixtures" / "shared-graph-v1.json").read_text(encoding="utf-8"))
        self.graph = graph
        self.service.sync_graph(self.actor, {"protocolVersion": PROTOCOL_VERSION, "deviceId": "desktop", "baseCloudRevision": 0, "graph": graph}, "graph-sync")

    def tearDown(self) -> None:
        self.service.shutdown()
        self.temp.cleanup()

    def test_encrypted_backup_round_trip_restores_accounts_sessions_and_graphs(self) -> None:
        manager = CloudBackupManager(self.backup_key)
        info = manager.create_backup(self.database, self.root / "backups", retention=3)
        backup_path = Path(info["path"])
        raw = backup_path.read_bytes()
        self.assertNotIn(b"SQLite format 3", raw)
        self.assertNotIn(b"backup-owner@example.com", raw)
        self.assertNotIn(self.graph["paper"]["title"].encode("utf-8"), raw)
        verified = manager.verify_backup(backup_path)
        self.assertTrue(verified["valid"])
        self.assertGreater(verified["plaintextBytes"], 0)

        restored_database = self.root / "restored" / "cloud.sqlite3"
        restored = manager.restore_backup(backup_path, restored_database)
        self.assertTrue(restored["restored"])
        restored_service = CloudApiService(restored_database, self.data_key, public_base_url="https://cloud.example")
        try:
            actor = restored_service.authenticate(self.session["accessToken"])
            self.assertEqual(restored_service.account(actor)["email"], "backup-owner@example.com")
            self.assertEqual(restored_service.get_cloud_graph(actor, self.graph["recordId"])["nodes"], self.graph["nodes"])
        finally:
            restored_service.shutdown()

    def test_wrong_key_tampering_and_unsafe_restore_are_rejected(self) -> None:
        manager = CloudBackupManager(self.backup_key)
        backup_path = Path(manager.create_backup(self.database, self.root / "backups")["path"])
        with self.assertRaises(CloudBackupError):
            CloudBackupManager(b"w" * 32).verify_backup(backup_path)
        tampered = self.root / "tampered.backup"
        payload = bytearray(backup_path.read_bytes())
        payload[-1] ^= 1
        tampered.write_bytes(payload)
        with self.assertRaises(CloudBackupError):
            manager.verify_backup(tampered)

        existing = self.root / "existing.sqlite3"
        existing.write_bytes(b"existing-database")
        with self.assertRaises(CloudBackupError):
            manager.restore_backup(backup_path, existing)
        result = manager.restore_backup(backup_path, existing, force=True)
        self.assertTrue(Path(result["safetyCopy"]).read_bytes() == b"existing-database")
        self.assertTrue(existing.read_bytes().startswith(b"SQLite format 3"))

    def test_retention_and_automatic_scheduler_keep_a_bounded_backup_set(self) -> None:
        manager = CloudBackupManager(self.backup_key)
        backup_directory = self.root / "scheduled"
        for _ in range(3):
            manager.create_backup(self.database, backup_directory, retention=2)
        self.assertEqual(len(list(backup_directory.glob("omnilit-cloud-*.backup"))), 2)

        scheduler_directory = self.root / "automatic"
        scheduler = CloudBackupScheduler(manager, self.database, scheduler_directory, interval_seconds=0.05, retention=2)
        scheduler.start()
        deadline = time.monotonic() + 2
        while not list(scheduler_directory.glob("omnilit-cloud-*.backup")) and time.monotonic() < deadline:
            time.sleep(0.01)
        scheduler.stop()
        backups = list(scheduler_directory.glob("omnilit-cloud-*.backup"))
        self.assertGreaterEqual(len(backups), 1)
        self.assertLessEqual(len(backups), 2)
        self.assertTrue(manager.verify_backup(backups[0])["valid"])
        status = scheduler.status_snapshot()
        self.assertGreater(status["lastSuccessUnixTime"], 0)
        self.assertEqual(status["consecutiveFailures"], 0)

    def test_scheduler_exposes_failure_state_without_leaking_exception_details(self) -> None:
        class FailingManager:
            def create_backup(self, *_args, **_kwargs):
                raise CloudBackupError("sensitive backend failure")

        scheduler = CloudBackupScheduler(FailingManager(), self.database, self.root / "failing", interval_seconds=0.05)
        with self.assertLogs("omnilit.cloud_api.backup", level="ERROR") as captured:
            scheduler.start()
            deadline = time.monotonic() + 1
            while scheduler.status_snapshot()["consecutiveFailures"] == 0 and time.monotonic() < deadline:
                time.sleep(0.01)
            scheduler.stop()
        status = scheduler.status_snapshot()
        self.assertGreater(status["lastFailureUnixTime"], 0)
        self.assertGreaterEqual(status["consecutiveFailures"], 1)
        self.assertNotIn("sensitive backend failure", "\n".join(captured.output))

    def test_offline_cli_creates_and_verifies_a_backup(self) -> None:
        backup_directory = self.root / "cli-backups"
        environment = {
            "OMNILIT_CLOUD_DATABASE": str(self.database),
            "OMNILIT_CLOUD_BACKUP_DIR": str(backup_directory),
            "OMNILIT_CLOUD_BACKUP_KEY_B64": base64.urlsafe_b64encode(self.backup_key).decode("ascii"),
            "OMNILIT_CLOUD_BACKUP_RETENTION": "2",
        }
        output = io.StringIO()
        with patch.dict(os.environ, environment, clear=True), redirect_stdout(output):
            self.assertEqual(cloud_main(["backup"]), 0)
        created = json.loads(output.getvalue())
        output = io.StringIO()
        with patch.dict(os.environ, environment, clear=True), redirect_stdout(output):
            self.assertEqual(cloud_main(["verify", created["path"]]), 0)
        self.assertTrue(json.loads(output.getvalue())["valid"])

    def test_offline_cli_reads_backup_key_from_a_secret_file(self) -> None:
        key_file = self.root / "backup-key.txt"
        key_file.write_text(base64.urlsafe_b64encode(self.backup_key).decode("ascii") + "\n", encoding="utf-8")
        environment = {
            "OMNILIT_CLOUD_DATABASE": str(self.database),
            "OMNILIT_CLOUD_BACKUP_DIR": str(self.root / "file-key-backups"),
            "OMNILIT_CLOUD_BACKUP_KEY_B64_FILE": str(key_file),
        }
        output = io.StringIO()
        with patch.dict(os.environ, environment, clear=True), redirect_stdout(output):
            self.assertEqual(cloud_main(["backup"]), 0)
        self.assertTrue(Path(json.loads(output.getvalue())["path"]).is_file())


if __name__ == "__main__":
    unittest.main()
