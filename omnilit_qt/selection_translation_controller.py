from __future__ import annotations

import hashlib
import json
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Property, Signal, Slot
from PySide6.QtWidgets import QApplication

from .background_tasks import ManagedWorker, shutdown_workers
from .pdf_extraction_core import sha256_file


class SelectionTranslationController(QObject):
    """Translate short text selections from the PDF reading surface."""

    changed = Signal()
    _taskFinished = Signal(int, str, str, bool, bool)

    def __init__(self, shell, paths, store, locale) -> None:
        super().__init__()
        self.shell = shell
        self.paths = paths
        self.store = store
        self.locale = locale
        self._translation_controller = None
        self._loading = False
        self._status = "选中文献中的词句后，将在这里显示翻译。"
        self._source_text = ""
        self._translated_text = ""
        self._error_text = ""
        self._cache_hit = False
        self._request_id = 0
        self._worker: ManagedWorker | None = None
        self._cancel = threading.Event()
        self._cache: dict[str, Any] | None = None
        self._taskFinished.connect(self._on_task_finished)

    def setTranslationController(self, controller) -> None:
        self._translation_controller = controller

    @Property(bool, notify=changed)
    def loading(self) -> bool:
        return self._loading

    @Property(str, notify=changed)
    def statusText(self) -> str:
        return self._status

    @Property(str, notify=changed)
    def sourceText(self) -> str:
        return self._source_text

    @Property(str, notify=changed)
    def translatedText(self) -> str:
        return self._translated_text

    @Property(str, notify=changed)
    def errorText(self) -> str:
        return self._error_text

    @Property(bool, notify=changed)
    def cacheHit(self) -> bool:
        return self._cache_hit

    @Property(str, notify=changed)
    def modelLabel(self) -> str:
        config = self._saved_config()
        model = str(config.get("model") or "deepseek-v4-flash").strip()
        base_url = str(config.get("baseUrl") or "https://api.deepseek.com").strip()
        return f"{model} @ {base_url}"

    @Slot()
    def clear(self) -> None:
        self._loading = False
        self._source_text = ""
        self._translated_text = ""
        self._error_text = ""
        self._cache_hit = False
        self._status = "选中文献中的词句后，将在这里显示翻译。"
        self.changed.emit()

    @Slot(str, str, str, result=str)
    def cachedTranslation(self, record_id: str, pdf_path: str, source_text: str, target_language: str = "zh") -> str:
        text = _clean_selection_text(source_text)
        if not _is_meaningful_selection(text):
            return ""
        key = self._cache_key(record_id, pdf_path, text, target_language)
        entry = self._load_cache().get(key, {})
        if isinstance(entry, dict):
            return str(entry.get("translatedText") or "")
        return ""

    @Slot(str, str, result=bool)
    def hasCachedRecord(self, record_id: str, pdf_path: str) -> bool:
        record = str(record_id or "")
        pdf_hash = self._pdf_identity(pdf_path)
        for entry in self._load_cache().values():
            if not isinstance(entry, dict):
                continue
            if str(entry.get("recordId") or "") == record and str(entry.get("pdfHash") or "") == pdf_hash:
                return True
        return False

    @Slot(str, result=bool)
    def copyText(self, text: str) -> bool:
        value = str(text or "")
        if not value:
            return False
        app = QApplication.instance()
        if app is None:
            return False
        app.clipboard().setText(value)
        self._status = "已复制到剪贴板。"
        self.changed.emit()
        return True

    @Slot(str, str, str, str)
    def translateSelection(self, record_id: str, pdf_path: str, source_text: str, target_language: str = "zh") -> None:
        self._translate_selection(record_id, pdf_path, source_text, target_language, use_cache=True)

    @Slot(str, str, str, str)
    def retranslateSelection(self, record_id: str, pdf_path: str, source_text: str, target_language: str = "zh") -> None:
        self._translate_selection(record_id, pdf_path, source_text, target_language, use_cache=False)

    def _translate_selection(self, record_id: str, pdf_path: str, source_text: str, target_language: str = "zh", *, use_cache: bool) -> None:
        text = _clean_selection_text(source_text)
        target = "en" if str(target_language or "").strip().lower() == "en" else "zh"
        self._request_id += 1
        request_id = self._request_id

        if not _is_meaningful_selection(text):
            self._loading = False
            self._source_text = text
            self._translated_text = ""
            self._error_text = "选区太短或缺少可翻译内容。"
            self._cache_hit = False
            self._status = self._error_text
            self.changed.emit()
            return

        cached = self.cachedTranslation(record_id, pdf_path, text, target) if use_cache else ""
        self._source_text = text
        self._translated_text = cached
        self._error_text = ""
        self._cache_hit = bool(cached)
        if cached:
            self._loading = False
            self._status = "已从缓存读取译文。"
            self.changed.emit()
            return

        if self._translation_controller is None:
            self._loading = False
            self._translated_text = ""
            self._error_text = "请先在翻译页配置模型与 API Key。"
            self._status = self._error_text
            self.changed.emit()
            return

        if self._worker is not None and self._worker.is_alive():
            self._worker.request_cancel()
        self._cancel = threading.Event()
        self._loading = True
        self._cache_hit = False
        self._status = "正在翻译选中文本..."
        self.changed.emit()

        def run() -> None:
            try:
                if self._cancel.is_set():
                    return
                translated = str(self._translation_controller.translateSnippet(text, target) or "").strip()
                if self._cancel.is_set():
                    return
                if translated:
                    self._write_cache_entry(record_id, pdf_path, text, target, translated)
                    self._taskFinished.emit(request_id, translated, "翻译完成。", True, False)
                else:
                    message = self._friendly_error(str(getattr(self._translation_controller, "statusText", "") or "翻译失败。"))
                    self._taskFinished.emit(request_id, "", message, False, False)
            except Exception as exc:
                self._taskFinished.emit(request_id, "", self._friendly_error(str(exc)), False, False)

        self._worker = ManagedWorker(
            name="SelectionTranslation",
            target=run,
            state_path=self._task_state_path(),
            cancel_event=self._cancel,
            metadata={"record_id": str(record_id or ""), "target_language": target},
        )
        self._worker.start()

    def _on_task_finished(self, request_id: int, translated: str, message: str, ok: bool, cache_hit: bool) -> None:
        if int(request_id) != self._request_id:
            return
        self._loading = False
        self._translated_text = str(translated or "")
        self._error_text = "" if ok else str(message or "翻译失败。")
        self._cache_hit = bool(cache_hit)
        self._status = str(message or ("翻译完成。" if ok else "翻译失败。"))
        self.changed.emit()

    def _task_state_path(self) -> Path:
        if hasattr(self.paths, "runtime"):
            return self.paths.runtime("task_state", "selection_translation.json")
        return self.paths.data("task_state", "selection_translation.json")

    def _cache_path(self) -> Path:
        if hasattr(self.paths, "cache"):
            return self.paths.cache("translate", "selection_cache", "selection_translation_cache.json")
        return self.paths.data("Translate", "selection_cache", "selection_translation_cache.json")

    def _load_cache(self) -> dict[str, Any]:
        if self._cache is not None:
            return self._cache
        path = self._cache_path()
        if not path.exists():
            self._cache = {}
            return self._cache
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            self._cache = {}
            return self._cache
        self._cache = dict(payload.get("items") or payload) if isinstance(payload, dict) else {}
        return self._cache

    def _save_cache(self) -> None:
        path = self._cache_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": 1, "items": self._load_cache()}
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    def _write_cache_entry(self, record_id: str, pdf_path: str, source_text: str, target_language: str, translated: str) -> None:
        key = self._cache_key(record_id, pdf_path, source_text, target_language)
        self._load_cache()[key] = {
            "recordId": str(record_id or ""),
            "pdfHash": self._pdf_identity(pdf_path),
            "sourceHash": _hash_text(source_text),
            "sourceText": source_text,
            "targetLanguage": "en" if str(target_language or "").lower() == "en" else "zh",
            "profileHash": self._profile_hash(),
            "translatedText": translated,
            "updatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        self._save_cache()

    def _cache_key(self, record_id: str, pdf_path: str, source_text: str, target_language: str) -> str:
        parts = [
            str(record_id or ""),
            self._pdf_identity(pdf_path),
            _hash_text(source_text),
            "en" if str(target_language or "").lower() == "en" else "zh",
            self._profile_hash(),
        ]
        return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()

    def _pdf_identity(self, pdf_path: str) -> str:
        source = Path(str(pdf_path or "")).expanduser()
        if source.exists():
            try:
                return sha256_file(source)
            except Exception:
                pass
        return _hash_text(str(source))

    def _saved_config(self) -> dict[str, Any]:
        if self._translation_controller is None:
            return {}
        try:
            return dict(getattr(self._translation_controller, "savedConfig", {}) or {})
        except Exception:
            return {}

    def _profile_hash(self) -> str:
        config = self._saved_config()
        profile = {
            "model": str(config.get("model") or "deepseek-v4-flash").strip(),
            "baseUrl": str(config.get("baseUrl") or "https://api.deepseek.com").strip(),
            "customService": bool(config.get("customService", True)),
            "glossaryPaths": config.get("glossaryPaths") or "",
        }
        return _hash_text(json.dumps(profile, ensure_ascii=False, sort_keys=True))

    @staticmethod
    def _friendly_error(message: str) -> str:
        text = str(message or "").strip()
        if re.search(r"api key|key is not set|api_key", text, re.I):
            return "请先在翻译页配置模型与 API Key。"
        return text or "翻译失败。"

    def shutdown(self, timeout: float = 15.0) -> bool:
        return shutdown_workers([self._worker], timeout)


def _hash_text(text: str) -> str:
    return hashlib.sha256(str(text or "").encode("utf-8")).hexdigest()


def _clean_selection_text(text: str) -> str:
    value = str(text or "").replace("\x00", " ")
    value = re.sub(r"(?<=\w)-\s*\n\s*(?=\w)", "", value)
    value = re.sub(r"[ \t\r\f\v]+", " ", value)
    value = re.sub(r"\s*\n\s*", " ", value)
    return value.strip()


def _is_meaningful_selection(text: str) -> bool:
    value = str(text or "").strip()
    if len(value) < 2:
        return False
    return bool(re.search(r"[\w\u4e00-\u9fff]", value))
