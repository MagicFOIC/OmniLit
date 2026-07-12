from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QObject, Property, Signal, Slot

from ._controller_support import _format_bytes, _open_path
from .app_controller import AppController
from .background_tasks import ManagedWorker, shutdown_workers
from .i18n import LocaleController, tr
from .paths import AppPaths
from .services import AccountStore, import_resource_module

DEFAULT_UPDATE_MANIFEST_URL = "https://originchaos.top/omnilit/update_manifest.json"


class UpdateController(QObject):
    """检查、下载并应用桌面端更新。"""

    changed = Signal()
    checkFinished = Signal(object, bool, str)
    downloadProgress = Signal(int, int, str)
    downloadFinished = Signal(bool, str, str)
    applyFinished = Signal(bool, str)

    def __init__(self, app: AppController, paths: AppPaths, store: AccountStore, locale: LocaleController):
        """初始化更新控制器。参数：应用、路径、设置和语言。返回值：无。"""
        super().__init__()
        self.app, self.paths, self.store, self.locale = app, paths, store, locale
        self._status, self._history = locale.textf("not_started"), locale.textf("no_update_history")
        self._history_items: list[dict[str, str]] = []
        self._latest_version = self._downloaded_path = ""
        self._available = self._checking = self._downloading = False
        self._has_check_status = False
        self._progress, self._progress_text, self._manifest = 0.0, locale.textf("download_not_started"), None
        self._workers: dict[str, ManagedWorker] = {}
        self.checkFinished.connect(self._on_check_finished)
        self.downloadProgress.connect(self._on_download_progress)
        self.downloadFinished.connect(self._on_download_finished)
        self.applyFinished.connect(self._on_apply_finished)

    @Property(str, notify=changed)
    def statusText(self) -> str:
        """返回更新状态。参数：无。返回值：状态文本。"""
        return self._status

    @Property(str, notify=changed)
    def historyText(self) -> str:
        """返回版本记录。参数：无。返回值：多行文本。"""
        return self._history

    @Property("QVariantList", notify=changed)
    def historyItems(self) -> list[dict[str, str]]:
        """Return release notes as cards instead of one undifferentiated text block."""
        return [dict(item) for item in self._history_items]

    @Property(str, notify=changed)
    def latestVersion(self) -> str:
        """返回远程版本。参数：无。返回值：版本文本。"""
        return self._latest_version

    @Property(bool, notify=changed)
    def available(self) -> bool:
        """返回更新状态。参数：无。返回值：是否有更新。"""
        return self._available

    @Property(bool, notify=changed)
    def checking(self) -> bool:
        """返回检查状态。参数：无。返回值：是否检查中。"""
        return self._checking

    @Property(bool, notify=changed)
    def hasCheckStatus(self) -> bool:
        """Return whether the update drawer should show a live check result."""
        return self._has_check_status

    @Property(bool, notify=changed)
    def downloading(self) -> bool:
        """返回下载状态。参数：无。返回值：是否下载中。"""
        return self._downloading

    @Property(float, notify=changed)
    def progressValue(self) -> float:
        """返回更新进度。参数：无。返回值：0 到 1。"""
        return self._progress

    @Property(str, notify=changed)
    def progressText(self) -> str:
        """返回进度文本。参数：无。返回值：状态文本。"""
        return self._progress_text

    @Property(str, notify=changed)
    def downloadedPath(self) -> str:
        """返回下载文件。参数：无。返回值：路径文本。"""
        return self._downloaded_path

    @Property(str, notify=changed)
    def sha256Text(self) -> str:
        """返回远程摘要。参数：无。返回值：SHA-256 或占位文本。"""
        return str(getattr(self._manifest, "sha256", "") or self.locale.textf("sha_unknown"))

    def _on_check_finished(self, result: object, ok: bool, message: str) -> None:
        """处理检查结果。参数：结果、成功标志和消息。返回值：无。"""
        self._checking = False
        self._has_check_status = True
        if ok:
            self._manifest = getattr(result, "manifest", None)
            self._latest_version = str(getattr(self._manifest, "version", "") or "")
            self._available = bool(getattr(result, "update_available", getattr(result, "is_newer", False)) and self._manifest)
            self._history = str(self._manifest.formatted_notes(limit=8) if self._manifest else self.locale.textf("no_update_history"))
            self._history_items = self._manifest_history_items(self._manifest)
        else:
            self._available = False
        self._status = message
        self.app.set_status(message)
        self.changed.emit()

    def _manifest_history_items(self, manifest) -> list[dict[str, str]]:
        if manifest is None:
            return []
        items: list[dict[str, str]] = []
        seen: set[tuple[str, str]] = set()
        current = {"version": str(getattr(manifest, "version", "") or ""), "date": "", "notes": str(getattr(manifest, "notes", "") or "")}
        source_items = list(getattr(manifest, "history", ()))
        if not any(str(item.get("version") or "").strip() == current["version"] and str(item.get("notes") or "").strip() == current["notes"] for item in source_items):
            source_items.insert(0, current)
        for item in source_items:
            version = str(item.get("version") or "").strip()
            date = str(item.get("date") or "").strip()
            notes = str(item.get("notes") or "").strip()
            key = (version, notes)
            if not notes or key in seen:
                continue
            items.append({"version": version or "unknown", "date": date, "notes": notes})
            seen.add(key)
            if len(items) >= 8:
                break
        return items

    def _on_download_progress(self, downloaded: int, total: int, message: str) -> None:
        """处理下载进度。参数：已下载、总数和消息。返回值：无。"""
        self._progress = downloaded / total if total > 0 else 0.0
        self._progress_text = f"{message}: {_format_bytes(downloaded)} / {_format_bytes(total)}" if total else message
        self.changed.emit()

    def _on_download_finished(self, ok: bool, message: str, path_text: str) -> None:
        """处理下载结果。参数：成功标志、消息和路径。返回值：无。"""
        self._downloading = False
        if ok:
            self._downloaded_path, self._progress = path_text, 1.0
        self._status = message
        self.app.set_status(message)
        self.changed.emit()

    def _on_apply_finished(self, ok: bool, message: str) -> None:
        """处理应用更新结果。参数：成功标志和消息。返回值：无。"""
        self._status = message
        self.app.set_status(message)
        self.changed.emit()
        if ok and os.name == "nt":
            QCoreApplication.quit()

    @Slot()
    def check(self) -> None:
        """异步检查更新。参数：无。返回值：无。"""
        if self._checking or self._downloading:
            return
        language = self.locale.language
        try:
            core = import_resource_module(self.paths, "Update", "update_core")
            label = "Update source" if language == "en" else "Источник обновления" if language == "ru" else "更新源"
            manifest_url = core.validate_remote_url(DEFAULT_UPDATE_MANIFEST_URL, label=label)
        except Exception as exc:
            self._on_check_finished(None, False, tr(language, "invalid_update_source", error=exc))
            return
        self._checking, self._has_check_status, self._status = True, True, tr(language, "checking_update")
        self.changed.emit()

        def worker() -> None:
            """执行更新检查。参数：无。返回值：无。"""
            try:
                current_sha256 = core.sha256_file(Path(sys.executable)) if getattr(sys, "frozen", False) else ""
                result = core.check_for_update(manifest_url, self.app.version, current_sha256=current_sha256, language=language)
            except Exception as exc:
                message = tr(language, "check_update_failed", error=exc)
                task.update_state("failed", detail=message)
                self.checkFinished.emit(None, False, message)
            else:
                task.update_state("completed", detail=str(result.status))
                self.checkFinished.emit(result, True, str(result.status))

        task = ManagedWorker(
            name="UpdateCheck",
            target=worker,
            state_path=self.paths.runtime("task_state", "update_check.json"),
        )
        self._workers["check"] = task
        task.start()

    @Slot()
    def download(self) -> None:
        """异步下载更新。参数：无。返回值：无。"""
        if self._downloading or not self._available or self._manifest is None:
            return
        language = self.locale.language
        self._downloading, self._downloaded_path, self._progress = True, "", 0.0
        self._status = tr(language, "downloading_version", version=self._manifest.version)
        self.changed.emit()

        def worker() -> None:
            """执行更新下载。参数：无。返回值：无。"""
            try:
                core = import_resource_module(self.paths, "Update", "update_core")
                path = core.download_update(
                    self._manifest,
                    self.paths.runtime("updates"),
                    progress_callback=lambda a, b, c: self.downloadProgress.emit(a, b, c),
                    language=language,
                    stop_callback=lambda: task.cancel_event.is_set(),
                )
            except Exception as exc:
                message = tr(language, "download_update_failed", error=exc)
                task.update_state("failed", detail=message)
                self.downloadFinished.emit(False, message, "")
            else:
                message = tr(language, "downloaded_version", version=self._manifest.version)
                task.update_state("completed", detail=message)
                self.downloadFinished.emit(True, message, str(path))

        task = ManagedWorker(
            name="UpdateDownload",
            target=worker,
            state_path=self.paths.runtime("task_state", "update_download.json"),
            metadata={"version": str(self._manifest.version)},
        )
        self._workers["download"] = task
        task.start()

    @Slot()
    def apply(self) -> None:
        """应用已下载更新。参数：无。返回值：无。"""
        if not self._downloaded_path:
            return
        if os.name != "nt" or not getattr(sys, "frozen", False):
            _open_path(Path(self._downloaded_path))
            self._on_apply_finished(False, self.locale.textf("manual_update"))
            return

        def worker() -> None:
            """生成替换脚本。参数：无。返回值：无。"""
            try:
                core = import_resource_module(self.paths, "Update", "update_core")
                status = core.apply_update(Path(self._downloaded_path), [sys.executable], self.paths.data_root, expected_sha256=str(getattr(self._manifest, "sha256", "") or ""), language=self.locale.language)
            except Exception as exc:
                message = self.locale.textf("apply_update_failed", error=exc)
                task.update_state("failed", detail=message)
                self.applyFinished.emit(False, message)
            else:
                task.update_state("completed", detail=status)
                self.applyFinished.emit(True, status)

        task = ManagedWorker(
            name="UpdateApply",
            target=worker,
            state_path=self.paths.runtime("task_state", "update_apply.json"),
        )
        self._workers["apply"] = task
        task.start()

    def shutdown(self, timeout: float = 15.0) -> bool:
        """Wait for update network and apply workers before process exit."""
        return shutdown_workers(list(self._workers.values()), timeout)
