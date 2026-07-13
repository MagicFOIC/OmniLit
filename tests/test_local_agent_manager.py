from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from omnilit_qt.local_agent_manager import LocalAgentManager
from omnilit_qt.paths import AppPaths


ROOT = Path(__file__).resolve().parents[1]


class LocalAgentManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.paths = AppPaths(ROOT, Path(self.temporary.name))
        self.managers: list[LocalAgentManager] = []

    def tearDown(self) -> None:
        for manager in self.managers:
            manager.shutdown(1)
        self.temporary.cleanup()

    def manager(self, **kwargs) -> LocalAgentManager:
        manager = LocalAgentManager(self.paths, startup_timeout=3, **kwargs)
        self.managers.append(manager)
        return manager

    def test_start_health_version_token_and_shutdown(self) -> None:
        manager = self.manager()
        self.assertTrue(manager.start())
        first_token = manager.access_token
        self.assertGreaterEqual(len(first_token), 24)
        self.assertEqual(manager.status()["status"], "ready")
        self.assertEqual(manager.status()["protocolVersion"], "1.0")
        self.assertNotIn(first_token, repr(manager.status()))
        process_id = manager.process_id
        self.assertIsNotNone(process_id)
        self.assertTrue(manager.shutdown(2))
        self.assertIsNone(manager.process_id)
        self.assertEqual(manager.endpoint, "")
        self.assertEqual(manager.access_token, "")

    def test_ensure_running_restarts_crashed_owned_process_with_new_token(self) -> None:
        manager = self.manager(max_restarts=1)
        self.assertTrue(manager.start())
        old_process = manager._process
        old_token = manager.access_token
        self.assertIsNotNone(old_process)
        old_process.kill()
        old_process.wait(timeout=2)
        self.assertTrue(manager.ensure_running())
        self.assertNotEqual(manager.access_token, old_token)
        self.assertEqual(manager.status()["restartCount"], 1)
        self.assertFalse(manager.restart())
        self.assertEqual(manager.status()["detail"], "Local Agent restart budget exhausted")

    def test_missing_fixed_executable_fails_without_leaking_path_or_shelling(self) -> None:
        missing = self.paths.data_root / "private" / "agent.exe"
        manager = self.manager(executable=missing)
        self.assertFalse(manager.start())
        status = manager.status()
        self.assertEqual(status["status"], "failed")
        self.assertNotIn(str(missing), repr(status))
        self.assertIsNone(manager.process_id)

    def test_command_is_fixed_argument_vector(self) -> None:
        web_root = self.paths.data_root / "web"
        web_root.mkdir()
        (web_root / "index.html").write_text("ok", encoding="utf-8")
        manager = self.manager(web_root=web_root)
        manager._port = 32123
        command = manager._command()
        self.assertIsInstance(command, list)
        self.assertEqual(command[1:3], ["-m", "services.local_agent"])
        self.assertIn("127.0.0.1", command)
        self.assertNotIn("shell", " ".join(command).casefold())
        self.assertEqual(command[-2:], ["--web-root", str(web_root.resolve())])
        self.assertTrue(manager.status()["webAvailable"])

    def test_frozen_build_reuses_signed_desktop_binary_for_agent_mode(self) -> None:
        manager = self.manager()
        manager._port = 32123
        with patch("omnilit_qt.local_agent_manager.sys.frozen", True, create=True), patch("omnilit_qt.local_agent_manager.sys.executable", str(ROOT / "OmniLit.exe")):
            command = manager._command()
        self.assertEqual(command[:2], [str((ROOT / "OmniLit.exe").resolve()), "--local-agent"])
        self.assertEqual(command[2:6], ["--host", "127.0.0.1", "--port", "32123"])

    def test_entrypoint_dispatches_agent_before_importing_qt_app(self) -> None:
        source = (ROOT / "omnilit_qt_app.py").read_text(encoding="utf-8")
        self.assertIn('sys.argv[1] == "--local-agent"', source)
        self.assertGreater(source.index("from omnilit_qt.app import run"), source.index("def _run_desktop"))
        self.assertIn("from services.local_agent.__main__ import main", source)

    def test_qt_app_wires_start_monitor_and_shutdown(self) -> None:
        source = (ROOT / "omnilit_qt" / "app.py").read_text(encoding="utf-8")
        self.assertIn("local_agent = LocalAgentManager(paths, web_root=paths.resource(\"apps\", \"web\", \"dist\"))", source)
        self.assertIn("local_agent.start()", source)
        self.assertIn("local_agent_monitor.timeout.connect(local_agent.ensure_running)", source)
        self.assertIn("app.aboutToQuit.connect(local_agent.shutdown)", source)


if __name__ == "__main__":
    unittest.main()
