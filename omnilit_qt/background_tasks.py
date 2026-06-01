from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


class ManagedWorker:
    """Run one background task in a tracked non-daemon thread."""

    def __init__(
        self,
        *,
        name: str,
        target: Callable[[], None],
        state_path: Path,
        cancel_event: threading.Event | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.name = name
        self._target = target
        self._state_path = state_path
        self._cancel_event = cancel_event or threading.Event()
        self._metadata = dict(metadata or {})
        self._lock = threading.Lock()
        self._started_at = ""
        self._status = "created"
        self._thread = threading.Thread(target=self._run, name=name, daemon=False)

    @property
    def cancel_event(self) -> threading.Event:
        return self._cancel_event

    @property
    def daemon(self) -> bool:
        return self._thread.daemon

    def is_alive(self) -> bool:
        return self._thread.is_alive()

    def start(self) -> None:
        self._started_at = _timestamp()
        self.update_state("running")
        self._thread.start()

    def request_cancel(self) -> None:
        self._cancel_event.set()
        if self.is_alive():
            self.update_state("stopping")

    def join(self, timeout: float | None = None) -> bool:
        if self._thread.ident is None:
            return True
        if threading.current_thread() is self._thread:
            return False
        self._thread.join(timeout)
        return not self._thread.is_alive()

    def update_state(self, status: str, *, detail: str = "") -> None:
        with self._lock:
            self._status = status
            state = {
                "name": self.name,
                "status": status,
                "updated_at": _timestamp(),
                "started_at": self._started_at,
                "cancellation_requested": self._cancel_event.is_set(),
                "detail": detail,
                "metadata": self._metadata,
            }
            _atomic_write_json(self._state_path, state)

    def _run(self) -> None:
        try:
            self._target()
        except BaseException as exc:
            self.update_state("failed", detail=f"{type(exc).__name__}: {exc}")
            raise
        finally:
            if self._status in {"running", "stopping"}:
                final_status = "cancelled" if self._cancel_event.is_set() else "completed"
                self.update_state(final_status)


def shutdown_workers(workers: list[ManagedWorker | None], timeout: float = 15.0) -> bool:
    """Request cancellation and wait for tracked workers before app exit."""
    active = [worker for worker in workers if worker is not None and worker.is_alive()]
    for worker in active:
        worker.request_cancel()
    remaining = max(0.0, timeout)
    for worker in active:
        before = time.monotonic()
        worker.join(remaining)
        elapsed = time.monotonic() - before
        remaining = max(0.0, remaining - elapsed)
    return all(not worker.is_alive() for worker in active)
