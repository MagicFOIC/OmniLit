from __future__ import annotations

import unittest

from omnilit_qt.knowledge_graph_history import KnowledgeGraphHistory


class KnowledgeGraphHistoryTests(unittest.TestCase):
    def test_undo_redo_round_trip_and_new_change_clears_redo(self) -> None:
        history = KnowledgeGraphHistory()
        history.record({"value": 0}, "first", now=1)
        history.record({"value": 1}, "second", now=2)

        entry = history.undo({"value": 2}, now=3)
        self.assertEqual((entry.action, entry.state), ("second", {"value": 1}))
        redone = history.redo({"value": 1}, now=4)
        self.assertEqual(redone.state, {"value": 2})
        history.undo({"value": 2}, now=5)
        history.record({"value": 1}, "replacement", now=6)
        self.assertFalse(history.can_redo)

    def test_continuous_search_is_coalesced_to_first_before_state(self) -> None:
        history = KnowledgeGraphHistory(coalesce_window=1.0)
        history.record({"search": ""}, "search", coalesce_key="search", now=1.0)
        history.record({"search": "g"}, "search", coalesce_key="search", now=1.2)
        history.record({"search": "gr"}, "search", coalesce_key="search", now=1.4)

        self.assertEqual(len(history.undo_entries), 1)
        self.assertEqual(history.undo_entries[0].state, {"search": ""})
        history.record({"search": "graph"}, "search", coalesce_key="search", now=3.0)
        self.assertEqual(len(history.undo_entries), 2)

    def test_history_is_bounded_and_deep_copies_state(self) -> None:
        history = KnowledgeGraphHistory(limit=3)
        state = {"nodes": ["a"]}
        history.record(state, "one", now=1)
        state["nodes"].append("mutated")
        history.record({"value": 2}, "two", now=2)
        self.assertEqual(history.undo_entries[0].state["nodes"], ["a"])
        history.record({"value": 3}, "three", now=3)
        history.record({"value": 4}, "four", now=4)

        self.assertEqual([entry.action for entry in history.undo_entries], ["two", "three", "four"])


if __name__ == "__main__":
    unittest.main()
