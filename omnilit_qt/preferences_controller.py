from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, Property, Qt, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QGuiApplication, QImageReader
from PySide6.QtWidgets import QFileDialog

from .appearance import (
    ACCENT_COLORS,
    ACCENT_PRESETS,
    BACKGROUND_MODE_ALIASES,
    BACKGROUND_MODES,
    BACKGROUND_PRESETS,
    DENSITY_VALUES,
    FONT_SIZE_VALUES,
    PDF_BACKGROUND_VALUES,
    RADIUS_VALUES,
    THEME_MODE_ALIASES,
    THEME_MODES,
    THEME_PRESET_ALIASES,
    THEME_PRESET_NAMES,
    THEME_PRESETS,
    TRANSLATION_LINE_HEIGHT_VALUES,
    normalize_hex_color,
)
from .auth_controller import AuthController
from .i18n import tr
from .paths import AppPaths
from .services import AccountStore

THEME_MODE_SETTING = "appearance/mode"
THEME_PRESET_SETTING = "appearance/theme"
ACCENT_NAME_SETTING = "appearance/accent"
CUSTOM_ACCENT_SETTING = "appearance/customAccent"
FONT_SIZE_SETTING = "appearance/fontSize"
DENSITY_SETTING = "appearance/density"
RADIUS_SETTING = "appearance/radius"
PDF_BACKGROUND_SETTING = "appearance/pdfBackground"
TRANSLATION_LINE_HEIGHT_SETTING = "appearance/translationLineHeight"
BACKGROUND_MODE_SETTING = "appearance/background/mode"
BACKGROUND_OPACITY_SETTING = "appearance/background/opacity"
BACKGROUND_BLUR_SETTING = "appearance/background/blur"
HIGH_CONTRAST_SETTING = "appearance/highContrast"
REDUCE_MOTION_SETTING = "appearance/reduceMotion"
AUTO_NIGHT_START_SETTING = "appearance/autoNight/start"
AUTO_NIGHT_END_SETTING = "appearance/autoNight/end"
SIDEBAR_EXPANDED_SETTING = "ui_sidebar_expanded"
WORKSPACE_BACKGROUND_SETTING = "ui_workspace_background"
AVATAR_SETTING_PREFIX = "ui_avatar:"
AVATAR_STATUS_SETTING_PREFIX = "ui_avatar_status:"
AVATAR_STATUS_ID_SETTING_PREFIX = "ui_avatar_status_id:"
AVATAR_CUSTOM_STATUSES_SETTING_PREFIX = "ui_avatar_custom_statuses:"
ACCENT_NAMES = set(ACCENT_COLORS) | {"custom"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
DEFAULT_AVATAR_STATUSES = (
    {"id": "online", "label": "status_online", "color": "#10b981"},
    {"id": "focused", "label": "status_focused", "color": "#3b82f6"},
    {"id": "writing", "label": "status_writing", "color": "#8b5cf6"},
    {"id": "away", "label": "status_away", "color": "#f59e0b"},
    {"id": "busy", "label": "status_busy", "color": "#ef4444"},
    {"id": "meeting", "label": "status_meeting", "color": "#06b6d4"},
    {"id": "break", "label": "status_break", "color": "#f97316"},
    {"id": "offline", "label": "status_offline", "color": "#94a3b8"},
)
CUSTOM_STATUS_COLORS = ("#0ea5e9", "#8b5cf6", "#f97316", "#ec4899", "#14b8a6", "#64748b")


class PreferencesController(QObject):
    """Persist application appearance and per-account avatar preferences."""

    changed = Signal()

    def __init__(self, paths: AppPaths, store: AccountStore, auth: AuthController):
        super().__init__()
        self.paths = paths
        self.store = store
        self.auth = auth
        self._theme_mode = self._saved_alias_choice(THEME_MODE_SETTING, "light", THEME_MODES, THEME_MODE_ALIASES, "ui_theme_mode")
        self._theme_preset = self._saved_alias_choice(THEME_PRESET_SETTING, "scholar_light", THEME_PRESET_NAMES, THEME_PRESET_ALIASES)
        self._accent_name = self._saved_choice(ACCENT_NAME_SETTING, "blue", ACCENT_NAMES, "ui_accent_name")
        self._custom_accent_color = normalize_hex_color(self.store.setting(CUSTOM_ACCENT_SETTING), "#2563eb")
        self._font_size = self._saved_choice(FONT_SIZE_SETTING, "standard", set(FONT_SIZE_VALUES))
        self._density = self._saved_choice(DENSITY_SETTING, "standard", set(DENSITY_VALUES))
        self._radius = self._saved_choice(RADIUS_SETTING, "modern", set(RADIUS_VALUES))
        self._pdf_background = self._saved_choice(PDF_BACKGROUND_SETTING, "sepia", set(PDF_BACKGROUND_VALUES))
        self._translation_line_height = self._saved_choice(TRANSLATION_LINE_HEIGHT_SETTING, "standard", set(TRANSLATION_LINE_HEIGHT_VALUES))
        default_background_mode = "image" if self.store.setting(WORKSPACE_BACKGROUND_SETTING) else "default"
        self._background_mode = self._saved_alias_choice(BACKGROUND_MODE_SETTING, default_background_mode, BACKGROUND_MODES, BACKGROUND_MODE_ALIASES)
        self._background_opacity = self._saved_float(BACKGROUND_OPACITY_SETTING, 0.42, 0.0, 1.0)
        self._background_blur = self._saved_int(BACKGROUND_BLUR_SETTING, 0, 0, 32)
        self._high_contrast = self.store.setting(HIGH_CONTRAST_SETTING) == "1"
        self._reduce_motion = self.store.setting(REDUCE_MOTION_SETTING) == "1"
        self._auto_night_start = self._saved_time(AUTO_NIGHT_START_SETTING, "22:00")
        self._auto_night_end = self._saved_time(AUTO_NIGHT_END_SETTING, "07:00")
        self._sidebar_expanded = self.store.setting(SIDEBAR_EXPANDED_SETTING) == "1"
        self.auth.changed.connect(self.changed)
        self.auth.locale.languageChanged.connect(self.changed)
        app = QGuiApplication.instance()
        hints = app.styleHints() if app is not None and hasattr(app, "styleHints") else None
        if hints is not None and hasattr(hints, "colorSchemeChanged"):
            hints.colorSchemeChanged.connect(self.changed)
        self._night_timer = QTimer(self)
        self._night_timer.setInterval(60_000)
        self._night_timer.timeout.connect(self.changed)
        self._night_timer.start()

    def _saved_choice(self, key: str, default: str, allowed: set[str], legacy_key: str = "") -> str:
        value = self.store.setting(key)
        if not value and legacy_key:
            value = self.store.setting(legacy_key)
        return value if value in allowed else default

    def _saved_alias_choice(self, key: str, default: str, allowed: set[str], aliases: dict[str, str], legacy_key: str = "") -> str:
        value = self.store.setting(key)
        if not value and legacy_key:
            value = self.store.setting(legacy_key)
        normalized = aliases.get(value, value)
        if normalized in allowed:
            if normalized != value:
                self.store.set_setting(key, normalized)
            return normalized
        return default

    def _saved_float(self, key: str, default: float, minimum: float, maximum: float) -> float:
        try:
            return max(minimum, min(maximum, float(self.store.setting(key, str(default)))))
        except ValueError:
            return default

    def _saved_int(self, key: str, default: int, minimum: int, maximum: int) -> int:
        try:
            return max(minimum, min(maximum, int(self.store.setting(key, str(default)))))
        except ValueError:
            return default

    @staticmethod
    def _normalize_time(value: str, default: str) -> str:
        try:
            hour_text, minute_text = str(value or "").strip().split(":", 1)
            hour, minute = int(hour_text), int(minute_text)
        except (TypeError, ValueError):
            return default
        return f"{hour:02d}:{minute:02d}" if 0 <= hour <= 23 and 0 <= minute <= 59 else default

    def _saved_time(self, key: str, default: str) -> str:
        return self._normalize_time(self.store.setting(key, default), default)

    def _path_url(self, value: str) -> str:
        path = Path(value)
        if not value or not path.is_file():
            return ""
        stat = path.stat()
        url = QUrl.fromLocalFile(str(path))
        url.setQuery(f"v={stat.st_mtime_ns}-{stat.st_size}")
        return url.toString()

    def _avatar_key(self) -> str:
        return AVATAR_SETTING_PREFIX + self.auth.username

    def _avatar_status_key(self) -> str:
        return AVATAR_STATUS_SETTING_PREFIX + self.auth.username

    def _avatar_status_id_key(self) -> str:
        return AVATAR_STATUS_ID_SETTING_PREFIX + self.auth.username

    def _avatar_custom_statuses_key(self) -> str:
        return AVATAR_CUSTOM_STATUSES_SETTING_PREFIX + self.auth.username

    def _custom_statuses(self) -> list[dict[str, str]]:
        if not self.auth.username:
            return []
        try:
            items = json.loads(self.store.setting(self._avatar_custom_statuses_key(), "[]"))
        except (TypeError, ValueError):
            return []
        return [
            {"id": str(item["id"]), "label": str(item["label"]), "color": str(item["color"])}
            for item in items
            if isinstance(item, dict) and item.get("id") and item.get("label") and item.get("color")
        ]

    def _save_custom_statuses(self, items: list[dict[str, str]]) -> None:
        self.store.set_setting(self._avatar_custom_statuses_key(), json.dumps(items, ensure_ascii=False))

    def _status_options(self) -> list[dict[str, object]]:
        defaults = [
            {"id": item["id"], "label": self.auth.locale.textf(item["label"]), "color": item["color"], "custom": False}
            for item in DEFAULT_AVATAR_STATUSES
        ]
        customs = [dict(item, custom=True) for item in self._custom_statuses()]
        return defaults + customs

    @staticmethod
    def _default_status_id_for_value(value: str) -> str:
        normalized = str(value or "").strip().casefold()
        for item in DEFAULT_AVATAR_STATUSES:
            if normalized == item["id"]:
                return item["id"]
            if any(normalized == tr(language, item["label"]).casefold() for language in ("zh", "en", "ru")):
                return item["id"]
        return ""

    def _status_id(self) -> str:
        if not self.auth.username:
            return ""
        options = self._status_options()
        saved = self.store.setting(self._avatar_status_id_key())
        if any(item["id"] == saved for item in options):
            return saved
        legacy = self.store.setting(self._avatar_status_key()).strip()
        if legacy:
            default_id = self._default_status_id_for_value(legacy)
            if default_id:
                self.store.set_setting(self._avatar_status_id_key(), default_id)
                return default_id
            for item in options:
                if legacy == item["label"] or legacy == item["id"]:
                    self.store.set_setting(self._avatar_status_id_key(), str(item["id"]))
                    return str(item["id"])
            return self._create_custom_status(legacy)
        self.store.set_setting(self._avatar_status_id_key(), "online")
        return "online"

    def _status_option(self, status_id: str) -> dict[str, object]:
        return next((item for item in self._status_options() if item["id"] == status_id), self._status_options()[0])

    def _create_custom_status(self, label: str) -> str:
        value = str(label or "").strip()
        if not value:
            return "online"
        for item in self._status_options():
            if item["label"] == value:
                return str(item["id"])
        items = self._custom_statuses()
        status_id = "custom_" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
        if not any(item["id"] == status_id for item in items):
            color = CUSTOM_STATUS_COLORS[len(items) % len(CUSTOM_STATUS_COLORS)]
            items.append({"id": status_id, "label": value, "color": color})
            self._save_custom_statuses(items)
        self.store.set_setting(self._avatar_status_id_key(), status_id)
        self.store.set_setting(self._avatar_status_key(), value)
        return status_id

    @staticmethod
    def _is_night_hour(hour: int) -> bool:
        return PreferencesController._is_night_time(hour * 60, "22:00", "07:00")

    @staticmethod
    def _is_night_time(now_minutes: int, start_text: str, end_text: str) -> bool:
        start_hour, start_minute = (int(item) for item in start_text.split(":", 1))
        end_hour, end_minute = (int(item) for item in end_text.split(":", 1))
        start, end = start_hour * 60 + start_minute, end_hour * 60 + end_minute
        return start <= now_minutes < end if start < end else now_minutes >= start or now_minutes < end

    def _choose_image(self, title: str) -> str:
        value, _selected_filter = QFileDialog.getOpenFileName(
            None,
            title,
            str(Path.home()),
            "Images (*.png *.jpg *.jpeg *.webp)",
        )
        return value

    def _copy_image(self, source_value: str, stem: str) -> str:
        local_value = QUrl(source_value).toLocalFile() if source_value.startswith("file:") else source_value
        source = Path(local_value).expanduser()
        if source.suffix.lower() not in IMAGE_SUFFIXES or not source.is_file():
            return ""
        reader = QImageReader(str(source))
        if not reader.canRead():
            return ""
        suffix = source.suffix.lower()
        ui_dir = self.paths.data("ui")
        ui_dir.mkdir(parents=True, exist_ok=True)
        target = ui_dir / f"{stem}{suffix}"
        if source.resolve() != target.resolve():
            shutil.copy2(source, target)
        return str(target.resolve())

    def _set_choice(self, attribute: str, key: str, value: str, default: str, allowed: set[str]) -> None:
        normalized = value if value in allowed else default
        if getattr(self, attribute) == normalized:
            return
        setattr(self, attribute, normalized)
        self.store.set_setting(key, normalized)
        self.changed.emit()

    @Property("QVariantList", constant=True)
    def themePresets(self) -> list[dict[str, str]]:
        return [dict(item) for item in THEME_PRESETS]

    @Property("QVariantList", constant=True)
    def backgroundPresets(self) -> list[dict[str, str]]:
        return [dict(item) for item in BACKGROUND_PRESETS]

    @Property("QVariantList", constant=True)
    def accentPresets(self) -> list[dict[str, str]]:
        return [dict(item) for item in ACCENT_PRESETS]

    @Property(str, notify=changed)
    def themeMode(self) -> str:
        return self._theme_mode

    @Property(str, notify=changed)
    def effectiveThemeMode(self) -> str:
        if self._theme_mode == "adaptive":
            local_time = datetime.now().astimezone()
            now_minutes = local_time.hour * 60 + local_time.minute
            return "dark" if self._is_night_time(now_minutes, self._auto_night_start, self._auto_night_end) else "light"
        if self._theme_mode != "system":
            return self._theme_mode
        app = QGuiApplication.instance()
        hints = app.styleHints() if app is not None and hasattr(app, "styleHints") else None
        scheme = hints.colorScheme() if hints is not None and hasattr(hints, "colorScheme") else None
        return "dark" if scheme == Qt.ColorScheme.Dark else "light"

    @Property(str, notify=changed)
    def themePreset(self) -> str:
        return self._theme_preset

    @Property(str, notify=changed)
    def effectiveThemePreset(self) -> str:
        return self._theme_preset

    @Property(str, notify=changed)
    def accentName(self) -> str:
        return self._accent_name

    @Property(str, notify=changed)
    def accentColor(self) -> str:
        return self._custom_accent_color if self._accent_name == "custom" else ACCENT_COLORS.get(self._accent_name, "#2563eb")

    @Property(str, notify=changed)
    def customAccentColor(self) -> str:
        return self._custom_accent_color

    @Property(str, notify=changed)
    def fontSize(self) -> str:
        return self._font_size

    @Property(int, notify=changed)
    def fontSizeBase(self) -> int:
        return FONT_SIZE_VALUES[self._font_size]

    @Property(str, notify=changed)
    def density(self) -> str:
        return self._density

    @Property(float, notify=changed)
    def densityScale(self) -> float:
        return DENSITY_VALUES[self._density]

    @Property(str, notify=changed)
    def radius(self) -> str:
        return self._radius

    @Property(int, notify=changed)
    def radiusBase(self) -> int:
        return RADIUS_VALUES[self._radius]

    @Property(str, notify=changed)
    def pdfBackground(self) -> str:
        return self._pdf_background

    @Property(str, notify=changed)
    def pdfBackgroundColor(self) -> str:
        return PDF_BACKGROUND_VALUES[self._pdf_background]

    @Property(str, notify=changed)
    def translationLineHeight(self) -> str:
        return self._translation_line_height

    @Property(float, notify=changed)
    def translationLineHeightValue(self) -> float:
        return TRANSLATION_LINE_HEIGHT_VALUES[self._translation_line_height]

    @Property(str, notify=changed)
    def backgroundMode(self) -> str:
        return self._background_mode

    @Property(float, notify=changed)
    def backgroundOpacity(self) -> float:
        return self._background_opacity

    @Property(int, notify=changed)
    def backgroundBlur(self) -> int:
        return self._background_blur

    @Property(bool, notify=changed)
    def highContrast(self) -> bool:
        return self._high_contrast

    @Property(bool, notify=changed)
    def reduceMotion(self) -> bool:
        return self._reduce_motion

    @Property(str, notify=changed)
    def autoNightStart(self) -> str:
        return self._auto_night_start

    @Property(str, notify=changed)
    def autoNightEnd(self) -> str:
        return self._auto_night_end

    @Property(bool, notify=changed)
    def sidebarExpanded(self) -> bool:
        return self._sidebar_expanded

    @Property(str, notify=changed)
    def workspaceBackgroundUrl(self) -> str:
        return self._path_url(self.store.setting(WORKSPACE_BACKGROUND_SETTING))

    @Property(str, notify=changed)
    def avatarUrl(self) -> str:
        return self._path_url(self.store.setting(self._avatar_key())) if self.auth.username else ""

    @Property(str, notify=changed)
    def avatarInitial(self) -> str:
        return (self.auth.username[:1] or "?").upper()

    @Property(str, notify=changed)
    def avatarStatus(self) -> str:
        return self.avatarStatusLabel

    @Property(str, notify=changed)
    def avatarStatusId(self) -> str:
        return self._status_id()

    @Property(str, notify=changed)
    def avatarStatusLabel(self) -> str:
        return str(self._status_option(self._status_id())["label"]) if self.auth.username else ""

    @Property(str, notify=changed)
    def avatarStatusColor(self) -> str:
        return str(self._status_option(self._status_id())["color"]) if self.auth.username else "#94a3b8"

    @Property("QVariantList", notify=changed)
    def avatarStatusOptions(self) -> list[dict[str, object]]:
        return self._status_options()

    @Property(str, notify=changed)
    def localTimezoneName(self) -> str:
        local_time = datetime.now().astimezone()
        return local_time.tzname() or str(local_time.tzinfo or "")

    @Slot(str)
    def setThemeMode(self, mode: str) -> None:
        self._set_choice("_theme_mode", THEME_MODE_SETTING, THEME_MODE_ALIASES.get(mode, mode), "light", THEME_MODES)

    @Slot(str)
    def setThemePreset(self, preset: str) -> None:
        self._set_choice("_theme_preset", THEME_PRESET_SETTING, THEME_PRESET_ALIASES.get(preset, preset), "scholar_light", THEME_PRESET_NAMES)

    @Slot(str)
    def setAccentName(self, name: str) -> None:
        self._set_choice("_accent_name", ACCENT_NAME_SETTING, name, "blue", ACCENT_NAMES)

    @Slot(str)
    def setCustomAccentColor(self, color: str) -> None:
        value = normalize_hex_color(color, "")
        if not value:
            return
        self._custom_accent_color = value
        self._accent_name = "custom"
        self.store.set_setting(CUSTOM_ACCENT_SETTING, value)
        self.store.set_setting(ACCENT_NAME_SETTING, "custom")
        self.changed.emit()

    @Slot(str)
    def setFontSize(self, value: str) -> None:
        self._set_choice("_font_size", FONT_SIZE_SETTING, value, "standard", set(FONT_SIZE_VALUES))

    @Slot(str)
    def setDensity(self, value: str) -> None:
        self._set_choice("_density", DENSITY_SETTING, value, "standard", set(DENSITY_VALUES))

    @Slot(str)
    def setRadius(self, value: str) -> None:
        self._set_choice("_radius", RADIUS_SETTING, value, "modern", set(RADIUS_VALUES))

    @Slot(str)
    def setPdfBackground(self, value: str) -> None:
        self._set_choice("_pdf_background", PDF_BACKGROUND_SETTING, value, "sepia", set(PDF_BACKGROUND_VALUES))

    @Slot(str)
    def setTranslationLineHeight(self, value: str) -> None:
        self._set_choice("_translation_line_height", TRANSLATION_LINE_HEIGHT_SETTING, value, "standard", set(TRANSLATION_LINE_HEIGHT_VALUES))

    @Slot(str)
    def setBackgroundMode(self, mode: str) -> None:
        self._set_choice("_background_mode", BACKGROUND_MODE_SETTING, BACKGROUND_MODE_ALIASES.get(mode, mode), "default", BACKGROUND_MODES)

    @Slot(float)
    def setBackgroundOpacity(self, opacity: float) -> None:
        value = max(0.0, min(1.0, float(opacity)))
        if value == self._background_opacity:
            return
        self._background_opacity = value
        self.store.set_setting(BACKGROUND_OPACITY_SETTING, f"{value:.2f}")
        self.changed.emit()

    @Slot(int)
    def setBackgroundBlur(self, blur: int) -> None:
        value = max(0, min(32, int(blur)))
        if value == self._background_blur:
            return
        self._background_blur = value
        self.store.set_setting(BACKGROUND_BLUR_SETTING, str(value))
        self.changed.emit()

    @Slot(bool)
    def setHighContrast(self, enabled: bool) -> None:
        self._high_contrast = bool(enabled)
        self.store.set_setting(HIGH_CONTRAST_SETTING, "1" if self._high_contrast else "0")
        self.changed.emit()

    @Slot(bool)
    def setReduceMotion(self, enabled: bool) -> None:
        self._reduce_motion = bool(enabled)
        self.store.set_setting(REDUCE_MOTION_SETTING, "1" if self._reduce_motion else "0")
        self.changed.emit()

    @Slot(str)
    def setAutoNightStart(self, value: str) -> None:
        self._auto_night_start = self._normalize_time(value, "22:00")
        self.store.set_setting(AUTO_NIGHT_START_SETTING, self._auto_night_start)
        self.changed.emit()

    @Slot(str)
    def setAutoNightEnd(self, value: str) -> None:
        self._auto_night_end = self._normalize_time(value, "07:00")
        self.store.set_setting(AUTO_NIGHT_END_SETTING, self._auto_night_end)
        self.changed.emit()

    @Slot()
    def toggleSidebarExpanded(self) -> None:
        self._sidebar_expanded = not self._sidebar_expanded
        self.store.set_setting(SIDEBAR_EXPANDED_SETTING, "1" if self._sidebar_expanded else "0")
        self.changed.emit()

    @Slot(str, result=bool)
    @Slot(result=bool)
    def uploadWorkspaceBackground(self, source: str = "") -> bool:
        value = source or self._choose_image("Choose workspace background")
        copied = self._copy_image(value, "workspace-background") if value else ""
        if not copied:
            return False
        self.store.set_setting(WORKSPACE_BACKGROUND_SETTING, copied)
        self._background_mode = "image"
        self.store.set_setting(BACKGROUND_MODE_SETTING, "image")
        self.changed.emit()
        return True

    @Slot()
    def clearWorkspaceBackground(self) -> None:
        self.store.delete_setting(WORKSPACE_BACKGROUND_SETTING)
        self._background_mode = "default"
        self.store.set_setting(BACKGROUND_MODE_SETTING, "default")
        self.changed.emit()

    @Slot()
    def extractAccentFromBackground(self) -> None:
        path = self.store.setting(WORKSPACE_BACKGROUND_SETTING)
        image = QImageReader(path).read() if path else None
        if image is None or image.isNull():
            return
        scaled = image.scaled(12, 12, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        colors = [scaled.pixelColor(x, y) for x in range(scaled.width()) for y in range(scaled.height())]
        useful = [color for color in colors if 48 <= color.lightness() <= 208]
        samples = useful or colors
        red = sum(color.red() for color in samples) // len(samples)
        green = sum(color.green() for color in samples) // len(samples)
        blue = sum(color.blue() for color in samples) // len(samples)
        self.setCustomAccentColor(f"#{red:02x}{green:02x}{blue:02x}")

    @Slot()
    def resetAppearance(self) -> None:
        keys = (
            THEME_MODE_SETTING, THEME_PRESET_SETTING, ACCENT_NAME_SETTING, CUSTOM_ACCENT_SETTING,
            FONT_SIZE_SETTING, DENSITY_SETTING, RADIUS_SETTING, PDF_BACKGROUND_SETTING,
            TRANSLATION_LINE_HEIGHT_SETTING, BACKGROUND_MODE_SETTING, BACKGROUND_OPACITY_SETTING,
            BACKGROUND_BLUR_SETTING, HIGH_CONTRAST_SETTING, REDUCE_MOTION_SETTING,
            AUTO_NIGHT_START_SETTING, AUTO_NIGHT_END_SETTING, WORKSPACE_BACKGROUND_SETTING,
        )
        for key in keys:
            self.store.delete_setting(key)
        self._theme_mode, self._theme_preset, self._accent_name = "light", "scholar_light", "blue"
        self._custom_accent_color = "#2563eb"
        self._font_size, self._density, self._radius = "standard", "standard", "modern"
        self._pdf_background, self._translation_line_height = "sepia", "standard"
        self._background_mode, self._background_opacity, self._background_blur = "default", 0.42, 0
        self._high_contrast, self._reduce_motion = False, False
        self._auto_night_start, self._auto_night_end = "22:00", "07:00"
        self.changed.emit()

    @Slot(str, result=bool)
    @Slot(result=bool)
    def uploadAvatar(self, source: str = "") -> bool:
        if not self.auth.username:
            return False
        value = source or self._choose_image("Choose avatar")
        digest = hashlib.sha256(self.auth.username.encode("utf-8")).hexdigest()[:16]
        copied = self._copy_image(value, f"avatar-{digest}") if value else ""
        if not copied:
            return False
        self.store.set_setting(self._avatar_key(), copied)
        self.changed.emit()
        return True

    @Slot()
    def clearAvatar(self) -> None:
        if self.auth.username:
            self.store.delete_setting(self._avatar_key())
            self.changed.emit()

    @Slot(str)
    def setAvatarStatus(self, status: str) -> None:
        if not self.auth.username:
            return
        value = status.strip()
        options = self._status_options()
        default_id = self._default_status_id_for_value(value)
        selected = next((item for item in options if item["id"] == default_id or value in {item["id"], item["label"]}), None)
        status_id = str(selected["id"]) if selected else self._create_custom_status(value)
        label = str(self._status_option(status_id)["label"])
        self.store.set_setting(self._avatar_status_id_key(), status_id)
        self.store.set_setting(self._avatar_status_key(), label)
        self.changed.emit()

    @Slot(str)
    def setAvatarStatusId(self, status_id: str) -> None:
        self.setAvatarStatus(status_id)

    @Slot(str, result=bool)
    def addCustomAvatarStatus(self, label: str) -> bool:
        if not self.auth.username or not label.strip():
            return False
        self._create_custom_status(label)
        self.changed.emit()
        return True

    @Slot(str, str, result=bool)
    def renameCustomAvatarStatus(self, status_id: str, label: str) -> bool:
        value = label.strip()
        items = self._custom_statuses()
        item = next((item for item in items if item["id"] == status_id), None)
        if item is None or not value:
            return False
        item["label"] = value
        self._save_custom_statuses(items)
        if self._status_id() == status_id:
            self.store.set_setting(self._avatar_status_key(), value)
        self.changed.emit()
        return True

    @Slot(str, result=bool)
    def deleteCustomAvatarStatus(self, status_id: str) -> bool:
        items = self._custom_statuses()
        filtered = [item for item in items if item["id"] != status_id]
        if len(filtered) == len(items):
            return False
        self._save_custom_statuses(filtered)
        if self.store.setting(self._avatar_status_id_key()) == status_id:
            self.store.set_setting(self._avatar_status_id_key(), "online")
            self.store.set_setting(self._avatar_status_key(), self.auth.locale.textf("status_online"))
        self.changed.emit()
        return True
