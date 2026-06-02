from __future__ import annotations

import re
from typing import Final


HEX_COLOR_PATTERN: Final = re.compile(r"#[0-9a-fA-F]{6}")

THEME_PRESETS: Final = (
    {"value": "scholar_light", "label": "preset_scholar_blue", "swatch": "#2563eb", "preview": "#dbeafe"},
    {"value": "manuscript_sepia", "label": "preset_manuscript_sepia", "swatch": "#a16207", "preview": "#f5e6c8"},
    {"value": "journal_blue", "label": "preset_journal_navy", "swatch": "#1e3a8a", "preview": "#d7e5f5"},
    {"value": "arxiv_minimal", "label": "preset_arxiv_minimal", "swatch": "#475569", "preview": "#e5e7eb"},
    {"value": "nature_green", "label": "preset_nature_green", "swatch": "#059669", "preview": "#d8efe0"},
    {"value": "citation_purple", "label": "preset_citation_purple", "swatch": "#7c3aed", "preview": "#e9ddff"},
    {"value": "nordic_slate", "label": "preset_nordic_slate", "swatch": "#0f766e", "preview": "#d7e6e5"},
    {"value": "focus_amber", "label": "preset_focus_amber", "swatch": "#d97706", "preview": "#f8e6bd"},
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
THEME_PRESET_ALIASES: Final = {"library_dark": "journal_blue"}
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
BACKGROUND_PRESETS: Final = (
    {"value": "default", "label": "background_default", "swatch": "#f8fafc"},
    {"value": "solid", "label": "background_solid", "swatch": "#ffffff"},
    {"value": "gradient", "label": "background_gradient", "swatch": "#dbeafe"},
    {"value": "paper", "label": "background_paper", "swatch": "#f7f1e3"},
    {"value": "grid", "label": "background_grid", "swatch": "#dbeafe"},
    {"value": "dots", "label": "background_dots", "swatch": "#d7e6e5"},
    {"value": "glow", "label": "background_glow", "swatch": "#e9ddff"},
    {"value": "focus", "label": "background_focus", "swatch": "#f8e6bd"},
    {"value": "image", "label": "background_image", "swatch": "#cbd5e1"},
)
BACKGROUND_MODES: Final = {item["value"] for item in BACKGROUND_PRESETS}
BACKGROUND_MODE_ALIASES: Final = {"none": "default"}
THEME_MODES: Final = {"light", "dark", "system", "adaptive"}
THEME_MODE_ALIASES: Final = {"auto_night": "adaptive"}


def normalize_hex_color(value: str, default: str = "#2563eb") -> str:
    """Return a canonical six-digit color or the supplied default."""
    text = str(value or "").strip()
    return text.lower() if HEX_COLOR_PATTERN.fullmatch(text) else default
