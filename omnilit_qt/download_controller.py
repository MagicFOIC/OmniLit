from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Property, Signal, Slot
from PySide6.QtWidgets import QFileDialog

from ._controller_support import _load_form_setting, _open_path, _save_form_setting
from .app_controller import AppController
from .background_tasks import ManagedWorker, shutdown_workers
from .i18n import LocaleController, tr
from .paths import AppPaths
from .services import AccountStore, build_download_config, import_resource_module

DOWNLOAD_FORM_SETTING = "download_form_config"
DOWNLOAD_FORM_FIELDS = (
    "email",
    "outputDir",
    "fromDate",
    "toDate",
    "keywords",
    "sort",
    "maxPages",
    "perPage",
    "maxRecords",
    "requestDelay",
    "pageDelay",
    "minPdfBytes",
    "downloadPdfs",
    "retryMissingPdfs",
    "writeRetryRecords",
    "strictKeywordMatch",
    "minKeywordMatchRatio",
    "loop",
    "loopSleep",
    "maxRuntimeHours",
    "resume",
    "fastForwardExistingPages",
    "oaOnly",
    "sources",
    "advancedVisible",
)


class DownloadController(QObject):
    """在后台线程中运行多来源文献下载核心。"""

    changed = Signal()
    progress = Signal(object, str)
    finished = Signal(bool, str)

    def __init__(self, app: AppController, paths: AppPaths, store: AccountStore, locale: LocaleController):
        """初始化下载控制器。参数：应用、路径和语言控制器。返回值：无。"""
        super().__init__()
        self.app, self.paths, self.store, self.locale = app, paths, store, locale
        self._saved_config = _load_form_setting(store, DOWNLOAD_FORM_SETTING)
        self._running = False
        self._active_task_text = ""
        self._status = locale.textf("not_started")
        self._stats = self._empty_stats()
        self._logs: list[str] = []
        self._stop = threading.Event()
        self._worker: ManagedWorker | None = None
        self.progress.connect(self._on_progress)
        self.finished.connect(self._on_finished)

    @staticmethod
    def _empty_stats() -> dict[str, int]:
        """生成空统计值。参数：无。返回值：统计字典。"""
        return {key: 0 for key in ("existing_records", "fetched_items", "added_records", "skipped_duplicates", "skipped_without_key", "skipped_irrelevant", "open_access_records", "downloaded_pdfs", "failed_pdfs", "retried_existing_records", "request_failures")}

    def _append(self, text: str) -> None:
        """追加日志并限制长度。参数：文本。返回值：无。"""
        if text.strip():
            self._logs.append(text.strip())
            self._logs = self._logs[-800:]

    def _on_progress(self, stats: object, message: str) -> None:
        """接收下载进度。参数：统计对象和消息。返回值：无。"""
        self._stats = {key: int(getattr(stats, key, 0) or 0) for key in self._empty_stats()}
        self._status = message
        self._append(message)
        self.app.set_status(message)
        self.changed.emit()

    def _on_finished(self, ok: bool, message: str) -> None:
        """完成下载状态流转。参数：成功标志和消息。返回值：无。"""
        self._running = False
        self._status = message
        self._append(message)
        self.app.set_status(message)
        self.changed.emit()

    @Property(bool, notify=changed)
    def running(self) -> bool:
        """返回任务状态。参数：无。返回值：是否运行。"""
        return self._running

    @Property(str, notify=changed)
    def statusText(self) -> str:
        """返回下载状态。参数：无。返回值：状态文本。"""
        return self._status

    @Property(str, notify=changed)
    def activeTaskText(self) -> str:
        """返回当前下载任务摘要。参数：无。返回值：任务摘要或空文本。"""
        return self._active_task_text if self._running else ""

    @Property(str, notify=changed)
    def logText(self) -> str:
        """返回下载日志。参数：无。返回值：多行文本。"""
        return "\n".join(self._logs)

    @Property("QVariantMap", notify=changed)
    def stats(self) -> dict[str, int]:
        """返回下载统计。参数：无。返回值：统计字典。"""
        return dict(self._stats)

    @Property(str, constant=True)
    def defaultOutputDir(self) -> str:
        """返回默认输出目录。参数：无。返回值：目录文本。"""
        return str(self.paths.data("Download"))

    @Property("QVariantMap", constant=True)
    def savedConfig(self) -> dict[str, Any]:
        """Return the saved non-sensitive download form fields."""
        return dict(self._saved_config)

    @Slot("QVariantMap")
    def saveConfig(self, config_map: dict[str, Any]) -> None:
        """Persist the non-sensitive download form fields."""
        self._saved_config = _save_form_setting(
            self.store,
            DOWNLOAD_FORM_SETTING,
            dict(config_map or {}),
            DOWNLOAD_FORM_FIELDS,
        )

    @Property(str, constant=True)
    def defaultKeywords(self) -> str:
        """返回默认关键词。参数：无。返回值：多行文本。"""
        return "\n".join(import_resource_module(self.paths, "Download", "literature_download_core").DEFAULT_KEYWORDS)

    @Property("QVariantList", constant=True)
    def availableSources(self) -> list[dict[str, str]]:
        """Return literature database choices for the download form."""
        return import_resource_module(self.paths, "Download", "literature_download_core").source_maps()

    @Property(str, constant=True)
    def defaultFromDate(self) -> str:
        """返回默认开始日期。参数：无。返回值：ISO 日期。"""
        return str(import_resource_module(self.paths, "Download", "literature_download_core").DEFAULT_FROM_DATE)

    @Property(str, constant=True)
    def defaultToDate(self) -> str:
        """返回默认结束日期。参数：无。返回值：ISO 日期。"""
        return str(import_resource_module(self.paths, "Download", "literature_download_core").DEFAULT_TO_DATE)

    @Slot(str, result=str)
    def chooseDirectory(self, initial_dir: str) -> str:
        """选择下载目录。参数：初始目录。返回值：所选目录。"""
        return str(QFileDialog.getExistingDirectory(None, self.locale.textf("output_dir"), initial_dir or self.defaultOutputDir) or "")

    @Slot(str)
    def openDirectory(self, path: str) -> None:
        """打开下载目录。参数：目录文本。返回值：无。"""
        _open_path(Path(path or self.defaultOutputDir))

    @Slot("QVariantMap", result=bool)
    def start(self, config_map: dict[str, Any]) -> bool:
        """启动下载线程。参数：QML 配置。返回值：是否成功启动。"""
        if self._running:
            self._on_finished(False, self.locale.textf("download_busy"))
            return False
        language = self.locale.language
        try:
            raw = dict(config_map or {})
            core, config = build_download_config(self.paths, raw, lambda: self._stop.is_set(), lambda stats, message: self.progress.emit(stats, str(message)), language)
            core.validate_config(config)
            self.saveConfig(raw)
        except Exception as exc:
            self._on_finished(False, tr(language, "config_error", error=exc))
            return False

        def worker() -> None:
            """执行下载任务并通过信号回到界面线程。参数：无。返回值：无。"""
            try:
                core.main(config)
            except Exception as exc:
                message = tr(language, "download_failed", error=exc)
                task.update_state("failed", detail=message)
                self.finished.emit(False, message)
            else:
                cancelled = self._stop.is_set()
                message = tr(language, "download_stopped" if cancelled else "download_done")
                task.update_state("cancelled" if cancelled else "completed", detail=message)
                self.finished.emit(not cancelled, message)

        self._stop.clear()
        self._logs, self._stats, self._running = [], self._empty_stats(), True
        keywords = raw.get("keywords") or []
        if isinstance(keywords, str):
            keywords = [item.strip() for item in keywords.replace("\n", ",").split(",") if item.strip()]
        keyword_text = (", " if language in {"en", "ru"} else "、").join(str(item) for item in keywords[:3])
        if len(keywords) > 3:
            keyword_text += tr(language, "keyword_count_suffix", count=len(keywords))
        self._active_task_text = tr(language, "downloading_keywords", keywords=keyword_text or tr(language, "unknown_keywords"))
        self._status = tr(language, "download_started")
        self._append(self._status)
        self.changed.emit()
        task = ManagedWorker(
            name="LiteratureDownload",
            target=worker,
            state_path=self.paths.data("task_state", "literature_download.json"),
            cancel_event=self._stop,
            metadata={"keywords": [str(item) for item in keywords]},
        )
        self._worker = task
        task.start()
        return True

    @Slot()
    def stop(self) -> None:
        """请求停止下载。参数：无。返回值：无。"""
        if self._running:
            if self._worker is not None:
                self._worker.request_cancel()
            else:
                self._stop.set()
            self._status = self.locale.textf("request_stop_download")
            self._append(self._status)
        self.app.set_status(self._status)
        self.changed.emit()

    def shutdown(self, timeout: float = 15.0) -> bool:
        """Request a clean stop and wait for metadata and PDF writes to settle."""
        return shutdown_workers([self._worker], timeout)
