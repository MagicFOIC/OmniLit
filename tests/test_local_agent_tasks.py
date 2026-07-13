from __future__ import annotations

import json
import threading
import time
import unittest
import uuid
from pathlib import Path
from tempfile import TemporaryDirectory

from services.local_agent import TaskRegistry, TaskRegistryError


class LocalAgentTaskRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.root = Path(self.temporary.name) / "tasks"
        self.registries: list[TaskRegistry] = []

    def tearDown(self) -> None:
        for registry in self.registries:
            registry.shutdown()
        self.temporary.cleanup()

    def registry(self, handlers, **kwargs) -> TaskRegistry:
        registry = TaskRegistry(self.root, handlers, **kwargs)
        self.registries.append(registry)
        return registry

    @staticmethod
    def wait_final(registry: TaskRegistry, task_id: str, timeout: float = 3) -> dict:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            task = registry.get(task_id)
            if task["status"] in {"succeeded", "failed", "cancelled"}:
                return task
            time.sleep(0.01)
        raise AssertionError("task did not finish")

    def test_success_progress_persistence_and_result_reference(self) -> None:
        def handler(payload, context):
            context.report(1, 2, "records", "Half way")
            context.report(2, 2, "records", "Done")
            return {"value": payload["value"] * 2}

        registry = self.registry({"test.double": handler})
        created = registry.create("test.double", {"value": 21})
        finished = self.wait_final(registry, created["id"])
        self.assertEqual(finished["status"], "succeeded")
        self.assertEqual(finished["progress"]["completed"], 2)
        self.assertEqual(finished["resultRef"], f"/v1/tasks/{created['id']}/result")
        self.assertEqual(registry.result(created["id"]), {"value": 42})
        persisted = json.loads((self.root / f"{created['id']}.json").read_text(encoding="utf-8"))
        self.assertEqual(persisted["status"], "succeeded")

    def test_running_task_can_be_cancelled(self) -> None:
        started = threading.Event()

        def handler(_payload, context):
            started.set()
            for index in range(500):
                context.report(index, 500, "items", "Working")
                time.sleep(0.002)
            return {"unexpected": True}

        registry = self.registry({"test.slow": handler})
        created = registry.create("test.slow", {})
        self.assertTrue(started.wait(1))
        stopping = registry.cancel(created["id"])
        self.assertIn(stopping["status"], {"stopping", "cancelled"})
        finished = self.wait_final(registry, created["id"])
        self.assertEqual(finished["status"], "cancelled")
        self.assertFalse(finished["cancellable"])
        with self.assertRaises(TaskRegistryError) as result_error:
            registry.result(created["id"])
        self.assertEqual(result_error.exception.code, "task_result_unavailable")

    def test_task_type_and_queue_are_bounded(self) -> None:
        release = threading.Event()

        def blocked(_payload, context):
            while not release.wait(0.01):
                context.check_cancelled()
            return {}

        registry = self.registry({"test.blocked": blocked}, max_workers=1, max_pending=1)
        with self.assertRaises(TaskRegistryError) as unsupported:
            registry.create("shell.exec", {})
        self.assertEqual(unsupported.exception.code, "unsupported_task_type")
        first = registry.create("test.blocked", {})
        with self.assertRaises(TaskRegistryError) as full:
            registry.create("test.blocked", {})
        self.assertEqual(full.exception.code, "task_queue_full")
        release.set()
        self.assertEqual(self.wait_final(registry, first["id"])["status"], "succeeded")

    def test_incomplete_persisted_task_is_explicitly_failed_after_restart(self) -> None:
        self.root.mkdir(parents=True)
        task_id = str(uuid.uuid4())
        (self.root / f"{task_id}.json").write_text(json.dumps({
            "protocolVersion": "1.0", "id": task_id, "type": "graph.audit", "status": "running", "cancellable": True,
            "progress": {"completed": 4, "total": 10, "unit": "elements"}, "createdAt": "2026-07-13T00:00:00Z"
        }), encoding="utf-8")
        registry = self.registry({})
        recovered = registry.get(task_id)
        self.assertEqual(recovered["status"], "failed")
        self.assertEqual(recovered["error"]["code"], "agent_restarted")
        self.assertTrue(recovered["error"]["retryable"])

    def test_controlled_task_timeout_is_explicit_and_retryable(self) -> None:
        def handler(_payload, context):
            while True:
                time.sleep(0.005)
                context.check_cancelled()

        registry = self.registry({"test.timeout": handler}, task_timeout=0.02)
        task = registry.create("test.timeout", {})
        finished = self.wait_final(registry, task["id"])
        self.assertEqual(finished["status"], "failed")
        self.assertEqual(finished["error"]["code"], "task_timeout")
        self.assertTrue(finished["error"]["retryable"])


if __name__ == "__main__":
    unittest.main()
