from __future__ import annotations

import re
from typing import Final


HEX_COLOR_PATTERN: Final = re.compile(r"#[0-9a-fA-F]{6}")

THEME_PRESETS: Final = (
    {"value": "scholar_light", "label": "preset_scholar_light", "mode": "light", "swatch": "#2563eb"},
    {"value": "manuscript_sepia", "label": "preset_manuscript_sepia", "mode": "light", "swatch": "#a16207"},
    {"value": "library_dark", "label": "preset_library_dark", "mode": "dark", "swatch": "#60a5fa"},
    {"value": "journal_blue", "label": "preset_journal_blue", "mode": "light", "swatch": "#1e3a8a"},
    {"value": "arxiv_minimal", "label": "preset_arxiv_minimal", "mode": "light", "swatch": "#475569"},
    {"value": "nature_green", "label": "preset_nature_green", "mode": "light", "swatch": "#059669"},
)

ACCENT_PRESETS: Final = (
    {"value": "blue", "label": "accent_scholar_blue", "color": "#2563eb"},
    {"value": "navy", "label": "accent_ink_navy", "color": "#1e3a8a"},
    {"value": "purple", "label": "accent_citation_purple", "color": "#7c3aed"},
    {"value": "cyan", "label": "accent_doi_teal", "color": "#0891b2"},
    {"value": "green", "label": "accent_nature_green", "color": "#059669"},
    {"value": "magenta", "label": "accent_review_magenta", "color": "#db2777"},
)

THEME_PRESET_NAMES: Final = {item["value"] for item in THEME_PRESETS}
THEME_PRESET_MODES: Final = {item["value"]: item["mode"] for item in THEME_PRESETS}
ACCENT_COLORS: Final = {item["value"]: item["color"] for item in ACCENT_PRESETS}

FONT_SIZE_VALUES: Final = {"small": 13, "standard": 14, "large": 15, "xlarge": 16}
DENSITY_VALUES: Final = {"compact": 0.88, "standard": 1.0, "relaxed": 1.14}
RADIUS_VALUES: Final = {"square": 3, "subtle": 7, "modern": 10}
PDF_BACKGROUND_VALUES: Final = {
    "white": "#ffffff",
    "sepia": "#faf6ed",
    "gray": "#f1f5f9",
    "dark": "#172033",
}
TRANSLATION_LINE_HEIGHT_VALUES: Final = {"compact": 1.35, "standard": 1.55, "comfortable": 1.75}
BACKGROUND_MODES: Final = {"none", "solid", "gradient", "paper", "grid", "image"}
THEME_MODES: Final = {"light", "dark", "system", "auto_night"}


def normalize_hex_color(value: str, default: str = "#2563eb") -> str:
    """Return a canonical six-digit color or the supplied default."""
    text = str(value or "").strip()
    return text.lower() if HEX_COLOR_PATTERN.fullmatch(text) else default

