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
        requested = normalize_engine_id(str(options.get("engine") or "auto"))
        if requested == "hybrid":
            requested = "auto"
        output_dir.mkdir(parents=True, exist_ok=True)

        base_index = self._run_fallback(pdf_path, output_dir, options)
        if requested == "fast":
            return _write_index(output_dir, base_index)

        if requested == "mineru":
            return _write_index(output_dir, self._merge_optional_engine(base_index, "mineru", pdf_path, output_dir, options, requested))

        if requested in {"paddleocr_vl", "auto"}:
            paddle_index, paddle_error = self._run_optional_engine("paddleocr_vl", pdf_path, output_dir, options, requested)
            if paddle_index is not None:
                return _write_index(output_dir, merge_indexes(base_index, paddle_index, _ENGINE_ORDER))

            if paddle_error:
                base_index.setdefault("engineErrors", []).append(paddle_error)

            merged = self._merge_optional_engine(base_index, "mineru", pdf_path, output_dir, options, requested)
            if _has_deep_engine(merged):
                return _write_index(output_dir, merged)

            if requested == "paddleocr_vl":
                _upgrade_missing_deep_warning(merged)
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
            merged["engineErrors"].append(error or _not_initialized_error(engine_name, requested))
            return merged
        if engine_name == "mineru":
            return fuse_pymupdf_mineru_indexes(base_index, index, output_dir)
        return merge_indexes(base_index, index, prefer_engine_order=_ENGINE_ORDER)

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
            return None, _not_initialized_error(engine_name, requested, code="NOT_CONFIGURED")
        try:
            if not engine.is_available():
                if engine_name == "mineru" and requested in {"auto", "mineru", "paddleocr_vl"}:
                    index = engine.analyze(pdf_path, output_dir, options)
                else:
                    return None, _not_initialized_error(engine_name, requested)
            else:
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


def _not_initialized_error(engine: str, requested: str, code: str = "NOT_INITIALIZED") -> dict[str, str]:
    if engine == "paddleocr_vl":
        level = "warning" if requested == "paddleocr_vl" else "info"
        return {
            "engine": engine,
            "level": level,
            "code": code,
            "message": "PaddleOCR-VL 高精度引擎未初始化，已使用 MinerU 或 PyMuPDF 回退。",
            "type": "EngineUnavailable",
        }
    if engine == "mineru":
        level = "warning" if requested in {"mineru", "auto", "paddleocr_vl"} else "info"
        return {
            "engine": engine,
            "level": level,
            "code": code,
            "message": "MinerU 深度解析组件未安装或初始化失败，已使用快速解析。",
            "type": "EngineUnavailable",
        }
    return {
        "engine": engine,
        "level": "warning",
        "code": code,
        "message": f"{engine} 解析引擎未初始化，已使用可用回退。",
        "type": "EngineUnavailable",
    }


def _friendly_message(engine: str, exc: Exception) -> str:
    text = str(exc or "").strip()
    if engine == "paddleocr_vl" and ("not available" in text.lower() or not text):
        return "PaddleOCR-VL 高精度引擎未初始化，已使用 MinerU 或 PyMuPDF 回退。"
    if engine == "mineru" and ("not available" in text.lower() or not text):
        return "MinerU 深度解析组件未安装或初始化失败，已使用快速解析。"
    return text or f"{engine} 解析失败，已使用可用回退。"


def _error_level(engine: str, requested: str, exc: Exception) -> str:
    text = str(exc).lower()
    if engine == "paddleocr_vl" and ("未初始化" in str(exc) or "not initialized" in text or "not available" in text):
        return "warning" if requested == "paddleocr_vl" else "info"
    return "warning"


def _error_code(exc: Exception) -> str:
    text = str(exc).lower()
    if "未初始化" in str(exc) or "not initialized" in text or "not available" in text:
        return "NOT_INITIALIZED"
    if "初始化失败" in str(exc) or "install" in text or "pip" in text:
        return "INITIALIZATION_FAILED"
    return "ENGINE_FAILED"


def _has_deep_engine(index: dict[str, Any]) -> bool:
    chain = {str(item) for item in index.get("engineChain") or []}
    return bool(chain.intersection({"mineru", "paddleocr_vl"}))


def _upgrade_missing_deep_warning(index: dict[str, Any]) -> None:
    for error in index.get("engineErrors") or []:
        if isinstance(error, dict) and error.get("level") == "info":
            error["level"] = "warning"


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
