from __future__ import annotations

import json
import hashlib
import re
import threading
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Property, QUrl, Signal, Slot
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from .background_tasks import ManagedWorker, shutdown_workers
from .pdf_extraction_core import analyze_pdf


class PdfExtractionController(QObject):
    changed = Signal()
    analysisReady = Signal(str)
    elementFocused = Signal(str, int, "QVariantList")
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

    def _index_path(self, record_id: str) -> Path:
        return self._record_dir(record_id) / "extraction_index.json"

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

    def _load_index_file(self, record_id: str) -> dict[str, Any]:
        path = self._index_path(record_id)
        if not path.exists():
            return {}
        with path.open("r", encoding="utf-8") as handle:
            index = json.load(handle)
        if isinstance(index, dict):
            return index
        return {}

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

    @Slot(str, str, result=bool)
    def analyzeRecord(self, record_id: str, pdf_path: str) -> bool:
        key = str(record_id or "").strip()
        source = Path(str(pdf_path or "")).expanduser()
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
        self.changed.emit()

        def run() -> None:
            try:
                index = analyze_pdf(source, self._record_dir(key))
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
            metadata={"record_id": key, "pdf_path": str(source)},
        )
        self._worker = task
        task.start()
        return True

    @Slot(str, result=bool)
    def loadIndex(self, record_id: str) -> bool:
        try:
            index = self._load_index_file(record_id)
            if not index:
                self._status = "还没有解析索引，请先解析 PDF。"
                self.changed.emit()
                return False
            self._set_index(record_id, index)
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
                path = str(self._record_dir(self._current_record_id))
                self._status = f"已导出到：{path}"
                self.changed.emit()
                return path
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
        if ok and isinstance(payload, dict):
            self._set_index(record_id, payload)
            self._status = message
            self.analysisReady.emit(str(record_id))
        else:
            self._status = message or "PDF 解析失败。"
        self.changed.emit()

    def shutdown(self, timeout: float = 15.0) -> bool:
        return shutdown_workers([self._worker], timeout)
