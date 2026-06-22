from __future__ import annotations

import importlib.util
import os
import re
from typing import Any

from .secrets import protect_secret, unprotect_secret


SECRET_PATTERN = re.compile(r"(?i)\b(api[_-]?key|token|password|secret|authorization)\b(\s*[:=]\s*)(?:bearer\s+|token\s+)?([^\s,;\"']+)")
JWT_PATTERN = re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")
SIGNED_URL_PATTERN = re.compile(r"(https?://[^\s?#]+)\?[^\s]+", re.IGNORECASE)

PARSER_CONFIG_VERSION = "cloud-api-v2"
MINERU_API_URL_DEFAULT = "https://mineru.net/api/v4"
PADDLEOCR_API_URL_DEFAULT = "https://paddleocr.aistudio-app.com/api/v2/ocr/jobs"
PARSER_SETTING_PREFIX = "pdf_parser/"


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
        value = os.environ.get("OMNILIT_MINERU_API_URL", "").strip() or parser_setting(store, "mineru/api_url", MINERU_API_URL_DEFAULT).strip() or MINERU_API_URL_DEFAULT
        return normalize_parser_api_url(engine, value)
    return os.environ.get("OMNILIT_PADDLEOCR_VL_URL", "").strip() or parser_setting(store, "paddleocr_vl/api_url", PADDLEOCR_API_URL_DEFAULT).strip() or PADDLEOCR_API_URL_DEFAULT


def normalize_parser_api_url(engine: str, api_url: str) -> str:
    value = str(api_url or "").strip().rstrip("/")
    if engine != "mineru":
        return value
    # The MinerU client uses the batch API and appends these routes itself.
    for suffix in ("/file-urls/batch", "/extract/task"):
        if value.lower().endswith(suffix):
            return value[: -len(suffix)].rstrip("/")
    return value


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
    set_parser_setting(store, f"{engine}/api_url", normalize_parser_api_url(engine, api_url))
    set_parser_setting(store, f"{engine}/enabled", "1" if enabled else "0")
    if token.strip():
        set_parser_setting(store, f"{engine}/token", protect_secret(token.strip()))


def clear_parser_token(store: Any, engine: str) -> None:
    if hasattr(store, "delete_setting"):
        store.delete_setting(PARSER_SETTING_PREFIX + f"{engine}/token")


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


def engine_status(store: Any | None = None) -> dict[str, dict[str, Any]]:
    return {
        "pymupdf": _pymupdf_status(),
        "paddleocr_vl": _cloud_status(store, "paddleocr_vl", "PaddleOCR-VL"),
        "mineru": _cloud_status(store, "mineru", "MinerU"),
    }


def _cloud_status(store: Any | None, engine: str, label: str) -> dict[str, Any]:
    if not parser_service_enabled(store, engine):
        return {"available": False, "status": "off", "message": f"{label} cloud API is disabled."}
    api_url = parser_api_url(store, engine)
    configured = bool(parser_api_token(store, engine) and api_url)
    return {
        "available": configured,
        "status": "ready" if configured else "not_configured",
        "message": f"{label} cloud API is configured." if configured else f"Configure the {label} API URL and token in system settings.",
    }


def _pymupdf_status() -> dict[str, Any]:
    if importlib.util.find_spec("fitz") is not None:
        return {"available": True, "status": "ready", "message": "可用"}
    return {"available": False, "status": "missing", "message": "未安装 PyMuPDF"}


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on", "auto"}
