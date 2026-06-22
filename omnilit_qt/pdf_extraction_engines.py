from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol

from .pdf_extraction_core import analyze_pdf
from .pdf_extraction_fusion import fuse_pymupdf_mineru_indexes
from .pdf_extraction_mineru import MinerUExtractionEngine
from .pdf_extraction_paddleocr_vl import PaddleOCRVLExtractionEngine
from .pdf_extraction_schema import ensure_version_3, make_base_index, merge_indexes
from .pdf_extraction_settings import normalize_engine_id


class ExtractionEngine(Protocol):
    name: str

    def is_available(self) -> bool:
        ...

    def analyze(self, pdf_path: Path, output_dir: Path, options: dict[str, Any] | None = None) -> dict[str, Any]:
        ...


class PyMuPDFExtractionEngine:
    name = "pymupdf"

    def is_available(self) -> bool:
        try:
            import fitz  # noqa: F401
        except Exception:
            return False
        return True

    def analyze(self, pdf_path: Path, output_dir: Path, options: dict[str, Any] | None = None) -> dict[str, Any]:
        index = analyze_pdf(pdf_path, output_dir)
        normalized = ensure_version_3(index, self.name)
        normalized["engine"] = self.name
        normalized["engineChain"] = [self.name]
        return normalized


class HybridExtractionPipeline:
    def __init__(self, engines: list[ExtractionEngine], fallback_engine: ExtractionEngine) -> None:
        self.engines = list(engines)
        self.fallback_engine = fallback_engine

    def analyze(self, pdf_path: Path, output_dir: Path, options: dict[str, Any] | None = None) -> dict[str, Any]:
        options = dict(options or {})
        requested = normalize_engine_id(str(options.get("engine") or "fast"))
        output_dir.mkdir(parents=True, exist_ok=True)

        base_index = self._run_fallback(pdf_path, output_dir, options)
        if requested == "fast":
            return _write_index(output_dir, base_index)

        if requested == "mineru":
            merged = self._merge_optional_engine(base_index, "mineru", pdf_path, output_dir, options, requested)
            return _write_index(output_dir, _mark_review_if_deep_failed(merged))

        if requested == "paddleocr_vl":
            merged = self._merge_optional_engine(base_index, "paddleocr_vl", pdf_path, output_dir, options, requested)
            return _write_index(output_dir, _mark_review_if_deep_failed(merged))

        base_index.setdefault("engineErrors", []).append(
            _engine_error(
                requested,
                RuntimeError(f"Unsupported extraction engine: {requested}"),
                level="warning",
                code="UNSUPPORTED_ENGINE",
            )
        )
        return _write_index(output_dir, base_index)

    def _run_fallback(self, pdf_path: Path, output_dir: Path, options: dict[str, Any]) -> dict[str, Any]:
        try:
            base_index = self.fallback_engine.analyze(pdf_path, output_dir, options)
        except Exception as exc:
            base_index = make_base_index(Path(pdf_path), Path(output_dir), self.fallback_engine.name)
            base_index.setdefault("engineErrors", []).append(
                _engine_error(self.fallback_engine.name, exc, level="warning", code="PYMUPDF_FAILED")
            )
        base_index = ensure_version_3(base_index, self.fallback_engine.name)
        base_index.setdefault("engineErrors", [])
        return base_index

    def _merge_optional_engine(
        self,
        base_index: dict[str, Any],
        engine_name: str,
        pdf_path: Path,
        output_dir: Path,
        options: dict[str, Any],
        requested: str,
    ) -> dict[str, Any]:
        index, error = self._run_optional_engine(engine_name, pdf_path, output_dir, options, requested)
        if index is None:
            merged = ensure_version_3(base_index)
            merged.setdefault("engineErrors", [])
            merged["engineErrors"].append(error or _not_configured_error(engine_name, requested))
            return merged
        if engine_name == "mineru":
            merged = fuse_pymupdf_mineru_indexes(base_index, index, output_dir)
        else:
            merged = merge_indexes(base_index, index, prefer_engine_order=_ENGINE_ORDER)
        for key in ("parserConfigVersion", "providerMode"):
            if index.get(key):
                merged[key] = index[key]
        return merged

    def _run_optional_engine(
        self,
        engine_name: str,
        pdf_path: Path,
        output_dir: Path,
        options: dict[str, Any],
        requested: str,
    ) -> tuple[dict[str, Any] | None, dict[str, str] | None]:
        engine = self._engine_by_name(engine_name)
        if engine is None:
            return None, _not_configured_error(engine_name, requested)
        try:
            if not engine.is_available():
                return None, _not_configured_error(engine_name, requested)
            index = engine.analyze(pdf_path, output_dir, options)
            normalized = ensure_version_3(index, engine_name)
            normalized["engine"] = engine_name
            chain = normalized.get("engineChain") or [engine_name]
            normalized["engineChain"] = [str(item) for item in chain if str(item or "").strip()]
            if engine_name not in normalized["engineChain"]:
                normalized["engineChain"].append(engine_name)
            return normalized, None
        except Exception as exc:
            return None, _engine_error(engine_name, exc, level=_error_level(engine_name, requested, exc), code=_error_code(exc))

    def _engine_by_name(self, engine_name: str) -> ExtractionEngine | None:
        for engine in self.engines:
            if str(getattr(engine, "name", "")) == engine_name:
                return engine
        return None


_ENGINE_ORDER = ["pymupdf", "mineru", "paddleocr_vl"]


def _engine_error(engine: str, exc: Exception, *, level: str = "warning", code: str = "ENGINE_FAILED") -> dict[str, str]:
    return {
        "engine": str(engine),
        "level": str(level or "warning"),
        "code": str(code or "ENGINE_FAILED"),
        "message": _friendly_message(str(engine), exc),
        "type": exc.__class__.__name__,
    }


def _not_configured_error(engine: str, requested: str) -> dict[str, str]:
    if engine == "paddleocr_vl":
        level = "warning" if requested == "paddleocr_vl" else "info"
        return {
            "engine": engine,
            "level": level,
            "code": "NOT_CONFIGURED",
            "message": "PaddleOCR-VL 云 API 未配置，已保留 PyMuPDF 快速解析结果。",
            "type": "EngineUnavailable",
        }
    if engine == "mineru":
        return {
            "engine": engine,
            "level": "warning",
            "code": "NOT_CONFIGURED",
            "message": "MinerU 云 API 未配置，已保留 PyMuPDF 快速解析结果。",
            "type": "EngineUnavailable",
        }
    return {
        "engine": engine,
        "level": "warning",
        "code": "NOT_CONFIGURED",
        "message": f"{engine} 云 API 未配置，已保留 PyMuPDF 快速解析结果。",
        "type": "EngineUnavailable",
    }


def _friendly_message(engine: str, exc: Exception) -> str:
    text = str(exc or "").strip()
    if engine == "paddleocr_vl" and ("not available" in text.lower() or not text):
        return "PaddleOCR-VL 云 API 不可用，已保留 PyMuPDF 快速解析结果。"
    if engine == "mineru" and ("not available" in text.lower() or not text):
        return "MinerU 云 API 不可用，已保留 PyMuPDF 快速解析结果。"
    return text or f"{engine} 解析失败，已保留 PyMuPDF 快速解析结果。"


def _error_level(engine: str, requested: str, exc: Exception) -> str:
    return "warning"


def _error_code(exc: Exception) -> str:
    explicit = str(getattr(exc, "code", "") or "").strip()
    if explicit:
        return explicit
    text = str(exc).lower()
    if "not configured" in text or "configure the" in text:
        return "NOT_CONFIGURED"
    return "ENGINE_FAILED"


def _has_deep_engine(index: dict[str, Any]) -> bool:
    chain = {str(item) for item in index.get("engineChain") or []}
    return bool(chain.intersection({"mineru", "paddleocr_vl"}))


def _mark_review_if_deep_failed(index: dict[str, Any]) -> dict[str, Any]:
    if _has_deep_engine(index):
        return index
    for element in index.get("elements") or []:
        if isinstance(element, dict):
            element["needsReview"] = True
    return index


def _write_index(output_dir: Path, index: dict[str, Any]) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "extraction_index.json").open("w", encoding="utf-8") as handle:
        json.dump(index, handle, ensure_ascii=False, indent=2)
    return index
