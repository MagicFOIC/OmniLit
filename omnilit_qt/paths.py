from __future__ import annotations

import csv
import os
import shutil
import sys
import ctypes
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


MIGRATION_ITEMS: tuple[tuple[str, str], ...] = (
    ("accounts.sqlite3", "config/accounts.sqlite3"),
    ("Download/APIKeys", "config/secrets/download"),
    ("Download/gui_settings.json", "config/download/gui_settings.json"),
    ("Download/metadata_*.jsonl", "data/downloads"),
    ("Download/metadata_*.jsonl.bak", "data/downloads"),
    ("Download/journal_metrics.csv", "data/downloads/journal_metrics.csv"),
    ("Download/journal_metrics.csv.legacy-*", "data/downloads"),
    ("Download/library_state.json", "data/downloads/library_state.json"),
    ("Download/library", "data/downloads/library"),
    ("Download/pdfs", "data/downloads/pdfs"),
    ("Download/crawl_state.json", "runtime/downloads/crawl_state.json"),
    ("Download/crawl_state", "runtime/downloads/crawl_state"),
    ("Download/library_cache.json", "cache/downloads/library_cache.json"),
    ("Download/library_cache.json.legacy-*", "cache/downloads"),
    ("Download/library_previews", "cache/downloads/library_previews"),
    ("Download/library_thumbnails", "cache/downloads/library_thumbnails"),
    ("Download/pdf_cache", "cache/downloads/pdf_cache"),
    ("Translate/pdf", "data/translate/pdf"),
    ("Translate/out", "data/translate/out"),
    ("Translate/*.pdf", "data/translate/pdf"),
    ("Translate/APIKey.enc", "config/secrets/translate/APIKey.enc"),
    ("Translate/UserAPIKey.enc", "config/secrets/translate/UserAPIKey.enc"),
    ("Translate/snippet_translation_cache.json", "cache/translate/snippet_translation_cache.json"),
    ("Translate/glossary", "config/glossary"),
    ("Translate/glossary.legacy-*", "config"),
    ("Literature/extractions", "data/literature/extractions"),
    ("Literature/graphs", "data/literature/graphs"),
    ("task_state", "runtime/task_state"),
    ("logs", "runtime/logs"),
    ("updates", "runtime/updates"),
    ("ui", "config/ui"),
    ("extraction_eval", "reports/extraction_eval"),
)

EMPTY_LEGACY_DIRS = (
    "Cache",
    "Extract",
    "Library",
    "Download",
    "Translate",
    "Literature",
    "task_state",
    "logs",
    "updates",
    "ui",
    "extraction_eval",
)


def _source_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _macos_bundle_sibling(executable: Path) -> Path:
    for parent in executable.parents:
        if parent.suffix.lower() == ".app":
            return parent.parent
    return executable.parent


def _program_data_root() -> Path:
    override = os.getenv("OMNILIT_DATA_DIR", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    if not getattr(sys, "frozen", False):
        return _source_root() / "Workspace"
    executable = Path(sys.executable).resolve()
    app_root = _macos_bundle_sibling(executable) if sys.platform == "darwin" else executable.parent
    portable_root = app_root / "Workspace"
    if portable_root.exists() and _directory_is_writable(portable_root):
        return portable_root
    if sys.platform == "win32" and _is_windows_elevated():
        return _user_data_root() / "Workspace"
    if not portable_root.exists() and _path_parent_is_writable(portable_root):
        return portable_root
    return _user_data_root() / "Workspace"


def _user_data_root() -> Path:
    if sys.platform == "win32":
        base = os.getenv("LOCALAPPDATA") or os.getenv("APPDATA") or str(Path.home())
    elif sys.platform == "darwin":
        base = str(Path.home() / "Library" / "Application Support")
    else:
        base = os.getenv("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base).expanduser() / "OmniLit"


def _path_parent_is_writable(path: Path) -> bool:
    parent = path.parent
    try:
        parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return False
    return _directory_is_writable(parent)


def _directory_is_writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".omnilit-write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
    except OSError:
        return False
    return True


def _is_windows_elevated() -> bool:
    if sys.platform != "win32":
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (AttributeError, OSError):
        return False


def _old_qt_data_root() -> Path | None:
    try:
        from PySide6.QtCore import QStandardPaths

        value = QStandardPaths.writableLocation(QStandardPaths.AppLocalDataLocation)
        return Path(value).expanduser().resolve() if value else None
    except ImportError:
        return None


def _legacy_roots(app_root: Path, data_root: Path) -> tuple[Path, ...]:
    candidates = [app_root, _old_qt_data_root()]
    unique: list[Path] = []
    for candidate in candidates:
        if candidate is None:
            continue
        resolved = candidate.resolve()
        if resolved != data_root and resolved not in unique:
            unique.append(resolved)
    return tuple(unique)


def _csv_glossary_rows(path: Path) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.reader(handle):
            if len(row) < 2:
                continue
            source, target = row[0].strip(), row[1].strip()
            if not source or not target or source.lower() == "source":
                continue
            rows.append((source, target))
    return rows


def _sync_glossary_defaults(resource_glossary: Path, writable_glossary: Path) -> None:
    if not resource_glossary.exists():
        return
    writable_glossary.mkdir(parents=True, exist_ok=True)
    for source_file in resource_glossary.glob("*.csv"):
        target_file = writable_glossary / source_file.name
        if not target_file.exists():
            shutil.copy2(source_file, target_file)
            continue
        existing = set(_csv_glossary_rows(target_file))
        missing = [row for row in _csv_glossary_rows(source_file) if row not in existing]
        if not missing:
            continue
        with target_file.open("a", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            for source, target in missing:
                writer.writerow([source, target])


def _migration_sources(legacy_root: Path) -> tuple[tuple[Path, Path], ...]:
    sources: list[tuple[Path, Path]] = []
    seen: set[tuple[Path, Path]] = set()
    for source_relative, target_relative in MIGRATION_ITEMS:
        matches = sorted(legacy_root.glob(source_relative)) if any(char in source_relative for char in "*?[") else [legacy_root / source_relative]
        for source in matches:
            target = Path(target_relative)
            if any(char in source_relative for char in "*?["):
                target = target / source.name
            key = (source.resolve(), target)
            if key in seen:
                continue
            seen.add(key)
            sources.append((source, target))
    return tuple(sources)


@dataclass(frozen=True)
class AppPaths:
    """Central paths for read-only resources and writable Workspace data."""

    resource_root: Path
    data_root: Path
    legacy_roots: tuple[Path, ...] | Path = ()

    def __post_init__(self) -> None:
        roots = self.legacy_roots
        normalized = (roots,) if isinstance(roots, Path) else tuple(roots)
        object.__setattr__(self, "resource_root", self.resource_root.resolve())
        object.__setattr__(self, "data_root", self.data_root.resolve())
        object.__setattr__(self, "legacy_roots", tuple(path.resolve() for path in normalized))

    @classmethod
    def discover(cls) -> "AppPaths":
        source_root = _source_root()
        app_root = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else source_root
        resource_root = Path(getattr(sys, "_MEIPASS", app_root)).resolve()
        data_root = _program_data_root().resolve()
        return cls(resource_root, data_root, _legacy_roots(app_root, data_root))

    def resource(self, *parts: str) -> Path:
        return self.resource_root.joinpath(*parts)

    def data(self, *parts: str) -> Path:
        return self.data_root.joinpath(*parts)

    def config(self, *parts: str) -> Path:
        return self.data_root.joinpath("config", *parts)

    def content(self, *parts: str) -> Path:
        return self.data_root.joinpath("data", *parts)

    def cache(self, *parts: str) -> Path:
        return self.data_root.joinpath("cache", *parts)

    def runtime(self, *parts: str) -> Path:
        return self.data_root.joinpath("runtime", *parts)

    def reports(self, *parts: str) -> Path:
        return self.data_root.joinpath("reports", *parts)

    @property
    def glossary_dir(self) -> Path:
        return self.config("glossary")

    def ensure_data_dirs(self) -> None:
        for relative in (
            "config/download",
            "config/glossary",
            "config/secrets/download",
            "config/secrets/translate",
            "config/ui",
            "data/downloads/library",
            "data/downloads/pdfs",
            "data/literature/extractions",
            "data/literature/graphs",
            "data/translate/pdf",
            "cache/downloads/library_previews",
            "cache/downloads/library_thumbnails",
            "cache/downloads/pdf_cache",
            "cache/translate",
            "runtime/task_state",
            "runtime/downloads",
            "runtime/logs",
            "runtime/updates",
            "reports",
        ):
            self.data(relative).mkdir(parents=True, exist_ok=True)
        resource_glossary = self.resource("Translate", "glossary")
        if resource_glossary != self.glossary_dir and resource_glossary.exists():
            shutil.copytree(resource_glossary, self.glossary_dir, dirs_exist_ok=True, copy_function=_copy_missing)
            _sync_glossary_defaults(resource_glossary, self.glossary_dir)

    def migrate_legacy_data(self) -> list[str]:
        self.data_root.mkdir(parents=True, exist_ok=True)
        copied: list[str] = []
        roots = (self.data_root, *self.legacy_roots)
        seen_roots: set[Path] = set()
        hold_root = self.runtime("migration_hold", datetime.now().strftime("%Y%m%d_%H%M%S"))
        for legacy_root in roots:
            legacy_root = legacy_root.resolve()
            if legacy_root in seen_roots:
                continue
            seen_roots.add(legacy_root)
            same_workspace = legacy_root == self.data_root
            if same_workspace:
                _remove_empty_legacy_dirs(legacy_root)
            for source, target_relative in _migration_sources(legacy_root):
                if not source.exists():
                    continue
                relative = source.relative_to(legacy_root).as_posix()
                target = self.data(target_relative.as_posix())
                if same_workspace:
                    if _move_missing(source, target, hold_root, source.relative_to(legacy_root)):
                        copied.append(relative)
                    continue
                if source.is_dir():
                    before = set(path.relative_to(target) for path in target.rglob("*")) if target.exists() else set()
                    shutil.copytree(source, target, dirs_exist_ok=True, copy_function=_copy_missing)
                    after = set(path.relative_to(target) for path in target.rglob("*"))
                    if after - before:
                        copied.append(relative)
                elif not target.exists():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
                    copied.append(relative)
            if same_workspace:
                _remove_empty_legacy_dirs(legacy_root)
        self.ensure_data_dirs()
        return list(dict.fromkeys(copied))


def _copy_missing(source: str, target: str) -> str:
    target_path = Path(target)
    if not target_path.exists():
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return str(target_path)


def _move_missing(source: Path, target: Path, hold_root: Path, hold_relative: Path) -> bool:
    if not source.exists():
        return False
    if source.resolve() == target.resolve():
        return False
    if source.is_dir():
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            source.replace(target)
            return True
        moved = False
        target.mkdir(parents=True, exist_ok=True)
        for child in sorted(source.iterdir(), key=lambda path: path.name.lower()):
            moved = _move_missing(child, target / child.name, hold_root, hold_relative / child.name) or moved
        try:
            source.rmdir()
        except OSError:
            pass
        return moved
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        source.replace(target)
        return True
    hold_path = hold_root / hold_relative
    hold_path.parent.mkdir(parents=True, exist_ok=True)
    source.replace(hold_path)
    return True


def _remove_empty_legacy_dirs(root: Path) -> None:
    for relative in EMPTY_LEGACY_DIRS:
        path = root / relative
        try:
            if path.exists() and path.is_dir():
                path.rmdir()
        except OSError:
            pass
