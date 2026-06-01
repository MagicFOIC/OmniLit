from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path


MIGRATION_MARKER = ".omnilit-data-migrated-v2"
MIGRATION_ITEMS = (
    "accounts.sqlite3",
    "Download/crawl_state.json",
    "Download/gui_settings.json",
    "Download/metadata_battery.jsonl",
    "Download/pdfs",
    "Translate/pdf",
    "Translate/out",
    "Translate/APIKey.enc",
    "Translate/UserAPIKey.enc",
    "Translate/glossary",
)


def _source_root() -> Path:
    """返回源码仓库根目录。参数：无。返回值：解析后的项目目录。"""
    return Path(__file__).resolve().parent.parent


def _macos_bundle_sibling(executable: Path) -> Path:
    """定位 macOS 应用包同级目录。参数：可执行文件路径。返回值：应用包父目录或可执行文件父目录。"""
    for parent in executable.parents:
        if parent.suffix.lower() == ".app":
            return parent.parent
    return executable.parent


def _program_data_root() -> Path:
    """确定当前运行实例的数据目录。参数：无。返回值：环境覆盖或程序所在目录。"""
    override = os.getenv("OMNILIT_DATA_DIR", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    if not getattr(sys, "frozen", False):
        return _source_root()
    executable = Path(sys.executable).resolve()
    return _macos_bundle_sibling(executable) if sys.platform == "darwin" else executable.parent


def _old_qt_data_root() -> Path | None:
    """读取旧 Qt 版本使用的数据目录。参数：无。返回值：旧目录；无法获取时返回空值。"""
    try:
        from PySide6.QtCore import QStandardPaths

        value = QStandardPaths.writableLocation(QStandardPaths.AppLocalDataLocation)
        return Path(value).expanduser().resolve() if value else None
    except ImportError:
        return None


def _legacy_roots(app_root: Path, data_root: Path) -> tuple[Path, ...]:
    """生成旧数据候选目录。参数：程序目录和新数据目录。返回值：去重后的旧目录元组。"""
    candidates = [app_root, _old_qt_data_root()]
    unique: list[Path] = []
    for candidate in candidates:
        if candidate is None:
            continue
        resolved = candidate.resolve()
        if resolved != data_root and resolved not in unique:
            unique.append(resolved)
    return tuple(unique)


@dataclass(frozen=True)
class AppPaths:
    """集中管理只读资源、可写数据和旧版迁移来源。"""

    resource_root: Path
    data_root: Path
    legacy_roots: tuple[Path, ...] | Path = ()

    def __post_init__(self) -> None:
        """规范化路径字段。参数：无。返回值：无。"""
        roots = self.legacy_roots
        normalized = (roots,) if isinstance(roots, Path) else tuple(roots)
        object.__setattr__(self, "resource_root", self.resource_root.resolve())
        object.__setattr__(self, "data_root", self.data_root.resolve())
        object.__setattr__(self, "legacy_roots", tuple(path.resolve() for path in normalized))

    @classmethod
    def discover(cls) -> "AppPaths":
        """发现运行路径。参数：无。返回值：当前进程使用的路径集合。"""
        source_root = _source_root()
        app_root = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else source_root
        resource_root = Path(getattr(sys, "_MEIPASS", app_root)).resolve()
        data_root = _program_data_root().resolve()
        return cls(resource_root, data_root, _legacy_roots(app_root, data_root))

    def resource(self, *parts: str) -> Path:
        """拼接资源路径。参数：相对路径片段。返回值：只读资源路径。"""
        return self.resource_root.joinpath(*parts)

    def data(self, *parts: str) -> Path:
        """拼接数据路径。参数：相对路径片段。返回值：可写数据路径。"""
        return self.data_root.joinpath(*parts)

    @property
    def glossary_dir(self) -> Path:
        """返回可写术语表目录。参数：无。返回值：术语表目录。"""
        return self.data("Translate", "glossary")

    def ensure_data_dirs(self) -> None:
        """创建运行目录并补齐内置术语表。参数：无。返回值：无。"""
        for relative in ("Download", "Download/pdfs", "Translate", "Translate/pdf", "Translate/out", "Translate/glossary", "updates"):
            self.data(relative).mkdir(parents=True, exist_ok=True)
        resource_glossary = self.resource("Translate", "glossary")
        if resource_glossary != self.glossary_dir and resource_glossary.exists():
            shutil.copytree(resource_glossary, self.glossary_dir, dirs_exist_ok=True, copy_function=_copy_missing)

    def migrate_legacy_data(self) -> list[str]:
        """从旧目录补齐缺失数据。参数：无。返回值：已复制的相对路径列表。"""
        self.data_root.mkdir(parents=True, exist_ok=True)
        marker = self.data(MIGRATION_MARKER)
        if marker.exists():
            self.ensure_data_dirs()
            return []
        copied: list[str] = []
        skipped: list[str] = []
        # 新目录拥有优先级；旧目录只补缺，不覆盖用户已经在项目目录保存的数据。
        for legacy_root in self.legacy_roots:
            for relative in MIGRATION_ITEMS:
                source = legacy_root / relative
                target = self.data(relative)
                if not source.exists():
                    continue
                if source.is_dir():
                    before = set(path.relative_to(target) for path in target.rglob("*")) if target.exists() else set()
                    shutil.copytree(source, target, dirs_exist_ok=True, copy_function=_copy_missing)
                    after = set(path.relative_to(target) for path in target.rglob("*"))
                    if after - before:
                        copied.append(relative)
                    elif target.exists():
                        skipped.append(relative)
                elif not target.exists():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
                    copied.append(relative)
                else:
                    skipped.append(relative)
        marker.write_text(
            "\n".join([*[f"copied:{item}" for item in copied], *[f"kept:{item}" for item in skipped]]) + "\n",
            encoding="utf-8",
        )
        self.ensure_data_dirs()
        return list(dict.fromkeys(copied))


def _copy_missing(source: str, target: str) -> str:
    """仅复制不存在的文件。参数：源文件和目标文件。返回值：目标路径。"""
    target_path = Path(target)
    if not target_path.exists():
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return str(target_path)
