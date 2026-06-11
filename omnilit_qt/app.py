from __future__ import annotations

import os
import sys

from PySide6.QtCore import QPoint, QTimer, QUrl
from PySide6.QtGui import QCursor, QFontDatabase, QIcon
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import QApplication

from .controllers import (
    AppController,
    AuthController,
    DownloadController,
    LiteratureLibraryController,
    OnboardingController,
    PdfExtractionController,
    PreferencesController,
    TranslationController,
    UpdateController,
)
from .i18n import LocaleController
from .paths import AppPaths
from .services import AccountStore


def _shutdown_background_tasks(*controllers, timeout: float = 15.0) -> bool:
    """Request cancellation and wait for controller workers during app exit."""
    clean = True
    for controller in controllers:
        clean = bool(controller.shutdown(timeout=timeout)) and clean
    return clean


def _center_window_on_cursor_screen(app: QApplication, window) -> None:
    """Center the window on the screen containing the startup cursor."""
    screen = app.screenAt(QCursor.pos()) or app.primaryScreen()
    if screen is None:
        return
    available = screen.availableGeometry()
    width = window.width()
    height = window.height()
    window.setScreen(screen)
    window.setPosition(
        available.x() + max(0, (available.width() - width) // 2),
        available.y() + max(0, (available.height() - height) // 2),
    )


def _center_window_frame_on_current_screen(window) -> None:
    """Center the native window frame inside the current screen work area."""
    screen = window.screen()
    if screen is None:
        return
    available = screen.availableGeometry()
    frame = window.frameGeometry()
    window.setFramePosition(
        QPoint(
            available.x() + max(0, (available.width() - frame.width()) // 2),
            available.y() + max(0, (available.height() - frame.height()) // 2),
        )
    )


def _schedule_window_frame_center(window) -> None:
    """Recenter after QML resize and again after the native frame settles."""
    QTimer.singleShot(0, lambda: _center_window_frame_on_current_screen(window))
    QTimer.singleShot(120, lambda: _center_window_frame_on_current_screen(window))


def run() -> int:
    """启动 Qt/QML 桌面应用。参数：无。返回值：进程退出码。"""
    QQuickStyle.setStyle("Fusion")
    app = QApplication(sys.argv)
    app.setApplicationName("OmniLit")
    app.setOrganizationName("magicfoic")
    QFontDatabase.addApplicationFont(":/fonts/Microsoft YaHei UI")

    paths = AppPaths.discover()
    copied = paths.migrate_legacy_data()
    store = AccountStore(paths.data("accounts.sqlite3"))
    locale = LocaleController(store)
    shell = AppController(paths, locale)
    auth = AuthController(shell, store, locale)
    preferences = PreferencesController(paths, store, auth)
    download = DownloadController(shell, paths, store, locale)
    literature_library = LiteratureLibraryController(shell, paths, store, locale)
    pdf_extraction = PdfExtractionController(shell, paths, store, locale)
    translation = TranslationController(shell, paths, store, locale)
    updater = UpdateController(shell, paths, store, locale)
    onboarding = OnboardingController(shell, paths, store)
    shell.set_migration_summary(copied)
    auth.authenticated.connect(updater.check)
    auth.authenticated.connect(lambda: onboarding.onAuthenticated(auth.username))
    app.aboutToQuit.connect(lambda: _shutdown_background_tasks(download, literature_library, pdf_extraction, translation, updater))

    icon_path = paths.resource("assets", "omnilit_logo.ico")
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    engine = QQmlApplicationEngine()
    qml_warnings: list[str] = []
    engine.warnings.connect(lambda warnings: qml_warnings.extend(str(item.toString()) for item in warnings))
    for name, value in {
        "appController": shell,
        "authController": auth,
        "preferencesController": preferences,
        "downloadController": download,
        "literatureLibraryController": literature_library,
        "pdfExtractionController": pdf_extraction,
        "translationController": translation,
        "updateController": updater,
        "onboardingController": onboarding,
        "localeController": locale,
    }.items():
        engine.rootContext().setContextProperty(name, value)

    qml_path = paths.resource("ui", "qml", "Main.qml")
    if not qml_path.exists():
        print(f"QML file not found: {qml_path}", file=sys.stderr)
        return 1
    engine.load(QUrl.fromLocalFile(str(qml_path)))
    if not engine.rootObjects():
        for warning in qml_warnings:
            print(warning, file=sys.stderr)
        return 1
    window = engine.rootObjects()[0]
    _center_window_on_cursor_screen(app, window)
    auth.authenticated.connect(lambda: _schedule_window_frame_center(window))
    auth.loggedOut.connect(lambda: _schedule_window_frame_center(window))
    return app.exec()
