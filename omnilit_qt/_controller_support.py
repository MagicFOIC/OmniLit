from __future__ import annotations

import json
import os
import subprocess
import sys
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
    """格式化字节数。参数：字节数量。返回值：适合界面展示的文本。"""
    value = float(max(0, size))
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{int(size)} B"


def _open_path(path: Path) -> None:
    """使用系统文件管理器打开目录。参数：文件或目录路径。返回值：无。"""
    target = path if path.is_dir() else path.parent
    target.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        os.startfile(target)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(target)])
    else:
        subprocess.Popen(["xdg-open", str(target)])


class LogWriter:
    """将核心模块的标准输出转发到 Qt 日志。"""

    def __init__(self, callback) -> None:
        """保存日志回调。参数：文本回调。返回值：无。"""
        self.callback = callback

    def write(self, text: str) -> int:
        """转发非空文本。参数：输出文本。返回值：原文本长度。"""
        if text.strip():
            self.callback(text)
        return len(text)

    def flush(self) -> None:
        """兼容文件接口。参数：无。返回值：无。"""
        return None