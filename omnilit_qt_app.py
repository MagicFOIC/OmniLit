from __future__ import annotations

import os
import sys
from pathlib import Path


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


_prepare_conda_qt_runtime()

try:
    from omnilit_qt.app import run
except ImportError as exc:
    raise SystemExit(
        "OmniLit Qt/QML dependencies are missing. Activate the OmniLit Conda "
        "environment and run: conda env update -n OmniLit -f environment.yml --prune"
    ) from exc


if __name__ == "__main__":
    raise SystemExit(run())


# TODO: 文献提取改进