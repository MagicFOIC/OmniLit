from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from services.local_agent.sync_store import DEFAULT_CATEGORIES, WorkspaceSyncStore


class WorkspaceSyncStoreTests(unittest.TestCase):
    def test_sync_is_opt_in_and_outbox_survives_restart(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sync.sqlite3"
            store = WorkspaceSyncStore(path)
            self.assertFalse(store.preferences()["enabled"])
            store.update_preferences(True, dict(DEFAULT_CATEGORIES), cloud_account_id="account-one", cloud_workspace_id="workspace-one")
            queued = store.enqueue({"resourceType": "literature_record", "resourceId": "paper-1", "operation": "upsert", "baseRevision": 0, "clientMutationId": "mutation-one", "payload": {"title": "Local"}})
            self.assertTrue(queued["queued"])
            restarted = WorkspaceSyncStore(path)
            batch = restarted.batch()
            self.assertEqual((batch["changes"][0]["payload"]["title"], restarted.status()["outboxCount"]), ("Local", 1))
            restarted.apply_result({"nextCursor": 4, "applied": [{"clientMutationId": "mutation-one"}], "conflicts": []})
            self.assertEqual((restarted.status()["cursor"], restarted.status()["outboxCount"]), (4, 0))

    def test_conflict_can_keep_local_or_copy_without_overwriting_cloud(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = WorkspaceSyncStore(Path(directory) / "sync.sqlite3")
            store.enqueue({"resourceType": "literature_record", "resourceId": "paper-1", "operation": "upsert", "baseRevision": 1, "clientMutationId": "mutation-conflict", "payload": {"title": "Local"}})
            store.apply_result({"nextCursor": 3, "applied": [], "conflicts": [{"id": "conflict-one", "clientMutationId": "mutation-conflict", "resourceType": "literature_record", "resourceId": "paper-1", "cloudRevision": 2, "cloudPayload": {"title": "Cloud"}}]})
            self.assertEqual(store.status()["conflictCount"], 1)
            status = store.resolve_conflict("conflict-one", "copy_local")
            self.assertEqual(status["conflictCount"], 0)
            self.assertEqual(len(store.batch()["changes"]), 2)
            copied = next(change for change in store.batch()["changes"] if change["resourceId"] != "paper-1")
            self.assertEqual((copied["baseRevision"], copied["payload"]["title"]), (2, "Local"))

    def test_delete_creates_tombstone_and_sensitive_binding_is_not_exposed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = WorkspaceSyncStore(Path(directory) / "sync.sqlite3")
            store.update_preferences(False, dict(DEFAULT_CATEGORIES), cloud_account_id="account-secret", cloud_workspace_id="workspace-secret")
            store.enqueue({"resourceType": "graph", "resourceId": "graph-one", "operation": "delete", "baseRevision": 5, "clientMutationId": "delete-one"})
            self.assertEqual(store.batch()["changes"][0]["operation"], "delete")
            self.assertNotIn("cloudAccountId", store.status())
            self.assertNotIn("cloudWorkspaceId", store.preferences())


if __name__ == "__main__":
    unittest.main()
