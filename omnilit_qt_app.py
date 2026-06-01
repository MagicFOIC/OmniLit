from __future__ import annotations

try:
    from omnilit_qt.app import run
except ImportError as exc:
    raise SystemExit(
        "OmniLit Qt/QML dependencies are missing. Activate the OmniLit Conda "
        "environment and run: conda env update -n OmniLit -f environment.yml --prune"
    ) from exc


if __name__ == "__main__":
    raise SystemExit(run())
