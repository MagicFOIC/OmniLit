from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import shutil
import subprocess
import sys
import threading
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Property, QCoreApplication, Qt, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QGuiApplication, QImageReader
from PySide6.QtWidgets import QFileDialog

from .i18n import LocaleController, tr
from .appearance import (
    ACCENT_COLORS,
    ACCENT_PRESETS,
    BACKGROUND_MODES,
    DENSITY_VALUES,
    FONT_SIZE_VALUES,
    PDF_BACKGROUND_VALUES,
    RADIUS_VALUES,
    THEME_MODES,
    THEME_PRESET_MODES,
    THEME_PRESET_NAMES,
    THEME_PRESETS,
    TRANSLATION_LINE_HEIGHT_VALUES,
    normalize_hex_color,
)
from .paths import AppPaths
from .secrets import protect_secret, unprotect_secret
from .services import AccountStore, as_bool, as_int, build_download_config, import_resource_module
from .support import (
    DEFAULT_GLOSSARY_FILENAMES,
    DEFAULT_KEY_FILE_NAME,
    USER_KEY_FILE_NAME,
    glossary_catalog,
    load_default_key,
    load_encrypted_key,
    profile_maps,
    write_encrypted_key,
)


DEFAULT_UPDATE_MANIFEST_URL = "https://originchaos.top/omnilit/update_manifest.json"
DOWNLOAD_FORM_SETTING = "download_form_config"
TRANSLATION_FORM_SETTING = "translation_form_config"
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
ACCENT_NAMES = set(ACCENT_COLORS) | {"custom"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
DOWNLOAD_FORM_FIELDS = (
    "email",
    "outputDir",
    "fromDate",
    "toDate",
    "keywords",
    "sort",
    "maxPages",
    "perPage",
    "maxRecords",
    "requestDelay",
    "pageDelay",
    "minPdfBytes",
    "downloadPdfs",
    "retryMissingPdfs",
    "writeRetryRecords",
    "strictKeywordMatch",
    "minKeywordMatchRatio",
    "loop",
    "loopSleep",
    "maxRuntimeHours",
    "resume",
    "fastForwardExistingPages",
    "oaOnly",
    "sources",
    "advancedVisible",
)
TRANSLATION_FORM_FIELDS = (
    "inputDir",
    "outputDir",
    "model",
    "baseUrl",
    "profileIndex",
    "glossaryPaths",
    "batchSize",
    "maxBatchChars",
    "maxPages",
    "layoutOnly",
    "useCache",
    "summaryPage",
    "translateReferences",
    "translateHeaderFooter",
)


def _json_form_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, float, int, str)):
        return value
    if isinstance(value, (list, tuple)):
        return [_json_form_value(item) for item in value]
    return str(value)


def _load_form_setting(store: AccountStore, key: str) -> dict[str, Any]:
    try:
        value = json.loads(store.setting(key, "{}"))
    except (TypeError, json.JSONDecodeError):
        return {}
    return dict(value) if isinstance(value, dict) else {}


def _save_form_setting(
    store: AccountStore,
    key: str,
    raw: dict[str, Any],
    fields: tuple[str, ...],
) -> dict[str, Any]:
    value = {field: _json_form_value(raw[field]) for field in fields if field in raw}
    store.set_setting(key, json.dumps(value, ensure_ascii=False, sort_keys=True))
    return value


def _format_bytes(size: int) -> str:
    """格式化字节数。参数：字节数量。返回值：适合界面展示的文本。"""
    value = float(max(0, size))
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{int(size)} B"


def _open_path(path: Path) -> None:
    """使用系统文件管理器打开目录。参数：文件或目录路径。返回值：无。"""
    target = path if path.is_dir() else path.parent
    target.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        os.startfile(target)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(target)])
    else:
        subprocess.Popen(["xdg-open", str(target)])


class LogWriter:
    """将核心模块的标准输出转发到 Qt 日志。"""

    def __init__(self, callback) -> None:
        """保存日志回调。参数：文本回调。返回值：无。"""
        self.callback = callback

    def write(self, text: str) -> int:
        """转发非空文本。参数：输出文本。返回值：原文本长度。"""
        if text.strip():
            self.callback(text)
        return len(text)

    def flush(self) -> None:
        """兼容文件接口。参数：无。返回值：无。"""
        return None


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
                return str(json.loads(path.read_text(encoding="utf-8")).get("version") or "unknown")
            except Exception:
                continue
        return "unknown"

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


class AuthController(QObject):
    """处理本地账号登录、注册和加密密码记忆。"""

    changed = Signal()
    authenticated = Signal()
    loggedOut = Signal()

    def __init__(self, app: AppController, store: AccountStore, locale: LocaleController):
        """初始化账号状态。参数：应用、账号存储和语言控制器。返回值：无。"""
        super().__init__()
        self.app = app
        self.store = store
        self.locale = locale
        self._username = ""
        self._status = ""
        self._remembered_password = ""
        self._restore_remembered_password()

    def _restore_remembered_password(self) -> None:
        """解密上次保存的密码。参数：无。返回值：无。"""
        if self.store.setting("remember_password") != "1":
            return
        try:
            self._remembered_password = unprotect_secret(self.store.setting("remember_secret"))
        except Exception:
            # 密文损坏或跨用户复制时直接清理，避免每次启动重复报错。
            self._clear_login_secret()

    def _clear_login_secret(self) -> None:
        """删除本地登录密文。参数：无。返回值：无。"""
        self._remembered_password = ""
        for key in ("remember_password", "remember_secret"):
            self.store.delete_setting(key)

    def _save_login_secret(self, username: str, password: str, remember_password: bool) -> None:
        """按用户选择保存或清理密码。参数：账号、密码和记忆开关。返回值：无。"""
        self.store.set_setting("remember_username", username.strip())
        if not remember_password:
            self._clear_login_secret()
            return
        self.store.set_setting("remember_password", "1")
        self.store.set_setting("remember_secret", protect_secret(password))
        self._remembered_password = password

    def _set_status(self, value: str) -> None:
        """更新账号状态。参数：消息文本。返回值：无。"""
        self._status = value
        self.app.set_status(value)
        self.changed.emit()

    def _error_text(self, exc: Exception) -> str:
        """翻译账号存储异常。参数：底层异常。返回值：当前语言错误文本。"""
        message = str(exc)
        if self.locale.language != "en":
            return message
        return {
            "用户名至少需要 3 个字符。": "Username must contain at least 3 characters.",
            "密码至少需要 6 个字符。": "Password must contain at least 6 characters.",
            "用户名已存在。": "Username already exists.",
            "请输入用户名和密码。": "Enter your username and password.",
            "账号不存在。": "Account does not exist.",
            "密码不正确。": "Incorrect password.",
        }.get(message, message)

    @Property(bool, notify=changed)
    def loggedIn(self) -> bool:
        """返回登录状态。参数：无。返回值：是否已登录。"""
        return bool(self._username)

    @Property(str, notify=changed)
    def username(self) -> str:
        """返回当前账号。参数：无。返回值：用户名。"""
        return self._username

    @Property(str, constant=True)
    def rememberedUsername(self) -> str:
        """返回上次账号。参数：无。返回值：用户名。"""
        return self.store.setting("remember_username")

    @Property(str, constant=True)
    def rememberedPassword(self) -> str:
        """返回已解密密码用于自动填充。参数：无。返回值：密码明文。"""
        return self._remembered_password

    @Property(bool, constant=True)
    def rememberPasswordChecked(self) -> bool:
        """返回记住密码复选框初始状态。参数：无。返回值：是否勾选。"""
        return bool(self._remembered_password)

    @Property(str, notify=changed)
    def statusText(self) -> str:
        """返回账号状态。参数：无。返回值：状态文本。"""
        return self._status

    @Slot(str, str, bool, result=bool)
    def login(self, username: str, password: str, remember_password: bool = False) -> bool:
        """登录账号。参数：账号、密码和记忆开关。返回值：是否成功。"""
        try:
            self.store.login(username, password)
            self._save_login_secret(username, password, remember_password)
        except (ValueError, OSError) as exc:
            self._set_status(self._error_text(exc))
            return False
        self._username = username.strip()
        self._set_status(self.locale.textf("logged_in", username=self._username))
        self.authenticated.emit()
        return True

    @Slot(str, str, str, bool, result=bool)
    def registerUser(self, username: str, password: str, confirm_password: str, remember_password: bool = False) -> bool:
        """注册并登录。参数：账号、两次密码和记忆开关。返回值：是否成功。"""
        if password != confirm_password:
            self._set_status(self.locale.textf("password_mismatch"))
            return False
        try:
            self.store.register(username, password)
            self.store.login(username, password)
            self._save_login_secret(username, password, remember_password)
        except (ValueError, OSError) as exc:
            self._set_status(self._error_text(exc))
            return False
        self._username = username.strip()
        self._set_status(self.locale.textf("registered", username=self._username))
        self.authenticated.emit()
        return True

    @Slot()
    def logout(self) -> None:
        """退出当前账号但保留用户选择的密文。参数：无。返回值：无。"""
        self._username = ""
        self._set_status(self.locale.textf("logged_out"))
        self.loggedOut.emit()


class PreferencesController(QObject):
    """Persist application appearance and per-account avatar preferences."""

    changed = Signal()

    def __init__(self, paths: AppPaths, store: AccountStore, auth: AuthController):
        super().__init__()
        self.paths = paths
        self.store = store
        self.auth = auth
        self._theme_mode = self._saved_choice(THEME_MODE_SETTING, "light", THEME_MODES, "ui_theme_mode")
        self._theme_preset = self._saved_choice(THEME_PRESET_SETTING, "scholar_light", THEME_PRESET_NAMES)
        self._accent_name = self._saved_choice(ACCENT_NAME_SETTING, "blue", ACCENT_NAMES, "ui_accent_name")
        self._custom_accent_color = normalize_hex_color(self.store.setting(CUSTOM_ACCENT_SETTING), "#2563eb")
        self._font_size = self._saved_choice(FONT_SIZE_SETTING, "standard", set(FONT_SIZE_VALUES))
        self._density = self._saved_choice(DENSITY_SETTING, "standard", set(DENSITY_VALUES))
        self._radius = self._saved_choice(RADIUS_SETTING, "modern", set(RADIUS_VALUES))
        self._pdf_background = self._saved_choice(PDF_BACKGROUND_SETTING, "sepia", set(PDF_BACKGROUND_VALUES))
        self._translation_line_height = self._saved_choice(TRANSLATION_LINE_HEIGHT_SETTING, "standard", set(TRANSLATION_LINE_HEIGHT_VALUES))
        default_background_mode = "image" if self.store.setting(WORKSPACE_BACKGROUND_SETTING) else "solid"
        self._background_mode = self._saved_choice(BACKGROUND_MODE_SETTING, default_background_mode, BACKGROUND_MODES)
        self._background_opacity = self._saved_float(BACKGROUND_OPACITY_SETTING, 0.42, 0.0, 1.0)
        self._background_blur = self._saved_int(BACKGROUND_BLUR_SETTING, 0, 0, 32)
        self._high_contrast = self.store.setting(HIGH_CONTRAST_SETTING) == "1"
        self._reduce_motion = self.store.setting(REDUCE_MOTION_SETTING) == "1"
        self._auto_night_start = self._saved_time(AUTO_NIGHT_START_SETTING, "22:00")
        self._auto_night_end = self._saved_time(AUTO_NIGHT_END_SETTING, "07:00")
        self._sidebar_expanded = self.store.setting(SIDEBAR_EXPANDED_SETTING) == "1"
        self.auth.changed.connect(self.changed)
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
    def accentPresets(self) -> list[dict[str, str]]:
        return [dict(item) for item in ACCENT_PRESETS]

    @Property(str, notify=changed)
    def themeMode(self) -> str:
        return self._theme_mode

    @Property(str, notify=changed)
    def effectiveThemeMode(self) -> str:
        if self._theme_mode == "auto_night":
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
        if self.effectiveThemeMode == "dark":
            return "library_dark"
        return "scholar_light" if self._theme_preset == "library_dark" else self._theme_preset

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
        return self.store.setting(self._avatar_status_key()) if self.auth.username else ""

    @Property(str, notify=changed)
    def localTimezoneName(self) -> str:
        local_time = datetime.now().astimezone()
        return local_time.tzname() or str(local_time.tzinfo or "")

    @Slot(str)
    def setThemeMode(self, mode: str) -> None:
        self._set_choice("_theme_mode", THEME_MODE_SETTING, mode, "light", THEME_MODES)

    @Slot(str)
    def setThemePreset(self, preset: str) -> None:
        value = preset if preset in THEME_PRESET_NAMES else "scholar_light"
        changed = value != self._theme_preset
        self._theme_preset = value
        self.store.set_setting(THEME_PRESET_SETTING, value)
        preferred_mode = THEME_PRESET_MODES[value]
        if preferred_mode != self._theme_mode:
            self._theme_mode = preferred_mode
            self.store.set_setting(THEME_MODE_SETTING, preferred_mode)
            changed = True
        if changed:
            self.changed.emit()

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
        self._set_choice("_background_mode", BACKGROUND_MODE_SETTING, mode, "solid", BACKGROUND_MODES)

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
        self._background_mode = "solid"
        self.store.set_setting(BACKGROUND_MODE_SETTING, "solid")
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
        self._background_mode, self._background_opacity, self._background_blur = "solid", 0.42, 0
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
        if value:
            self.store.set_setting(self._avatar_status_key(), value)
        else:
            self.store.delete_setting(self._avatar_status_key())
        self.changed.emit()


class DownloadController(QObject):
    """在后台线程中运行多来源文献下载核心。"""

    changed = Signal()
    progress = Signal(object, str)
    finished = Signal(bool, str)

    def __init__(self, app: AppController, paths: AppPaths, store: AccountStore, locale: LocaleController):
        """初始化下载控制器。参数：应用、路径和语言控制器。返回值：无。"""
        super().__init__()
        self.app, self.paths, self.store, self.locale = app, paths, store, locale
        self._saved_config = _load_form_setting(store, DOWNLOAD_FORM_SETTING)
        self._running = False
        self._status = locale.textf("not_started")
        self._stats = self._empty_stats()
        self._logs: list[str] = []
        self._stop = threading.Event()
        self.progress.connect(self._on_progress)
        self.finished.connect(self._on_finished)

    @staticmethod
    def _empty_stats() -> dict[str, int]:
        """生成空统计值。参数：无。返回值：统计字典。"""
        return {key: 0 for key in ("existing_records", "fetched_items", "added_records", "skipped_duplicates", "skipped_without_key", "skipped_irrelevant", "open_access_records", "downloaded_pdfs", "failed_pdfs", "retried_existing_records", "request_failures")}

    def _append(self, text: str) -> None:
        """追加日志并限制长度。参数：文本。返回值：无。"""
        if text.strip():
            self._logs.append(text.strip())
            self._logs = self._logs[-800:]

    def _on_progress(self, stats: object, message: str) -> None:
        """接收下载进度。参数：统计对象和消息。返回值：无。"""
        self._stats = {key: int(getattr(stats, key, 0) or 0) for key in self._empty_stats()}
        self._status = message
        self._append(message)
        self.app.set_status(message)
        self.changed.emit()

    def _on_finished(self, ok: bool, message: str) -> None:
        """完成下载状态流转。参数：成功标志和消息。返回值：无。"""
        self._running = False
        self._status = message
        self._append(message)
        self.app.set_status(message)
        self.changed.emit()

    @Property(bool, notify=changed)
    def running(self) -> bool:
        """返回任务状态。参数：无。返回值：是否运行。"""
        return self._running

    @Property(str, notify=changed)
    def statusText(self) -> str:
        """返回下载状态。参数：无。返回值：状态文本。"""
        return self._status

    @Property(str, notify=changed)
    def logText(self) -> str:
        """返回下载日志。参数：无。返回值：多行文本。"""
        return "\n".join(self._logs)

    @Property("QVariantMap", notify=changed)
    def stats(self) -> dict[str, int]:
        """返回下载统计。参数：无。返回值：统计字典。"""
        return dict(self._stats)

    @Property(str, constant=True)
    def defaultOutputDir(self) -> str:
        """返回默认输出目录。参数：无。返回值：目录文本。"""
        return str(self.paths.data("Download"))

    @Property("QVariantMap", constant=True)
    def savedConfig(self) -> dict[str, Any]:
        """Return the saved non-sensitive download form fields."""
        return dict(self._saved_config)

    @Slot("QVariantMap")
    def saveConfig(self, config_map: dict[str, Any]) -> None:
        """Persist the non-sensitive download form fields."""
        self._saved_config = _save_form_setting(
            self.store,
            DOWNLOAD_FORM_SETTING,
            dict(config_map or {}),
            DOWNLOAD_FORM_FIELDS,
        )

    @Property(str, constant=True)
    def defaultKeywords(self) -> str:
        """返回默认关键词。参数：无。返回值：多行文本。"""
        return "\n".join(import_resource_module(self.paths, "Download", "literature_download_core").DEFAULT_KEYWORDS)

    @Property("QVariantList", constant=True)
    def availableSources(self) -> list[dict[str, str]]:
        """Return literature database choices for the download form."""
        return import_resource_module(self.paths, "Download", "literature_download_core").source_maps()

    @Property(str, constant=True)
    def defaultFromDate(self) -> str:
        """返回默认开始日期。参数：无。返回值：ISO 日期。"""
        return str(import_resource_module(self.paths, "Download", "literature_download_core").DEFAULT_FROM_DATE)

    @Property(str, constant=True)
    def defaultToDate(self) -> str:
        """返回默认结束日期。参数：无。返回值：ISO 日期。"""
        return str(import_resource_module(self.paths, "Download", "literature_download_core").DEFAULT_TO_DATE)

    @Slot(str, result=str)
    def chooseDirectory(self, initial_dir: str) -> str:
        """选择下载目录。参数：初始目录。返回值：所选目录。"""
        return str(QFileDialog.getExistingDirectory(None, self.locale.textf("output_dir"), initial_dir or self.defaultOutputDir) or "")

    @Slot(str)
    def openDirectory(self, path: str) -> None:
        """打开下载目录。参数：目录文本。返回值：无。"""
        _open_path(Path(path or self.defaultOutputDir))

    @Slot("QVariantMap", result=bool)
    def start(self, config_map: dict[str, Any]) -> bool:
        """启动下载线程。参数：QML 配置。返回值：是否成功启动。"""
        if self._running:
            self._on_finished(False, self.locale.textf("download_busy"))
            return False
        language = self.locale.language
        try:
            raw = dict(config_map or {})
            core, config = build_download_config(self.paths, raw, lambda: self._stop.is_set(), lambda stats, message: self.progress.emit(stats, str(message)), language)
            core.validate_config(config)
            self.saveConfig(raw)
        except Exception as exc:
            self._on_finished(False, tr(language, "config_error", error=exc))
            return False

        def worker() -> None:
            """执行下载任务并通过信号回到界面线程。参数：无。返回值：无。"""
            try:
                core.main(config)
            except Exception as exc:
                self.finished.emit(False, tr(language, "download_failed", error=exc))
            else:
                self.finished.emit(not self._stop.is_set(), tr(language, "download_stopped" if self._stop.is_set() else "download_done"))

        self._stop.clear()
        self._logs, self._stats, self._running = [], self._empty_stats(), True
        self._status = tr(language, "download_started")
        self._append(self._status)
        self.changed.emit()
        threading.Thread(target=worker, name="LiteratureDownload", daemon=True).start()
        return True

    @Slot()
    def stop(self) -> None:
        """请求停止下载。参数：无。返回值：无。"""
        if self._running:
            self._stop.set()
            self._status = self.locale.textf("request_stop_download")
            self._append(self._status)
        self.app.set_status(self._status)
        self.changed.emit()


class TranslationCancelled(RuntimeError):
    """表示用户主动取消翻译。"""


class TranslationController(QObject):
    """在后台线程中运行文献翻译和版式重建核心。"""

    changed = Signal()
    progress = Signal(str, str, int, int)
    log = Signal(str)
    document = Signal(str)
    preview = Signal(str)
    finished = Signal(bool, str)

    def __init__(self, app: AppController, paths: AppPaths, store: AccountStore, locale: LocaleController):
        """初始化翻译控制器。参数：应用、路径和语言。返回值：无。"""
        super().__init__()
        self.app, self.paths, self.store, self.locale = app, paths, store, locale
        self._saved_config = _load_form_setting(store, TRANSLATION_FORM_SETTING)
        self._running, self._progress, self._workflow_index = False, 0.0, 0
        self._status, self._current_document = locale.textf("not_started"), ""
        self._preview_text = locale.textf("preview_waiting")
        self._logs: list[str] = []
        self._stop = threading.Event()
        self._file_index, self._file_total = 0, 1
        self._default_key = self._default_key_source = self._user_key = ""
        self.progress.connect(self._on_progress)
        self.log.connect(self._append_log)
        self.document.connect(self._on_document)
        self.preview.connect(self._on_preview)
        self.finished.connect(self._on_finished)

    @Property("QVariantList", constant=True)
    def modelProfiles(self) -> list[dict[str, object]]:
        """返回模型档案。参数：无。返回值：档案列表。"""
        return profile_maps()

    @Property("QVariantList", notify=changed)
    def glossaryCatalog(self) -> list[dict[str, object]]:
        """返回可写目录中的术语表。参数：无。返回值：术语表列表。"""
        return glossary_catalog(self.paths.glossary_dir)

    @Property(str, constant=True)
    def defaultInputDir(self) -> str:
        """返回默认输入目录。参数：无。返回值：目录文本。"""
        return str(self.paths.data("Translate", "pdf"))

    @Property(str, constant=True)
    def defaultOutputDir(self) -> str:
        """返回默认输出目录。参数：无。返回值：目录文本。"""
        return str(self.paths.data("Translate", "out"))

    @Property("QVariantMap", constant=True)
    def savedConfig(self) -> dict[str, Any]:
        """Return the saved non-sensitive translation form fields."""
        return dict(self._saved_config)

    @Slot("QVariantMap")
    def saveConfig(self, config_map: dict[str, Any]) -> None:
        """Persist translation form fields without credentials."""
        self._saved_config = _save_form_setting(
            self.store,
            TRANSLATION_FORM_SETTING,
            dict(config_map or {}),
            TRANSLATION_FORM_FIELDS,
        )

    @Property(bool, notify=changed)
    def running(self) -> bool:
        """返回任务状态。参数：无。返回值：是否运行。"""
        return self._running

    @Property(str, notify=changed)
    def statusText(self) -> str:
        """返回翻译状态。参数：无。返回值：状态文本。"""
        return self._status

    @Property(float, notify=changed)
    def progressValue(self) -> float:
        """返回整体进度。参数：无。返回值：0 到 1。"""
        return self._progress

    @Property(int, notify=changed)
    def workflowIndex(self) -> int:
        """返回当前阶段。参数：无。返回值：阶段索引。"""
        return self._workflow_index

    @Property(str, notify=changed)
    def currentDocument(self) -> str:
        """返回当前文档。参数：无。返回值：文档文本。"""
        return self._current_document

    @Property(str, notify=changed)
    def logText(self) -> str:
        """返回翻译日志。参数：无。返回值：多行文本。"""
        return "\n".join(self._logs)

    @Property(str, notify=changed)
    def previewText(self) -> str:
        """Return translated text completed so far for live preview."""
        return self._preview_text

    @Property(bool, notify=changed)
    def defaultKeyLoaded(self) -> bool:
        """返回默认 Key 状态。参数：无。返回值：是否已加载。"""
        return bool(self._default_key)

    @Property(str, notify=changed)
    def defaultKeySource(self) -> str:
        """返回默认 Key 来源。参数：无。返回值：来源文本。"""
        return self._default_key_source

    @Property(str, constant=True)
    def defaultKeyPath(self) -> str:
        """返回可写部署 Key 路径。参数：无。返回值：路径文本。"""
        return str(self.paths.data("Translate", DEFAULT_KEY_FILE_NAME))

    @Property(bool, notify=changed)
    def defaultKeyExists(self) -> bool:
        """返回可写部署 Key 文件状态。参数：无。返回值：是否存在。"""
        return Path(self.defaultKeyPath).exists()

    @Property(bool, notify=changed)
    def rememberedKeyExists(self) -> bool:
        """返回用户 Key 文件状态。参数：无。返回值：是否存在。"""
        return self.paths.data("Translate", USER_KEY_FILE_NAME).exists()

    @staticmethod
    def _stage_fraction(stage: str, current: int, total: int) -> float:
        """计算单文件阶段进度。参数：阶段、当前值和总数。返回值：0 到 1。"""
        ratio = max(0.0, min(1.0, current / max(1, total)))
        start, width = {"prepare": (0.0, 0.02), "extract": (0.02, 0.10), "translate": (0.12, 0.64), "summary": (0.76, 0.06), "render": (0.82, 0.16), "done": (1.0, 0.0)}.get(stage, (0.0, 0.0))
        return start + width * ratio

    def _append_log(self, message: str) -> None:
        """追加日志并限制长度。参数：日志文本。返回值：无。"""
        self._logs.extend(line.strip() for line in str(message).splitlines() if line.strip())
        self._logs = self._logs[-1000:]
        self.changed.emit()

    def _on_document(self, document: str) -> None:
        """切换当前文档。参数：文档文本。返回值：无。"""
        self._current_document = document
        self.changed.emit()

    def _on_preview(self, text: str) -> None:
        """Refresh the live translation preview."""
        self._preview_text = str(text)
        self.changed.emit()

    def _on_progress(self, stage: str, message: str, current: int, total: int) -> None:
        """合并核心阶段进度。参数：阶段、消息、当前值和总数。返回值：无。"""
        self._workflow_index = {"prepare": 0, "extract": 1, "translate": 2, "summary": 3, "render": 4, "done": 5}.get(stage, self._workflow_index)
        self._progress = ((max(1, self._file_index) - 1) + self._stage_fraction(stage, current, total)) / max(1, self._file_total)
        self._status = message
        self._append_log(f"{stage}: {message}")
        self.app.set_status(message)
        self.changed.emit()

    def _on_finished(self, ok: bool, message: str) -> None:
        """完成翻译状态流转。参数：成功标志和消息。返回值：无。"""
        self._running, self._status = False, message
        if ok:
            self._progress, self._workflow_index = 1.0, 5
        self._append_log(message)
        self.app.set_status(message)
        self.changed.emit()

    @Slot(str, str, result=str)
    def chooseDirectory(self, title: str, initial_dir: str) -> str:
        """选择目录。参数：标题和初始目录。返回值：所选目录。"""
        return str(QFileDialog.getExistingDirectory(None, title, initial_dir or str(self.paths.data("Translate"))) or "")

    @Slot(str)
    def openDirectory(self, path: str) -> None:
        """打开目录。参数：目录文本。返回值：无。"""
        _open_path(Path(path))

    @Slot()
    def openGlossaryDirectory(self) -> None:
        """打开可写术语表目录。参数：无。返回值：无。"""
        self.openDirectory(str(self.paths.glossary_dir))

    @Slot()
    def refreshGlossaries(self) -> None:
        """刷新术语表列表。参数：无。返回值：无。"""
        self.changed.emit()

    @Slot(str, result=bool)
    def unlockDefaultKey(self, password: str) -> bool:
        """解锁部署 Key。参数：加密密码。返回值：是否成功。"""
        try:
            self._default_key, self._default_key_source = load_default_key(self.paths.data("Translate"), self.paths.resource("Translate"), password)
            if not self._default_key:
                raise ValueError(self.locale.textf("default_key_unconfigured"))
        except Exception as exc:
            self._default_key = self._default_key_source = ""
            self._status = self.locale.textf("default_key_unlock_failed", error=exc)
            self.changed.emit()
            return False
        self._status = self.locale.textf("default_key_unlocked", source=self._default_key_source)
        self.changed.emit()
        return True

    @Slot(str, str, str, result=bool)
    def saveDefaultKey(self, api_key: str, password: str, confirm_password: str) -> bool:
        """保存并载入部署 Key。参数：Key 和两次密码。返回值：是否成功。"""
        if password != confirm_password:
            self._status = self.locale.textf("password_mismatch")
            self.changed.emit()
            return False
        try:
            write_encrypted_key(Path(self.defaultKeyPath), api_key, password)
        except Exception as exc:
            self._status = self.locale.textf("key_write_failed", error=exc)
            self.changed.emit()
            return False
        self._default_key = api_key.strip()
        self._default_key_source = self.defaultKeyPath
        self._status = self.locale.textf("default_key_saved")
        self.app.set_status(self._status)
        self.changed.emit()
        return True

    @Slot(str, result=bool)
    def unlockRememberedKey(self, password: str) -> bool:
        """解锁用户 Key。参数：加密密码。返回值：是否成功。"""
        try:
            self._user_key = load_encrypted_key(self.paths.data("Translate", USER_KEY_FILE_NAME), password)
        except Exception as exc:
            self._status = self.locale.textf("user_key_unlock_failed", error=exc)
            self.changed.emit()
            return False
        self._status = self.locale.textf("user_key_unlocked")
        self.changed.emit()
        return True

    @Slot(str, str, str, result=bool)
    def rememberUserKey(self, api_key: str, password: str, confirm_password: str) -> bool:
        """保存用户 Key。参数：Key 和两次密码。返回值：是否成功。"""
        if password != confirm_password:
            self._status = self.locale.textf("password_mismatch")
            self.changed.emit()
            return False
        try:
            write_encrypted_key(self.paths.data("Translate", USER_KEY_FILE_NAME), api_key, password)
        except Exception as exc:
            self._status = self.locale.textf("user_key_save_failed", error=exc)
            self.changed.emit()
            return False
        self._user_key, self._status = api_key.strip(), self.locale.textf("user_key_saved")
        self.changed.emit()
        return True

    @Slot()
    def clearRememberedKey(self) -> None:
        """清除用户 Key。参数：无。返回值：无。"""
        self.paths.data("Translate", USER_KEY_FILE_NAME).unlink(missing_ok=True)
        self._user_key, self._status = "", self.locale.textf("user_key_cleared")
        self.changed.emit()

    def _glossary_paths(self, raw: Any) -> list[Path]:
        """规范化术语表路径。参数：QML 列表或文本。返回值：路径列表。"""
        values = [str(item).strip() for item in raw if str(item).strip()] if isinstance(raw, list) else [item.strip() for item in str(raw or "").replace(";", "\n").splitlines() if item.strip()]
        if not values:
            values = [str(self.paths.glossary_dir / DEFAULT_GLOSSARY_FILENAMES[0])]
        return [Path(item).expanduser() for item in values]

    def _build_config(self, raw: dict[str, Any], language: str):
        """构建翻译核心配置。参数：QML 配置和固定语言。返回值：核心、参数和 PDF 列表。"""
        core = import_resource_module(self.paths, "Translate", "literature_translate_core")
        input_dir = Path(str(raw.get("inputDir") or self.defaultInputDir)).expanduser()
        output_dir = Path(str(raw.get("outputDir") or self.defaultOutputDir)).expanduser()
        if not input_dir.is_dir():
            raise ValueError(tr(language, "input_dir_missing"))
        layout_only = as_bool(raw.get("layoutOnly"))
        api_key = str(raw.get("apiKey") or "").strip() or self._user_key or self._default_key
        if not layout_only and not api_key:
            raise ValueError(tr(language, "api_key_required"))
        args = argparse.Namespace(input=str(input_dir), output=str(output_dir), suffix="_全文翻译", translator="copy" if layout_only else "deepseek", target_lang="zh", api_key=api_key or None, base_url=str(raw.get("baseUrl") or "https://api.deepseek.com").strip(), model=str(raw.get("model") or "deepseek-v4-flash").strip(), temperature=0.15, max_retries=4, disable_json_mode=False, glossary=self._glossary_paths(raw.get("glossaryPaths")), batch_size=as_int(raw.get("batchSize"), 3), max_batch_chars=as_int(raw.get("maxBatchChars"), 3500), render_scale=2.0, whiteout_padding_x=1.4, whiteout_padding_y=0.9, font=None, bold_font=None, translate_references=as_bool(raw.get("translateReferences")), translate_header_footer=as_bool(raw.get("translateHeaderFooter")), summary_page=as_bool(raw.get("summaryPage"), True), max_pages=int(raw["maxPages"]) if str(raw.get("maxPages") or "").strip() else None, no_cache=not as_bool(raw.get("useCache"), True), progress_callback=None, language=language)
        pdfs = core.find_pdf_files(input_dir)
        if not pdfs:
            raise ValueError(tr(language, "pdf_missing"))
        output_dir.mkdir(parents=True, exist_ok=True)
        return core, args, pdfs

    @Slot("QVariantMap", result=bool)
    def start(self, config_map: dict[str, Any]) -> bool:
        """启动翻译线程。参数：QML 配置。返回值：是否成功启动。"""
        if self._running:
            return False
        language = self.locale.language
        try:
            raw = dict(config_map or {})
            core, args, pdfs = self._build_config(raw, language)
            self.saveConfig(raw)
        except Exception as exc:
            self._on_finished(False, tr(language, "config_error", error=exc))
            return False

        def progress(stage: str, message: str, current: int | None = None, total: int | None = None) -> None:
            """转发进度并响应取消。参数：阶段、消息和计数。返回值：无。"""
            if self._stop.is_set():
                raise TranslationCancelled(tr(language, "translate_cancelled"))
            self.progress.emit(stage, message, int(current or 0), int(total or 1))

        def worker() -> None:
            """执行翻译任务并通过信号回到界面线程。参数：无。返回值：无。"""
            try:
                core.tqdm = None
                args.progress_callback = progress
                args.preview_callback = lambda text: self.preview.emit(str(text))
                glossary_text = core.load_glossary(args.glossary)
                translator = core.make_translator(args, glossary_text)
                writer = LogWriter(lambda text: self.log.emit(text))
                with contextlib.redirect_stdout(writer), contextlib.redirect_stderr(writer):
                    for index, pdf in enumerate(pdfs, start=1):
                        if self._stop.is_set():
                            raise TranslationCancelled(tr(language, "translate_cancelled"))
                        self._file_index = index
                        self.document.emit(f"{index}/{len(pdfs)}  {pdf.name}")
                        core.translate_pdf(pdf, args, translator, glossary_text)
            except TranslationCancelled as exc:
                self.finished.emit(False, str(exc))
            except Exception as exc:
                self.log.emit(traceback.format_exc())
                self.finished.emit(False, tr(language, "translate_failed", error=exc))
            else:
                self.finished.emit(True, tr(language, "translate_done"))

        self._stop.clear()
        self._logs, self._progress, self._workflow_index = [], 0.0, 0
        self._preview_text = tr(language, "preview_waiting")
        self._file_index, self._file_total, self._running = 0, len(pdfs), True
        self._status = tr(language, "translate_started", count=len(pdfs))
        self.changed.emit()
        threading.Thread(target=worker, name="AcademicPdfTranslation", daemon=True).start()
        return True

    @Slot()
    def stop(self) -> None:
        """请求停止翻译。参数：无。返回值：无。"""
        if self._running:
            self._stop.set()
            self._status = self.locale.textf("request_stop_translate")
        self.app.set_status(self._status)
        self.changed.emit()


class UpdateController(QObject):
    """检查、下载并应用桌面端更新。"""

    changed = Signal()
    checkFinished = Signal(object, bool, str)
    downloadProgress = Signal(int, int, str)
    downloadFinished = Signal(bool, str, str)
    applyFinished = Signal(bool, str)

    def __init__(self, app: AppController, paths: AppPaths, store: AccountStore, locale: LocaleController):
        """初始化更新控制器。参数：应用、路径、设置和语言。返回值：无。"""
        super().__init__()
        self.app, self.paths, self.store, self.locale = app, paths, store, locale
        self._status, self._history = locale.textf("not_started"), locale.textf("no_update_history")
        self._latest_version = self._downloaded_path = ""
        self._available = self._checking = self._downloading = False
        self._progress, self._progress_text, self._manifest = 0.0, locale.textf("download_not_started"), None
        self.checkFinished.connect(self._on_check_finished)
        self.downloadProgress.connect(self._on_download_progress)
        self.downloadFinished.connect(self._on_download_finished)
        self.applyFinished.connect(self._on_apply_finished)

    @Property(str, notify=changed)
    def statusText(self) -> str:
        """返回更新状态。参数：无。返回值：状态文本。"""
        return self._status

    @Property(str, notify=changed)
    def historyText(self) -> str:
        """返回版本记录。参数：无。返回值：多行文本。"""
        return self._history

    @Property(str, notify=changed)
    def latestVersion(self) -> str:
        """返回远程版本。参数：无。返回值：版本文本。"""
        return self._latest_version

    @Property(bool, notify=changed)
    def available(self) -> bool:
        """返回更新状态。参数：无。返回值：是否有更新。"""
        return self._available

    @Property(bool, notify=changed)
    def checking(self) -> bool:
        """返回检查状态。参数：无。返回值：是否检查中。"""
        return self._checking

    @Property(bool, notify=changed)
    def downloading(self) -> bool:
        """返回下载状态。参数：无。返回值：是否下载中。"""
        return self._downloading

    @Property(float, notify=changed)
    def progressValue(self) -> float:
        """返回更新进度。参数：无。返回值：0 到 1。"""
        return self._progress

    @Property(str, notify=changed)
    def progressText(self) -> str:
        """返回进度文本。参数：无。返回值：状态文本。"""
        return self._progress_text

    @Property(str, notify=changed)
    def downloadedPath(self) -> str:
        """返回下载文件。参数：无。返回值：路径文本。"""
        return self._downloaded_path

    @Property(str, notify=changed)
    def sha256Text(self) -> str:
        """返回远程摘要。参数：无。返回值：SHA-256 或占位文本。"""
        return str(getattr(self._manifest, "sha256", "") or self.locale.textf("sha_unknown"))

    def _on_check_finished(self, result: object, ok: bool, message: str) -> None:
        """处理检查结果。参数：结果、成功标志和消息。返回值：无。"""
        self._checking = False
        if ok:
            self._manifest = getattr(result, "manifest", None)
            self._latest_version = str(getattr(self._manifest, "version", "") or "")
            self._available = bool(getattr(result, "update_available", getattr(result, "is_newer", False)) and self._manifest)
            self._history = str(self._manifest.formatted_notes(limit=8) if self._manifest else self.locale.textf("no_update_history"))
        else:
            self._available = False
        self._status = message
        self.app.set_status(message)
        self.changed.emit()

    def _on_download_progress(self, downloaded: int, total: int, message: str) -> None:
        """处理下载进度。参数：已下载、总数和消息。返回值：无。"""
        self._progress = downloaded / total if total > 0 else 0.0
        self._progress_text = f"{message}: {_format_bytes(downloaded)} / {_format_bytes(total)}" if total else message
        self.changed.emit()

    def _on_download_finished(self, ok: bool, message: str, path_text: str) -> None:
        """处理下载结果。参数：成功标志、消息和路径。返回值：无。"""
        self._downloading = False
        if ok:
            self._downloaded_path, self._progress = path_text, 1.0
        self._status = message
        self.app.set_status(message)
        self.changed.emit()

    def _on_apply_finished(self, ok: bool, message: str) -> None:
        """处理应用更新结果。参数：成功标志和消息。返回值：无。"""
        self._status = message
        self.app.set_status(message)
        self.changed.emit()
        if ok and os.name == "nt":
            QCoreApplication.quit()

    @Slot()
    def check(self) -> None:
        """异步检查更新。参数：无。返回值：无。"""
        if self._checking or self._downloading:
            return
        language = self.locale.language
        try:
            core = import_resource_module(self.paths, "Update", "update_core")
            label = "Update source" if language == "en" else "更新源"
            manifest_url = core.validate_remote_url(DEFAULT_UPDATE_MANIFEST_URL, label=label)
        except Exception as exc:
            self._on_check_finished(None, False, tr(language, "invalid_update_source", error=exc))
            return
        self._checking, self._status = True, tr(language, "checking_update")
        self.changed.emit()

        def worker() -> None:
            """执行更新检查。参数：无。返回值：无。"""
            try:
                current_sha256 = core.sha256_file(Path(sys.executable)) if getattr(sys, "frozen", False) else ""
                result = core.check_for_update(manifest_url, self.app.version, current_sha256=current_sha256, language=language)
            except Exception as exc:
                self.checkFinished.emit(None, False, tr(language, "check_update_failed", error=exc))
            else:
                self.checkFinished.emit(result, True, str(result.status))

        threading.Thread(target=worker, name="UpdateCheck", daemon=True).start()

    @Slot()
    def download(self) -> None:
        """异步下载更新。参数：无。返回值：无。"""
        if self._downloading or not self._available or self._manifest is None:
            return
        language = self.locale.language
        self._downloading, self._downloaded_path, self._progress = True, "", 0.0
        self._status = tr(language, "downloading_version", version=self._manifest.version)
        self.changed.emit()

        def worker() -> None:
            """执行更新下载。参数：无。返回值：无。"""
            try:
                core = import_resource_module(self.paths, "Update", "update_core")
                path = core.download_update(self._manifest, self.paths.data("updates"), progress_callback=lambda a, b, c: self.downloadProgress.emit(a, b, c), language=language)
            except Exception as exc:
                self.downloadFinished.emit(False, tr(language, "download_update_failed", error=exc), "")
            else:
                message = tr(language, "downloaded_version", version=self._manifest.version)
                self.downloadFinished.emit(True, message, str(path))

        threading.Thread(target=worker, name="UpdateDownload", daemon=True).start()

    @Slot()
    def apply(self) -> None:
        """应用已下载更新。参数：无。返回值：无。"""
        if not self._downloaded_path:
            return
        if os.name != "nt" or not getattr(sys, "frozen", False):
            _open_path(Path(self._downloaded_path))
            self._on_apply_finished(False, self.locale.textf("manual_update"))
            return

        def worker() -> None:
            """生成替换脚本。参数：无。返回值：无。"""
            try:
                core = import_resource_module(self.paths, "Update", "update_core")
                status = core.apply_update(Path(self._downloaded_path), [sys.executable], self.paths.data_root, expected_sha256=str(getattr(self._manifest, "sha256", "") or ""), language=self.locale.language)
            except Exception as exc:
                self.applyFinished.emit(False, self.locale.textf("apply_update_failed", error=exc))
            else:
                self.applyFinished.emit(True, status)

        threading.Thread(target=worker, name="UpdateApply", daemon=True).start()
