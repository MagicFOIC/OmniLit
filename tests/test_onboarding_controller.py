from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from omnilit_qt.onboarding_controller import WORKDIR_SUBDIRS, OnboardingController
from omnilit_qt.paths import AppPaths
from omnilit_qt.services import AccountStore


class DummyApp:
    version = "9.9.9"


class OnboardingControllerTests(unittest.TestCase):
    def make_controller(self, root: Path) -> tuple[OnboardingController, AccountStore]:
        paths = AppPaths(root, root)
        store = AccountStore(root / "accounts.sqlite3")
        return OnboardingController(DummyApp(), paths, store), store

    def test_first_login_requires_workdir_then_starts_tour(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            controller, store = self.make_controller(Path(temp))

            controller.onAuthenticated("alice")

            self.assertTrue(controller.needsWorkdir)
            self.assertFalse(controller.active)
            self.assertEqual(controller.currentStep["id"], "workdir.setup")

            workdir = Path(temp) / "workspace"
            self.assertTrue(controller.setWorkdir(str(workdir)))

            self.assertFalse(controller.needsWorkdir)
            self.assertTrue(controller.active)
            self.assertEqual(controller.currentStep["id"], "nav.download")
            self.assertEqual(store.setting("onboarding/workdir"), str(workdir.resolve()))
            for name in WORKDIR_SUBDIRS:
                self.assertTrue((workdir / name).is_dir())

    def test_finish_persists_completion_and_last_version(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            controller, store = self.make_controller(root)
            self.assertTrue(controller.setWorkdir(str(root / "workspace")))
            controller.onAuthenticated("alice")

            controller.finish()

            self.assertFalse(controller.active)
            self.assertEqual(store.setting("onboarding/completed/alice"), "1")
            self.assertEqual(store.setting("onboarding/last_version/alice"), "9.9.9")

            restored = OnboardingController(DummyApp(), AppPaths(root, root), store)
            restored.onAuthenticated("alice")
            self.assertFalse(restored.active)
            self.assertFalse(restored.needsWorkdir)

    def test_skip_marks_completed_unless_show_every_login_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            controller, store = self.make_controller(root)
            self.assertTrue(controller.setWorkdir(str(root / "workspace")))
            controller.onAuthenticated("alice")

            controller.skip()
            self.assertEqual(store.setting("onboarding/completed/alice"), "1")
            self.assertFalse(controller.active)

            controller.setShowEveryLogin(True)
            controller.onAuthenticated("alice")
            self.assertTrue(controller.active)
            self.assertEqual(controller.currentStep["id"], "nav.download")

    def test_set_workdir_rejects_file_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            controller, _store = self.make_controller(root)
            blocked = root / "not-a-directory"
            blocked.write_text("content", encoding="utf-8")

            self.assertFalse(controller.setWorkdir(""))
            self.assertFalse(controller.setWorkdir(str(blocked)))
            self.assertEqual(controller.workdir, "")

    def test_login_reprompts_when_saved_workdir_is_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            controller, store = self.make_controller(root)
            blocked = root / "not-a-directory"
            blocked.write_text("content", encoding="utf-8")
            store.set_setting("onboarding/workdir", str(blocked))

            controller.onAuthenticated("alice")

            self.assertTrue(controller.needsWorkdir)
            self.assertFalse(controller.active)


if __name__ == "__main__":
    unittest.main()
