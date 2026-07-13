from __future__ import annotations

from pathlib import Path
from typing import Iterable

from .crash_reporting import crash_directories, write_diagnostic_event


def startup_log_candidates() -> tuple[Path, ...]:
    return tuple(path / "startup-diagnostic.json" for path in crash_directories())


def write_startup_log(title: str, lines: Iterable[str] = (), exc: BaseException | None = None) -> Path | None:
    return write_diagnostic_event("startup", title, exc=exc, fatal=True, extra_fingerprint=(str(line) for line in lines))
