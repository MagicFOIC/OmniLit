from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import sys
import tempfile
import threading
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


REPORT_VERSION = 1
MAX_REPORTS = 20
SOURCES = {"startup", "qt_main", "qt_worker", "qml", "webengine", "local_agent"}
_CODE_PATTERN = re.compile(r"[^a-z0-9_]+")
_install_lock = threading.Lock()
_installed = False


def _code(value: str) -> str:
    normalized = _CODE_PATTERN.sub("_", value.strip().casefold()).strip("_")
    return (normalized or "unclassified_error")[:80]


def _fingerprint(source: str, code: str, exc: BaseException | None, extra: Iterable[str]) -> str:
    parts = [source, code]
    if exc is not None:
        parts.append(f"{type(exc).__module__}.{type(exc).__qualname__}")
        for frame in traceback.extract_tb(exc.__traceback__):
            parts.append(f"{Path(frame.filename).name}:{frame.name}:{frame.lineno}")
    parts.extend(hashlib.sha256(str(value).encode("utf-8", errors="replace")).hexdigest() for value in extra)
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def crash_directories() -> tuple[Path, ...]:
    configured = os.environ.get("OMNILIT_CRASH_DIR", "").strip()
    if configured:
        return (Path(configured).expanduser(),)
    candidates: list[Path] = []
    local_app_data = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    if local_app_data:
        candidates.append(Path(local_app_data).expanduser() / "OmniLit" / "crashes")
    state_home = os.environ.get("XDG_STATE_HOME", "").strip()
    if state_home:
        candidates.append(Path(state_home).expanduser() / "omnilit" / "crashes")
    candidates.append(Path(tempfile.gettempdir()) / "OmniLit" / "crashes")
    return tuple(dict.fromkeys(candidates))


def write_diagnostic_event(
    source: str,
    code: str,
    *,
    exc: BaseException | None = None,
    fatal: bool = False,
    directory: Path | None = None,
    extra_fingerprint: Iterable[str] = (),
) -> Path | None:
    """Persist a bounded privacy-safe event without messages, stacks, URLs, arguments or paths."""
    safe_source = source if source in SOURCES else "qt_main"
    safe_code = _code(code)
    report = {
        "reportVersion": REPORT_VERSION,
        "id": str(uuid.uuid4()),
        "occurredAt": datetime.now(timezone.utc).isoformat(),
        "source": safe_source,
        "code": safe_code,
        "fatal": bool(fatal),
        "exceptionType": f"{type(exc).__module__}.{type(exc).__qualname__}" if exc is not None else "",
        "fingerprint": _fingerprint(safe_source, safe_code, exc, extra_fingerprint),
        "platform": sys.platform,
        "python": platform.python_version(),
        "frozen": bool(getattr(sys, "frozen", False)),
    }
    destinations = (Path(directory),) if directory is not None else crash_directories()
    for destination in destinations:
        temporary: Path | None = None
        try:
            destination.mkdir(parents=True, exist_ok=True)
            name = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}-{report['id']}.json"
            target = destination / name
            temporary = destination / f".{name}.tmp"
            temporary.write_text(json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
            if os.name != "nt":
                temporary.chmod(0o600)
            temporary.replace(target)
            reports = sorted(destination.glob("*.json"), key=lambda path: path.name, reverse=True)
            for stale in reports[MAX_REPORTS:]:
                stale.unlink(missing_ok=True)
            return target
        except OSError:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    return None


def install_crash_handlers() -> None:
    """Install idempotent process and worker exception capture while preserving default reporting."""
    global _installed
    with _install_lock:
        if _installed:
            return
        previous_system = sys.excepthook
        previous_thread = threading.excepthook

        def system_hook(exception_type, value, trace) -> None:
            if isinstance(value, BaseException):
                write_diagnostic_event("qt_main", "unhandled_exception", exc=value, fatal=True)
            previous_system(exception_type, value, trace)

        def thread_hook(args: threading.ExceptHookArgs) -> None:
            if isinstance(args.exc_value, BaseException):
                write_diagnostic_event("qt_worker", "unhandled_thread_exception", exc=args.exc_value, fatal=False)
            previous_thread(args)

        sys.excepthook = system_hook
        threading.excepthook = thread_hook
        _installed = True
