from __future__ import annotations

import argparse
import contextlib
import re
import shutil
import threading
import traceback
from datetime import datetime
from pathlib import Path
from collections.abc import Mapping
from typing import Any

from PySide6.QtCore import QObject, Property, Signal, Slot
from PySide6.QtWidgets import QApplication, QFileDialog

from ._controller_support import (
    LogWriter,
    _format_bytes,
    _load_form_setting,
    _open_path,
    _save_form_setting,
    classify_log_level,
    export_log_entries,
    log_entries_to_text,
    log_entry,
)
from .app_controller import AppController
from .background_tasks import ManagedWorker, shutdown_workers
from .i18n import LocaleController, tr
from .paths import AppPaths
from .services import AccountStore, as_bool, as_int, import_resource_module
from .support import (
    DEFAULT_GLOSSARY_FILENAMES,
    DEFAULT_KEY_FILE_NAME,
    USER_KEY_FILE_NAME,
    glossary_catalog,
    load_bundled_default_key,
    load_default_key,
    load_encrypted_key,
    profile_maps,
    write_encrypted_key,
)

TRANSLATION_FORM_SETTING = "translation_form_config"
TRANSLATION_FORM_FIELDS = (
    "translationDir",
    "model",
    "baseUrl",
    "profileIndex",
    "customService",
    "targetLang",
    "glossaryPaths",
    "maxPages",
    "rangeMode",
    "customMaxPages",
    "layoutOnly",
    "useCache",
    "summaryPage",
    "translateReferences",
    "translateHeaderFooter",
)


def _clean_pdf_title(title: object) -> str:
    """Normalize a PDF title so UI lists do not show raw metadata noise."""
    text = str(title or "").replace("\x00", " ")
    text = " ".join(text.split())
    if not text:
        return ""
    lowered = text.lower()
    if lowered in {"untitled", "none", "null"}:
        return ""
    return text


def _plausible_literature_title(text: object) -> str:
    """Return a cleaned title only when the text looks like a real paper title."""
    title = _clean_pdf_title(text)
    if not title:
        return ""
    lowered = title.lower()
    if lowered in {"abstract", "keywords", "introduction", "contents"}:
        return ""
    if re.match(r"^(doi|https?://|www\.|arxiv:|issn|isbn)\b", lowered):
        return ""
    if re.search(r"\b(journal|volume|issue|copyright|published by|all rights reserved)\b", lowered):
        return ""
    if len(title) < 8 or len(title) > 320:
        return ""
    return title


def _title_from_first_page_segments(document: object, core: object) -> str:
    """Extract the visible article title from the first page layout."""
    try:
        segments = core.extract_segments(
            document,
            translate_references=False,
            translate_header_footer=False,
            max_pages=1,
        )
    except Exception:
        return ""

    title_parts: list[str] = []
    for segment in segments:
        if getattr(segment, "page_index", 0) != 0:
            continue
        if getattr(segment, "kind", "") == "title":
            title = _plausible_literature_title(getattr(segment, "text", ""))
            if title:
                title_parts.append(title)
                if len(" ".join(title_parts)) >= 220:
                    break
            continue
        if title_parts and getattr(segment, "kind", "") in {"authors", "metadata", "body", "heading"}:
            break
    return _plausible_literature_title(" ".join(title_parts))


def _literature_display_name(path: Path, core: object | None = None) -> str:
    """Use the visible first-page article title, then PDF metadata, then file stem."""
    try:
        import fitz

        document = fitz.open(path)
        try:
            if core is not None:
                title = _title_from_first_page_segments(document, core)
                if title:
                    return title
            title = _plausible_literature_title((document.metadata or {}).get("title"))
            if title and title.lower() != path.stem.lower():
                return title
        finally:
            document.close()
    except Exception:
        pass
    return _clean_pdf_title(path.stem) or path.name


class TranslationCancelled(RuntimeError):
    """表示用户主动取消翻译。"""


class TranslationController(QObject):
    """在后台线程中运行文献翻译和版式重建核心。"""

    changed = Signal()
    pendingDocumentsChanged = Signal()
    progress = Signal(str, str, int, int)
    log = Signal(str)
    document = Signal(str)
    preview = Signal(str)
    finished = Signal(bool, str)
    snippetTranslationFinished = Signal(str, str, bool, str)

    def __init__(self, app: AppController, paths: AppPaths, store: AccountStore, locale: LocaleController):
        """初始化翻译控制器。参数：应用、路径和语言。返回值：无。"""
        super().__init__()
        self.app, self.paths, self.store, self.locale = app, paths, store, locale
        self._saved_config = _load_form_setting(store, TRANSLATION_FORM_SETTING)
        self._running, self._progress, self._workflow_index = False, 0.0, 0
        self._status, self._current_document = locale.textf("not_started"), ""
        self._pending_documents: list[dict[str, str]] = []
        self._preview_text = locale.textf("preview_waiting")
        self._preview_entries: list[dict[str, str]] = []
        self._log_entries: list[dict[str, Any]] = []
        self._stop = threading.Event()
        self._worker: ManagedWorker | None = None
        self._file_index, self._file_total = 0, 1
        self._translated_documents: list[str] = []
        self._failed_documents: list[str] = []
        self._skipped_documents: list[str] = []
        self._default_key = self._default_key_source = self._user_key = ""
        self.progress.connect(self._on_progress)
        self.log.connect(self._append_log)
        self.document.connect(self._on_document)
        self.preview.connect(self._on_preview)
        self.finished.connect(self._on_finished)
        self._ensure_default_glossaries()
        self._auto_load_default_key()

    @Property("QVariantList", constant=True)
    def modelProfiles(self) -> list[dict[str, object]]:
        """返回模型档案。参数：无。返回值：档案列表。"""
        return profile_maps()

    @Property("QVariantList", notify=changed)
    def glossaryCatalog(self) -> list[dict[str, object]]:
        """返回可写目录中的术语表。参数：无。返回值：术语表列表。"""
        return glossary_catalog(self.paths.glossary_dir)

    @Property(str, constant=True)
    def defaultInputDir(self) -> str:
        """返回默认输入目录。参数：无。返回值：目录文本。"""
        return str(self.paths.data("Translate", "pdf"))

    @Property(str, constant=True)
    def defaultOutputDir(self) -> str:
        """返回兼容旧调用方的默认目录。参数：无。返回值：文献翻译目录。"""
        return self.defaultInputDir

    @Property("QVariantMap", constant=True)
    def savedConfig(self) -> dict[str, Any]:
        """Return the saved non-sensitive translation form fields."""
        return dict(self._saved_config)

    @Slot("QVariantMap")
    def saveConfig(self, config_map: dict[str, Any]) -> None:
        """Persist translation form fields without credentials."""
        raw = dict(config_map or {})
        raw["translationDir"] = raw.get("translationDir") or raw.get("inputDir") or self.defaultInputDir
        self._saved_config = _save_form_setting(
            self.store,
            TRANSLATION_FORM_SETTING,
            raw,
            TRANSLATION_FORM_FIELDS,
        )

    @Property(bool, notify=changed)
    def running(self) -> bool:
        """返回任务状态。参数：无。返回值：是否运行。"""
        return self._running

    @Property(str, notify=changed)
    def statusText(self) -> str:
        """返回翻译状态。参数：无。返回值：状态文本。"""
        return self._status

    @Property(float, notify=changed)
    def progressValue(self) -> float:
        """返回整体进度。参数：无。返回值：0 到 1。"""
        return self._progress

    @Property(int, notify=changed)
    def workflowIndex(self) -> int:
        """返回当前阶段。参数：无。返回值：阶段索引。"""
        return self._workflow_index

    @Property(str, notify=changed)
    def currentDocument(self) -> str:
        """返回当前文档。参数：无。返回值：文档文本。"""
        return self._current_document

    @Property(str, notify=changed)
    def activeTaskText(self) -> str:
        """返回当前翻译文献摘要。参数：无。返回值：任务摘要或空文本。"""
        if not self._running or not self._current_document:
            return ""
        return self.locale.textf("translating_document", document=self._current_document)

    @Property("QVariantList", notify=pendingDocumentsChanged)
    def pendingDocuments(self) -> list[dict[str, str]]:
        """返回文献翻译目录中的 PDF。参数：无。返回值：待翻译文献列表。"""
        return list(self._pending_documents)

    @Property(int, notify=pendingDocumentsChanged)
    def pendingDocumentCount(self) -> int:
        """返回待翻译文献数量。参数：无。返回值：PDF 数量。"""
        return len(self._pending_documents)

    @Property(str, notify=changed)
    def logText(self) -> str:
        """返回翻译日志。参数：无。返回值：多行文本。"""
        return log_entries_to_text(self._log_entries)

    @Property("QVariantList", notify=changed)
    def logEntries(self) -> list[dict[str, Any]]:
        """Return structured translation task log entries."""
        return [dict(item) for item in self._log_entries]

    @Property(str, notify=changed)
    def previewText(self) -> str:
        """Return translated text completed so far for live preview."""
        return self._preview_text

    @Property("QVariantList", notify=changed)
    def previewEntries(self) -> list[dict[str, str]]:
        """Return translated preview paragraphs as stable entries."""
        return [dict(item) for item in self._preview_entries]

    @Slot()
    def clearLog(self) -> None:
        """Clear visible translation logs."""
        self._log_entries = []
        self.changed.emit()

    @Slot(result=str)
    def exportLog(self) -> str:
        """Export current translation logs and return the JSONL path."""
        if not self._log_entries:
            return ""
        path = export_log_entries(self.paths, "literature_translation", self._log_entries)
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

    @Property(bool, notify=changed)
    def defaultKeyLoaded(self) -> bool:
        """返回默认 Key 状态。参数：无。返回值：是否已加载。"""
        return bool(self._default_key)

    @Property(str, notify=changed)
    def defaultKeySource(self) -> str:
        """返回默认 Key 来源。参数：无。返回值：来源文本。"""
        return self._default_key_source

    @Property(str, constant=True)
    def defaultKeyPath(self) -> str:
        """返回可写部署 Key 路径。参数：无。返回值：路径文本。"""
        return str(self.paths.data("Translate", DEFAULT_KEY_FILE_NAME))

    @Property(bool, notify=changed)
    def defaultKeyExists(self) -> bool:
        """返回可写部署 Key 文件状态。参数：无。返回值：是否存在。"""
        return Path(self.defaultKeyPath).exists()

    @Property(bool, notify=changed)
    def rememberedKeyExists(self) -> bool:
        """返回用户 Key 文件状态。参数：无。返回值：是否存在。"""
        return self.paths.data("Translate", USER_KEY_FILE_NAME).exists()

    @staticmethod
    def _stage_fraction(stage: str, current: int, total: int) -> float:
        """计算单文件阶段进度。参数：阶段、当前值和总数。返回值：0 到 1。"""
        ratio = max(0.0, min(1.0, current / max(1, total)))
        start, width = {"prepare": (0.0, 0.02), "extract": (0.02, 0.10), "translate": (0.12, 0.64), "summary": (0.76, 0.06), "render": (0.82, 0.16), "done": (1.0, 0.0)}.get(stage, (0.0, 0.0))
        return start + width * ratio

    def _append_log(self, message: str) -> None:
        """追加日志并限制长度。参数：日志文本。返回值：无。"""
        raw = str(message or "").strip()
        if not raw:
            return
        if "Traceback" in raw or "\n  File " in raw:
            self._log_entries.append(
                log_entry(
                    level="error",
                    stage="technical",
                    title="Technical error details",
                    message=raw.splitlines()[-1] if raw.splitlines() else "Technical error details",
                    details=raw,
                    document=self._current_document,
                    index=len(self._log_entries),
                )
            )
        else:
            for line in (line.strip() for line in raw.splitlines() if line.strip()):
                self._log_entries.append(
                    log_entry(
                        level=classify_log_level(line),
                        stage="runtime",
                        message=line,
                        document=self._current_document,
                        index=len(self._log_entries),
                    )
                )
        self._log_entries = self._log_entries[-1000:]
        self.changed.emit()

    def _ensure_default_glossaries(self) -> None:
        """Append missing bundled glossary rows without replacing user edits."""
        try:
            core = import_resource_module(self.paths, "Translate", "literature_translate_core")
            ensure = getattr(core, "ensure_default_glossaries", None)
            if ensure is not None:
                ensure(self.paths.glossary_dir)
        except Exception:
            # Glossaries are helpful defaults; translation should still open if
            # the resource module is unavailable or a user file is malformed.
            return

    def _auto_load_default_key(self) -> None:
        """Try to make the bundled service available without user interaction."""
        try:
            self._default_key, self._default_key_source = load_bundled_default_key(
                self.paths.data("Translate"),
                self.paths.resource("Translate"),
            )
        except Exception as exc:
            self._default_key = self._default_key_source = ""
            self._status = self.locale.textf("default_service_unavailable", error=exc)
            return
        if self._default_key:
            self._status = self.locale.textf("default_service_ready")
        else:
            self._status = self.locale.textf("default_service_unavailable", error=self.locale.textf("default_key_unconfigured"))

    def _on_document(self, document: str) -> None:
        """切换当前文档。参数：文档文本。返回值：无。"""
        self._current_document = document
        self.changed.emit()

    def _set_preview_text(self, text: str, document: str = "") -> None:
        """Update live preview text and stable paragraph entries."""
        self._preview_text = str(text)
        lines = self._preview_text.splitlines()
        current_document = document or (lines[0].strip() if lines else self._current_document)
        body = "\n".join(lines[1:]).strip() if len(lines) > 1 else self._preview_text.strip()
        paragraphs = [part.strip() for part in re.split(r"\n\s*\n", body) if part.strip()]
        self._preview_entries = [
            {
                "id": f"{current_document}-{index}",
                "document": current_document,
                "index": str(index + 1),
                "text": paragraph,
            }
            for index, paragraph in enumerate(paragraphs)
        ]

    def _on_preview(self, text: str) -> None:
        """Refresh the live translation preview."""
        self._set_preview_text(str(text))
        self.changed.emit()

    def _on_progress(self, stage: str, message: str, current: int, total: int) -> None:
        """合并核心阶段进度。参数：阶段、消息、当前值和总数。返回值：无。"""
        self._workflow_index = {"prepare": 0, "extract": 1, "translate": 2, "summary": 3, "render": 4, "done": 5}.get(stage, self._workflow_index)
        self._progress = ((max(1, self._file_index) - 1) + self._stage_fraction(stage, current, total)) / max(1, self._file_total)
        self._status = message
        self._log_entries.append(
            log_entry(
                level=classify_log_level(message),
                stage=stage or "task",
                message=message,
                document=self._current_document,
                index=len(self._log_entries),
            )
        )
        self._log_entries = self._log_entries[-1000:]
        self.app.set_status(message)
        self.changed.emit()

    def _append_translation_summary(self, ok: bool, message: str) -> None:
        total = self._file_total
        success = len(self._translated_documents)
        failed = len(self._failed_documents)
        skipped = len(self._skipped_documents)
        details = ""
        if self._failed_documents:
            details = "Failed documents:\n" + "\n".join(f"- {name}" for name in self._failed_documents)
        self._log_entries.append(
            log_entry(
                level="success" if ok and not failed else "error" if failed else "warning",
                stage="summary",
                message=f"{message}\nTotal={total}; success={success}; failed={failed}; skipped={skipped}.",
                details=details,
                index=len(self._log_entries),
            )
        )
        self._log_entries = self._log_entries[-1000:]

    def _mark_unfinished_documents_skipped(self, pdfs: list[Path]) -> None:
        finished = set(self._translated_documents) | set(self._failed_documents)
        self._skipped_documents = [pdf.name for pdf in pdfs if pdf.name not in finished]

    def _on_finished(self, ok: bool, message: str) -> None:
        """完成翻译状态流转。参数：成功标志和消息。返回值：无。"""
        self._running, self._status = False, message
        if ok:
            self._progress, self._workflow_index = 1.0, 5
        self._append_translation_summary(ok, message)
        self.app.set_status(message)
        self.changed.emit()

    @Slot(str, str, result=str)
    def chooseDirectory(self, title: str, initial_dir: str) -> str:
        """选择目录。参数：标题和初始目录。返回值：所选目录。"""
        return str(QFileDialog.getExistingDirectory(None, title, initial_dir or str(self.paths.data("Translate"))) or "")

    @Slot(str)
    def openDirectory(self, path: str) -> None:
        """打开目录。参数：目录文本。返回值：无。"""
        _open_path(Path(path or self.defaultInputDir))

    @Slot(str)
    def refreshPendingDocuments(self, directory: str) -> None:
        """扫描文献翻译目录。参数：目录文本。返回值：无。"""
        root = Path(directory or self.defaultInputDir).expanduser()
        documents: list[dict[str, str]] = []
        core = None
        try:
            core = import_resource_module(self.paths, "Translate", "literature_translate_core")
        except Exception:
            core = None
        if root.is_dir():
            for path in sorted(
                (item for item in root.iterdir() if item.is_file() and item.suffix.lower() == ".pdf"),
                key=lambda item: item.name.lower(),
            ):
                stat = path.stat()
                documents.append(
                    {
                        "name": _literature_display_name(path, core),
                        "fileName": path.name,
                        "path": str(path.resolve()),
                        "sizeText": _format_bytes(stat.st_size),
                        "modifiedText": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
                    }
                )
        self._pending_documents = documents
        self._status = self.locale.textf("ready") if documents else self.locale.textf("empty_translation_dir")
        self.pendingDocumentsChanged.emit()
        self.changed.emit()

    @Slot(str)
    def addDocuments(self, directory: str) -> None:
        """选择 PDF 并复制到文献翻译目录。参数：目录文本。返回值：无。"""
        root = Path(directory or self.defaultInputDir).expanduser()
        root.mkdir(parents=True, exist_ok=True)
        selected, _filter = QFileDialog.getOpenFileNames(
            None,
            self.locale.textf("add_literature"),
            str(root),
            "PDF (*.pdf *.PDF)",
        )
        for source_text in selected:
            source = Path(source_text)
            if not source.is_file():
                continue
            target = root / source.name
            if target.exists() and source.resolve() == target.resolve():
                continue
            index = 2
            while target.exists():
                target = root / f"{source.stem}_{index}{source.suffix}"
                index += 1
            shutil.copy2(source, target)
        self.refreshPendingDocuments(str(root))

    @Slot()
    def openGlossaryDirectory(self) -> None:
        """打开可写术语表目录。参数：无。返回值：无。"""
        self.openDirectory(str(self.paths.glossary_dir))

    @Slot()
    def refreshGlossaries(self) -> None:
        """刷新术语表列表。参数：无。返回值：无。"""
        self.changed.emit()

    @Slot(str, result=bool)
    def unlockDefaultKey(self, password: str) -> bool:
        """解锁部署 Key。参数：加密密码。返回值：是否成功。"""
        try:
            self._default_key, self._default_key_source = load_default_key(self.paths.data("Translate"), self.paths.resource("Translate"), password)
            if not self._default_key:
                raise ValueError(self.locale.textf("default_key_unconfigured"))
        except Exception as exc:
            self._default_key = self._default_key_source = ""
            self._status = self.locale.textf("default_key_unlock_failed", error=exc)
            self.changed.emit()
            return False
        self._status = self.locale.textf("default_key_unlocked", source=self._default_key_source)
        self.changed.emit()
        return True

    @Slot(result=bool)
    def unlockBundledDefaultKey(self) -> bool:
        """Load bundled APIKey.enc without exposing the key in the UI."""
        try:
            self._default_key, self._default_key_source = load_bundled_default_key(
                self.paths.data("Translate"),
                self.paths.resource("Translate"),
            )
            if not self._default_key:
                raise ValueError(self.locale.textf("default_key_unconfigured"))
        except Exception as exc:
            self._default_key = self._default_key_source = ""
            self._status = self.locale.textf("default_key_unlock_failed", error=exc)
            self.changed.emit()
            return False
        self._status = self.locale.textf("default_key_unlocked", source=self._default_key_source)
        self.changed.emit()
        return True

    @Slot(str, str, str, result=bool)
    def saveDefaultKey(self, api_key: str, password: str, confirm_password: str) -> bool:
        """保存并载入部署 Key。参数：Key 和两次密码。返回值：是否成功。"""
        if password != confirm_password:
            self._status = self.locale.textf("password_mismatch")
            self.changed.emit()
            return False
        try:
            write_encrypted_key(Path(self.defaultKeyPath), api_key, password)
        except Exception as exc:
            self._status = self.locale.textf("key_write_failed", error=exc)
            self.changed.emit()
            return False
        self._default_key = api_key.strip()
        self._default_key_source = self.defaultKeyPath
        self._status = self.locale.textf("default_key_saved")
        self.app.set_status(self._status)
        self.changed.emit()
        return True

    @Slot(str, result=bool)
    def unlockRememberedKey(self, password: str) -> bool:
        """解锁用户 Key。参数：加密密码。返回值：是否成功。"""
        try:
            self._user_key = load_encrypted_key(self.paths.data("Translate", USER_KEY_FILE_NAME), password)
        except Exception as exc:
            self._status = self.locale.textf("user_key_unlock_failed", error=exc)
            self.changed.emit()
            return False
        self._status = self.locale.textf("user_key_unlocked")
        self.changed.emit()
        return True

    @Slot(str, str, str, result=bool)
    def rememberUserKey(self, api_key: str, password: str, confirm_password: str) -> bool:
        """保存用户 Key。参数：Key 和两次密码。返回值：是否成功。"""
        if password != confirm_password:
            self._status = self.locale.textf("password_mismatch")
            self.changed.emit()
            return False
        try:
            write_encrypted_key(self.paths.data("Translate", USER_KEY_FILE_NAME), api_key, password)
        except Exception as exc:
            self._status = self.locale.textf("user_key_save_failed", error=exc)
            self.changed.emit()
            return False
        self._user_key, self._status = api_key.strip(), self.locale.textf("user_key_saved")
        self.changed.emit()
        return True

    @Slot()
    def clearRememberedKey(self) -> None:
        """清除用户 Key。参数：无。返回值：无。"""
        self.paths.data("Translate", USER_KEY_FILE_NAME).unlink(missing_ok=True)
        self._user_key, self._status = "", self.locale.textf("user_key_cleared")
        self.changed.emit()

    @Slot(str, str, result=str)
    def translateSnippet(self, text: str, target_lang: str = "zh") -> str:
        """翻译短文本片段，用于解析阅读页图例对照。"""
        source_text = str(text or "").strip()
        if not source_text:
            self._status = "没有可翻译的文本。"
            self.changed.emit()
            return ""

        try:
            core = import_resource_module(self.paths, "Translate", "literature_translate_core")

            raw = dict(self._saved_config or {})
            normalized_target = "en" if str(target_lang or "").strip().lower() == "en" else "zh"

            glossary_text = core.load_glossary(
                self._glossary_paths(raw.get("glossaryPaths")),
                target_lang=normalized_target,
            )

            api_key = (
                    str(raw.get("apiKey") or "").strip()
                    or self._user_key
                    or self._default_key
                    or None
            )

            args = argparse.Namespace(
                translator="deepseek",
                target_lang=normalized_target,
                api_key=api_key,
                base_url=str(raw.get("baseUrl") or "https://api.deepseek.com").strip(),
                model=str(raw.get("model") or "deepseek-v4-flash").strip(),
                temperature=0.15,
                max_retries=2,
                disable_json_mode=False,
            )

            translator = core.make_translator(args, glossary_text)

            segment = core.Segment(
                sid="snippet_1",
                page_index=0,
                kind="caption",
                text=source_text[:5000],
                lines=[],
                translate=True,
            )

            cache = core.TranslationCache(
                self.paths.data("Translate", "snippet_translation_cache.json"),
                enabled=True,
            )
            cache_key = cache.key(
                translator.provider,
                translator.model,
                normalized_target,
                segment.text,
                glossary_text,
            )
            cached = cache.get(cache_key)
            if cached:
                self._status = "图例翻译已从缓存读取。"
                self.changed.emit()
                return str(cached).strip()

            result = translator.translate_many([segment], context="Figure caption from PDF reading panel.")
            translated = str(result.get(segment.sid, "") or "").strip()
            translated, cacheable = core.guarded_translation(
                translator,
                segment,
                translated,
                context="Figure caption from PDF reading panel.",
                target_lang=normalized_target,
            )

            translated = str(translated or "").strip()
            if not translated:
                self._status = "图例翻译失败：模型未返回有效译文。"
                self.changed.emit()
                return ""

            if cacheable:
                cache.set(cache_key, translated)
                cache.save()

            self._status = "图例翻译完成。"
            self.changed.emit()
            return translated

        except Exception as exc:
            self._status = f"图例翻译失败：{exc}"
            self.changed.emit()
            return ""

    @Slot(str, str, str)
    def translateSnippetAsync(self, element_key: str, text: str, target_lang: str = "zh") -> None:
        """异步翻译短文本，避免 QML 主线程卡顿。"""
        key = str(element_key or "").strip()
        source_text = str(text or "").strip()
        target = str(target_lang or "zh").strip() or "zh"

        if not source_text:
            self.snippetTranslationFinished.emit(key, "", False, "暂无可翻译图例。")
            return

        def _worker() -> None:
            try:
                translated = self.translateSnippet(source_text, target)
                translated = str(translated or "").strip()

                if translated:
                    message = "图例翻译完成。"
                    self.snippetTranslationFinished.emit(key, translated, True, message)
                else:
                    message = str(getattr(self, "_status", "") or "图例翻译失败。")
                    self.snippetTranslationFinished.emit(key, "", False, message)

            except Exception as exc:
                message = f"图例翻译失败：{exc}"
                try:
                    self._status = message
                    self.changed.emit()
                except Exception:
                    pass
                self.snippetTranslationFinished.emit(key, "", False, message)

        thread = threading.Thread(target=_worker, daemon=False)
        thread.start()

    def _glossary_paths(self, raw: Any) -> list[Path]:
        """规范化术语表路径。参数：QML 列表或文本。返回值：路径列表。"""
        values = [str(item).strip() for item in raw if str(item).strip()] if isinstance(raw, list) else [item.strip() for item in str(raw or "").replace(";", "\n").splitlines() if item.strip()]
        if not values:
            values = [str(self.paths.glossary_dir / DEFAULT_GLOSSARY_FILENAMES[0])]
        return [Path(item).expanduser() for item in values]

    def _build_config(self, raw: dict[str, Any], language: str):
        """构建翻译核心配置。参数：QML 配置和固定语言。返回值：核心、参数和 PDF 列表。"""
        core = import_resource_module(self.paths, "Translate", "literature_translate_core")
        translation_dir = Path(str(raw.get("translationDir") or raw.get("inputDir") or self.defaultInputDir)).expanduser()
        if not translation_dir.is_dir():
            raise ValueError(tr(language, "translation_dir_missing"))
        layout_only = as_bool(raw.get("layoutOnly"))
        target_lang = str(raw.get("targetLang") or "zh").strip().lower()
        target_lang = "en" if target_lang == "en" else "zh"
        suffix = "_Full_Translation" if target_lang == "en" else "_全文翻译"
        use_custom_service = as_bool(raw.get("customService"), True)
        current_key = str(raw.get("apiKey") or "").strip() if use_custom_service else ""
        api_key = current_key or self._user_key or self._default_key
        if not layout_only and not api_key:
            raise ValueError(tr(language, "api_key_required"))
        base_url = str(raw.get("baseUrl") or "https://api.deepseek.com").strip() if use_custom_service else "https://api.deepseek.com"
        model = str(raw.get("model") or "deepseek-v4-flash").strip() if use_custom_service else "deepseek-v4-flash"
        args = argparse.Namespace(input=str(translation_dir), output=str(translation_dir), suffix=suffix, translator="copy" if layout_only else "deepseek", target_lang=target_lang, api_key=api_key or None, base_url=base_url, model=model, temperature=0.15, max_retries=4, disable_json_mode=False, glossary=self._glossary_paths(raw.get("glossaryPaths")), batch_size=as_int(raw.get("batchSize"), 3), max_batch_chars=as_int(raw.get("maxBatchChars"), 3500), render_scale=2.0, whiteout_padding_x=1.4, whiteout_padding_y=0.9, font=None, bold_font=None, translate_references=as_bool(raw.get("translateReferences")), translate_header_footer=as_bool(raw.get("translateHeaderFooter")), summary_page=as_bool(raw.get("summaryPage"), True), max_pages=int(raw["maxPages"]) if str(raw.get("maxPages") or "").strip() else None, no_cache=not as_bool(raw.get("useCache"), True), progress_callback=None, language=language)
        pdfs = core.find_pdf_files(translation_dir)
        if not pdfs:
            raise ValueError(tr(language, "pdf_missing"))
        return core, args, pdfs

    @Slot("QVariantMap", result=bool)
    def start(self, config_map: dict[str, Any]) -> bool:
        """启动翻译线程。参数：QML 配置。返回值：是否成功启动。"""
        if self._running:
            return False
        language = self.locale.language
        try:
            raw = dict(config_map or {})
            core, args, pdfs = self._build_config(raw, language)
            self.saveConfig(raw)
        except Exception as exc:
            self._on_finished(False, tr(language, "config_error", error=exc))
            return False

        def progress(stage: str, message: str, current: int | None = None, total: int | None = None) -> None:
            """转发进度并响应取消。参数：阶段、消息和计数。返回值：无。"""
            if self._stop.is_set():
                raise TranslationCancelled(tr(language, "translate_cancelled"))
            self.progress.emit(stage, message, int(current or 0), int(total or 1))

        def worker() -> None:
            """执行翻译任务并通过信号回到界面线程。参数：无。返回值：无。"""
            try:
                core.tqdm = None
                args.progress_callback = progress
                args.preview_callback = lambda text: self.preview.emit(str(text))
                glossary_text = core.load_glossary(args.glossary, target_lang=args.target_lang)
                translator = core.make_translator(args, glossary_text)
                writer = LogWriter(lambda text: self.log.emit(text))
                with contextlib.redirect_stdout(writer), contextlib.redirect_stderr(writer):
                    for index, pdf in enumerate(pdfs, start=1):
                        if self._stop.is_set():
                            raise TranslationCancelled(tr(language, "translate_cancelled"))
                        self._file_index = index
                        self.document.emit(pdf.name)
                        core.translate_pdf(pdf, args, translator, glossary_text)
                        self._translated_documents.append(pdf.name)
            except TranslationCancelled as exc:
                message = str(exc)
                self._mark_unfinished_documents_skipped(pdfs)
                task.update_state("cancelled", detail=message)
                self.finished.emit(False, message)
            except Exception as exc:
                if self._current_document and self._current_document not in self._failed_documents:
                    self._failed_documents.append(self._current_document)
                self._mark_unfinished_documents_skipped(pdfs)
                self.log.emit(traceback.format_exc())
                message = tr(language, "translate_failed", error=exc)
                task.update_state("failed", detail=message)
                self.finished.emit(False, message)
            else:
                message = tr(language, "translate_done")
                task.update_state("completed", detail=message)
                self.finished.emit(True, message)

        self._stop.clear()
        self._log_entries, self._progress, self._workflow_index = [], 0.0, 0
        self._translated_documents, self._failed_documents, self._skipped_documents = [], [], []
        self._current_document = pdfs[0].name
        self._set_preview_text(tr(language, "preview_waiting"), self._current_document)
        self._file_index, self._file_total, self._running = 0, len(pdfs), True
        self._status = tr(language, "translate_started", count=len(pdfs))
        self._log_entries.append(
            log_entry(
                level="info",
                stage="prepare",
                message=self._status,
                document=self._current_document,
                index=len(self._log_entries),
            )
        )
        self.changed.emit()
        task = ManagedWorker(
            name="AcademicPdfTranslation",
            target=worker,
            state_path=self.paths.data("task_state", "literature_translation.json"),
            cancel_event=self._stop,
            metadata={"documents": [pdf.name for pdf in pdfs]},
        )
        self._worker = task
        task.start()
        return True

    @Slot()
    def stop(self) -> None:
        """请求停止翻译。参数：无。返回值：无。"""
        if self._running:
            if self._worker is not None:
                self._worker.request_cancel()
            else:
                self._stop.set()
            self._status = self.locale.textf("request_stop_translate")
            self._log_entries.append(
                log_entry(
                    level="warning",
                    stage="cancel",
                    message=self._status,
                    document=self._current_document,
                    index=len(self._log_entries),
                )
            )
            self._log_entries = self._log_entries[-1000:]
        self.app.set_status(self._status)
        self.changed.emit()

    def shutdown(self, timeout: float = 15.0) -> bool:
        """Request translation cancellation and wait for atomic output writes."""
        return shutdown_workers([self._worker], timeout)
