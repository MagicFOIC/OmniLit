from __future__ import annotations

import importlib.util
import os
import re
from pathlib import Path
from typing import Any

from .secrets import protect_secret, unprotect_secret


SECRET_PATTERN = re.compile(r"(?i)\b(api[_-]?key|token|password|secret|authorization)\b(\s*[:=]\s*)(?:bearer\s+|token\s+)?([^\s,;\"']+)")
JWT_PATTERN = re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")
SIGNED_URL_PATTERN = re.compile(r"(https?://[^\s?#]+)\?[^\s]+", re.IGNORECASE)

PARSER_CONFIG_VERSION = "cloud-api-v1"
MINERU_API_URL_DEFAULT = "https://mineru.net/api/v4"
PADDLEOCR_API_URL_DEFAULT = ""
PARSER_SETTING_PREFIX = "pdf_parser/"
LEGACY_TOKEN_PATHS = {
    "mineru": Path(r"D:\Tool\Java\API\Mineru.txt"),
    "paddleocr_vl": Path(r"D:\Tool\Java\API\PaddleOCR.txt"),
}


def redact_sensitive_text(value: Any) -> str:
    text = str(value or "")
    text = SECRET_PATTERN.sub(lambda match: f"{match.group(1)}{match.group(2)}***", text)
    text = JWT_PATTERN.sub("***", text)
    return SIGNED_URL_PATTERN.sub(r"\1?***", text)


def parser_setting(store: Any | None, name: str, default: str = "") -> str:
    if store is None or not hasattr(store, "setting"):
        return default
    return str(store.setting(PARSER_SETTING_PREFIX + name, default))


def set_parser_setting(store: Any, name: str, value: str) -> None:
    store.set_setting(PARSER_SETTING_PREFIX + name, str(value))


def parser_service_enabled(store: Any | None, engine: str) -> bool:
    env_name = "OMNILIT_MINERU_ENABLED" if engine == "mineru" else "OMNILIT_PADDLEOCR_VL_ENABLED"
    if env_name in os.environ:
        return _env_bool(env_name, True)
    return parser_setting(store, f"{engine}/enabled", "1") != "0"


def parser_api_url(store: Any | None, engine: str) -> str:
    if engine == "mineru":
        return os.environ.get("OMNILIT_MINERU_API_URL", "").strip() or parser_setting(store, "mineru/api_url", MINERU_API_URL_DEFAULT).strip() or MINERU_API_URL_DEFAULT
    return os.environ.get("OMNILIT_PADDLEOCR_VL_URL", "").strip() or parser_setting(store, "paddleocr_vl/api_url", PADDLEOCR_API_URL_DEFAULT).strip() or PADDLEOCR_API_URL_DEFAULT


def parser_api_token(store: Any | None, engine: str) -> str:
    env_name = "OMNILIT_MINERU_API_TOKEN" if engine == "mineru" else "OMNILIT_PADDLEOCR_VL_API_KEY"
    value = os.environ.get(env_name, "").strip()
    if value:
        return value
    encrypted = parser_setting(store, f"{engine}/token", "")
    if not encrypted:
        return ""
    try:
        return unprotect_secret(encrypted).strip()
    except Exception:
        return ""


def save_parser_service(store: Any, engine: str, api_url: str, token: str, enabled: bool) -> None:
    set_parser_setting(store, f"{engine}/api_url", api_url.strip())
    set_parser_setting(store, f"{engine}/enabled", "1" if enabled else "0")
    if token.strip():
        set_parser_setting(store, f"{engine}/token", protect_secret(token.strip()))


def clear_parser_token(store: Any, engine: str) -> None:
    if hasattr(store, "delete_setting"):
        store.delete_setting(PARSER_SETTING_PREFIX + f"{engine}/token")


def import_legacy_parser_tokens(store: Any | None) -> dict[str, bool]:
    result = {"mineru": False, "paddleocr_vl": False}
    if store is None or parser_setting(store, "legacy_tokens_imported", "") == "1":
        return result
    for engine, default_path in LEGACY_TOKEN_PATHS.items():
        if parser_api_token(store, engine):
            continue
        env_name = "OMNILIT_MINERU_TOKEN_FILE" if engine == "mineru" else "OMNILIT_PADDLEOCR_TOKEN_FILE"
        path = Path(os.environ.get(env_name, "").strip() or default_path)
        try:
            token = path.read_text(encoding="utf-8-sig").strip()
        except OSError:
            token = ""
        if token:
            set_parser_setting(store, f"{engine}/token", protect_secret(token))
            result[engine] = True
    set_parser_setting(store, "legacy_tokens_imported", "1")
    return result


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
    }
    return aliases.get(s, s)


def engine_status(runtime_manager: Any | None = None, store: Any | None = None) -> dict[str, dict[str, Any]]:
    if runtime_manager is None:
        from .parser_runtime_manager import ParserRuntimeManager

        runtime_manager = ParserRuntimeManager()
    return {
        "pymupdf": _pymupdf_status(),
        "paddleocr_vl": _cloud_status(store, "paddleocr_vl", "PaddleOCR-VL"),
        "mineru": _cloud_status(store, "mineru", "MinerU"),
    }


def _cloud_status(store: Any | None, engine: str, label: str) -> dict[str, Any]:
    if not parser_service_enabled(store, engine):
        return {"available": False, "installable": False, "status": "off", "message": f"{label} cloud API is disabled."}
    configured = bool(parser_api_token(store, engine) and parser_api_url(store, engine))
    return {
        "available": configured,
        "installable": False,
        "status": "ready" if configured else "not_configured",
        "message": f"{label} cloud API is configured." if configured else f"Configure the {label} API URL and token in system settings.",
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
            "message": str(runtime_status.get("message") or "PaddleOCR-VL 高精度引擎未初始化。"),
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
