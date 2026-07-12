from __future__ import annotations

import os
import sys
import tempfile
import traceback
from datetime import datetime
from pathlib import Path
from typing import Iterable


def startup_log_candidates() -> tuple[Path, ...]:
    candidates: list[Path] = []
    try:
        candidates.append(Path(sys.executable).resolve().with_name("OmniLit_startup_error.log"))
    except OSError:
        pass
    local_app_data = os.getenv("LOCALAPPDATA") or os.getenv("APPDATA")
    if local_app_data:
        candidates.append(Path(local_app_data).expanduser() / "OmniLit" / "OmniLit_startup_error.log")
    candidates.append(Path(tempfile.gettempdir()) / "OmniLit_startup_error.log")
    return tuple(dict.fromkeys(candidates))


def write_startup_log(title: str, lines: Iterable[str] = (), exc: BaseException | None = None) -> Path | None:
    body = [
        f"{datetime.now().isoformat(timespec='seconds')} {title}",
        f"executable={sys.executable}",
        f"cwd={os.getcwd()}",
        f"argv={sys.argv!r}",
        "",
    ]
    body.extend(str(line) for line in lines)
    if exc is not None:
        body.append("")
        body.extend(traceback.format_exception(type(exc), exc, exc.__traceback__))
    text = "\n".join(body).rstrip() + "\n"
    for path in startup_log_candidates():
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
            return path
        except OSError:
            continue
    return None
