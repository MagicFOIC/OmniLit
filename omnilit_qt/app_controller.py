from __future__ import annotations

import json

from PySide6.QtCore import QObject, Property, QUrl, Signal

from .i18n import LocaleController
from .paths import AppPaths
from .version import APP_VERSION


class AppController(QObject):
    """提供应用级状态、版本和资源路径。"""

    statusChanged = Signal()

    def __init__(self, paths: AppPaths, locale: LocaleController):
        """初始化应用控制器。参数：路径集合和语言控制器。返回值：无。"""
        super().__init__()
        self.paths = paths
        self.locale = locale
        self._status = locale.textf("ready")
        self._migration_summary = ""
        self._version = self._read_version()

    def _read_version(self) -> str:
        """读取运行版本。参数：无。返回值：版本文本。"""
        for path in (self.paths.data("update_manifest.json"), self.paths.resource("update_manifest.json")):
            try:
                return str(json.loads(path.read_text(encoding="utf-8")).get("version") or APP_VERSION)
            except Exception:
                continue
        return APP_VERSION

    def set_status(self, message: str) -> None:
        """更新全局状态栏。参数：消息文本。返回值：无。"""
        self._status = str(message)
        self.statusChanged.emit()

    def set_migration_summary(self, copied: list[str]) -> None:
        """展示旧数据补齐结果。参数：复制项列表。返回值：无。"""
        if copied:
            self._migration_summary = self.locale.textf("migrated", count=len(copied))
            self.set_status(self._migration_summary)

    @Property(str, constant=True)
    def version(self) -> str:
        """返回应用版本。参数：无。返回值：版本文本。"""
        return self._version

    @Property(str, notify=statusChanged)
    def statusText(self) -> str:
        """返回状态栏文本。参数：无。返回值：状态文本。"""
        return self._status

    @Property(str, constant=True)
    def dataRoot(self) -> str:
        """返回运行数据目录。参数：无。返回值：目录文本。"""
        return str(self.paths.data_root)

    @Property(str, constant=True)
    def migrationSummary(self) -> str:
        """返回迁移摘要。参数：无。返回值：摘要文本。"""
        return self._migration_summary

    @Property(str, constant=True)
    def logoUrl(self) -> str:
        """返回 Logo URL。参数：无。返回值：本地 URL。"""
        return QUrl.fromLocalFile(str(self.paths.resource("assets", "omnilit_logo.png"))).toString()
