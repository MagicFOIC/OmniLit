from __future__ import annotations

import hashlib
import importlib
import json
import re
import secrets
import sqlite3
import sys
from contextlib import closing
from pathlib import Path
from typing import Any

from .paths import AppPaths
from datetime import date


PASSWORD_SCHEME = "pbkdf2_sha256"
PASSWORD_ITERATIONS = 310_000
LEGACY_TK_PASSWORD_ITERATIONS = 260_000
WORKDIR_SETTING = "onboarding/workdir"
DOWNLOAD_FORM_SETTING = "download_form_config"
CONTACT_EMAIL_SETTING = "contact_email"
KEYWORD_SPLIT_RE = re.compile(r"[\r\n;,，；]+")
SPACE_RE = re.compile(r"\s+")
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
QUALITY_PRESETS: dict[str, dict[str, Any]] = {
    "keyword": {
        "strict_keyword_match": False,
        "min_keyword_match_ratio": 0.3,
        "min_topic_score": 0,
        "journal_whitelist_only": False,
        "oa_only": False,
    },
    "relaxed": {
        "strict_keyword_match": False,
        "min_keyword_match_ratio": 0.5,
        "min_topic_score": 4,
        "journal_whitelist_only": False,
        "oa_only": False,
    },
    "balanced": {
        "strict_keyword_match": True,
        "min_keyword_match_ratio": 0.7,
        "min_topic_score": 6,
        "journal_whitelist_only": False,
        "oa_only": True,
    },
    "strict": {
        "strict_keyword_match": True,
        "min_keyword_match_ratio": 0.8,
        "min_topic_score": 9,
        "journal_whitelist_only": False,
        "oa_only": True,
    },
    "very_strict": {
        "strict_keyword_match": True,
        "min_keyword_match_ratio": 0.9,
        "min_topic_score": 12,
        "journal_whitelist_only": True,
        "oa_only": True,
    },
}


def as_bool(value: Any, default: bool = False) -> bool:
    """解析布尔配置。参数：原始值和默认值。返回值：布尔值。"""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def as_int(value: Any, default: int) -> int:
    """解析整数配置。参数：原始值和默认值。返回值：整数。"""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def as_float(value: Any, default: float) -> float:
    """解析浮点配置。参数：原始值和默认值。返回值：浮点数。"""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def optional_int(value: Any) -> int | None:
    """解析可选整数。参数：原始值。返回值：整数或空值。"""
    text = str(value or "").strip()
    return int(text) if text else None


def optional_float(value: Any) -> float | None:
    """解析可选浮点数。参数：原始值。返回值：浮点数或空值。"""
    text = str(value or "").strip()
    return float(text) if text else None


def parse_download_keywords(value: Any) -> list[str]:
    """Return unique user-entered download keywords from form text or lists."""
    if value is None:
        return []

    if isinstance(value, (list, tuple, set)):
        raw_items: list[Any] = []
        for item in value:
            raw_items.extend(KEYWORD_SPLIT_RE.split(str(item or "")))
    else:
        raw_items = KEYWORD_SPLIT_RE.split(str(value or ""))

    keywords: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        keyword = SPACE_RE.sub(" ", str(item or "").strip())
        if not keyword:
            continue
        key = keyword.casefold()
        if key in seen:
            continue
        seen.add(key)
        keywords.append(keyword)
    return keywords


def import_resource_module(paths: AppPaths, folder: str, module_name: str):
    """导入资源模块。参数：路径、目录和模块名。返回值：模块对象。"""
    module_dir = paths.resource(folder)
    if str(module_dir) not in sys.path:
        sys.path.insert(0, str(module_dir))
    return importlib.import_module(module_name)


def configured_workdir(paths: AppPaths, store: "AccountStore") -> Path:
    raw = store.setting(WORKDIR_SETTING, "").strip()
    if not raw:
        return paths.data_root
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = paths.data_root / candidate
    return candidate.resolve()


def workdir_data(paths: AppPaths, store: "AccountStore", *parts: str) -> Path:
    return configured_workdir(paths, store).joinpath(*parts)


def default_download_dir(paths: AppPaths, store: "AccountStore") -> Path:
    return workdir_data(paths, store, "Download")


def _resolved_config_path(paths: AppPaths, value: Any) -> Path:
    path = Path(str(value or "")).expanduser()
    if not path.is_absolute():
        path = paths.data(path)
    return path.resolve()


def is_legacy_default_download_dir(paths: AppPaths, value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return True
    try:
        candidate = _resolved_config_path(paths, text)
    except OSError:
        return False
    defaults = {
        paths.resource("Download").resolve(),
        paths.data("Download").resolve(),
    }
    return candidate in defaults


def normalize_download_form_config(paths: AppPaths, store: "AccountStore", settings: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(settings or {})
    if is_legacy_default_download_dir(paths, normalized.get("outputDir")):
        normalized["outputDir"] = str(default_download_dir(paths, store))
    if "keywords" in normalized:
        normalized["keywords"] = "\n".join(parse_download_keywords(normalized.get("keywords")))
    if "sources" not in normalized:
        core = import_resource_module(paths, "Download", "literature_download_core")
        normalized["sources"] = list(core.DEFAULT_SOURCES)
    return normalized


def update_download_form_output_dir(paths: AppPaths, store: "AccountStore") -> None:
    try:
        settings = json.loads(store.setting(DOWNLOAD_FORM_SETTING, "{}"))
    except (TypeError, json.JSONDecodeError):
        settings = {}
    if not isinstance(settings, dict):
        settings = {}
    settings["outputDir"] = str(default_download_dir(paths, store))
    store.set_setting(DOWNLOAD_FORM_SETTING, json.dumps(settings, ensure_ascii=False, sort_keys=True))


class AccountStore:
    """保存本地账号和设置。"""

    def __init__(self, db_path: Path):
        """初始化账号库。参数：数据库路径。返回值：无。"""
        self.db_path = db_path
        self.ensure_schema()

    def ensure_schema(self) -> None:
        """创建数据表。参数：无。返回值：无。"""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    salt TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def setting(self, key: str, default: str = "") -> str:
        """读取设置。参数：键和默认值。返回值：设置文本。"""
        try:
            with closing(sqlite3.connect(self.db_path)) as conn:
                row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
            return str(row[0]) if row else default
        except sqlite3.Error:
            return default

    def set_setting(self, key: str, value: str) -> None:
        """保存设置。参数：键和值。返回值：无。"""
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute("INSERT OR REPLACE INTO settings(key, value) VALUES(?, ?)", (key, value))
            conn.commit()

    def delete_setting(self, key: str) -> None:
        """删除设置。参数：键。返回值：无。"""
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute("DELETE FROM settings WHERE key = ?", (key,))
            conn.commit()

    def contact_email(self) -> str:
        """Return the user contact email used by literature APIs."""
        saved = self.setting(CONTACT_EMAIL_SETTING, "").strip()
        if saved:
            return saved
        username = self.setting("remember_username", "").strip()
        return username if EMAIL_PATTERN.fullmatch(username) else ""

    def save_contact_email(self, email: str) -> None:
        """Persist the literature API contact email."""
        self.set_setting(CONTACT_EMAIL_SETTING, email.strip())

    @staticmethod
    def encode_password(password: str, salt: bytes | None = None) -> tuple[str, str]:
        """生成当前密码哈希。参数：密码和可选盐。返回值：编码哈希和盐。"""
        salt = salt or secrets.token_bytes(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS).hex()
        encoded = f"{PASSWORD_SCHEME}${PASSWORD_ITERATIONS}${salt.hex()}${digest}"
        return encoded, salt.hex()

    @staticmethod
    def _verify_modern(password: str, encoded: str) -> bool:
        """验证当前密码哈希。参数：密码和编码哈希。返回值：是否匹配。"""
        try:
            scheme, iterations_text, salt_hex, expected = encoded.split("$", 3)
            if scheme != PASSWORD_SCHEME:
                return False
            digest = hashlib.pbkdf2_hmac(
                "sha256",
                password.encode("utf-8"),
                bytes.fromhex(salt_hex),
                int(iterations_text),
            ).hex()
            return secrets.compare_digest(digest, expected)
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _legacy_candidates(password: str, salt: str) -> set[str]:
        """生成历史哈希候选。参数：密码和旧盐。返回值：哈希集合。"""
        raw_salt = salt.encode("utf-8")
        raw_password = password.encode("utf-8")
        candidates = {
            hashlib.sha256((password + salt).encode("utf-8")).hexdigest(),
            hashlib.sha256((salt + password).encode("utf-8")).hexdigest(),
            hashlib.sha256(raw_salt + raw_password).hexdigest(),
            hashlib.sha256(raw_password + raw_salt).hexdigest(),
        }
        try:
            salt_bytes = bytes.fromhex(salt)
            candidates.add(hashlib.sha256(salt_bytes + raw_password).hexdigest())
            candidates.add(hashlib.sha256(raw_password + salt_bytes).hexdigest())
            candidates.add(hashlib.pbkdf2_hmac("sha256", raw_password, salt_bytes, 100_000).hex())
            # Tk 版本未保存算法版本号，实际使用 PBKDF2-SHA256 / 260000 次。
            candidates.add(hashlib.pbkdf2_hmac("sha256", raw_password, salt_bytes, LEGACY_TK_PASSWORD_ITERATIONS).hex())
        except ValueError:
            pass
        return candidates

    def register(self, username: str, password: str) -> None:
        """注册本地账号。参数：用户名和密码。返回值：无。"""
        username = username.strip()
        if len(username) < 3:
            raise ValueError("用户名至少需要 3 个字符。")
        if len(password) < 6:
            raise ValueError("密码至少需要 6 个字符。")
        encoded, salt = self.encode_password(password)
        try:
            with closing(sqlite3.connect(self.db_path)) as conn:
                conn.execute(
                    "INSERT INTO users(username, password_hash, salt) VALUES(?, ?, ?)",
                    (username, encoded, salt),
                )
                conn.commit()
        except sqlite3.IntegrityError as exc:
            raise ValueError("用户名已存在。") from exc

    def login(self, username: str, password: str) -> bool:
        """登录并升级历史哈希。参数：用户名和密码。返回值：是否成功。"""
        username = username.strip()
        if not username or not password:
            raise ValueError("请输入用户名和密码。")
        with closing(sqlite3.connect(self.db_path)) as conn:
            row = conn.execute(
                "SELECT password_hash, salt FROM users WHERE username = ?",
                (username,),
            ).fetchone()
            if not row:
                raise ValueError("账号不存在。")
            saved_hash, salt = str(row[0]), str(row[1])
            if saved_hash.startswith(PASSWORD_SCHEME + "$"):
                if not self._verify_modern(password, saved_hash):
                    raise ValueError("密码不正确。")
            elif saved_hash in self._legacy_candidates(password, salt):
                upgraded, upgraded_salt = self.encode_password(password)
                conn.execute(
                    "UPDATE users SET password_hash = ?, salt = ? WHERE username = ?",
                    (upgraded, upgraded_salt, username),
                )
                conn.commit()
            else:
                raise ValueError("密码不正确。")
        self.set_setting("remember_username", username)
        if not self.setting(CONTACT_EMAIL_SETTING, "").strip() and EMAIL_PATTERN.fullmatch(username):
            self.save_contact_email(username)
        return True


def build_download_config(paths: AppPaths, raw: dict[str, Any], stop_callback, progress_callback, language: str = "zh"):
    """构建下载核心配置。参数：路径、界面配置、回调和语言。返回值：核心模块与配置。"""
    core = import_resource_module(paths, "Download", "literature_download_core")
    output_root = Path(str(raw.get("outputDir") or paths.data("Download"))).expanduser()
    if not output_root.is_absolute():
        output_root = paths.data(output_root)
    keywords = parse_download_keywords(raw.get("keywords")) or None
    sources_raw = raw.get("sources")
    if sources_raw is None:
        sources = None
    elif isinstance(sources_raw, list):
        sources = [str(item).strip() for item in sources_raw if str(item).strip()]
    else:
        sources = [item.strip() for item in str(sources_raw).replace(";", "\n").splitlines() if item.strip()]
    selected_journals_raw = raw.get("selectedJournals")
    if selected_journals_raw is None:
        selected_journals = None
    elif isinstance(selected_journals_raw, list):
        selected_journals = [str(item).strip() for item in selected_journals_raw if str(item).strip()] or None
    else:
        selected_journals = [item.strip() for item in str(selected_journals_raw).replace(";", "\n").splitlines() if item.strip()] or None
    quality_preset = str(raw.get("qualityPreset") or "balanced").strip()
    quality = QUALITY_PRESETS.get(quality_preset, QUALITY_PRESETS["balanced"])
    strict_keyword_match = bool(quality["strict_keyword_match"])
    min_keyword_match_ratio = float(quality["min_keyword_match_ratio"])
    min_topic_score = int(quality["min_topic_score"])
    journal_whitelist_only = bool(quality["journal_whitelist_only"])
    oa_only = bool(quality["oa_only"])
    include_unknown_impact_factor = as_bool(raw.get("includeUnknownImpactFactor"), True)
    journal_metric_source = str(raw.get("journalMetricSource") or "local_then_openalex").strip()
    if raw.get("journalMetricCsv"):
        journal_metric_csv = Path(str(raw.get("journalMetricCsv"))).expanduser()
    else:
        default_metric_csv = output_root / "journal_metrics.csv"
        journal_metric_csv = default_metric_csv if default_metric_csv.exists() else None
    resume = True
    fast_forward_existing_pages = True

    return core, core.CrawlConfig(
        email=str(raw.get("email") or "").strip(),
        out_dir=output_root / "pdfs",
        meta_path=output_root / "metadata_battery.jsonl",
        state_path=output_root / "crawl_state.json",
        keywords=keywords,
        sources=sources,
        from_date=str(raw.get("fromDate") or core.DEFAULT_FROM_DATE).strip(),
        to_date=str(raw.get("toDate") or core.DEFAULT_TO_DATE).strip(),
        oa_only=oa_only,
        sort=str(raw.get("sort") or "relevance_score:desc").strip() or None,
        max_pages_per_keyword=as_int(raw.get("maxPages"), 1000),
        per_page=as_int(raw.get("perPage"), 50),
        max_records=None,
        request_delay=as_float(raw.get("requestDelay"), 0.2),
        page_delay=as_float(raw.get("pageDelay"), 0.5),
        min_pdf_bytes=as_int(raw.get("minPdfBytes"), 1024),
        download_pdfs=True,
        retry_missing_pdfs=True,
        write_retry_records=False,
        auto_backfill_missing_pdfs=True,
        strict_keyword_match=strict_keyword_match,
        min_keyword_match_ratio=min_keyword_match_ratio,
        topic_pack=str(raw.get("topicPack") or "auto").strip() or None,
        journal_pack=str(raw.get("journalPack") or "auto").strip() or None,
        selected_journals=selected_journals,
        min_topic_score=min_topic_score,
        journal_whitelist_only=journal_whitelist_only,
        min_impact_factor=optional_float(raw.get("minImpactFactor")),
        include_unknown_impact_factor=include_unknown_impact_factor,
        journal_metric_source=journal_metric_source or "local_then_openalex",
        journal_metric_csv=journal_metric_csv,
        loop=False,
        loop_sleep=as_float(raw.get("loopSleep"), 3600),
        max_runtime_hours=None,
        resume=resume,
        fast_forward_existing_pages=fast_forward_existing_pages,
        language=language,
        stop_callback=stop_callback,
        progress_callback=progress_callback,
    )
