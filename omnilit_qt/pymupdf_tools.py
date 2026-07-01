from __future__ import annotations

import threading


_LOCK = threading.Lock()
_SILENCED = False


def silence_mupdf_diagnostics() -> None:
    """Disable MuPDF stderr diagnostics that bypass normal Python exceptions."""
    global _SILENCED
    if _SILENCED:
        return
    with _LOCK:
        if _SILENCED:
            return
        try:
            import fitz

            tools = getattr(fitz, "TOOLS", None)
            if tools is not None:
                display_errors = getattr(tools, "mupdf_display_errors", None)
                display_warnings = getattr(tools, "mupdf_display_warnings", None)
                if callable(display_errors):
                    display_errors(False)
                if callable(display_warnings):
                    display_warnings(False)
        except Exception:
            pass
        _SILENCED = True
