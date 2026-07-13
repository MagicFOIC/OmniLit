from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from omnilit_qt.shared_protocol import PROTOCOL_VERSION, validate_task


LOGGER = logging.getLogger("omnilit.local_agent.tasks")
FINAL_STATUSES = {"succeeded", "failed", "cancelled"}
ACTIVE_STATUSES = {"queued", "running", "stopping"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class TaskRegistryError(ValueError):
    def __init__(self, code: str, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


class TaskCancelled(RuntimeError):
    pass


class TaskTimedOut(RuntimeError):
    pass


class TaskContext:
    def __init__(self, registry: "TaskRegistry", task_id: str, cancellation: threading.Event, deadline: float) -> None:
        self.registry = registry
        self.task_id = task_id
        self.cancellation = cancellation
        self.deadline = deadline

    def check_cancelled(self) -> None:
        if self.cancellation.is_set():
            raise TaskCancelled()
        if time.monotonic() >= self.deadline:
            raise TaskTimedOut()

    def report(self, completed: float, total: float, unit: str, message: str = "") -> None:
        self.check_cancelled()
        self.registry._report(self.task_id, completed, total, unit, message)


TaskHandler = Callable[[dict[str, Any], TaskContext], dict[str, Any]]


class TaskRegistry:
    """Bounded task runner with crash recovery and result references."""

    def __init__(self, state_root: Path, handlers: dict[str, TaskHandler], *, max_workers: int = 2, max_pending: int = 32, task_timeout: float = 300.0) -> None:
        self.state_root = Path(state_root).resolve()
        self.result_root = self.state_root / "results"
        self.state_root.mkdir(parents=True, exist_ok=True)
        self.result_root.mkdir(parents=True, exist_ok=True)
        self.handlers = dict(handlers)
        self.max_pending = max(1, int(max_pending))
        self.task_timeout = max(0.01, float(task_timeout))
        self._lock = threading.RLock()
        self._tasks: dict[str, dict[str, Any]] = {}
        self._cancellations: dict[str, threading.Event] = {}
        self._futures: dict[str, Future[None]] = {}
        self._executor = ThreadPoolExecutor(max_workers=max(1, int(max_workers)), thread_name_prefix="omnilit-agent-task")
        self._closed = False
        self._recover()

    @staticmethod
    def _task_id(value: str) -> str:
        try:
            return str(uuid.UUID(str(value)))
        except (ValueError, AttributeError) as exc:
            raise TaskRegistryError("invalid_task_id", "Task id is invalid") from exc

    def _state_path(self, task_id: str) -> Path:
        return self.state_root / f"{self._task_id(task_id)}.json"

    def _result_path(self, task_id: str) -> Path:
        return self.result_root / f"{self._task_id(task_id)}.json"

    @staticmethod
    def _write_json(path: Path, payload: dict[str, Any]) -> None:
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        temporary.replace(path)

    def _persist(self, task_id: str) -> None:
        validate_task(self._tasks[task_id])
        self._write_json(self._state_path(task_id), self._tasks[task_id])

    def _recover(self) -> None:
        for path in self.state_root.glob("*.json"):
            try:
                if path.stat().st_size > 1024 * 1024:
                    continue
                task = json.loads(path.read_text(encoding="utf-8"))
                task_id = self._task_id(str(task.get("id") or ""))
                if not isinstance(task, dict) or task.get("protocolVersion") != PROTOCOL_VERSION:
                    continue
                if task.get("status") in ACTIVE_STATUSES:
                    task["status"] = "failed"
                    task["cancellable"] = False
                    task["message"] = "Local Agent restarted before the task finished"
                    task["finishedAt"] = _now()
                    task["error"] = {"protocolVersion": PROTOCOL_VERSION, "code": "agent_restarted", "message": "Task did not survive Local Agent restart", "retryable": True}
                    self._write_json(path, task)
                self._tasks[task_id] = task
            except (OSError, ValueError, json.JSONDecodeError, AttributeError):
                LOGGER.warning("task_state_recovery_skipped file=%s", path.name)

    def create(self, task_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        selected_type = str(task_type or "")
        if selected_type not in self.handlers:
            raise TaskRegistryError("unsupported_task_type", "Task type is not supported")
        if not isinstance(payload, dict):
            raise TaskRegistryError("invalid_input", "Task input must be an object")
        with self._lock:
            if self._closed:
                raise TaskRegistryError("agent_stopping", "Local Agent is stopping", 503)
            active = sum(1 for task in self._tasks.values() if task.get("status") in ACTIVE_STATUSES)
            if active >= self.max_pending:
                raise TaskRegistryError("task_queue_full", "Local Agent task queue is full", 503)
            task_id = str(uuid.uuid4())
            task = {
                "protocolVersion": PROTOCOL_VERSION,
                "id": task_id,
                "type": selected_type,
                "status": "queued",
                "cancellable": True,
                "progress": {"completed": 0, "total": 1, "unit": "task", "message": "Queued"},
                "message": "Queued",
                "createdAt": _now(),
            }
            cancellation = threading.Event()
            self._tasks[task_id] = task
            self._cancellations[task_id] = cancellation
            self._persist(task_id)
            future = self._executor.submit(self._run, task_id, selected_type, deepcopy(payload), cancellation)
            self._futures[task_id] = future
            future.add_done_callback(lambda completed, key=task_id: self._forget_future(key, completed))
            return deepcopy(task)

    def _forget_future(self, task_id: str, future: Future[None]) -> None:
        with self._lock:
            if self._futures.get(task_id) is future:
                self._futures.pop(task_id, None)

    def _run(self, task_id: str, task_type: str, payload: dict[str, Any], cancellation: threading.Event) -> None:
        context = TaskContext(self, task_id, cancellation, time.monotonic() + self.task_timeout)
        try:
            with self._lock:
                task = self._tasks[task_id]
                if cancellation.is_set():
                    raise TaskCancelled()
                task.update({"status": "running", "message": "Running", "startedAt": _now()})
                task["progress"]["message"] = "Running"
                self._persist(task_id)
            result = self.handlers[task_type](payload, context)
            context.check_cancelled()
            if not isinstance(result, dict):
                raise TypeError("task handler result must be an object")
            self._write_json(self._result_path(task_id), result)
            with self._lock:
                task = self._tasks[task_id]
                total = float(task["progress"].get("total") or 1)
                task["progress"].update({"completed": total, "message": "Succeeded"})
                task.update({"status": "succeeded", "cancellable": False, "message": "Succeeded", "finishedAt": _now(), "resultRef": f"/v1/tasks/{task_id}/result"})
                self._persist(task_id)
        except TaskCancelled:
            with self._lock:
                task = self._tasks[task_id]
                task.update({"status": "cancelled", "cancellable": False, "message": "Cancelled", "finishedAt": _now()})
                task["progress"]["message"] = "Cancelled"
                self._persist(task_id)
        except TaskTimedOut:
            with self._lock:
                task = self._tasks[task_id]
                task.update({"status": "failed", "cancellable": False, "message": "Task timed out", "finishedAt": _now(), "error": {"protocolVersion": PROTOCOL_VERSION, "code": "task_timeout", "message": "Local Agent task timed out", "retryable": True}})
                task["progress"]["message"] = "Timed out"
                self._persist(task_id)
        except Exception as exc:
            LOGGER.exception("local_agent_task_failed task_id=%s type=%s", task_id, task_type)
            with self._lock:
                task = self._tasks[task_id]
                task.update({"status": "failed", "cancellable": False, "message": "Task failed", "finishedAt": _now(), "error": {"protocolVersion": PROTOCOL_VERSION, "code": "task_failed", "message": "Local Agent task failed", "retryable": False}})
                task["progress"]["message"] = "Failed"
                self._persist(task_id)
        finally:
            with self._lock:
                self._cancellations.pop(task_id, None)

    def _report(self, task_id: str, completed: float, total: float, unit: str, message: str) -> None:
        with self._lock:
            task = self._tasks[task_id]
            safe_total = max(0.0, float(total))
            safe_completed = max(0.0, min(float(completed), safe_total if safe_total else float(completed)))
            task["progress"] = {"completed": safe_completed, "total": safe_total, "unit": str(unit or "items")[:64], "message": str(message or "")[:512]}
            task["message"] = str(message or "Running")[:512]
            self._persist(task_id)

    def get(self, task_id: str) -> dict[str, Any]:
        task_id = self._task_id(task_id)
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                raise TaskRegistryError("task_not_found", "Task not found", 404)
            return deepcopy(task)

    def result(self, task_id: str) -> dict[str, Any]:
        task = self.get(task_id)
        if task.get("status") != "succeeded":
            raise TaskRegistryError("task_result_unavailable", "Task result is not available", 409)
        try:
            result = json.loads(self._result_path(task_id).read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise TaskRegistryError("task_result_missing", "Task result is missing", 410) from exc
        if not isinstance(result, dict):
            raise TaskRegistryError("task_result_invalid", "Task result is invalid", 500)
        return result

    def cancel(self, task_id: str) -> dict[str, Any]:
        task_id = self._task_id(task_id)
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                raise TaskRegistryError("task_not_found", "Task not found", 404)
            if task.get("status") in FINAL_STATUSES:
                return deepcopy(task)
            cancellation = self._cancellations.get(task_id)
            if cancellation is not None:
                cancellation.set()
            future = self._futures.get(task_id)
            if task.get("status") == "queued" and future is not None and future.cancel():
                task.update({"status": "cancelled", "cancellable": False, "message": "Cancelled", "finishedAt": _now()})
            else:
                task.update({"status": "stopping", "cancellable": False, "message": "Stopping"})
            task["progress"]["message"] = task["message"]
            self._persist(task_id)
            return deepcopy(task)

    def shutdown(self, wait: bool = True) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            for cancellation in self._cancellations.values():
                cancellation.set()
        self._executor.shutdown(wait=wait, cancel_futures=True)
