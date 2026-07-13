from __future__ import annotations

import os
import sys
import ctypes
from pathlib import Path

from omnilit_qt.startup_diagnostics import write_startup_log
from omnilit_qt.crash_reporting import install_crash_handlers


def _prepare_frozen_dll_runtime() -> None:
    if os.name != "nt" or not getattr(sys, "frozen", False):
        return
    bundle_root = Path(getattr(sys, "_MEIPASS", "") or "").resolve()
    if not bundle_root.exists():
        return
    bundle_text = str(bundle_root)
    os.environ["PATH"] = bundle_text + os.pathsep + os.environ.get("PATH", "")
    if hasattr(os, "add_dll_directory"):
        os.add_dll_directory(bundle_text)
    try:
        ctypes.windll.kernel32.SetDllDirectoryW(bundle_text)
    except (AttributeError, OSError):
        pass


def _prepare_conda_qt_runtime() -> None:
    """Expose Conda Qt DLL directories when python.exe is run without activation."""
    if os.name != "nt":
        return
    prefix = Path(sys.prefix)
    for relative in ("Library/bin", "Library/lib", "Library/lib/qt6/bin"):
        folder = prefix / relative
        if not folder.exists():
            continue
        folder_text = str(folder)
        os.environ["PATH"] = folder_text + os.pathsep + os.environ.get("PATH", "")
        if hasattr(os, "add_dll_directory"):
            os.add_dll_directory(folder_text)
    qt_root = prefix / "Library" / "lib" / "qt6"
    plugin_path = qt_root / "plugins"
    qml_path = qt_root / "qml"
    if plugin_path.exists():
        plugin_text = str(plugin_path)
        os.environ.setdefault("QT_PLUGIN_PATH", plugin_text)
        os.environ.setdefault("QT_QPA_PLATFORM_PLUGIN_PATH", str(plugin_path / "platforms"))
    if qml_path.exists():
        os.environ.setdefault("QML2_IMPORT_PATH", str(qml_path))
    webengine_process = qt_root / "QtWebEngineProcess.exe"
    webengine_resources = prefix / "Library" / "share" / "qt6" / "resources"
    webengine_locales = prefix / "Library" / "share" / "qt6" / "translations" / "qtwebengine_locales"
    if webengine_process.is_file():
        os.environ.setdefault("QTWEBENGINEPROCESS_PATH", str(webengine_process))
    if (webengine_resources / "qtwebengine_resources.pak").is_file():
        os.environ.setdefault("QTWEBENGINE_RESOURCES_PATH", str(webengine_resources))
    if webengine_locales.is_dir():
        os.environ.setdefault("QTWEBENGINE_LOCALES_PATH", str(webengine_locales))


_prepare_frozen_dll_runtime()
_prepare_conda_qt_runtime()
install_crash_handlers()


def _run_desktop() -> int:
    try:
        from omnilit_qt.app import run
    except ImportError as exc:
        write_startup_log("OmniLit import failed", exc=exc)
        raise SystemExit(
            "OmniLit Qt/QML dependencies are missing. Activate the OmniLit Conda "
            "environment and run: conda env update -n OmniLit -f environment.yml --prune"
        ) from exc
    return run()


def _run_local_agent() -> int:
    from services.local_agent.__main__ import main

    sys.argv = [sys.argv[0], *sys.argv[2:]]
    return main()


if __name__ == "__main__":
    try:
        target = _run_local_agent if len(sys.argv) > 1 and sys.argv[1] == "--local-agent" else _run_desktop
        raise SystemExit(target())
    except SystemExit:
        raise
    except BaseException as exc:
        write_startup_log("OmniLit startup failed", exc=exc)
        raise


# TODO: 文献提取改进
# TODO: 图分割，坐标轴的识别，点位数据
# TODO: 网页端和桌面端统一
