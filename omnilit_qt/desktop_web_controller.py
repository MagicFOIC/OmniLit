from __future__ import annotations

import os
import re
from urllib.parse import quote

from PySide6.QtCore import QObject, Property, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices

from .crash_reporting import write_diagnostic_event


_RECORD_ID = re.compile(r"^[A-Za-z0-9_.:@-]{1,256}$")
_WEB_ROUTES = frozenset({"graph", "library", "collections", "workspace", "statistics", "ai", "account", "settings", "about"})


def initialize_qt_webengine() -> bool:
    """Initialize Qt WebEngine by default; an explicit false value disables it."""
    if os.getenv("OMNILIT_SHARED_WEB_GRAPH", "").strip().casefold() in {"0", "false", "no", "off"}:
        return False
    try:
        from PySide6.QtWebEngineQuick import QtWebEngineQuick
        QtWebEngineQuick.initialize()
        return True
    except (ImportError, RuntimeError):
        return False


class DesktopWebController(QObject):
    stateChanged = Signal()

    def __init__(self, paths, local_agent, *, webengine_ready: bool = False, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("omnilitDesktopBridge")
        self.paths = paths
        self.local_agent = local_agent
        self._enabled = bool(webengine_ready and local_agent.web_root is not None)
        self._available = False
        self._detail = "Shared web graph is disabled"
        self._interceptor = None
        if self._enabled:
            self._install_request_interceptor()
            self._detail = "Waiting for Local Agent"

    def _install_request_interceptor(self) -> None:
        from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEngineUrlRequestInterceptor

        controller = self

        class SessionRequestInterceptor(QWebEngineUrlRequestInterceptor):
            def interceptRequest(self, info) -> None:  # noqa: N802 - Qt virtual method
                endpoint = QUrl(controller.local_agent.endpoint)
                target = info.requestUrl()
                if endpoint.isValid() and target.scheme() == endpoint.scheme() and target.host() == endpoint.host() and target.port() == endpoint.port():
                    token = controller.local_agent.access_token
                    if token:
                        info.setHttpHeader(b"Authorization", f"Bearer {token}".encode("ascii"))

        self._interceptor = SessionRequestInterceptor(self)
        QWebEngineProfile.defaultProfile().setUrlRequestInterceptor(self._interceptor)

    @Property(bool, notify=stateChanged)
    def enabled(self) -> bool:
        return self._enabled

    @Property(bool, notify=stateChanged)
    def available(self) -> bool:
        return self._enabled and self._available

    @Property(str, notify=stateChanged)
    def detail(self) -> str:
        return self._detail

    @Slot()
    def refresh(self) -> None:
        status = self.local_agent.status()
        available = self._enabled and status.get("status") == "ready" and bool(status.get("webAvailable"))
        detail = "Ready" if available else str(status.get("detail") or "Local Agent is unavailable")
        if available != self._available or detail != self._detail:
            self._available, self._detail = available, detail
            self.stateChanged.emit()

    @Slot()
    def fallbackToQml(self) -> None:  # noqa: N802 - QML API
        if self._enabled:
            self._enabled, self._available = False, False
            self._detail = "QML fallback selected for this session"
            self.stateChanged.emit()

    @Slot(str, str)
    def recordDiagnostic(self, source: str, code: str) -> None:  # noqa: N802 - QML API
        if source == "webengine":
            write_diagnostic_event("webengine", code, directory=self.paths.runtime("crashes"))

    @Slot(str, result=QUrl)
    def graphUrl(self, record_id: str) -> QUrl:  # noqa: N802 - QML API
        value = str(record_id or "").strip()
        if not self.available or not _RECORD_ID.fullmatch(value):
            return QUrl()
        fragment = f"/graph?embedded=1&recordId={quote(value, safe='')}"
        return QUrl(f"{self.local_agent.endpoint}/app/index.html#{fragment}")

    @Slot(str, result=QUrl)
    def canvasUrl(self, record_id: str) -> QUrl:  # noqa: N802 - QML API
        value = str(record_id or "").strip()
        if not self.available or not _RECORD_ID.fullmatch(value):
            return QUrl()
        fragment = f"/graph-canvas?embedded=1&recordId={quote(value, safe='')}"
        return QUrl(f"{self.local_agent.endpoint}/app/index.html#{fragment}")

    @Slot(str, result=QUrl)
    def routeUrl(self, route: str) -> QUrl:  # noqa: N802 - QML API
        value = str(route or "").strip().casefold()
        if not self.available or value not in _WEB_ROUTES:
            return QUrl()
        return QUrl(f"{self.local_agent.endpoint}/app/index.html#/{value}?embedded=1")

    @Slot(str, result=bool)
    def isAllowedNavigation(self, value: str) -> bool:  # noqa: N802 - QML API
        target, endpoint = QUrl(value), QUrl(self.local_agent.endpoint)
        return bool(target.isValid() and target.scheme() == endpoint.scheme() and target.host() == endpoint.host() and target.port() == endpoint.port() and target.path().startswith("/app/"))

    @Slot(str, result=bool)
    def openExternalUrl(self, value: str) -> bool:  # noqa: N802 - QWebChannel API
        target = QUrl(value)
        if not target.isValid() or target.scheme() not in {"http", "https"} or self.isAllowedNavigation(value):
            return False
        return bool(QDesktopServices.openUrl(target))

    @Slot(result="QVariantMap")
    def getAppInfo(self) -> dict:  # noqa: N802 - QWebChannel API
        return {"name": "OmniLit", "version": "0.1.0", "platform": "qt-desktop"}

    @Slot(result="QVariantMap")
    def getLocalServiceStatus(self) -> dict:  # noqa: N802 - QWebChannel API
        status = self.local_agent.status()
        return {"available": status.get("status") == "ready", "reason": str(status.get("detail") or "")}
