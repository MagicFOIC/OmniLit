from __future__ import annotations

import json
import hashlib
import re
import shutil
import threading
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Property, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices, QImage
from PySide6.QtWidgets import QApplication

from .background_tasks import ManagedWorker, shutdown_workers
from .chart_digitizer_core import analyze_chart_element
from .chart_digitizer_schema import chart_result_to_json, normalize_sample_count, validate_chart_result, write_chart_result
from .pdf_extraction_core import sha256_file
from .pdf_extraction_engines import (
    HybridExtractionPipeline,
    MinerUExtractionEngine,
    PaddleOCRVLExtractionEngine,
    PyMuPDFExtractionEngine,
)
from .pdf_extraction_settings import (
    MINERU_API_URL_DEFAULT,
    PADDLEOCR_API_URL_DEFAULT,
    PARSER_CONFIG_VERSION,
    clear_parser_token,
    engine_status,
    normalize_engine_id,
    parser_api_token,
    parser_api_url,
    parser_service_enabled,
    save_parser_service,
)


OVERRIDE_FIELDS = {
    "type",
    "bbox",
    "caption",
    "captionBBox",
    "text",
    "latex",
    "markdown",
    "table",
    "needsReview",
    "qualityFlags",
    "structureType",
    "metadata",
}


class PdfExtractionController(QObject):
    changed = Signal()
    analysisReady = Signal(str)
    chartDataReady = Signal(str)
    elementFocused = Signal(str, int, "QVariantList")
    pageRenderReady = Signal(str, int, int, str)
    textWordsReady = Signal(str, str, int, "QVariantList")
    _taskFinished = Signal(int, str, object, str, bool)
    _pageRenderFinished = Signal(str, int, int, str, bool, str)
    _textWordsFinished = Signal(str, str, int, object, bool, str)

    def __init__(self, shell, paths, store, locale) -> None:
        super().__init__()
        self.shell = shell
        self.paths = paths
        self.store = store
        self.locale = locale
        self._loading = False
        self._status = ""
        self._progress = ""
        self._elements: list[dict[str, Any]] = []
        self._selected: dict[str, Any] = {}
        self._current_pdf_path = ""
        self._current_record_id = ""
        self._page_count = 0
        self._pages: list[dict[str, Any]] = []
        self._indexes: dict[str, dict[str, Any]] = {}
        self._pdf_paths: dict[str, str] = {}
        self._chart_results: dict[str, dict[str, Any]] = {}
        self._chart_calibrations: dict[str, dict[str, Any]] = {}
        self._text_word_cache: dict[tuple[str, str, int], list[dict[str, Any]]] = {}
        self._pending_engines: dict[str, str] = {}
        self._worker: ManagedWorker | None = None
        self._page_render_workers: dict[tuple[str, int, int], ManagedWorker] = {}
        self._text_word_workers: dict[tuple[str, str, int], ManagedWorker] = {}
        self._analysis_request_id = 0
        self._stop = threading.Event()
        self._parser_settings_status = ""
        self._taskFinished.connect(self._on_task_finished)
        self._pageRenderFinished.connect(self._on_page_render_finished)
        self._textWordsFinished.connect(self._on_text_words_finished)

    @staticmethod
    def _safe_record_id(record_id: str) -> str:
        value = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(record_id or "record")).strip("._")
        value = value[:72] or "record"
        suffix = hashlib.sha1(str(record_id).encode("utf-8")).hexdigest()[:8]
        return f"{value}_{suffix}"

    def _record_dir(self, record_id: str) -> Path:
        if hasattr(self.paths, "content"):
            return self.paths.content("literature", "extractions", self._safe_record_id(record_id))
        return self.paths.data("Literature", "extractions", self._safe_record_id(record_id))

    def _task_state_path(self, name: str) -> Path:
        if hasattr(self.paths, "runtime"):
            return self.paths.runtime("task_state", name)
        return self.paths.data("task_state", name)

    def _index_path(self, record_id: str, engine: str = "active") -> Path:
        if engine and engine != "active":
            return self._record_dir(record_id) / "engines" / self._engine_cache_key(engine) / "extraction_index.json"
        return self._record_dir(record_id) / "extraction_index.json"

    def _engine_output_dir(self, record_id: str, engine: str) -> Path:
        return self._record_dir(record_id) / "engines" / self._engine_cache_key(engine)

    def _overrides_path(self, record_id: str) -> Path:
        return self._record_dir(record_id) / "overrides.json"

    def _chart_result_path(self, record_id: str, element_id: str) -> Path | None:
        if not record_id or self.paths is None:
            return None
        safe_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(element_id or "element")).strip("._") or "element"
        return self._record_dir(record_id) / "charts" / f"{safe_id}.chart_data.json"

    def _chart_calibration_path(self, record_id: str, element_id: str) -> Path | None:
        if not record_id or self.paths is None:
            return None
        safe_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(element_id or "element")).strip("._") or "element"
        return self._record_dir(record_id) / "charts" / f"{safe_id}.calibration.json"

    @staticmethod
    def _engine_cache_key(engine: str) -> str:
        selected = normalize_engine_id(engine)
        if selected == "fast":
            return "pymupdf"
        return selected or "pymupdf"

    def _clear_current_index_state(self, record_id: str = "", pdf_path: str = "") -> None:
        self._current_record_id = str(record_id or "")
        self._current_pdf_path = str(pdf_path or "")
        self._page_count = 0
        self._pages = []
        self._elements = []
        self._selected = {}
        self._chart_results = {}
        self._chart_calibrations = {}

    def _set_index(self, record_id: str, index: dict[str, Any]) -> None:
        key = str(record_id)
        index = self._apply_element_overrides(key, index)
        self._indexes[key] = index
        self._current_record_id = key
        self._current_pdf_path = str(index.get("sourcePath") or self._pdf_paths.get(key, ""))
        self._page_count = int(index.get("pageCount") or 0)
        self._pages = [dict(item) for item in index.get("pages") or []]
        self._elements = [dict(item) for item in index.get("elements") or []]
        self._chart_results = {}
        self._chart_calibrations = {}
        if self._selected and not any(item.get("id") == self._selected.get("id") for item in self._elements):
            self._selected = {}

    def _load_index_file(self, record_id: str, engine: str = "active") -> dict[str, Any]:
        path = self._index_path(record_id, engine)
        if not path.exists():
            return {}
        with path.open("r", encoding="utf-8") as handle:
            index = json.load(handle)
        if not isinstance(index, dict):
            return {}
        if self._is_legacy_cloud_index(index):
            if engine != "active":
                return {}
            fast_path = self._index_path(record_id, "fast")
            if not fast_path.exists():
                return {}
            with fast_path.open("r", encoding="utf-8") as handle:
                fast_index = json.load(handle)
            return self._apply_element_overrides(record_id, fast_index) if isinstance(fast_index, dict) else {}
        return self._apply_element_overrides(record_id, index)

    @staticmethod
    def _is_legacy_cloud_index(index: dict[str, Any]) -> bool:
        engines = {str(index.get("engine") or "")}
        engines.update(str(item) for item in index.get("engineChain") or [])
        is_cloud_engine = bool(engines.intersection({"mineru", "paddleocr_vl", "fusion"}))
        return is_cloud_engine and index.get("parserConfigVersion") != PARSER_CONFIG_VERSION

    def _write_active_index(self, record_id: str, index: dict[str, Any], source_engine: str = "") -> None:
        index = self._apply_element_overrides(record_id, index)
        record_dir = self._record_dir(record_id)
        record_dir.mkdir(parents=True, exist_ok=True)
        active_path = self._index_path(record_id)
        with active_path.open("w", encoding="utf-8") as handle:
            json.dump(index, handle, ensure_ascii=False, indent=2)
        cache_key = self._engine_cache_key(source_engine or str(index.get("engine") or "active"))
        engine_path = self._index_path(record_id, cache_key)
        if engine_path != active_path:
            engine_path.parent.mkdir(parents=True, exist_ok=True)
            with engine_path.open("w", encoding="utf-8") as handle:
                json.dump(index, handle, ensure_ascii=False, indent=2)

    def _load_element_overrides(self, record_id: str) -> dict[str, dict[str, Any]]:
        path = self._overrides_path(record_id)
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        elements = payload.get("elements") if isinstance(payload, dict) else {}
        if not isinstance(elements, dict):
            return {}
        result: dict[str, dict[str, Any]] = {}
        for element_id, entry in elements.items():
            if not isinstance(entry, dict):
                continue
            fields = entry.get("fields")
            if isinstance(fields, dict):
                result[str(element_id)] = {"fields": dict(fields), "updatedAt": str(entry.get("updatedAt") or "")}
        return result

    def _write_element_overrides(self, record_id: str, overrides: dict[str, dict[str, Any]]) -> None:
        path = self._overrides_path(record_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": 1, "elements": overrides}
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _apply_element_overrides(self, record_id: str, index: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(index, dict):
            return {}
        overrides = self._load_element_overrides(record_id)
        if not overrides:
            return index
        result = deepcopy(index)
        for element in result.get("elements") or []:
            if not isinstance(element, dict):
                continue
            element_id = str(element.get("id") or "")
            entry = overrides.get(element_id)
            if not entry:
                continue
            _apply_override_fields(element, entry.get("fields") or {}, entry.get("updatedAt") or "")
        result["hasManualOverrides"] = True
        return result

    @staticmethod
    def _has_renderable_pages(index: dict[str, Any]) -> bool:
        try:
            page_count = int(index.get("pageCount") or 0)
        except (TypeError, ValueError):
            page_count = 0
        pages = index.get("pages") or []
        return page_count > 0 and isinstance(pages, list) and len(pages) > 0

    @staticmethod
    def _same_path(left: Path, right: Path) -> bool:
        try:
            if left.exists() and right.exists():
                return left.resolve() == right.resolve()
        except OSError:
            pass
        return str(left.expanduser()) == str(right.expanduser())

    def _index_matches_pdf(self, index: dict[str, Any], pdf_path: Path, *, verify_sha: bool = True) -> tuple[bool, str]:
        if not self._has_renderable_pages(index):
            return False, "PDF extraction index is invalid."

        if not pdf_path.exists():
            return False, "PDF extraction index is invalid."

        indexed_source_value = str(index.get("sourcePath") or "").strip()
        if indexed_source_value:
            indexed_source = Path(indexed_source_value).expanduser()
            if not self._same_path(pdf_path, indexed_source):
                return False, "PDF extraction index is invalid."

        indexed_sha = str(index.get("sourceSha256") or "").strip()
        if indexed_sha and verify_sha:
            try:
                current_sha = sha256_file(pdf_path)
            except Exception as exc:
                return False, f"Unable to verify PDF fingerprint: {exc}"
            if current_sha != indexed_sha:
                return False, "PDF extraction index is invalid."

        return True, ""

    @staticmethod
    def _render_scale(zoom: float) -> float:
        return max(0.5, min(4.0, float(zoom or 1.0)))

    @staticmethod
    def _render_scale_key(scale: float) -> int:
        return int(round(float(scale or 1.0) * 100))

    def _page_image_path(self, record_id: str, page_index: int, scale: float) -> Path:
        return self._record_dir(record_id) / "pages" / f"page_{page_index + 1:04d}_z{self._render_scale_key(scale)}.png"

    def _pdf_path_for_record(self, record_id: str) -> Path:
        key = str(record_id)
        known = str(self._pdf_paths.get(key, "")).strip()
        if known:
            return Path(known)
        if key not in self._indexes:
            self.loadIndex(key)
        return Path(str(self._indexes.get(key, {}).get("sourcePath") or self._pdf_paths.get(key, "")))

    @staticmethod
    def _is_page_image_fresh(image_path: Path, pdf_path: Path) -> bool:
        return image_path.exists() and pdf_path.exists() and image_path.stat().st_mtime >= pdf_path.stat().st_mtime

    @staticmethod
    def _render_pdf_page_to_file(pdf_path: Path, page_index: int, scale: float, image_path: Path) -> None:
        import fitz

        image_path.parent.mkdir(parents=True, exist_ok=True)
        with fitz.open(pdf_path) as document:
            if page_index >= len(document):
                raise IndexError("PDF page index out of range.")
            pixmap = document.load_page(page_index).get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
            pixmap.save(str(image_path))

    @Property(bool, notify=changed)
    def loading(self) -> bool:
        return self._loading

    @Property(str, notify=changed)
    def statusText(self) -> str:
        return self._status

    @Property(str, notify=changed)
    def progressText(self) -> str:
        return self._progress

    @Property("QVariantList", notify=changed)
    def elements(self) -> list[dict[str, Any]]:
        return list(self._elements)

    @Property("QVariantMap", notify=changed)
    def selectedElement(self) -> dict[str, Any]:
        return dict(self._selected)

    @Property(str, notify=changed)
    def currentPdfPath(self) -> str:
        return self._current_pdf_path

    @Property(int, notify=changed)
    def pageCount(self) -> int:
        return self._page_count

    @Property("QVariantList", notify=changed)
    def pages(self) -> list[dict[str, Any]]:
        return list(self._pages)

    @Slot(result="QVariantMap")
    def engineStatus(self) -> dict[str, Any]:
        return engine_status(self.store)

    @Property(str, notify=changed)
    def mineruApiUrl(self) -> str:
        return parser_api_url(self.store, "mineru") if self.store is not None else MINERU_API_URL_DEFAULT

    @Property(str, notify=changed)
    def paddleocrApiUrl(self) -> str:
        return parser_api_url(self.store, "paddleocr_vl") if self.store is not None else PADDLEOCR_API_URL_DEFAULT

    @Property(bool, notify=changed)
    def mineruTokenConfigured(self) -> bool:
        return bool(parser_api_token(self.store, "mineru"))

    @Property(bool, notify=changed)
    def paddleocrTokenConfigured(self) -> bool:
        return bool(parser_api_token(self.store, "paddleocr_vl"))

    @Property(bool, notify=changed)
    def mineruApiEnabled(self) -> bool:
        return parser_service_enabled(self.store, "mineru")

    @Property(bool, notify=changed)
    def paddleocrApiEnabled(self) -> bool:
        return parser_service_enabled(self.store, "paddleocr_vl")

    @Property(str, notify=changed)
    def parserSettingsStatus(self) -> str:
        return self._parser_settings_status

    @Slot(str, str, str, bool, result=bool)
    def saveParserService(self, engine: str, api_url: str, token: str, enabled: bool) -> bool:
        selected = normalize_engine_id(engine)
        if self.store is None or selected not in {"mineru", "paddleocr_vl"}:
            return False
        url = str(api_url or "").strip()
        if not url.startswith(("https://", "http://")):
            self._parser_settings_status = "Parser settings updated."
            self.changed.emit()
            return False
        save_parser_service(self.store, selected, url, str(token or ""), bool(enabled))
        self._parser_settings_status = "Parser settings updated."
        self.changed.emit()
        return True

    @Slot(str, result=bool)
    def clearParserServiceToken(self, engine: str) -> bool:
        selected = normalize_engine_id(engine)
        if self.store is None or selected not in {"mineru", "paddleocr_vl"}:
            return False
        clear_parser_token(self.store, selected)
        self._parser_settings_status = "Parser settings updated."
        self.changed.emit()
        return True

    @Slot(str, result=bool)
    def testParserService(self, engine: str) -> bool:
        selected = normalize_engine_id(engine)
        status = self.engineStatus().get(selected, {})
        ok = bool(status.get("available"))
        self._parser_settings_status = "Parser service is available." if ok else str(status.get("message") or "Parser service is not configured.")
        self.changed.emit()
        return ok

    @Property("QVariantMap", notify=changed)
    def currentIndex(self) -> dict[str, Any]:
        if not self._current_record_id:
            return {}
        return dict(self._indexes.get(self._current_record_id, {}))

    @Property(str, notify=changed)
    def currentEngine(self) -> str:
        return str(self.currentIndex.get("engine") or "")

    @Property(str, notify=changed)
    def markdownPath(self) -> str:
        return str(self.currentIndex.get("markdownPath") or "")

    @Property("QVariantList", notify=changed)
    def engineErrors(self) -> list[dict[str, Any]]:
        return [dict(item) for item in self.currentIndex.get("engineErrors") or [] if isinstance(item, dict)]

    @Slot(str, str, result=bool)
    def analyzeRecord(self, record_id: str, pdf_path: str) -> bool:
        return self.analyzeRecordWithEngine(record_id, pdf_path, "fast")

    @Slot(result=bool)
    def cancelAnalysis(self) -> bool:
        if not self._loading:
            return False
        self._stop.set()
        self._status = "正在取消 PDF 云解析..."
        self.changed.emit()
        return True

    @Slot()
    def clearPdfSession(self) -> None:
        if self._loading:
            self.cancelAnalysis()
        self._analysis_request_id += 1
        self._loading = False
        self._progress = ""
        self._pending_engines = {}
        self._clear_current_index_state()
        self._status = "PDF extraction status updated."
        self.changed.emit()

    @Slot(str, str)
    def preparePdfSession(self, record_id: str, pdf_path: str) -> None:
        if self._loading:
            self.cancelAnalysis()
        self._analysis_request_id += 1
        key = str(record_id or "").strip()
        source = Path(str(pdf_path or "")).expanduser()
        self._loading = False
        self._progress = ""
        self._pending_engines = {}
        if key and source.exists():
            self._pdf_paths[key] = str(source)
            self._clear_current_index_state(key, str(source))
        else:
            self._clear_current_index_state()
        self._status = "PDF extraction status updated."
        self.changed.emit()

    @Slot(str, str, str, result=bool)
    def selectExtractionEngine(self, record_id: str, pdf_path: str, engine: str) -> bool:
        key = str(record_id or "").strip()
        source = Path(str(pdf_path or "")).expanduser()
        selected_engine = normalize_engine_id(str(engine or "fast"))
        if not key or not source.exists():
            self._status = "PDF extraction status updated."
            self.changed.emit()
            return False
        cached = self._load_index_file(key, selected_engine)
        if cached:
            ok, reason = self._index_matches_pdf(cached, source)
            if ok:
                self._pdf_paths[key] = str(source)
                self._write_active_index(key, cached, selected_engine)
                self._set_index(key, cached)
                self._status = "Loaded cached extraction index."
                self.changed.emit()
                self.analysisReady.emit(key)
                return True
            self._status = reason
            self.changed.emit()
        if self._loading:
            self.cancelAnalysis()
        return self.analyzeRecordWithEngine(key, str(source), selected_engine)

    @Slot(str, str, str, result=bool)
    def analyzeRecordWithEngine(self, record_id: str, pdf_path: str, engine: str) -> bool:
        key = str(record_id or "").strip()
        source = Path(str(pdf_path or "")).expanduser()
        selected_engine = normalize_engine_id(str(engine or "fast"))
        if not key or not source.exists():
            self._status = "PDF extraction status updated."
            self.changed.emit()
            return False

        if self._loading:
            self.cancelAnalysis()

        self._analysis_request_id += 1
        request_id = self._analysis_request_id
        cancel_event = threading.Event()

        self._loading = True
        self._progress = "正在后台解析 PDF..."
        self._status = self._progress
        self._stop = cancel_event
        self._pdf_paths[key] = str(source)
        self._pending_engines[key] = selected_engine
        if selected_engine == "fast" or self._page_count <= 0:
            self._clear_current_index_state(key, str(source))
        else:
            self._current_record_id = key
            self._current_pdf_path = str(source)
        self.changed.emit()

        def run() -> None:
            try:
                def progress(name: str, percent: int, message: str) -> None:
                    if request_id != self._analysis_request_id:
                        return
                    self._progress = str(message or "")
                    self.changed.emit()

                pipeline = HybridExtractionPipeline(
                    engines=[
                        PaddleOCRVLExtractionEngine(store=self.store),
                        MinerUExtractionEngine(store=self.store),
                    ],
                    fallback_engine=PyMuPDFExtractionEngine(),
                )
                record_dir = self._record_dir(key)
                output_dir = self._engine_output_dir(key, selected_engine)
                index = pipeline.analyze(
                    source,
                    output_dir,
                    {
                        "engine": selected_engine,
                        "record_dir": str(record_dir),
                        "progress_callback": progress,
                        "cancel_event": cancel_event,
                    },
                )
                task.update_state("completed", detail="PDF extraction completed.")
                self._taskFinished.emit(request_id, key, index, "PDF extraction completed.", True)
            except Exception as exc:
                message = f"PDF extraction failed: {exc}"
                task.update_state("failed", detail=message)
                self._taskFinished.emit(request_id, key, {}, message, False)

        task = ManagedWorker(
            name="PdfExtractionAnalyze",
            target=run,
            state_path=self._task_state_path(f"pdf_extraction_{self._safe_record_id(key)}.json"),
            cancel_event=cancel_event,
            metadata={"record_id": key, "pdf_path": str(source), "engine": selected_engine},
        )
        self._worker = task
        task.start()
        return True

    @Slot(str, result=bool)
    @Slot(str, str, result=bool)
    @Slot(str, str, str, result=bool)
    def loadIndex(self, record_id: str, pdf_path: str = "", engine: str = "active") -> bool:
        try:
            key = str(record_id or "").strip()
            selected_engine = normalize_engine_id(engine) if engine and engine != "active" else "active"
            index = self._load_index_file(key, selected_engine)
            if not index or not self._has_renderable_pages(index):
                self._status = "PDF extraction status updated."
                self.changed.emit()
                return False

            known_pdf = str(pdf_path or self._pdf_paths.get(key, "")).strip()
            if known_pdf:
                ok, reason = self._index_matches_pdf(index, Path(known_pdf).expanduser())
                if not ok:
                    self._status = reason
                    self.changed.emit()
                    return False
                self._pdf_paths[key] = known_pdf

            self._set_index(key, index)
            if selected_engine != "active":
                self._write_active_index(key, index, selected_engine)
            self._status = "PDF extraction status updated."
            self.changed.emit()
            return True
        except Exception as exc:
            self._status = f"Failed to load extraction index: {exc}"
            self.changed.emit()
            return False

    @Slot(str, str, result=bool)
    def loadIndexForPdf(self, record_id: str, pdf_path: str) -> bool:
        return self._load_index_for_pdf(record_id, pdf_path, verify_sha=True)

    @Slot(str, str, result=bool)
    def loadIndexForPdfQuick(self, record_id: str, pdf_path: str) -> bool:
        return self._load_index_for_pdf(record_id, pdf_path, verify_sha=False)

    @Slot(str, str, result=bool)
    def loadPdfPagesForTranslation(self, record_id: str, pdf_path: str) -> bool:
        key = str(record_id or "").strip()
        source = Path(str(pdf_path or "")).expanduser()
        if not key or not source.exists():
            self._status = "PDF extraction status updated."
            self.changed.emit()
            return False
        try:
            import fitz

            pages: list[dict[str, Any]] = []
            with fitz.open(source) as document:
                for page_index, page in enumerate(document):
                    rect = page.rect
                    pages.append(
                        {
                            "page": page_index,
                            "width": float(rect.width),
                            "height": float(rect.height),
                            "rect": [float(rect.x0), float(rect.y0), float(rect.x1), float(rect.y1)],
                        }
                    )
            self._pdf_paths[key] = str(source)
            self._current_record_id = key
            self._current_pdf_path = str(source)
            self._page_count = len(pages)
            self._pages = pages
            self._elements = []
            self._selected = {}
            self._status = "PDF pages loaded for translation."
            self.changed.emit()
            return bool(pages)
        except Exception as exc:
            self._status = f"Failed to load PDF pages: {exc}"
            self.changed.emit()
            return False

    def _load_index_for_pdf(self, record_id: str, pdf_path: str, *, verify_sha: bool) -> bool:
        try:
            key = str(record_id or "").strip()
            source = Path(str(pdf_path or "")).expanduser()
            if not key:
                self._status = "PDF extraction status updated."
                self.changed.emit()
                return False

            index = self._load_index_file(key)
            if not index:
                self._status = "PDF extraction status updated."
                self.changed.emit()
                return False

            ok, reason = self._index_matches_pdf(index, source, verify_sha=verify_sha)
            if not ok:
                self._status = reason
                self.changed.emit()
                return False

            self._pdf_paths[key] = str(source)
            self._set_index(key, index)
            self._status = "PDF extraction status updated."
            self.changed.emit()
            return True
        except Exception as exc:
            self._status = f"Failed to load extraction index: {exc}"
            self.changed.emit()
            return False

    @Slot(str, result="QVariantList")
    def elementsFor(self, record_id: str) -> list[dict[str, Any]]:
        key = str(record_id)
        if key not in self._indexes:
            self.loadIndex(key)
        index = self._indexes.get(key, {})
        return [dict(item) for item in index.get("elements") or []]

    @Slot(str, result="QVariantList")
    def pagesFor(self, record_id: str) -> list[dict[str, Any]]:
        key = str(record_id)
        if key not in self._indexes:
            self.loadIndex(key)
        index = self._indexes.get(key, {})
        return [dict(item) for item in index.get("pages") or []]

    @Slot(str, str, result="QVariantList")
    def textBlocksForPdf(self, record_id: str, pdf_path: str) -> list[dict[str, Any]]:
        """Return positioned text blocks for the selection translation overlay."""
        source = Path(str(pdf_path or "")).expanduser()
        if not source.exists():
            self._status = "PDF extraction status updated."
            self.changed.emit()
            return []

        try:
            import fitz

            blocks: list[dict[str, Any]] = []
            with fitz.open(source) as document:
                for page_index, page in enumerate(document):
                    rect = page.rect
                    page_size = [float(rect.width), float(rect.height)]
                    for block_index, block in enumerate(page.get_text("blocks") or []):
                        if len(block) < 5:
                            continue
                        block_type = int(block[6]) if len(block) > 6 else 0
                        if block_type != 0:
                            continue
                        text = _clean_text_block(str(block[4] or ""))
                        if len(text) < 2:
                            continue
                        bbox = [float(block[0]), float(block[1]), float(block[2]), float(block[3])]
                        if bbox[2] <= bbox[0] or bbox[3] <= bbox[1]:
                            continue
                        blocks.append(
                            {
                                "id": f"text_{page_index}_{block_index}",
                                "type": "text",
                                "page": page_index,
                                "bbox": bbox,
                                "pageSize": page_size,
                                "text": text,
                            }
                        )
            self._status = "PDF text blocks loaded."
            self.changed.emit()
            return blocks
        except Exception as exc:
            self._status = f"Failed to read PDF text blocks: {exc}"
            self.changed.emit()
            return []

    @Slot(str, str, int, result="QVariantList")
    def textWordsForPdfPage(self, record_id: str, pdf_path: str, page: int) -> list[dict[str, Any]]:
        """Return positioned word boxes for one PDF page, loaded on demand."""
        try:
            items = self._text_words_for_pdf_page(record_id, pdf_path, page)
            self._status = "PDF text words loaded."
            self.changed.emit()
            return items
        except Exception as exc:
            self._status = f"Failed to read PDF text words: {exc}"
            self.changed.emit()
            return []

    @Slot(str, str, int, result=bool)
    def requestTextWordsForPdfPage(self, record_id: str, pdf_path: str, page: int) -> bool:
        source = Path(str(pdf_path or "")).expanduser()
        page_index = max(0, int(page or 0))
        key = str(record_id or "")
        if not key or not source.exists():
            return False

        cache_key = (key, str(source), page_index)
        if cache_key in self._text_word_cache:
            self.textWordsReady.emit(key, str(source), page_index, [dict(item) for item in self._text_word_cache[cache_key]])
            return True

        existing = self._text_word_workers.get(cache_key)
        if existing is not None and existing.is_alive():
            return True

        def run() -> None:
            try:
                items = self._text_words_for_pdf_page(key, str(source), page_index)
                self._textWordsFinished.emit(key, str(source), page_index, items, True, "")
            except Exception as exc:
                self._textWordsFinished.emit(key, str(source), page_index, [], False, str(exc))

        worker = ManagedWorker(
            name=f"PdfTextWords-{self._safe_record_id(key)}-{page_index + 1}",
            target=run,
            state_path=self._task_state_path(f"pdf_text_words_{self._safe_record_id(key)}_{page_index + 1}.json"),
            metadata={"record_id": key, "pdf_path": str(source), "page": page_index},
        )
        self._text_word_workers[cache_key] = worker
        worker.start()
        return True

    def _text_words_for_pdf_page(self, record_id: str, pdf_path: str, page: int) -> list[dict[str, Any]]:
        source = Path(str(pdf_path or "")).expanduser()
        page_index = max(0, int(page or 0))
        if not source.exists():
            return []

        cache_key = (str(record_id or ""), str(source), page_index)
        if cache_key in self._text_word_cache:
            return [dict(item) for item in self._text_word_cache[cache_key]]

        import fitz

        items: list[dict[str, Any]] = []
        with fitz.open(source) as document:
            if page_index >= len(document):
                return []
            pdf_page = document.load_page(page_index)
            rect = pdf_page.rect
            page_size = [float(rect.width), float(rect.height)]
            for word_index, word in enumerate(pdf_page.get_text("words") or []):
                if len(word) < 5:
                    continue
                text = str(word[4] or "").strip()
                if not text:
                    continue
                bbox = [float(word[0]), float(word[1]), float(word[2]), float(word[3])]
                if bbox[2] <= bbox[0] or bbox[3] <= bbox[1]:
                    continue
                block_no = int(word[5]) if len(word) > 5 else 0
                line_no = int(word[6]) if len(word) > 6 else 0
                word_no = int(word[7]) if len(word) > 7 else word_index
                items.append(
                    {
                        "id": f"word_{page_index}_{block_no}_{line_no}_{word_no}",
                        "type": "word",
                        "page": page_index,
                        "bbox": bbox,
                        "pageSize": page_size,
                        "text": text,
                        "block": block_no,
                        "line": line_no,
                        "word": word_no,
                        "order": word_index,
                    }
                )
        self._text_word_cache[cache_key] = [dict(item) for item in items]
        return items

    @Slot(str, result=bool)
    def focusElement(self, element_id: str) -> bool:
        for element in self._elements:
            if str(element.get("id") or "") == str(element_id):
                self._selected = dict(element)
                page = int(element.get("page") or 0)
                bbox = list(element.get("bbox") or [])
                self.changed.emit()
                self.elementFocused.emit(str(element_id), page, bbox)
                return True
        self._status = "PDF extraction status updated."
        self.changed.emit()
        return False

    @Slot(str, "QVariantMap", result=bool)
    def saveElementOverride(self, element_id: str, fields: dict[str, Any]) -> bool:
        try:
            if not self._current_record_id:
                self._status = "No active extraction index to correct."
                self.changed.emit()
                return False
            element = self._element_by_id(element_id)
            if not element:
                self._status = "Element not found for correction."
                self.changed.emit()
                return False
            clean_fields = _sanitize_override_fields(fields)
            if not clean_fields:
                self._status = "No supported correction fields to save."
                self.changed.emit()
                return False
            overrides = self._load_element_overrides(self._current_record_id)
            updated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
            overrides[str(element_id)] = {
                "fields": clean_fields,
                "originalFields": _snapshot_override_fields(element),
                "updatedAt": updated_at,
            }
            self._write_element_overrides(self._current_record_id, overrides)
            index = self._apply_element_overrides(self._current_record_id, self.currentIndex)
            self._write_active_index(self._current_record_id, index, str(index.get("engine") or "active"))
            self._set_index(self._current_record_id, index)
            self.focusElement(str(element_id))
            self._status = "Element correction saved."
            self.changed.emit()
            return True
        except Exception as exc:
            self._status = f"Failed to save correction: {exc}"
            self.changed.emit()
            return False

    @Slot(str, result=bool)
    def clearElementOverride(self, element_id: str) -> bool:
        try:
            if not self._current_record_id:
                return False
            overrides = self._load_element_overrides(self._current_record_id)
            if str(element_id) not in overrides:
                return False
            del overrides[str(element_id)]
            self._write_element_overrides(self._current_record_id, overrides)
            index = self._load_index_file(self._current_record_id)
            self._write_active_index(self._current_record_id, index, str(index.get("engine") or "active"))
            self._set_index(self._current_record_id, index)
            self._status = "Element correction cleared."
            self.changed.emit()
            return True
        except Exception as exc:
            self._status = f"Failed to clear correction: {exc}"
            self.changed.emit()
            return False
    @Slot(str, str, result=str)
    def exportElement(self, element_id: str, fmt: str) -> str:
        try:
            if str(element_id) == "__all__":
                if not self._current_record_id:
                    self._status = "No extraction result to export."
                    self.changed.emit()
                    return ""
                path = self._record_dir(self._current_record_id)
                path.mkdir(parents=True, exist_ok=True)
                self._status = f"Exported to: {path}"
                self.changed.emit()
                return str(path)

            element = self._element_by_id(element_id)
            if not element:
                self._status = "Element not found for export."
                self.changed.emit()
                return ""

            key = str(fmt or "").lower()
            path = ""
            if key == "csv":
                path = str(element.get("csvPath") or "")
            elif key == "json":
                path = str(element.get("jsonPath") or "")
            elif key in {"png", "image"}:
                if str(element.get("type") or "") == "formula":
                    self._status = "Formula image export is not supported."
                    self.changed.emit()
                    return ""
                path = str(element.get("pngPath") or "")

            if path and Path(path).exists():
                self._status = f"已导出：{path}"
                self.changed.emit()
                return path

            self._status = "PDF extraction status updated."
            self.changed.emit()
            return ""
        except Exception as exc:
            self._status = f"Export failed: {exc}"
            self.changed.emit()
            return ""

    @Slot(str, result=str)
    def exportMarkdown(self, record_id: str) -> str:
        try:
            key = str(record_id or self._current_record_id or "").strip()
            index = self._indexes.get(key) or self._load_index_file(key)
            path = Path(str(index.get("markdownPath") or "")).expanduser()
            if path.exists():
                self._status = f"Exported Markdown: {path}"
                self.changed.emit()
                return str(path)
            self._status = "PDF extraction status updated."
            self.changed.emit()
            return ""
        except Exception as exc:
            self._status = f"Markdown export failed: {exc}"
            self.changed.emit()
            return ""

    @Slot(str, result=str)
    def exportRawOutputDirectory(self, record_id: str) -> str:
        try:
            key = str(record_id or self._current_record_id or "").strip()
            if not key:
                self._status = "PDF extraction status updated."
                self.changed.emit()
                return ""
            path = self._record_dir(key)
            if path.exists():
                self._status = f"已导出原始解析结果目录：{path}"
                self.changed.emit()
                return str(path)
            self._status = "PDF extraction status updated."
            self.changed.emit()
            return ""
        except Exception as exc:
            self._status = f"Raw output export failed: {exc}"
            self.changed.emit()
            return ""

    @Slot(str, result=bool)
    def openExportDirectory(self, path: str) -> bool:
        try:
            raw = str(path or "").strip()
            if not raw:
                self._status = "PDF extraction status updated."
                self.changed.emit()
                return False

            target = Path(raw).expanduser()
            directory = target if target.is_dir() else target.parent
            if not directory.exists():
                self._status = "PDF extraction status updated."
                self.changed.emit()
                return False

            ok = QDesktopServices.openUrl(QUrl.fromLocalFile(str(directory)))
            self._status = f"Opened directory: {directory}" if ok else "Failed to open export directory."
            self.changed.emit()
            return bool(ok)
        except Exception as exc:
            self._status = f"Failed to open export directory: {exc}"
            self.changed.emit()
            return False

    @Slot(str, result=bool)
    def copyElement(self, element_id: str) -> bool:
        try:
            element = self._element_by_id(element_id)
            if not element:
                self._status = "PDF extraction status updated."
                self.changed.emit()
                return False

            clipboard = QApplication.clipboard()
            kind = str(element.get("type") or "")
            if kind == "table":
                rows = element.get("table") or []
                clipboard.setText("\n".join("\t".join(str(cell) for cell in row) for row in rows))
            elif kind == "formula" and str(element.get("text") or "").strip():
                clipboard.setText(str(element.get("text") or ""))
            else:
                image_value = str(element.get("pngPath") or "")
                image_path = Path(image_value) if image_value else None
                if image_path is None or not image_path.exists():
                    self._status = "PDF extraction status updated."
                    self.changed.emit()
                    return False
                clipboard.setImage(QImage(str(image_path)))

            self._status = "PDF extraction status updated."
            self.changed.emit()
            return True
        except Exception as exc:
            self._status = f"Copy failed: {exc}"
            self.changed.emit()
            return False

    @Slot(str, result=bool)
    def copyElementImage(self, element_id: str) -> bool:
        try:
            element = self._element_by_id(element_id)
            if element and str(element.get("type") or "") == "formula":
                self._status = "Formula image copy is not supported."
                self.changed.emit()
                return False

            image_value = str(element.get("pngPath") or "") if element else ""
            image_path = Path(image_value) if image_value else None
            if image_path is None or not image_path.exists():
                self._status = "PDF extraction status updated."
                self.changed.emit()
                return False

            QApplication.clipboard().setImage(QImage(str(image_path)))
            self._status = "PDF extraction status updated."
            self.changed.emit()
            return True
        except Exception as exc:
            self._status = f"Copy image failed: {exc}"
            self.changed.emit()
            return False

    @Slot(str, int, float, result=str)
    def renderPage(self, record_id: str, page: int, zoom: float) -> str:
        try:
            key = str(record_id)
            pdf_path = self._pdf_path_for_record(key)
            if not pdf_path.exists():
                self._status = "PDF extraction status updated."
                self.changed.emit()
                return ""

            page_index = max(0, int(page))
            scale = self._render_scale(zoom)
            image_path = self._page_image_path(key, page_index, scale)

            if not self._is_page_image_fresh(image_path, pdf_path):
                self._render_pdf_page_to_file(pdf_path, page_index, scale, image_path)

            return QUrl.fromLocalFile(str(image_path)).toString()
        except Exception as exc:
            self._status = f"Page render failed: {exc}"
            self.changed.emit()
            return ""

    @Slot(str, int, float, result=str)
    def cachedRenderedPage(self, record_id: str, page: int, zoom: float) -> str:
        try:
            key = str(record_id)
            pdf_path = self._pdf_path_for_record(key)
            if not pdf_path.exists():
                return ""
            page_index = max(0, int(page))
            scale = self._render_scale(zoom)
            image_path = self._page_image_path(key, page_index, scale)
            if self._is_page_image_fresh(image_path, pdf_path):
                return QUrl.fromLocalFile(str(image_path)).toString()
            return ""
        except Exception:
            return ""

    @Slot(str, int, float, result=bool)
    def renderPageAsync(self, record_id: str, page: int, zoom: float) -> bool:
        try:
            key = str(record_id)
            pdf_path = self._pdf_path_for_record(key)
            if not pdf_path.exists():
                return False
            page_index = max(0, int(page))
            scale = self._render_scale(zoom)
            scale_key = self._render_scale_key(scale)
            image_path = self._page_image_path(key, page_index, scale)
            cached = self.cachedRenderedPage(key, page_index, scale)
            if cached:
                self.pageRenderReady.emit(key, page_index, scale_key, cached)
                return True

            task_key = (key, page_index, scale_key)
            existing = self._page_render_workers.get(task_key)
            if existing is not None and existing.is_alive():
                return True

            def run() -> None:
                try:
                    self._render_pdf_page_to_file(pdf_path, page_index, scale, image_path)
                    url = QUrl.fromLocalFile(str(image_path)).toString()
                    self._pageRenderFinished.emit(key, page_index, scale_key, url, True, "")
                except Exception as exc:
                    self._pageRenderFinished.emit(key, page_index, scale_key, "", False, str(exc))

            worker = ManagedWorker(
                name=f"PdfPageRender-{self._safe_record_id(key)}-{page_index + 1}-{scale_key}",
                target=run,
                state_path=self._task_state_path(
                    f"pdf_page_render_{self._safe_record_id(key)}_{page_index + 1}_{scale_key}.json"
                ),
                metadata={"record_id": key, "page": page_index, "scale": scale},
            )
            self._page_render_workers[task_key] = worker
            worker.start()
            return True
        except Exception as exc:
            self._status = f"Page render failed: {exc}"
            self.changed.emit()
            return False

    @Slot(str, result=str)
    def cropElement(self, element_id: str) -> str:
        element = self._element_by_id(element_id)
        path = str(element.get("pngPath") or "") if element else ""
        return QUrl.fromLocalFile(path).toString() if path and Path(path).exists() else ""

    @Slot(str, int, result="QVariantMap")
    def analyzeChartData(self, element_id: str, sample_count: int = 10) -> dict[str, Any]:
        try:
            element = self._element_by_id(element_id)
            if not element:
                self._status = "Element not found for chart analysis."
                self.changed.emit()
                return {}
            calibration = self._load_chart_calibration(str(element_id))
            result = analyze_chart_element(
                element,
                self.currentIndex,
                record_id=self._current_record_id,
                sample_count=normalize_sample_count(sample_count),
                calibration=calibration,
            )
            errors = validate_chart_result(result)
            if errors:
                analysis = dict(result.get("analysis") or {})
                warnings = list(analysis.get("warnings") or [])
                warnings.extend(f"Schema warning: {error}" for error in errors)
                analysis["warnings"] = warnings
                analysis["needsReview"] = True
                analysis["status"] = "需要手动校准"
                result["analysis"] = analysis
            key = str(element_id)
            self._chart_results[key] = result
            result_path = self._chart_result_path(self._current_record_id, key)
            if result_path is not None:
                write_chart_result(result_path, result)
            needs_review = bool((result.get("analysis") or {}).get("needsReview"))
            self._status = "Chart analysis needs manual calibration." if needs_review else "Chart analysis completed."
            self.changed.emit()
            self.chartDataReady.emit(key)
            return result
        except Exception as exc:
            self._status = f"Chart analysis failed: {exc}"
            self.changed.emit()
            return {}

    @Slot(str, result="QVariantMap")
    def chartDataResult(self, element_id: str) -> dict[str, Any]:
        key = str(element_id or "")
        if key in self._chart_results:
            return dict(self._chart_results[key])
        path = self._chart_result_path(self._current_record_id, key)
        if path is None or not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        if isinstance(payload, dict):
            self._chart_results[key] = payload
            return dict(payload)
        return {}

    @Slot(str, result=str)
    def chartDataJson(self, element_id: str) -> str:
        result = self.chartDataResult(element_id)
        return chart_result_to_json(result) if result else ""

    @Slot(str, result=bool)
    def copyChartData(self, element_id: str) -> bool:
        text = self.chartDataJson(element_id)
        if not text:
            self._status = "No chart data to copy."
            self.changed.emit()
            return False
        QApplication.clipboard().setText(text)
        self._status = "Chart data JSON copied."
        self.changed.emit()
        return True

    @Slot(str, result=str)
    def exportChartData(self, element_id: str) -> str:
        result = self.chartDataResult(element_id)
        if not result:
            result = self.analyzeChartData(element_id, 10)
        if not result:
            self._status = "No chart data to export."
            self.changed.emit()
            return ""
        path = self._chart_result_path(self._current_record_id, str(element_id))
        if path is None:
            self._status = "No active extraction directory for chart data export."
            self.changed.emit()
            return ""
        write_chart_result(path, result)
        self._status = f"Exported chart data JSON: {path}"
        self.changed.emit()
        return str(path)

    @Slot(str, "QVariantMap", result=bool)
    def saveChartCalibration(self, element_id: str, calibration_payload: dict[str, Any]) -> bool:
        try:
            key = str(element_id or "")
            if not key or not isinstance(calibration_payload, dict):
                self._status = "Invalid chart calibration."
                self.changed.emit()
                return False
            payload = self._merge_chart_calibration(key, calibration_payload)
            payload["updatedAt"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            self._chart_calibrations[key] = payload
            path = self._chart_calibration_path(self._current_record_id, key)
            if path is not None:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            self._chart_results.pop(key, None)
            self._status = "Chart calibration saved."
            self.changed.emit()
            return True
        except Exception as exc:
            self._status = f"Failed to save chart calibration: {exc}"
            self.changed.emit()
            return False

    def _element_by_id(self, element_id: str) -> dict[str, Any]:
        for element in self._elements:
            if str(element.get("id") or "") == str(element_id):
                return dict(element)
        return {}

    def _merge_chart_calibration(self, element_id: str, calibration_payload: dict[str, Any]) -> dict[str, Any]:
        payload = dict(calibration_payload)
        if "subplotIndex" not in payload:
            return payload
        try:
            subplot_index = max(0, int(payload.get("subplotIndex") or 0))
        except (TypeError, ValueError):
            subplot_index = 0
        subplot_payload = payload.get("calibration")
        if not isinstance(subplot_payload, dict):
            subplot_payload = {key: value for key, value in payload.items() if key not in {"subplotIndex", "calibration"}}
        existing = self._load_chart_calibration(element_id)
        merged = dict(existing) if isinstance(existing, dict) else {}
        subplots = merged.get("subplots")
        if not isinstance(subplots, list):
            subplots = []
        while len(subplots) <= subplot_index:
            subplots.append({})
        subplots[subplot_index] = dict(subplot_payload)
        merged["subplots"] = subplots
        merged["activeSubplotIndex"] = subplot_index
        return merged

    def _load_chart_calibration(self, element_id: str) -> dict[str, Any]:
        key = str(element_id or "")
        if key in self._chart_calibrations:
            return dict(self._chart_calibrations[key])
        path = self._chart_calibration_path(self._current_record_id, key)
        if path is None or not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        if isinstance(payload, dict):
            self._chart_calibrations[key] = payload
            return dict(payload)
        return {}

    def _on_task_finished(self, request_id: int, record_id: str, payload: object, message: str, ok: bool) -> None:
        if int(request_id) != self._analysis_request_id:
            return
        self._loading = False
        self._progress = ""
        if ok and isinstance(payload, dict):
            selected_engine = self._pending_engines.pop(str(record_id), str(payload.get("engine") or "active"))
            self._write_active_index(str(record_id), payload, selected_engine)
            self._set_index(record_id, payload)
            self._status = message
            self.changed.emit()
            self.analysisReady.emit(str(record_id))
        else:
            self._status = "PDF extraction status updated."
            self.changed.emit()

    def _on_page_render_finished(self, record_id: str, page: int, scale_key: int, url: str, ok: bool, message: str) -> None:
        self._page_render_workers.pop((str(record_id), int(page), int(scale_key)), None)
        if ok and url:
            self.pageRenderReady.emit(str(record_id), int(page), int(scale_key), str(url))
            return
        if message:
            self._status = f"Page render failed: {message}"
            self.changed.emit()

    def _on_text_words_finished(self, record_id: str, pdf_path: str, page: int, payload: object, ok: bool, message: str) -> None:
        key = (str(record_id), str(Path(str(pdf_path or "")).expanduser()), int(page))
        self._text_word_workers.pop(key, None)
        if ok and isinstance(payload, list):
            self.textWordsReady.emit(str(record_id), str(pdf_path), int(page), [dict(item) for item in payload if isinstance(item, dict)])
            return
        if message:
            self._status = f"Failed to read PDF text words: {message}"
            self.changed.emit()

    def shutdown(self, timeout: float = 15.0) -> bool:
        return shutdown_workers([self._worker] + list(self._page_render_workers.values()) + list(self._text_word_workers.values()), timeout)


def _sanitize_override_fields(fields: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(fields, dict):
        return {}
    clean: dict[str, Any] = {}
    for key, value in fields.items():
        name = str(key)
        if name not in OVERRIDE_FIELDS:
            continue
        if name in {"bbox", "captionBBox"}:
            clean[name] = _clean_number_list(value)
        elif name == "table":
            clean[name] = _clean_table(value)
        elif name == "qualityFlags":
            clean[name] = [str(item) for item in value or [] if str(item or "").strip()] if isinstance(value, list) else []
        elif name == "metadata":
            clean[name] = dict(value) if isinstance(value, dict) else {}
        elif name == "needsReview":
            clean[name] = bool(value)
        else:
            clean[name] = str(value or "") if value is not None else ""
    return clean


def _snapshot_override_fields(element: dict[str, Any]) -> dict[str, Any]:
    return {field: deepcopy(element.get(field)) for field in OVERRIDE_FIELDS if field in element}


def _apply_override_fields(element: dict[str, Any], fields: dict[str, Any], updated_at: str) -> None:
    clean = _sanitize_override_fields(fields)
    for key, value in clean.items():
        if key == "metadata":
            metadata = dict(element.get("metadata") or {})
            metadata.update(value if isinstance(value, dict) else {})
            element["metadata"] = metadata
        else:
            element[key] = value
    metadata = dict(element.get("metadata") or {})
    metadata["manualOverride"] = True
    if updated_at:
        metadata["overrideUpdatedAt"] = updated_at
    element["metadata"] = metadata
    element["manualOverride"] = True


def _clean_number_list(value: Any) -> list[float]:
    if not isinstance(value, (list, tuple)):
        return []
    result: list[float] = []
    for item in value[:4]:
        try:
            result.append(float(item))
        except (TypeError, ValueError):
            result.append(0.0)
    return result


def _clean_table(value: Any) -> list[list[str]]:
    if not isinstance(value, list):
        return []
    rows: list[list[str]] = []
    for row in value:
        if isinstance(row, list):
            rows.append([str(cell or "") for cell in row])
    return rows


def _clean_text_block(text: str) -> str:
    value = str(text or "").replace("\x00", " ")
    value = re.sub(r"(?<=\w)-\s*\n\s*(?=\w)", "", value)
    value = re.sub(r"[ \t\r\f\v]+", " ", value)
    value = re.sub(r"\s*\n\s*", " ", value)
    return value.strip()
