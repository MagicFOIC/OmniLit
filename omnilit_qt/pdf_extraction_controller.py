from __future__ import annotations

import json
import hashlib
import re
import shutil
import threading
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Property, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices, QImage
from PySide6.QtWidgets import QApplication

from .background_tasks import ManagedWorker, shutdown_workers
from .pdf_extraction_core import sha256_file
from .pdf_extraction_engines import (
    HybridExtractionPipeline,
    MinerUExtractionEngine,
    PaddleOCRVLExtractionEngine,
    PyMuPDFExtractionEngine,
)
from .pdf_extraction_settings import (
    engine_status,
    normalize_engine_id,
)
from .parser_runtime_manager import ParserRuntimeManager


class PdfExtractionController(QObject):
    changed = Signal()
    analysisReady = Signal(str)
    elementFocused = Signal(str, int, "QVariantList")
    runtimeStatusChanged = Signal("QVariantMap")
    runtimeInstallProgress = Signal(str, int, str)
    _taskFinished = Signal(str, object, str, bool)

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
        self._pending_engines: dict[str, str] = {}
        self.runtime_manager = ParserRuntimeManager()
        self._worker: ManagedWorker | None = None
        self._stop = threading.Event()
        self._taskFinished.connect(self._on_task_finished)

    @staticmethod
    def _safe_record_id(record_id: str) -> str:
        value = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(record_id or "record")).strip("._")
        value = value[:72] or "record"
        suffix = hashlib.sha1(str(record_id).encode("utf-8")).hexdigest()[:8]
        return f"{value}_{suffix}"

    def _record_dir(self, record_id: str) -> Path:
        return self.paths.data("Literature", "extractions", self._safe_record_id(record_id))

    def _index_path(self, record_id: str, engine: str = "active") -> Path:
        if engine and engine != "active":
            return self._record_dir(record_id) / "engines" / self._engine_cache_key(engine) / "extraction_index.json"
        return self._record_dir(record_id) / "extraction_index.json"

    def _engine_output_dir(self, record_id: str, engine: str) -> Path:
        return self._record_dir(record_id) / "engines" / self._engine_cache_key(engine)

    @staticmethod
    def _engine_cache_key(engine: str) -> str:
        selected = normalize_engine_id(engine)
        if selected == "fast":
            return "pymupdf"
        if selected == "auto":
            return "fusion"
        return selected or "pymupdf"

    def _clear_current_index_state(self, record_id: str = "", pdf_path: str = "") -> None:
        self._current_record_id = str(record_id or "")
        self._current_pdf_path = str(pdf_path or "")
        self._page_count = 0
        self._pages = []
        self._elements = []
        self._selected = {}

    def _set_index(self, record_id: str, index: dict[str, Any]) -> None:
        key = str(record_id)
        self._indexes[key] = index
        self._current_record_id = key
        self._current_pdf_path = str(index.get("sourcePath") or self._pdf_paths.get(key, ""))
        self._page_count = int(index.get("pageCount") or 0)
        self._pages = [dict(item) for item in index.get("pages") or []]
        self._elements = [dict(item) for item in index.get("elements") or []]
        if self._selected and not any(item.get("id") == self._selected.get("id") for item in self._elements):
            self._selected = {}

    def _load_index_file(self, record_id: str, engine: str = "active") -> dict[str, Any]:
        path = self._index_path(record_id, engine)
        if not path.exists():
            return {}
        with path.open("r", encoding="utf-8") as handle:
            index = json.load(handle)
        return index if isinstance(index, dict) else {}

    def _write_active_index(self, record_id: str, index: dict[str, Any], source_engine: str = "") -> None:
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

    def _index_matches_pdf(self, index: dict[str, Any], pdf_path: Path) -> tuple[bool, str]:
        if not self._has_renderable_pages(index):
            return False, "解析索引为空或不完整，请重新解析。"

        if not pdf_path.exists():
            return False, "无法加载解析索引：本地 PDF 不存在。"

        indexed_source_value = str(index.get("sourcePath") or "").strip()
        if indexed_source_value:
            indexed_source = Path(indexed_source_value).expanduser()
            if not self._same_path(pdf_path, indexed_source):
                return False, "解析索引对应的 PDF 与当前文献不一致，请重新解析。"

        indexed_sha = str(index.get("sourceSha256") or "").strip()
        if indexed_sha:
            try:
                current_sha = sha256_file(pdf_path)
            except Exception as exc:
                return False, f"无法校验 PDF 指纹：{exc}"
            if current_sha != indexed_sha:
                return False, "PDF 文件已变化，请重新解析"

        return True, ""

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
        return engine_status(self.runtime_manager)

    @Slot(str, result=bool)
    def bootstrapEngine(self, engine: str) -> bool:
        selected = normalize_engine_id(engine)
        if self._loading:
            self._status = "PDF 正在解析中，请稍后再初始化解析引擎。"
            self.changed.emit()
            return False

        if selected == "mineru":
            self._loading = True
            self._progress = "正在初始化深度解析组件，首次使用需要下载依赖。"
            self._status = self._progress
            self.changed.emit()

            def run() -> None:
                def progress(name: str, percent: int, message: str) -> None:
                    self.runtimeInstallProgress.emit(name, int(percent), str(message or ""))

                result = self.runtime_manager.ensure_mineru_runtime(progress)
                ok = bool(result.get("available"))
                message = str(result.get("message") or ("MinerU 初始化完成。" if ok else "深度解析初始化失败，已保留快速解析结果。"))
                self._taskFinished.emit("__runtime__", result, message, ok)
                self.runtimeStatusChanged.emit(self.engineStatus())

            task = ManagedWorker(
                name="PdfParserRuntimeBootstrap",
                target=run,
                state_path=self.paths.data("task_state", "pdf_parser_runtime_bootstrap_mineru.json"),
                cancel_event=self._stop,
                metadata={"engine": selected},
            )
            self._worker = task
            task.start()
            return True

        if selected == "paddleocr_vl":
            result = PaddleOCRVLExtractionEngine(runtime_manager=self.runtime_manager).bootstrap_paddleocr_vl_service()
            self._status = str(result.get("message") or "PaddleOCR-VL 高精度引擎未初始化，可通过 Docker 或独立环境启用。")
            self.runtimeStatusChanged.emit(self.engineStatus())
            self.changed.emit()
            return bool(result.get("available"))

        self._status = "该解析引擎无需单独初始化。"
        self.runtimeStatusChanged.emit(self.engineStatus())
        self.changed.emit()
        return True

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

    @Slot(str, str, str, result=bool)
    def selectExtractionEngine(self, record_id: str, pdf_path: str, engine: str) -> bool:
        key = str(record_id or "").strip()
        source = Path(str(pdf_path or "")).expanduser()
        selected_engine = normalize_engine_id(str(engine or "auto"))
        if not key or not source.exists():
            self._status = "无法切换解析引擎：PDF 文件不存在。"
            self.changed.emit()
            return False
        cached = self._load_index_file(key, selected_engine)
        if cached:
            ok, reason = self._index_matches_pdf(cached, source)
            if ok:
                self._pdf_paths[key] = str(source)
                self._write_active_index(key, cached, selected_engine)
                self._set_index(key, cached)
                self._status = "已切换到缓存的解析结果。"
                self.changed.emit()
                self.analysisReady.emit(key)
                return True
            self._status = reason
            self.changed.emit()
        if self._loading:
            self._status = "PDF 正在解析中，请稍候。"
            self.changed.emit()
            return False
        return self.analyzeRecordWithEngine(key, str(source), selected_engine)

    @Slot(str, str, str, result=bool)
    def analyzeRecordWithEngine(self, record_id: str, pdf_path: str, engine: str) -> bool:
        key = str(record_id or "").strip()
        source = Path(str(pdf_path or "")).expanduser()
        selected_engine = normalize_engine_id(str(engine or "auto"))
        if not key or not source.exists():
            self._status = "无法解析：本地 PDF 不存在。"
            self.changed.emit()
            return False

        if self._loading:
            self._status = "PDF 正在解析中，请稍候。"
            self.changed.emit()
            return False

        self._loading = True
        self._progress = "正在后台解析 PDF..."
        self._status = self._progress
        self._stop.clear()
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
                    self._progress = str(message or "")
                    self.runtimeInstallProgress.emit(name, int(percent), str(message or ""))
                    self.changed.emit()

                pipeline = HybridExtractionPipeline(
                    engines=[
                        PaddleOCRVLExtractionEngine(runtime_manager=self.runtime_manager),
                        MinerUExtractionEngine(runtime_manager=self.runtime_manager),
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
                        "runtime_progress_callback": progress,
                    },
                )
                self.runtimeStatusChanged.emit(self.engineStatus())
                task.update_state("completed", detail="PDF 解析完成。")
                self._taskFinished.emit(key, index, "PDF 解析完成。", True)
            except Exception as exc:
                message = f"PDF 解析失败：{exc}"
                task.update_state("failed", detail=message)
                self._taskFinished.emit(key, {}, message, False)

        task = ManagedWorker(
            name="PdfExtractionAnalyze",
            target=run,
            state_path=self.paths.data("task_state", f"pdf_extraction_{self._safe_record_id(key)}.json"),
            cancel_event=self._stop,
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
                self._status = "还没有可用的解析索引，请先解析 PDF。"
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
            self._status = "已加载解析索引。"
            self.changed.emit()
            return True
        except Exception as exc:
            self._status = f"加载解析索引失败：{exc}"
            self.changed.emit()
            return False

    @Slot(str, str, result=bool)
    def loadIndexForPdf(self, record_id: str, pdf_path: str) -> bool:
        try:
            key = str(record_id or "").strip()
            source = Path(str(pdf_path or "")).expanduser()
            if not key:
                self._status = "无法加载解析索引：缺少文献 ID。"
                self.changed.emit()
                return False

            index = self._load_index_file(key)
            if not index:
                self._status = "还没有解析索引，请先解析 PDF。"
                self.changed.emit()
                return False

            ok, reason = self._index_matches_pdf(index, source)
            if not ok:
                self._status = reason
                self.changed.emit()
                return False

            self._pdf_paths[key] = str(source)
            self._set_index(key, index)
            self._status = "已加载解析索引。"
            self.changed.emit()
            return True
        except Exception as exc:
            self._status = f"加载解析索引失败：{exc}"
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
        self._status = "未找到该解析元素。"
        self.changed.emit()
        return False

    @Slot(str, str, result=str)
    def exportElement(self, element_id: str, fmt: str) -> str:
        try:
            if str(element_id) == "__all__":
                if not self._current_record_id:
                    self._status = "还没有可导出的解析结果。"
                    self.changed.emit()
                    return ""
                path = self._record_dir(self._current_record_id)
                path.mkdir(parents=True, exist_ok=True)
                self._status = f"已导出到：{path}"
                self.changed.emit()
                return str(path)

            element = self._element_by_id(element_id)
            if not element:
                self._status = "未找到要导出的元素。"
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
                    self._status = "公式不提供图片导出。"
                    self.changed.emit()
                    return ""
                path = str(element.get("pngPath") or "")

            if path and Path(path).exists():
                self._status = f"已导出：{path}"
                self.changed.emit()
                return path

            self._status = "该元素没有可导出的文件。"
            self.changed.emit()
            return ""
        except Exception as exc:
            self._status = f"导出失败：{exc}"
            self.changed.emit()
            return ""

    @Slot(str, result=str)
    def exportMarkdown(self, record_id: str) -> str:
        try:
            key = str(record_id or self._current_record_id or "").strip()
            index = self._indexes.get(key) or self._load_index_file(key)
            path = Path(str(index.get("markdownPath") or "")).expanduser()
            if path.exists():
                self._status = f"已导出 Markdown：{path}"
                self.changed.emit()
                return str(path)
            self._status = "当前解析结果没有可导出的 Markdown。"
            self.changed.emit()
            return ""
        except Exception as exc:
            self._status = f"导出 Markdown 失败：{exc}"
            self.changed.emit()
            return ""

    @Slot(str, result=str)
    def exportRawOutputDirectory(self, record_id: str) -> str:
        try:
            key = str(record_id or self._current_record_id or "").strip()
            if not key:
                self._status = "还没有可导出的解析结果。"
                self.changed.emit()
                return ""
            path = self._record_dir(key)
            if path.exists():
                self._status = f"已导出原始解析结果目录：{path}"
                self.changed.emit()
                return str(path)
            self._status = "原始解析结果目录不存在，请先解析 PDF。"
            self.changed.emit()
            return ""
        except Exception as exc:
            self._status = f"导出原始解析结果目录失败：{exc}"
            self.changed.emit()
            return ""

    @Slot(str, result=bool)
    def openExportDirectory(self, path: str) -> bool:
        try:
            raw = str(path or "").strip()
            if not raw:
                self._status = "还没有可打开的导出目录。"
                self.changed.emit()
                return False

            target = Path(raw).expanduser()
            directory = target if target.is_dir() else target.parent
            if not directory.exists():
                self._status = "导出目录不存在。"
                self.changed.emit()
                return False

            ok = QDesktopServices.openUrl(QUrl.fromLocalFile(str(directory)))
            self._status = f"已打开目录：{directory}" if ok else "打开导出目录失败。"
            self.changed.emit()
            return bool(ok)
        except Exception as exc:
            self._status = f"打开导出目录失败：{exc}"
            self.changed.emit()
            return False

    @Slot(str, result=bool)
    def copyElement(self, element_id: str) -> bool:
        try:
            element = self._element_by_id(element_id)
            if not element:
                self._status = "未找到要复制的元素。"
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
                    self._status = "该元素没有可复制的图片。"
                    self.changed.emit()
                    return False
                clipboard.setImage(QImage(str(image_path)))

            self._status = "已复制到剪贴板。"
            self.changed.emit()
            return True
        except Exception as exc:
            self._status = f"复制失败：{exc}"
            self.changed.emit()
            return False

    @Slot(str, result=bool)
    def copyElementImage(self, element_id: str) -> bool:
        try:
            element = self._element_by_id(element_id)
            if element and str(element.get("type") or "") == "formula":
                self._status = "公式不提供图片复制。"
                self.changed.emit()
                return False

            image_value = str(element.get("pngPath") or "") if element else ""
            image_path = Path(image_value) if image_value else None
            if image_path is None or not image_path.exists():
                self._status = "该元素没有可复制的图片。"
                self.changed.emit()
                return False

            QApplication.clipboard().setImage(QImage(str(image_path)))
            self._status = "已复制图片到剪贴板。"
            self.changed.emit()
            return True
        except Exception as exc:
            self._status = f"复制图片失败：{exc}"
            self.changed.emit()
            return False

    @Slot(str, int, float, result=str)
    def renderPage(self, record_id: str, page: int, zoom: float) -> str:
        try:
            key = str(record_id)
            if key not in self._indexes:
                self.loadIndex(key)

            pdf_path = Path(str(self._indexes.get(key, {}).get("sourcePath") or self._pdf_paths.get(key, "")))
            if not pdf_path.exists():
                self._status = "无法渲染页面：本地 PDF 不存在。"
                self.changed.emit()
                return ""

            import fitz

            page_index = max(0, int(page))
            scale = max(0.5, min(4.0, float(zoom or 1.0)))
            image_path = self._record_dir(key) / "pages" / f"page_{page_index + 1:04d}_z{int(scale * 100)}.png"

            if not image_path.exists() or image_path.stat().st_mtime < pdf_path.stat().st_mtime:
                image_path.parent.mkdir(parents=True, exist_ok=True)
                with fitz.open(pdf_path) as document:
                    if page_index >= len(document):
                        return ""
                    pixmap = document.load_page(page_index).get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
                    pixmap.save(str(image_path))

            return QUrl.fromLocalFile(str(image_path)).toString()
        except Exception as exc:
            self._status = f"页面渲染失败：{exc}"
            self.changed.emit()
            return ""

    @Slot(str, result=str)
    def cropElement(self, element_id: str) -> str:
        element = self._element_by_id(element_id)
        path = str(element.get("pngPath") or "") if element else ""
        return QUrl.fromLocalFile(path).toString() if path and Path(path).exists() else ""

    def _element_by_id(self, element_id: str) -> dict[str, Any]:
        for element in self._elements:
            if str(element.get("id") or "") == str(element_id):
                return dict(element)
        return {}

    def _on_task_finished(self, record_id: str, payload: object, message: str, ok: bool) -> None:
        self._loading = False
        self._progress = ""
        if str(record_id) == "__runtime__":
            self._status = message
            self.runtimeStatusChanged.emit(self.engineStatus())
            self.changed.emit()
            return
        if ok and isinstance(payload, dict):
            selected_engine = self._pending_engines.pop(str(record_id), str(payload.get("engine") or "active"))
            self._write_active_index(str(record_id), payload, selected_engine)
            self._set_index(record_id, payload)
            self._status = message
            self.changed.emit()
            self.analysisReady.emit(str(record_id))
        else:
            self._status = message or "PDF 解析失败。"
            self.changed.emit()

    def shutdown(self, timeout: float = 15.0) -> bool:
        return shutdown_workers([self._worker], timeout)
