from __future__ import annotations
from datetime import date

import threading
from pathlib import Path
from collections.abc import Mapping
from typing import Any

from PySide6.QtCore import QObject, Property, Signal, Slot
from PySide6.QtWidgets import QApplication, QFileDialog

from ._controller_support import (
    _load_form_setting,
    _open_path,
    _save_form_setting,
    classify_download_stage,
    classify_log_level,
    export_log_entries,
    log_entries_to_text,
    log_entry,
)
from .app_controller import AppController
from .background_tasks import ManagedWorker, shutdown_workers
from .i18n import LocaleController, tr
from .paths import AppPaths
from .services import (
    AccountStore,
    EMAIL_PATTERN,
    build_download_config,
    default_download_dir,
    import_resource_module,
    normalize_download_form_config,
    parse_download_keywords,
)
from .source_api_config import (
    clear_source_api_key,
    load_source_api_settings,
    public_source_api_settings,
    save_source_api_settings,
    source_api_statuses,
)

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
    "topicPack",
    "journalPack",
    "selectedJournals",
    "minTopicScore",
    "journalWhitelistOnly",
    "minImpactFactor",
    "includeUnknownImpactFactor",
    "journalMetricSource",
    "journalMetricCsv",
    "qualityPreset",
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
        self._saved_config = normalize_download_form_config(paths, store, _load_form_setting(store, DOWNLOAD_FORM_SETTING))
        self._running = False
        self._active_task_text = ""
        self._status = locale.textf("not_started")
        self._last_round_summary = ""
        self._stats = self._empty_stats()
        self._active_source_key = ""
        self._active_source_label = ""
        self._active_source_text = ""
        self._log_entries: list[dict[str, Any]] = []
        self._source_api_tests: dict[str, dict[str, str]] = {}
        self._stop = threading.Event()
        self._worker: ManagedWorker | None = None
        self.progress.connect(self._on_progress)
        self.finished.connect(self._on_finished)

    @staticmethod
    def _empty_stats() -> dict[str, int]:
        """Return all integer stats exposed to QML."""
        return {key: 0 for key in (
            "existing_records",
            "fetched_items",
            "fetched_items_total",
            "added_records",
            "skipped_duplicates",
            "skipped_without_key",
            "skipped_irrelevant",
            "skipped_not_oa",
            "skipped_by_topic_score",
            "skipped_by_keyword_match",
            "skipped_by_impact_factor",
            "journal_metric_resolved",
            "journal_metric_missing",
            "open_access_records",
            "downloaded_pdfs",
            "failed_pdfs",
            "pdf_candidates_found",
            "pdf_download_attempted",
            "pdf_downloaded",
            "pdf_failed",
            "retried_existing_records",
            "backfill_scanned_records",
            "backfill_missing_pdf_records",
            "backfill_downloaded_pdfs",
            "backfill_failed_pdfs",
            "request_failures",
        )}
    @staticmethod
    def _is_round_summary_message(message: str) -> bool:
        """判断进度消息是否是本轮抓取总结。"""
        text = (message or "").strip()
        if not text:
            return False

        return any(
            marker in text
            for marker in (
                "本轮抓取完成",
                "Crawl round finished",
                "Crawl round completed",
                "元数据 PDF 补全完成",
                "Metadata PDF backfill finished",
                "Раунд сканирования завершён",
                "Раунд обхода завершён",
            )
        )


    def _append(self, text: str, *, level: str | None = None, stage: str | None = None, details: str = "") -> None:
        """Append one structured download log entry."""
        clean = str(text or "").strip()
        if not clean:
            return
        if "\n" in clean and not details:
            title, detail_text = clean.split("\n", 1)
            clean, details = title.strip(), detail_text.strip()
        self._log_entries.append(
            log_entry(
                level=level or classify_log_level(clean),
                stage=stage or classify_download_stage(clean),
                message=clean,
                details=details,
                source=self._active_source_label,
                index=len(self._log_entries),
            )
        )
        self._log_entries = self._log_entries[-1000:]

    def _append_summary(self, ok: bool, message: str) -> None:
        """Append a compact final task summary."""
        pdf_failed = self._stats.get("pdf_failed") or self._stats.get("failed_pdfs") or self._stats.get("backfill_failed_pdfs") or 0
        pdf_downloaded = self._stats.get("pdf_downloaded") or self._stats.get("downloaded_pdfs") or self._stats.get("backfill_downloaded_pdfs") or 0
        skipped = (
            self._stats.get("skipped_duplicates", 0)
            + self._stats.get("skipped_without_key", 0)
            + self._stats.get("skipped_irrelevant", 0)
            + self._stats.get("skipped_not_oa", 0)
            + self._stats.get("skipped_by_topic_score", 0)
            + self._stats.get("skipped_by_keyword_match", 0)
            + self._stats.get("skipped_by_impact_factor", 0)
        )
        total = self._stats.get("fetched_items_total") or self._stats.get("fetched_items") or self._stats.get("backfill_scanned_records") or 0
        summary = (
            f"{message}\n"
            f"Total={total}; success={pdf_downloaded}; failed={pdf_failed}; skipped={skipped}; "
            f"metadata_saved={self._stats.get('added_records', 0)}."
        )
        self._append(summary, level="success" if ok else "error", stage="summary")

    def _on_progress(self, stats: object, message: str) -> None:
        """接收下载进度。参数：统计对象和消息。返回值：无。"""
        message = str(message or "")

        self._stats = {
            key: int(getattr(stats, key, 0) or 0)
            for key in self._empty_stats()
        }

        self._status = message
        self._active_source_key = str(getattr(stats, "active_source_key", "") or "")
        self._active_source_label = str(getattr(stats, "active_source_label", "") or "")
        if self._active_source_label:
            if self.locale.language == "zh":
                self._active_source_text = f"当前文献库：{self._active_source_label}"
            else:
                self._active_source_text = f"Current database: {self._active_source_label}"
        else:
            self._active_source_text = ""
        self._append(message)

        if self._is_round_summary_message(message):
            self._last_round_summary = message

        self.app.set_status(message)
        self.changed.emit()

    def _on_finished(self, ok: bool, message: str) -> None:
        """完成下载状态流转。参数：成功标志和消息。返回值：无。"""
        message = str(message or "")

        self._running = False
        self._active_source_key = ""
        self._active_source_label = ""
        self._active_source_text = ""

        final_status = (
            self._last_round_summary
            if ok and self._last_round_summary
            else message
        )

        self._status = final_status

        if ok and self._last_round_summary:
            self._append(self._last_round_summary, level="success", stage="summary")
        else:
            self._append_summary(ok, message)

        self.app.set_status(final_status)

        # Clear the cached round summary before the next task.
        self._last_round_summary = ""

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
    def activeSourceKey(self) -> str:
        """Return the currently processed literature database key."""
        return self._active_source_key if self._running else ""

    @Property(str, notify=changed)
    def activeSourceLabel(self) -> str:
        """Return the currently processed literature database label."""
        return self._active_source_label if self._running else ""

    @Property(str, notify=changed)
    def activeSourceText(self) -> str:
        """Return user-facing text for the currently processed source."""
        return self._active_source_text if self._running else ""

    @Property(str, notify=changed)
    def logText(self) -> str:
        """返回下载日志。参数：无。返回值：多行文本。"""
        return log_entries_to_text(self._log_entries)

    @Property("QVariantList", notify=changed)
    def logEntries(self) -> list[dict[str, Any]]:
        """Return structured download log entries."""
        return [dict(item) for item in self._log_entries]

    @Slot()
    def clearLog(self) -> None:
        """Clear visible download logs."""
        self._log_entries = []
        self.changed.emit()

    @Slot(result=str)
    def exportLog(self) -> str:
        """Export current download logs and return the JSONL path."""
        if not self._log_entries:
            return ""
        path = export_log_entries(self.paths, "literature_download", self._log_entries)
        self._status = path
        self.changed.emit()
        return path

    @Slot("QVariantList", result=bool)
    def copyLogEntries(self, entries: list[Any]) -> bool:
        """Copy the provided visible log entries to the system clipboard."""
        app = QApplication.instance()
        if app is None:
            return False
        normalized: list[dict[str, Any]] = []
        for item in entries or []:
            value = item.toVariant() if hasattr(item, "toVariant") else item
            if isinstance(value, Mapping):
                normalized.append(dict(value))
        text = log_entries_to_text(normalized)
        if not text:
            return False
        app.clipboard().setText(text)
        return True

    @Property("QVariantMap", notify=changed)
    def stats(self) -> dict[str, int]:
        """返回下载统计。参数：无。返回值：统计字典。"""
        return dict(self._stats)

    @Property(str, constant=True)
    def defaultOutputDir(self) -> str:
        """返回默认输出目录。参数：无。返回值：目录文本。"""
        return str(default_download_dir(self.paths, self.store))

    @Property("QVariantMap", constant=True)
    def savedConfig(self) -> dict[str, Any]:
        """Return the saved non-sensitive download form fields."""
        config = normalize_download_form_config(self.paths, self.store, self._saved_config)
        config["email"] = str(config.get("email") or self.contactEmail).strip()
        return config

    @Slot("QVariantMap")
    def saveConfig(self, config_map: dict[str, Any]) -> None:
        """Persist the non-sensitive download form fields."""
        config_map = dict(config_map or {})
        config_map["email"] = str(config_map.get("email") or self.contactEmail).strip()
        if "keywords" in config_map:
            config_map["keywords"] = "\n".join(parse_download_keywords(config_map.get("keywords")))
        self._saved_config = _save_form_setting(
            self.store,
            DOWNLOAD_FORM_SETTING,
            config_map,
            DOWNLOAD_FORM_FIELDS,
        )

    @Property(str, constant=True)
    def defaultKeywords(self) -> str:
        """返回默认关键词。参数：无。返回值：多行文本。"""
        return "\n".join(import_resource_module(self.paths, "Download", "literature_download_core").DEFAULT_KEYWORDS)

    @Property("QVariantList", constant=True)
    def keywordSuggestions(self) -> list[str]:
        """Return default keyword suggestions for the editable dropdown."""
        return list(import_resource_module(self.paths, "Download", "literature_download_core").DEFAULT_KEYWORDS)

    @Property(str, notify=changed)
    def contactEmail(self) -> str:
        """Return the contact email used for literature API requests."""
        return self.store.contact_email()

    @Slot(str, result=bool)
    def saveContactEmail(self, email: str) -> bool:
        """Persist the contact email from system settings."""
        value = str(email or "").strip()
        if not value or not EMAIL_PATTERN.fullmatch(value):
            self._status = self.locale.textf("contact_email_invalid")
            self.changed.emit()
            return False
        self.store.save_contact_email(value)
        self._saved_config["email"] = value
        self._saved_config = _save_form_setting(
            self.store,
            DOWNLOAD_FORM_SETTING,
            self._saved_config,
            DOWNLOAD_FORM_FIELDS,
        )
        self._status = self.locale.textf("contact_email_saved")
        self.changed.emit()
        return True

    @Property("QVariantList", constant=True)
    def availableSources(self) -> list[dict[str, str]]:
        """Return literature database choices for the download form."""
        return import_resource_module(self.paths, "Download", "literature_download_core").source_maps()

    @Property("QVariantList", notify=changed)
    def availableSourceApiStatuses(self) -> list[dict[str, Any]]:
        """Return safe per-source API configuration statuses for QML."""
        statuses = source_api_statuses(self.paths, self.store, self.contactEmail)
        for status in statuses:
            source = str(status.get("source") or "")
            if source in self._source_api_tests:
                status.update(self._source_api_tests[source])
        return statuses

    @Property("QVariantMap", notify=changed)
    def sourceApiSettings(self) -> dict[str, Any]:
        """Return non-sensitive source API settings and masked key state."""
        return public_source_api_settings(self.paths, self.store, self.contactEmail)

    @Slot("QVariantMap", result=bool)
    def saveSourceApiSettings(self, settings: dict[str, Any]) -> bool:
        """Persist source API settings; sensitive keys are encrypted outside savedConfig."""
        try:
            save_source_api_settings(self.paths, self.store, dict(settings or {}), self.contactEmail)
        except Exception as exc:
            self._status = tr(self.locale.language, "source_api_settings_failed", error=exc)
            self.changed.emit()
            return False
        self._source_api_tests.clear()
        self._status = self.locale.textf("source_api_settings_saved")
        self.changed.emit()
        return True

    @Slot(str, result=bool)
    def clearSourceApiKey(self, source: str) -> bool:
        """Clear an encrypted source API key."""
        ok = clear_source_api_key(self.paths, self.store, str(source or "").strip())
        self._source_api_tests.pop(str(source or "").strip(), None)
        self._status = self.locale.textf("source_api_key_cleared" if ok else "source_api_key_clear_failed")
        self.changed.emit()
        return ok

    @Slot(str, result=bool)
    def testSourceApi(self, source: str) -> bool:
        """Run a lightweight source API check without exposing credentials."""
        source_key = str(source or "").strip()
        language = self.locale.language
        try:
            core = import_resource_module(self.paths, "Download", "literature_download_core")
            settings = load_source_api_settings(self.paths, self.store, self.contactEmail)
            config = core.CrawlConfig(
                email=self.contactEmail,
                keywords=["test"],
                per_page=1,
                max_pages_per_keyword=1,
                request_delay=0,
                page_delay=0,
                language=language,
                api_settings=settings,
            )
            session = core.build_session(self.contactEmail)
            self._test_source_api_request(core, session, source_key, config)
        except Exception:
            self._source_api_tests[source_key] = {
                "status": "test_failed",
                "message": self.locale.textf("source_api_test_failed"),
            }
            self._status = self.locale.textf("source_api_test_failed")
            self.changed.emit()
            return False
        self._source_api_tests[source_key] = {
            "status": "test_success",
            "message": self.locale.textf("source_api_test_success"),
        }
        self._status = self.locale.textf("source_api_test_success")
        self.changed.emit()
        return True

    @staticmethod
    def _test_source_api_request(core: Any, session: Any, source: str, config: Any) -> None:
        if source == core.SOURCE_OPENALEX:
            response = core.source_api_get(session, source, core.source_url(config, source, core.OPENALEX_URL), config, params={"per-page": 1, "select": "id"})
        elif source == core.SOURCE_EUROPE_PMC:
            response = core.source_api_get(session, source, core.source_url(config, source, core.EUROPE_PMC_URL), config, params={"query": "OPEN_ACCESS:Y", "format": "json", "pageSize": 1})
        elif source == core.SOURCE_ARXIV:
            response = core.source_api_get(session, source, core.source_url(config, source, core.ARXIV_URL), config, params={"search_query": "all:test", "start": 0, "max_results": 1})
        elif source == core.SOURCE_CROSSREF:
            response = core.source_api_get(session, source, core.source_url(config, source, core.CROSSREF_URL), config, params={"query.bibliographic": "test", "rows": 1})
        elif source == core.SOURCE_DOAJ:
            response = core.source_api_get(session, source, core.source_url(config, source, core.DOAJ_URL, "/test"), config, params={"page": 1, "pageSize": 1})
        else:
            response = core.source_api_get(session, "semantic_scholar", core.source_url(config, "semantic_scholar", core.SEMANTIC_SCHOLAR_PAPER_URL, "/search"), config, params={"query": "test", "limit": 1, "fields": "paperId"})
        core.raise_source_for_status(response)

    @Property(str, constant=True)
    def defaultFromDate(self) -> str:
        """返回默认开始日期。参数：无。返回值：ISO 日期。"""
        return str(import_resource_module(self.paths, "Download", "literature_download_core").DEFAULT_FROM_DATE)

    @Property(str, notify=changed)
    def defaultToDate(self) -> str:
        """返回默认结束日期：当前本地日期。"""
        return date.today().isoformat()

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
            raw["email"] = str(raw.get("email") or self.contactEmail).strip()
            api_settings = load_source_api_settings(self.paths, self.store, raw["email"])
            core, config = build_download_config(self.paths, raw, lambda: self._stop.is_set(), lambda stats, message: self.progress.emit(stats, str(message)), language, api_settings=api_settings)
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
        self._last_round_summary = ""
        self._log_entries, self._stats, self._running = [], self._empty_stats(), True
        self._active_source_key = ""
        self._active_source_label = ""
        self._active_source_text = ""
        keywords = parse_download_keywords(raw.get("keywords"))
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

    @Slot("QVariantMap", result=bool)
    def backfillMissingPdfs(self, config_map: dict[str, Any]) -> bool:
        """Start a metadata-only PDF backfill task."""
        if self._running:
            self._on_finished(False, self.locale.textf("download_busy"))
            return False
        language = self.locale.language
        try:
            raw = dict(config_map or {})
            raw["email"] = str(raw.get("email") or self.contactEmail).strip()
            api_settings = load_source_api_settings(self.paths, self.store, raw["email"])
            core, config = build_download_config(
                self.paths,
                raw,
                lambda: self._stop.is_set(),
                lambda stats, message: self.progress.emit(stats, str(message)),
                language,
                api_settings=api_settings,
            )
            core.validate_config(config)
            self.saveConfig(raw)
        except Exception as exc:
            self._on_finished(False, tr(language, "config_error", error=exc))
            return False

        def worker() -> None:
            try:
                core.backfill_missing_pdfs_from_metadata(config, stop_event=self._stop)
            except Exception as exc:
                message = tr(language, "pdf_backfill_failed", error=exc)
                task.update_state("failed", detail=message)
                self.finished.emit(False, message)
            else:
                cancelled = self._stop.is_set()
                message = tr(language, "pdf_backfill_stopped" if cancelled else "pdf_backfill_done")
                task.update_state("cancelled" if cancelled else "completed", detail=message)
                self.finished.emit(not cancelled, message)

        self._stop.clear()
        self._last_round_summary = ""
        self._log_entries, self._stats, self._running = [], self._empty_stats(), True
        self._active_source_key = ""
        self._active_source_label = ""
        self._active_source_text = ""
        self._active_task_text = tr(language, "pdf_backfill_task")
        self._status = tr(language, "pdf_backfill_started")
        self._append(self._status)
        self.changed.emit()
        task = ManagedWorker(
            name="LiteraturePdfBackfill",
            target=worker,
            state_path=self.paths.data("task_state", "literature_pdf_backfill.json"),
            cancel_event=self._stop,
            metadata={"mode": "metadata_pdf_backfill"},
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
