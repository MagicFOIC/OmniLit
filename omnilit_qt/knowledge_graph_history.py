from __future__ import annotations

import copy
import time
from dataclasses import dataclass
from typing import Any


@dataclass
class HistoryEntry:
    action: str
    state: dict[str, Any]
    timestamp: float
    coalesce_key: str = ""


class KnowledgeGraphHistory:
    """Bounded undo/redo storage for compact graph-view state."""

    def __init__(self, limit: int = 60, coalesce_window: float = 0.9) -> None:
        self.limit = max(1, int(limit))
        self.coalesce_window = max(0.0, float(coalesce_window))
        self.undo_entries: list[HistoryEntry] = []
        self.redo_entries: list[HistoryEntry] = []

    def reset(self) -> None:
        self.undo_entries.clear()
        self.redo_entries.clear()

    def record(
        self,
        state: dict[str, Any],
        action: str,
        *,
        coalesce_key: str = "",
        now: float | None = None,
    ) -> bool:
        timestamp = time.monotonic() if now is None else float(now)
        if (
            coalesce_key
            and self.undo_entries
            and self.undo_entries[-1].coalesce_key == coalesce_key
            and timestamp - self.undo_entries[-1].timestamp <= self.coalesce_window
        ):
            self.undo_entries[-1].timestamp = timestamp
            self.undo_entries[-1].action = str(action or self.undo_entries[-1].action)
            self.redo_entries.clear()
            return False
        self.undo_entries.append(HistoryEntry(str(action or "change"), copy.deepcopy(state), timestamp, str(coalesce_key or "")))
        if len(self.undo_entries) > self.limit:
            del self.undo_entries[:len(self.undo_entries) - self.limit]
        self.redo_entries.clear()
        return True

    def undo(self, current_state: dict[str, Any], now: float | None = None) -> HistoryEntry | None:
        if not self.undo_entries:
            return None
        entry = self.undo_entries.pop()
        timestamp = time.monotonic() if now is None else float(now)
        self.redo_entries.append(HistoryEntry(entry.action, copy.deepcopy(current_state), timestamp))
        return entry

    def redo(self, current_state: dict[str, Any], now: float | None = None) -> HistoryEntry | None:
        if not self.redo_entries:
            return None
        entry = self.redo_entries.pop()
        timestamp = time.monotonic() if now is None else float(now)
        self.undo_entries.append(HistoryEntry(entry.action, copy.deepcopy(current_state), timestamp))
        if len(self.undo_entries) > self.limit:
            del self.undo_entries[:len(self.undo_entries) - self.limit]
        return entry

    @property
    def can_undo(self) -> bool:
        return bool(self.undo_entries)

    @property
    def can_redo(self) -> bool:
        return bool(self.redo_entries)

    @property
    def undo_action(self) -> str:
        return self.undo_entries[-1].action if self.undo_entries else ""

    @property
    def redo_action(self) -> str:
        return self.redo_entries[-1].action if self.redo_entries else ""
