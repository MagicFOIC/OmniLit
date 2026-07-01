from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from .services import AccountStore


def _json_form_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, float, int, str)):
        return value
    if isinstance(value, (list, tuple)):
        return [_json_form_value(item) for item in value]
    return str(value)


def _load_form_setting(store: AccountStore, key: str) -> dict[str, Any]:
    try:
        value = json.loads(store.setting(key, "{}"))
    except (TypeError, json.JSONDecodeError):
        return {}
    return dict(value) if isinstance(value, dict) else {}


def _save_form_setting(
    store: AccountStore,
    key: str,
    raw: dict[str, Any],
    fields: tuple[str, ...],
) -> dict[str, Any]:
    value = {field: _json_form_value(raw[field]) for field in fields if field in raw}
    store.set_setting(key, json.dumps(value, ensure_ascii=False, sort_keys=True))
    return value


def _format_bytes(size: int) -> str:
    value = float(max(0, size))
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{int(size)} B"


def _open_path(path: Path) -> None:
    target = path if path.is_dir() else path.parent
    target.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        os.startfile(target)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(target)])
    else:
        subprocess.Popen(["xdg-open", str(target)])


class LogWriter:
    """Forward stdout/stderr chunks to a controller callback."""

    def __init__(self, callback) -> None:
        self.callback = callback

    def write(self, text: str) -> int:
        if text.strip():
            self.callback(text)
        return len(text)

    def flush(self) -> None:
        return None


def classify_log_level(message: str, default: str = "info") -> str:
    """Return a stable UI severity for task log text."""
    text = str(message or "").casefold()
    if "traceback" in text or "exception" in text or "error:" in text or " failed" in text or "fail" in text:
        return "error"
    if "warning" in text or "retry" in text or "skipped" in text or "fallback" in text or "skip" in text:
        return "warning"
    if "debug" in text:
        return "debug"
    if "done" in text or "finished" in text or "completed" in text or "saved:" in text or "success" in text:
        return "success"
    return default


def classify_download_stage(message: str, fallback: str = "task") -> str:
    """Map download progress text to a user-facing task stage."""
    text = str(message or "").casefold()
    if "metadata" in text or "fetched" in text or "records" in text:
        return "metadata"
    if "pdf" in text:
        if "candidate" in text:
            return "pdf_lookup"
        return "pdf_download"
    if "source" in text or "api" in text or "database" in text:
        return "source"
    if "summary" in text or "finished" in text:
        return "summary"
    return fallback


def log_entry(
    *,
    level: str = "info",
    stage: str = "task",
    message: str,
    title: str = "",
    details: str = "",
    event: str = "log",
    document: str = "",
    source: str = "",
    index: int = 0,
) -> dict[str, Any]:
    """Build a JSON-serializable task log event for QML."""
    clean_message = str(message or "").strip()
    clean_details = str(details or "").strip()
    now = datetime.now()
    return {
        "id": f"{now.strftime('%H%M%S%f')}-{index}",
        "time": now.strftime("%H:%M:%S"),
        "level": level if level in {"debug", "info", "success", "warning", "error"} else "info",
        "stage": str(stage or "task"),
        "event": str(event or "log"),
        "title": str(title or "").strip() or (clean_message.splitlines()[0][:96] if clean_message else "Log"),
        "message": clean_message,
        "details": clean_details,
        "document": str(document or ""),
        "source": str(source or ""),
    }


def log_entries_to_text(entries: list[dict[str, Any]]) -> str:
    """Render structured entries as plain text for compatibility and copy/export."""
    lines: list[str] = []
    for entry in entries:
        prefix = f"[{entry.get('time', '')}] [{str(entry.get('level', 'info')).upper()}] [{entry.get('stage', 'task')}]"
        message = str(entry.get("message") or entry.get("title") or "").strip()
        if message:
            lines.append(f"{prefix} {message}")
        details = str(entry.get("details") or "").strip()
        if details:
            lines.append(details)
    return "\n".join(lines)


def export_log_entries(paths: Any, name: str, entries: list[dict[str, Any]]) -> str:
    """Write task logs as JSONL plus a readable TXT companion file."""
    root = paths.data("logs")
    root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in name).strip("_") or "task"
    jsonl_path = root / f"{safe_name}_{stamp}.jsonl"
    txt_path = root / f"{safe_name}_{stamp}.txt"
    with jsonl_path.open("w", encoding="utf-8") as handle:
        for entry in entries:
            handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
    txt_path.write_text(log_entries_to_text(entries), encoding="utf-8")
    return str(jsonl_path)
