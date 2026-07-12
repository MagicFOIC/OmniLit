from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from omnilit_qt.paths import AppPaths
from omnilit_qt.services import AccountStore

try:
    from omnilit_qt.onboarding_controller import WORKDIR_SUBDIRS, OnboardingController
except ModuleNotFoundError:  # pragma: no cover - depends on local Qt runtime.
    WORKDIR_SUBDIRS = ()
    OnboardingController = None


class DummyApp:
    version = "9.9.9"


@unittest.skipUnless(OnboardingController is not None, "PySide6 is not installed in this environment")
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

    def test_tour_steps_follow_workspace_layout_order(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            controller, _store = self.make_controller(Path(temp))

            step_ids = [step["id"] for step in controller.steps]

            self.assertEqual(
                step_ids,
                [
                    "workdir.setup",
                    "nav.download",
                    "nav.library",
                    "nav.extract",
                    "nav.translate",
                    "account.avatar",
                    "account.language",
                    "account.appearance",
                    "account.update",
                    "system.settings",
                ],
            )
            self.assertEqual(controller.steps[0]["targetId"], "workdir.setup")
            self.assertEqual(controller.steps[-1]["targetId"], "system.prompt_settings")
            self.assertEqual(controller.steps[-1]["drawerPage"], 6)

    def test_settings_workdir_save_does_not_start_tour(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            controller, store = self.make_controller(root)

            controller.onAuthenticated("alice")
            self.assertTrue(controller.needsWorkdir)
            self.assertFalse(controller.active)

            workdir = root / "workspace"
            self.assertTrue(controller.saveWorkdirPreference(str(workdir)))

            self.assertFalse(controller.needsWorkdir)
            self.assertFalse(controller.active)
            self.assertEqual(controller.currentStep["id"], "workdir.setup")
            self.assertEqual(store.setting("onboarding/workdir"), str(workdir.resolve()))

    def test_saving_workdir_rebases_download_output_dir(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            controller, store = self.make_controller(root)
            store.set_setting("download_form_config", json.dumps({"outputDir": str(root / "Download"), "keywords": "battery"}))

            workdir = root / "workspace"
            self.assertTrue(controller.saveWorkdirPreference(str(workdir)))

            settings = json.loads(store.setting("download_form_config"))
            self.assertEqual(settings["outputDir"], str((workdir / "data" / "downloads").resolve()))
            self.assertEqual(settings["keywords"], "battery")

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
