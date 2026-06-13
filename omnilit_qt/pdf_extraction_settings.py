from __future__ import annotations

import importlib.util
import os
import re
from typing import Any


SECRET_PATTERN = re.compile(r"(?i)\b(api[_-]?key|token|password|secret)\b(\s*[:=]\s*)([^\s,;\"']+)")


def redact_sensitive_text(value: Any) -> str:
    text = str(value or "")
    return SECRET_PATTERN.sub(lambda match: f"{match.group(1)}{match.group(2)}***", text)


def normalize_engine_id(value: str) -> str:
    s = (value or "").strip().lower()
    aliases = {
        "paddleocr_vl": "paddleocr_vl",
        "paddleocr-vl": "paddleocr_vl",
        "paddleocrvl": "paddleocr_vl",
        "paddleocr_vi": "paddleocr_vl",
        "mineru": "mineru",
        "fast": "fast",
        "pymupdf": "fast",
        "deep": "auto",
        "hybrid": "auto",
        "auto": "auto",
    }
    return aliases.get(s, s)


def engine_status(runtime_manager: Any | None = None) -> dict[str, dict[str, Any]]:
    if runtime_manager is None:
        from .parser_runtime_manager import ParserRuntimeManager

        runtime_manager = ParserRuntimeManager()
    return {
        "pymupdf": _pymupdf_status(),
        "paddleocr_vl": _paddleocr_vl_status(runtime_manager.check_paddleocr_vl_available()),
        "mineru": _mineru_status(runtime_manager.check_mineru_available()),
    }


def _pymupdf_status() -> dict[str, Any]:
    if importlib.util.find_spec("fitz") is not None:
        return {"available": True, "installable": False, "status": "ready", "message": "可用"}
    return {"available": False, "installable": False, "status": "missing", "message": "未安装 PyMuPDF"}


def _paddleocr_vl_status(runtime_status: dict[str, Any]) -> dict[str, Any]:
    mode = os.environ.get("OMNILIT_PADDLEOCR_VL_MODE", "auto").strip().lower() or "auto"
    enabled = _env_bool("OMNILIT_PADDLEOCR_VL_ENABLED", True)
    if not enabled or mode == "off":
        return {"available": False, "installable": False, "status": "off", "message": "PaddleOCR-VL 高精度引擎已禁用。"}
    if mode in {"auto", "service", "subprocess", "cli"}:
        return {
            "available": bool(runtime_status.get("available")),
            "installable": bool(runtime_status.get("installable")),
            "status": str(runtime_status.get("status") or "not_initialized"),
            "message": str(runtime_status.get("message") or "PaddleOCR-VL 高精度引擎未初始化，可使用 MinerU 或 PyMuPDF 回退。"),
        }
    return {"available": False, "installable": False, "status": "invalid", "message": f"不支持的 PaddleOCR-VL 模式：{mode}"}


def _mineru_status(runtime_status: dict[str, Any]) -> dict[str, Any]:
    mode = os.environ.get("OMNILIT_MINERU_MODE", "auto").strip().lower() or "auto"
    enabled = _env_bool("OMNILIT_MINERU_ENABLED", True)
    if not enabled or mode == "off":
        return {"available": False, "installable": False, "status": "off", "message": "MinerU 深度解析组件已禁用。"}
    if mode in {"auto", "cli"}:
        return {
            "available": bool(runtime_status.get("available")),
            "installable": bool(runtime_status.get("installable")),
            "status": str(runtime_status.get("status") or "installable"),
            "message": str(runtime_status.get("message") or "MinerU 深度解析组件未安装，可自动初始化。"),
        }
    if mode == "api":
        return {"available": False, "installable": False, "status": "reserved", "message": "MinerU API 模式已预留，当前仅支持 CLI。"}
    return {"available": False, "installable": False, "status": "invalid", "message": f"不支持的 MinerU 模式：{mode}"}


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on", "auto"}

