from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Property, Signal, Slot
from PySide6.QtWidgets import QFileDialog

from .app_controller import AppController
from .paths import AppPaths
from .services import AccountStore, WORKDIR_SETTING, as_bool, update_download_form_output_dir
SHOW_EVERY_LOGIN_SETTING = "onboarding/show_every_login"
WORKDIR_SUBDIRS = ("config", "data", "cache", "runtime", "reports")


class OnboardingController(QObject):
    changed = Signal()

    def __init__(self, app: AppController, paths: AppPaths, store: AccountStore):
        super().__init__()
        self.app = app
        self.paths = paths
        self.store = store
        self._active = False
        self._needs_workdir = False
        self._username = ""
        self._step_index = 0
        self._workdir = self.store.setting(WORKDIR_SETTING, "")
        self._show_every_login = as_bool(self.store.setting(SHOW_EVERY_LOGIN_SETTING), False)
        self._steps = [
            {
                "id": "workdir.setup",
                "titleKey": "onboarding_workdir_title",
                "bodyKey": "onboarding_workdir_body",
                "targetId": "workdir.setup",
                "pageIndex": -1,
                "preferPlacement": "center",
            },
            {
                "id": "nav.download",
                "titleKey": "onboarding_download_title",
                "bodyKey": "onboarding_download_body",
                "targetId": "nav.download",
                "pageIndex": 0,
                "preferPlacement": "right",
            },
            {
                "id": "nav.library",
                "titleKey": "onboarding_library_title",
                "bodyKey": "onboarding_library_body",
                "targetId": "nav.library",
                "pageIndex": 1,
                "preferPlacement": "right",
            },
            {
                "id": "nav.extract",
                "titleKey": "onboarding_extract_title",
                "bodyKey": "onboarding_extract_body",
                "targetId": "nav.extract",
                "pageIndex": 1,
                "preferPlacement": "left",
            },
            {
                "id": "nav.translate",
                "titleKey": "onboarding_translate_title",
                "bodyKey": "onboarding_translate_body",
                "targetId": "nav.translate",
                "pageIndex": 2,
                "preferPlacement": "right",
            },
            {
                "id": "account.avatar",
                "titleKey": "onboarding_account_title",
                "bodyKey": "onboarding_account_body",
                "targetId": "account.avatar",
                "pageIndex": -1,
                "preferPlacement": "right",
            },
            {
                "id": "account.language",
                "titleKey": "onboarding_language_title",
                "bodyKey": "onboarding_language_body",
                "targetId": "account.language",
                "pageIndex": -1,
                "drawerPage": 0,
                "preferPlacement": "left",
            },
            {
                "id": "account.appearance",
                "titleKey": "onboarding_appearance_title",
                "bodyKey": "onboarding_appearance_body",
                "targetId": "account.appearance",
                "pageIndex": -1,
                "drawerPage": 0,
                "preferPlacement": "left",
            },
            {
                "id": "account.update",
                "titleKey": "onboarding_update_title",
                "bodyKey": "onboarding_update_body",
                "targetId": "account.update",
                "pageIndex": -1,
                "drawerPage": 0,
                "preferPlacement": "left",
            },
            {
                "id": "system.settings",
                "titleKey": "onboarding_system_settings_title",
                "bodyKey": "onboarding_system_settings_body",
                "targetId": "system.prompt_settings",
                "pageIndex": -1,
                "drawerPage": 6,
                "preferPlacement": "left",
            },
        ]

    def _completed_key(self, username: str | None = None) -> str:
        return f"onboarding/completed/{username or self._username}"

    def _last_version_key(self, username: str | None = None) -> str:
        return f"onboarding/last_version/{username or self._username}"

    def _default_workdir(self) -> Path:
        return self.paths.data_root

    def _normalize_workdir(self, path: str) -> Path:
        candidate = Path(str(path or "").strip()).expanduser()
        if not candidate.is_absolute():
            candidate = self.paths.data_root / candidate
        return candidate.resolve()

    def _ensure_workdir(self, path: Path) -> bool:
        try:
            if path.exists() and not path.is_dir():
                return False
            path.mkdir(parents=True, exist_ok=True)
            for name in WORKDIR_SUBDIRS:
                (path / name).mkdir(parents=True, exist_ok=True)
            probe = path / "cache" / ".write-test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
        except OSError:
            return False
        return True

    def _should_show_for(self, username: str) -> bool:
        if not username:
            return False
        return self._show_every_login or self.store.setting(self._completed_key(username)) != "1"

    def _mark_seen(self) -> None:
        if not self._username:
            return
        self.store.set_setting(self._completed_key(), "1")
        self.store.set_setting(self._last_version_key(), self.app.version)

    def _emit(self) -> None:
        self.changed.emit()

    @Property(bool, notify=changed)
    def active(self) -> bool:
        return self._active

    @Property(bool, notify=changed)
    def needsWorkdir(self) -> bool:
        return self._needs_workdir

    @Property(str, notify=changed)
    def workdir(self) -> str:
        return self._workdir

    @Property(bool, notify=changed)
    def showEveryLogin(self) -> bool:
        return self._show_every_login

    @Property(int, notify=changed)
    def stepIndex(self) -> int:
        return self._step_index

    @Property("QVariantList", notify=changed)
    def steps(self) -> list[dict[str, object]]:
        return [dict(step) for step in self._steps]

    @Property("QVariantMap", notify=changed)
    def currentStep(self) -> dict[str, object]:
        if 0 <= self._step_index < len(self._steps):
            return dict(self._steps[self._step_index])
        return {}

    @Slot(str)
    def onAuthenticated(self, username: str) -> None:
        self._username = str(username or "").strip()
        self._active = False
        self._step_index = 0
        saved_workdir = self.store.setting(WORKDIR_SETTING, self._workdir)
        self._workdir = saved_workdir
        self._show_every_login = as_bool(self.store.setting(SHOW_EVERY_LOGIN_SETTING), False)
        self._needs_workdir = not bool(saved_workdir)
        if saved_workdir and not self._ensure_workdir(self._normalize_workdir(saved_workdir)):
            self._needs_workdir = True
        if not self._needs_workdir and self._should_show_for(self._username):
            self.startTour()
        else:
            self._emit()

    @Slot(result=str)
    def chooseWorkdir(self) -> str:
        initial_dir = self._workdir or str(self._default_workdir())
        return str(QFileDialog.getExistingDirectory(None, "OmniLit Workspace", initial_dir) or "")

    def _save_workdir(self, path: str, *, continue_tour: bool) -> bool:
        if not str(path or "").strip():
            return False
        resolved = self._normalize_workdir(path)
        if not self._ensure_workdir(resolved):
            return False
        self._workdir = str(resolved)
        self._needs_workdir = False
        self.store.set_setting(WORKDIR_SETTING, self._workdir)
        update_download_form_output_dir(self.paths, self.store)
        if continue_tour and self._should_show_for(self._username):
            self.startTour()
        else:
            self._emit()
        return True

    @Slot(str, result=bool)
    def setWorkdir(self, path: str) -> bool:
        return self._save_workdir(path, continue_tour=True)

    @Slot(str, result=bool)
    def saveWorkdirPreference(self, path: str) -> bool:
        return self._save_workdir(path, continue_tour=False)

    @Slot(result=bool)
    def useDefaultWorkdir(self) -> bool:
        return self.setWorkdir(str(self._default_workdir()))

    @Slot()
    def startTour(self) -> None:
        if self._needs_workdir:
            self._step_index = 0
            self._active = False
        else:
            self._step_index = 1 if len(self._steps) > 1 else 0
            self._active = True
        self._emit()

    @Slot()
    def next(self) -> None:
        if not self._active:
            return
        if self._step_index >= len(self._steps) - 1:
            self.finish()
            return
        self._step_index += 1
        self._emit()

    @Slot()
    def previous(self) -> None:
        if not self._active:
            return
        self._step_index = max(1, self._step_index - 1)
        self._emit()

    @Slot()
    def skip(self) -> None:
        self._mark_seen()
        self._active = False
        self._emit()

    @Slot()
    def finish(self) -> None:
        self._mark_seen()
        self._active = False
        self._emit()

    @Slot(bool)
    def setShowEveryLogin(self, value: bool) -> None:
        enabled = bool(value)
        if enabled == self._show_every_login:
            return
        self._show_every_login = enabled
        self.store.set_setting(SHOW_EVERY_LOGIN_SETTING, "1" if enabled else "0")
        self._emit()
