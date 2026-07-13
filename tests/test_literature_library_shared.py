from __future__ import annotations

import unittest
import threading
from pathlib import Path
from tempfile import TemporaryDirectory

from omnilit_qt.literature_library_shared import LibraryStateConflict, LibraryStateStore, project_library_state


class LibraryStateStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.path = Path(self.temporary.name) / "library_state.json"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_versioned_mutations_are_visible_across_store_instances(self) -> None:
        first, second = LibraryStateStore(self.path), LibraryStateStore(self.path)
        initial = first.load()
        self.assertEqual(initial["revision"], 0)
        created, changed = first.mutate("create_collection", expected_revision=0, name="Catalysis")
        self.assertTrue(changed)
        collection_id = next(item["id"] for item in created["projects"] if item["name"] == "Catalysis")
        self.assertEqual(second.load()["revision"], 1)
        favorited, _ = second.mutate("toggle_collection_record", expected_revision=1, collection_id=collection_id, record_id="doi:10.1/example")
        self.assertEqual(favorited["favorites"]["doi:10.1/example"], [collection_id])
        projected = project_library_state(favorited)
        self.assertEqual(next(item for item in projected["collections"] if item["id"] == collection_id)["recordCount"], 1)

    def test_stale_revision_is_an_explicit_conflict(self) -> None:
        store = LibraryStateStore(self.path)
        store.load()
        store.mutate("toggle_compare_record", expected_revision=0, record_id="paper-1")
        with self.assertRaises(LibraryStateConflict):
            store.mutate("toggle_compare_record", expected_revision=0, record_id="paper-2")
        self.assertEqual(store.load()["compare"]["active"], ["paper-1"])

    def test_compare_workspace_is_bounded_and_builtin_collections_are_protected(self) -> None:
        store = LibraryStateStore(self.path)
        state = store.load()
        for index in range(4):
            state, _ = store.mutate("toggle_compare_record", expected_revision=state["revision"], record_id=f"paper-{index}")
        with self.assertRaises(ValueError):
            store.mutate("toggle_compare_record", expected_revision=state["revision"], record_id="paper-5")
        with self.assertRaises(ValueError):
            store.mutate("delete_collection", expected_revision=state["revision"], collection_id="core")

    def test_broken_state_is_backed_up_and_repaired(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("{broken", encoding="utf-8")
        state = LibraryStateStore(self.path).load()
        self.assertTrue(self.path.with_suffix(".json.bak").is_file())
        self.assertEqual(state["schema_version"], 2)
        self.assertIn("favorites", state)

    def test_simultaneous_writers_cannot_silently_overwrite(self) -> None:
        LibraryStateStore(self.path).load()
        barrier = threading.Barrier(2)
        outcomes: list[str] = []

        def write(record_id: str) -> None:
            barrier.wait()
            try:
                LibraryStateStore(self.path).mutate("toggle_compare_record", expected_revision=0, record_id=record_id)
                outcomes.append("saved")
            except LibraryStateConflict:
                outcomes.append("conflict")

        threads = [threading.Thread(target=write, args=(f"paper-{index}",)) for index in range(2)]
        for thread in threads: thread.start()
        for thread in threads: thread.join(timeout=3)
        self.assertCountEqual(outcomes, ["saved", "conflict"])
        self.assertEqual(len(LibraryStateStore(self.path).load()["compare"]["active"]), 1)


if __name__ == "__main__":
    unittest.main()
