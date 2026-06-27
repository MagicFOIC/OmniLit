# Copyright (c) 2026 magicfoic. All rights reserved.

import hashlib
import html
import json
import logging
import os
import re
import time
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, TextIO
from urllib.parse import quote, urljoin, urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

try:
    from .journal_registry import is_whitelisted_journal
    from .journal_metrics import (
        JournalMetricResolver,
        attach_journal_metric,
        match_journal_metric,
        record_passes_impact_factor_filter as metric_passes_impact_factor_filter,
    )
    from .pack_builder import journal_pack_match_score, resolve_journal_pack, resolve_topic_pack
    from .topic_packs import score_topic_relevance
except ImportError:  # pragma: no cover - supports direct script execution.
    from journal_registry import is_whitelisted_journal
    from journal_metrics import (
        JournalMetricResolver,
        attach_journal_metric,
        match_journal_metric,
        record_passes_impact_factor_filter as metric_passes_impact_factor_filter,
    )
    from pack_builder import journal_pack_match_score, resolve_journal_pack, resolve_topic_pack
    from topic_packs import score_topic_relevance

DEFAULT_EMAIL = ""
COPYRIGHT_NOTICE = "Copyright (c) 2026 magicfoic. All rights reserved."
LITERATURE_DOWNLOAD_DIR = Path(__file__).resolve().parent
BASE_DIR = LITERATURE_DOWNLOAD_DIR.parent
DEFAULT_OUT_DIR = LITERATURE_DOWNLOAD_DIR / "pdfs"
DEFAULT_META_PATH = LITERATURE_DOWNLOAD_DIR / "metadata_battery.jsonl"
DEFAULT_STATE_PATH = LITERATURE_DOWNLOAD_DIR / "crawl_state.json"
DEFAULT_FROM_DATE = "2016-07-30"
DEFAULT_TO_DATE = datetime.now().strftime("%Y-%m-%d")
DEFAULT_KEYWORDS = [
    # "lithium ion battery cathode material",
    # "solid state battery electrolyte",
    # "battery degradation capacity fade",
    # "anode material lithium battery",
    # "SEI layer lithium ion battery",
    # "sodium ion",
    # "battery electrolyte",
    # "battery cathode",
    # "battery anode",
    # "battery capacity",
    # "battery degradation",
    "lithium-sulfur batteries",
    "polysulfides",
]

OPENALEX_URL = "https://api.openalex.org/works"
EUROPE_PMC_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
ARXIV_URL = "https://export.arxiv.org/api/query"
CROSSREF_URL = "https://api.crossref.org/v1/works"
DOAJ_URL = "https://doaj.org/api/v4/search/articles"
UNPAYWALL_URL = "https://api.unpaywall.org/v2"
SEMANTIC_SCHOLAR_PAPER_URL = "https://api.semanticscholar.org/graph/v1/paper"
SOURCE_OPENALEX = "openalex"
SOURCE_EUROPE_PMC = "europe_pmc"
SOURCE_ARXIV = "arxiv"
SOURCE_CROSSREF = "crossref"
SOURCE_DOAJ = "doaj"
SOURCE_LABELS = {
    SOURCE_OPENALEX: "OpenAlex",
    SOURCE_EUROPE_PMC: "Europe PMC",
    SOURCE_ARXIV: "arXiv",
    SOURCE_CROSSREF: "Crossref",
    SOURCE_DOAJ: "DOAJ",
}
DEFAULT_SOURCES = [SOURCE_OPENALEX, SOURCE_EUROPE_PMC, SOURCE_ARXIV, SOURCE_CROSSREF, SOURCE_DOAJ]
OPENALEX_SELECT = (
    "id,doi,title,display_name,publication_date,publication_year,"
    "cited_by_count,authorships,primary_location,open_access,"
    "abstract_inverted_index,best_oa_location,locations,"
    "has_content,content_urls,ids"
)
NON_PDF_EXTENSIONS = (
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".webp",
    ".svg",
    ".xml",
    ".html",
    ".htm",
)
SHADOW_LIBRARY_DOMAINS = (
    "sci-hub",
    "scihub",
    "libgen",
    "z-library",
    "zlibrary",
    "annas-archive",
    "booksc",
)
PDF_CHUNK_SIZE = 1024 * 64
HTML_LANDING_PAGE_MAX_BYTES = 1024 * 1024
ARXIV_MIN_DOWNLOAD_INTERVAL = 3.0
PDF_HEAD_TIMEOUT = (8, 12)
PDF_LANDING_TIMEOUT = (8, 15)
PDF_API_TIMEOUT = (8, 15)
PDF_DOWNLOAD_TIMEOUT = (12, 30)
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PDF_RESOLVER_VERSION = "oa_pdf_resolver_v3"
PDF_RETRY_COOLDOWN = timedelta(days=7)
PERMANENT_FAILURE_STATUSES = {"blocked_or_login", "not_open_access", "no_candidate"}
MAX_PDF_RETRY_ATTEMPTS = 8
MAX_PERMANENT_PDF_RETRY_ATTEMPTS = 3


@dataclass
class CrawlConfig:
    """Docstring."""
    email: str = DEFAULT_EMAIL
    out_dir: Path = DEFAULT_OUT_DIR
    meta_path: Path = DEFAULT_META_PATH
    state_path: Path = DEFAULT_STATE_PATH
    keywords: list[str] | None = None
    sources: list[str] | None = None
    from_date: str = DEFAULT_FROM_DATE
    to_date: str = DEFAULT_TO_DATE
    oa_only: bool = False
    sort: str | None = None
    max_pages_per_keyword: int = 3
    per_page: int = 50
    max_records: int | None = None
    request_delay: float = 1.0
    page_delay: float = 2.0
    min_pdf_bytes: int = 1024
    log_level: str = "INFO"
    download_pdfs: bool = True
    retry_missing_pdfs: bool = True
    write_retry_records: bool = False
    auto_backfill_missing_pdfs: bool = True
    strict_keyword_match: bool = True
    min_keyword_match_ratio: float = 0.75
    topic_pack: str | None = "auto"
    journal_pack: str | None = "auto"
    selected_journals: list[str] | None = None
    min_topic_score: int = 6
    journal_whitelist_only: bool = False
    min_impact_factor: float | None = None
    include_unknown_impact_factor: bool = True
    journal_metric_source: str = "local_then_openalex"
    journal_metric_csv: Path | None = None
    loop: bool = False
    loop_sleep: float = 3600.0
    max_runtime_hours: float | None = None
    resume: bool = True
    fast_forward_existing_pages: bool = True
    language: str = "zh"
    stop_callback: Callable[[], bool] | None = None
    progress_callback: Callable[[Any, str], None] | None = None

    @property
    def effective_keywords(self) -> list[str]:
        """Docstring."""
        return self.keywords or DEFAULT_KEYWORDS

    @property
    def effective_sources(self) -> list[str]:
        """Docstring."""
        return DEFAULT_SOURCES if self.sources is None else self.sources


def localized(config: CrawlConfig, zh: str, en: str, ru: str = "") -> str:
    """Docstring."""
    return (ru or en) if config.language == "ru" else en if config.language == "en" else zh


@dataclass
class CrawlStats:
    """Docstring."""
    existing_records: int = 0
    fetched_items: int = 0
    fetched_items_total: int = 0
    fetched_by_source: dict[str, int] = field(default_factory=dict)
    added_records: int = 0
    skipped_duplicates: int = 0
    skipped_without_key: int = 0
    skipped_irrelevant: int = 0
    skipped_not_oa: int = 0
    skipped_by_topic_score: int = 0
    skipped_by_keyword_match: int = 0
    skipped_by_impact_factor: int = 0
    impact_factor_known_records: int = 0
    impact_factor_unknown_records: int = 0
    journal_metric_resolved: int = 0
    journal_metric_missing: int = 0
    open_access_records: int = 0
    downloaded_pdfs: int = 0
    failed_pdfs: int = 0
    pdf_candidates_found: int = 0
    pdf_download_attempted: int = 0
    pdf_downloaded: int = 0
    pdf_failed: int = 0
    retried_existing_records: int = 0
    backfill_scanned_records: int = 0
    backfill_missing_pdf_records: int = 0
    backfill_downloaded_pdfs: int = 0
    backfill_failed_pdfs: int = 0
    request_failures: int = 0
    pdf_failure_reasons: dict[str, int] = field(default_factory=dict)
    backfill_failure_reasons: dict[str, int] = field(default_factory=dict)
    active_source_key: str = ""
    active_source_label: str = ""
    active_keyword: str = ""
    active_stage: str = ""
    active_detail: str = ""


@dataclass
class ExistingIndex:
    """Docstring."""
    keys: set[str]
    downloaded_keys: set[str]
    retry_pdf_keys: set[str]
    canonical_keys: set[str] = field(default_factory=set)
    downloaded_canonical_keys: set[str] = field(default_factory=set)
    canonical_pdf_paths: dict[str, str] = field(default_factory=dict)
    pdf_sha256_paths: dict[str, str] = field(default_factory=dict)
    pdf_url_keys: set[str] = field(default_factory=set)
    pdf_url_paths: dict[str, str] = field(default_factory=dict)


@dataclass
class DownloadResult:
    """Docstring."""
    path: str | None
    status: str
    source_url: str | None = None
    reason: str | None = None
    size_bytes: int | None = None
    candidate_source: str | None = None
    http_status: int | None = None
    content_type: str | None = None
    final_url: str | None = None
    failure_reason: str | None = None
    discovered_candidates: list[str] = field(default_factory=list)


@dataclass
class PdfResolution:
    """Docstring."""
    url: str | None
    candidates: list[str]
    reason: str | None = None
    candidate_details: list[dict[str, str]] = field(default_factory=list)
    candidate_rejection_reasons: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class PdfCandidate:
    """A legal OA PDF candidate with provenance for diagnostics."""
    url: str
    candidate_source: str


@dataclass
class CrawlStateEntry:
    """Docstring."""
    next_cursor: str | None = None
    completed_pages: int = 0
    exhausted: bool = False


def configure_logging(level: str) -> None:
    """Docstring."""
    log_level = getattr(logging, level.upper(), logging.INFO)
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    if not root_logger.handlers:
        logging.basicConfig(
            level=log_level,
            format="%(asctime)s %(levelname)s %(message)s",
            datefmt="%H:%M:%S",
        )
    logging.getLogger("urllib3.connectionpool").setLevel(logging.ERROR)


def stop_requested(config: CrawlConfig) -> bool:
    """Docstring."""
    return bool(config.stop_callback and config.stop_callback())


def emit_progress(config: CrawlConfig, stats: Any, message: str) -> None:
    """Docstring."""
    if not config.progress_callback:
        return
    try:
        config.progress_callback(stats, message)
    except Exception:
        logging.exception("Progress callback failed.")


def emit_source_progress(
    config: CrawlConfig,
    stats: CrawlStats,
    source: str,
    keyword: str,
    stage: str,
    zh_message: str,
    en_message: str,
    ru_message: str = "",
    detail: str = "",
) -> None:
    """Emit progress with structured source metadata for the UI."""
    stats.active_source_key = source
    stats.active_source_label = SOURCE_LABELS.get(source, source)
    stats.active_keyword = keyword
    stats.active_stage = stage
    stats.active_detail = detail
    emit_progress(config, stats, localized(config, zh_message, en_message, ru_message))


def emit_pdf_progress(
    config: CrawlConfig,
    stats: CrawlStats | None,
    stage: str,
    zh_message: str,
    en_message: str,
    detail: str = "",
) -> None:
    """Emit fine-grained PDF resolver/download progress without losing source context."""
    if stats is None:
        return
    stats.active_stage = stage
    stats.active_detail = detail
    emit_progress(config, stats, localized(config, zh_message, en_message, en_message))


def host_label(url: str | None) -> str:
    """Return a compact host label for progress messages."""
    normalized = normalize_candidate_url(url)
    if not normalized:
        return "unknown host"
    parsed = urlparse(normalized)
    return parsed.netloc or "unknown host"


def increment_counter(mapping: dict[str, int], key: str | None) -> None:
    """Increment a reason/source counter with a stable fallback key."""
    normalized_key = str(key or "unknown").strip() or "unknown"
    mapping[normalized_key] = mapping.get(normalized_key, 0) + 1


def note_pdf_failure(stats: CrawlStats, reason: str | None, backfill: bool = False) -> None:
    """Track PDF failure counts without breaking legacy aggregate fields."""
    if backfill:
        stats.backfill_failed_pdfs += 1
        stats.failed_pdfs += 1
        stats.pdf_failed += 1
        increment_counter(stats.backfill_failure_reasons, reason)
        increment_counter(stats.pdf_failure_reasons, reason)
        return
    stats.failed_pdfs += 1
    stats.pdf_failed += 1
    increment_counter(stats.pdf_failure_reasons, reason)


def note_pdf_download(stats: CrawlStats, backfill: bool = False) -> None:
    """Track PDF download counts without breaking legacy aggregate fields."""
    if backfill:
        stats.backfill_downloaded_pdfs += 1
        stats.downloaded_pdfs += 1
        stats.pdf_downloaded += 1
        return
    stats.downloaded_pdfs += 1
    stats.pdf_downloaded += 1


def sleep_or_stop(seconds: float, config: CrawlConfig) -> bool:
    """Docstring."""
    if seconds <= 0:
        return stop_requested(config)

    end_time = time.monotonic() + seconds
    while time.monotonic() < end_time:
        if stop_requested(config):
            return True
        time.sleep(min(0.25, max(0, end_time - time.monotonic())))
    return stop_requested(config)


def state_key(keyword: str, config: CrawlConfig, source: str = SOURCE_OPENALEX) -> str:
    """Docstring."""
    parts = {
        "keyword": keyword,
        "from_date": config.from_date,
        "to_date": config.to_date,
        "oa_only": config.oa_only,
        "sort": config.sort,
        "per_page": config.per_page,
        "strict_keyword_match": config.strict_keyword_match,
        "min_keyword_match_ratio": config.min_keyword_match_ratio,
        "topic_pack": config.topic_pack,
        "journal_pack": config.journal_pack,
        "selected_journals": config.selected_journals,
        "min_topic_score": config.min_topic_score,
        "journal_whitelist_only": config.journal_whitelist_only,
        "min_impact_factor": config.min_impact_factor,
        "include_unknown_impact_factor": config.include_unknown_impact_factor,
        "journal_metric_source": config.journal_metric_source,
        "journal_metric_csv": str(config.journal_metric_csv or ""),
    }
    # Preserve historical OpenAlex state keys while isolating new source cursors.
    if source != SOURCE_OPENALEX:
        parts["source"] = source
    return json.dumps(parts, ensure_ascii=False, sort_keys=True)


def load_crawl_state(path: Path) -> dict[str, CrawlStateEntry]:
    """Docstring."""
    if not path.exists():
        return {}

    try:
        with path.open("r", encoding="utf-8") as fin:
            raw_state = json.load(fin)
    except (OSError, json.JSONDecodeError) as exc:
        logging.warning("Ignoring unreadable crawl state %s: %s", path, exc)
        return {}

    state: dict[str, CrawlStateEntry] = {}
    if not isinstance(raw_state, dict):
        logging.warning("Ignoring invalid crawl state format in %s", path)
        return state

    for key, raw_entry in raw_state.items():
        if not isinstance(raw_entry, dict):
            continue
        try:
            completed_pages = int(raw_entry.get("completed_pages") or 0)
        except (TypeError, ValueError):
            logging.warning("Skipping invalid crawl state entry %s in %s", key, path)
            continue
        if completed_pages < 0:
            logging.warning("Skipping negative crawl state entry %s in %s", key, path)
            continue

        next_cursor = raw_entry.get("next_cursor")
        if next_cursor is not None and not isinstance(next_cursor, str):
            logging.warning("Skipping crawl state entry with invalid cursor %s in %s", key, path)
            continue

        exhausted = raw_entry.get("exhausted")
        state[key] = CrawlStateEntry(
            next_cursor=next_cursor,
            completed_pages=completed_pages,
            exhausted=exhausted if isinstance(exhausted, bool) else False,
        )
    return state


def save_crawl_state(path: Path, state: dict[str, CrawlStateEntry]) -> None:
    """Docstring."""
    path.parent.mkdir(parents=True, exist_ok=True)
    serializable = {
        key: {
            "next_cursor": entry.next_cursor,
            "completed_pages": entry.completed_pages,
            "exhausted": entry.exhausted,
        }
        for key, entry in state.items()
    }
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as fout:
        json.dump(serializable, fout, ensure_ascii=False, indent=2)
        fout.flush()
        os.fsync(fout.fileno())
    tmp_path.replace(path)


def append_jsonl_record(fout: TextIO, record: dict[str, Any]) -> None:
    """Docstring."""
    fout.write(json.dumps(record, ensure_ascii=False) + "\n")
    fout.flush()
    try:
        os.fsync(fout.fileno())
    except (AttributeError, OSError):
        # In-memory streams used by callers and tests do not expose a descriptor.
        pass


def build_session(email: str) -> requests.Session:
    """Docstring."""
    retry = Retry(
        total=3,
        connect=3,
        read=1,
        backoff_factor=0.8,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET", "HEAD"),
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)

    session = requests.Session()
    user_agent = "OmniLit/1.0 LiteratureDownloader (+https://github.com/MagicFOIC/OmniLit"
    if email:
        user_agent = f"{user_agent}; mailto:{email}"
    user_agent = f"{user_agent})"
    headers = {
        "User-Agent": user_agent,
        "Accept": "application/pdf, text/html;q=0.9, application/json;q=0.8, */*;q=0.5",
        "Accept-Language": "en-US,en;q=0.8",
    }
    if email:
        headers["From"] = email
    session.headers.update(headers)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def normalize_doi(doi: str | None) -> str | None:
    """Docstring."""
    if not doi:
        return None
    doi = doi.strip()
    doi = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", doi, flags=re.IGNORECASE)
    doi = re.sub(r"^doi:\s*", "", doi, flags=re.IGNORECASE)
    return doi.lower() or None


def record_key(record: dict[str, Any]) -> str | None:
    """Docstring."""
    doi = normalize_doi(record.get("doi"))
    if doi:
        return f"doi:{doi}"

    literature_source = record.get("literature_source")
    openalex_id = record.get("openalex_id") or record.get("id")
    if openalex_id and literature_source in {None, SOURCE_OPENALEX}:
        return f"openalex:{openalex_id}"

    source_record_id = record.get("source_record_id")
    if source_record_id:
        return f"source:{source_record_id}"

    arxiv_id = extract_arxiv_id(record)
    if arxiv_id:
        return f"arxiv:{arxiv_id}"

    return None


def normalize_arxiv_id(value: Any) -> str | None:
    """Return an arXiv identifier without a version suffix."""
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    text = re.sub(r"^arxiv:\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^https?://arxiv\.org/(?:abs|pdf)/", "", text, flags=re.IGNORECASE)
    text = text.split("?", 1)[0].split("#", 1)[0].strip().strip("/")
    patterns = (
        r"(\d{4}\.\d{4,5})(?:v\d+)?",
        r"([a-z.-]+/\d{7})(?:v\d+)?",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(1).lower()
    return None


def normalized_title_year_key(record: dict[str, Any]) -> str | None:
    """Build a conservative title/year fallback key for cross-source duplicates."""
    title = str(record.get("title") or record.get("display_name") or "").strip()
    year = record.get("publication_year") or record.get("year")
    if not year and record.get("publication_date"):
        year = str(record.get("publication_date"))[:4]
    try:
        year_int = int(year)
    except (TypeError, ValueError):
        return None

    normalized_title = re.sub(r"[^a-z0-9]+", " ", title.casefold()).strip()
    terms = [term for term in normalized_title.split() if term]
    if len(terms) < 4 or len(normalized_title) < 20:
        return None
    digest = hashlib.sha1(normalized_title.encode("utf-8")).hexdigest()[:16]
    return f"titleyear:{year_int}:{digest}"


def canonical_record_key(record: dict[str, Any]) -> str | None:
    """Return a source-independent key for duplicate detection."""
    doi = normalize_doi(record.get("doi") or record.get("normalized_doi"))
    if doi:
        return f"doi:{doi}"

    for key in ("arxiv_id", "source_record_id", "id", "url", "pdf_url"):
        arxiv_id = normalize_arxiv_id(record.get(key))
        if arxiv_id:
            return f"arxiv:{arxiv_id}"

    for key in ("openalex_id", "id", "source_record_id"):
        work_id = extract_openalex_work_id(record.get(key))
        if work_id:
            return f"openalex:{work_id.lower()}"

    return normalized_title_year_key(record)


def extract_openalex_work_id(value: Any) -> str | None:
    """Return an OpenAlex work ID suitable for the works endpoint."""
    if not value:
        return None
    text = str(value).strip()
    match = re.search(r"(W\d+)", text, flags=re.IGNORECASE)
    return match.group(1).upper() if match else None


def extract_pmcid(record: dict[str, Any]) -> str | None:
    """Extract a PMCID from common metadata fields."""
    for key in ("pmcid", "pmc_id", "source_record_id", "id", "open_access_url", "url"):
        value = record.get(key)
        if not value:
            continue
        match = re.search(r"\bPMC\d+\b", str(value), flags=re.IGNORECASE)
        if match:
            return match.group(0).upper()
    full_text_urls = (record.get("fullTextUrlList") or {}).get("fullTextUrl") or []
    for link in full_text_urls:
        if not isinstance(link, dict):
            continue
        for key in ("url", "URL"):
            match = re.search(r"\bPMC\d+\b", str(link.get(key) or ""), flags=re.IGNORECASE)
            if match:
                return match.group(0).upper()
    ids = record.get("ids") or {}
    if isinstance(ids, dict):
        for key in ("pmcid", "pmc", "pmc_id"):
            match = re.search(r"\bPMC\d+\b", str(ids.get(key) or ""), flags=re.IGNORECASE)
            if match:
                return match.group(0).upper()
    return None


def extract_arxiv_id(record: dict[str, Any]) -> str | None:
    """Extract an arXiv identifier from normalized records and legacy metadata."""
    for key in ("arxiv_id", "source_record_id", "id", "url", "pdf_url"):
        value = record.get(key)
        if not value:
            continue
        text = str(value).strip()
        match = re.search(r"arxiv:(\d{4}\.\d{4,5}(?:v\d+)?)", text, flags=re.IGNORECASE)
        if match:
            return match.group(1)
        match = re.search(r"arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5}(?:v\d+)?)", text, flags=re.IGNORECASE)
        if match:
            return match.group(1)
        if re.fullmatch(r"\d{4}\.\d{4,5}(?:v\d+)?", text):
            return text
    ids = record.get("ids") or {}
    if isinstance(ids, dict):
        for key in ("arxiv", "arxiv_id"):
            arxiv_id = normalize_arxiv_id(ids.get(key))
            if arxiv_id:
                return arxiv_id
    return None


def safe_filename(text: str) -> str:
    """Docstring."""
    return hashlib.md5(text.encode("utf-8")).hexdigest() + ".pdf"


def path_for_pdf(doi_or_url: str, out_dir: Path) -> Path:
    """Docstring."""
    return out_dir / safe_filename(doi_or_url)


def safe_keyword_folder_name(keyword: str) -> str:
    """Docstring."""
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", keyword.strip()).strip(" .")
    cleaned = re.sub(r"\s+", " ", cleaned) or "keyword"
    if cleaned.casefold() in {
        "con",
        "prn",
        "aux",
        "nul",
        *(f"com{number}" for number in range(1, 10)),
        *(f"lpt{number}" for number in range(1, 10)),
    }:
        cleaned += "_"
    digest = hashlib.sha256(keyword.encode("utf-8")).hexdigest()[:10]
    cleaned = cleaned[:80].rstrip(" .") or "keyword"
    return f"{cleaned}_{digest}"


def keyword_pdf_dir(keyword: str, out_dir: Path) -> Path:
    """Docstring."""
    return out_dir / safe_keyword_folder_name(keyword)


def display_path(path: Path, base_dir: Path) -> str:
    """Docstring."""
    try:
        return os.path.relpath(path.resolve(), base_dir.resolve())
    except ValueError:
        return str(path)


def strip_query(url: str) -> str:
    """Docstring."""
    return url.split("?", 1)[0].split("#", 1)[0]


def normalize_candidate_url(value: Any) -> str | None:
    """Normalize user/API supplied OA URL candidates into absolute HTTP(S) URLs."""
    if not value:
        return None
    url = html.unescape(str(value)).strip().strip("<>\"'")
    if not url:
        return None
    if url.startswith("//"):
        url = "https:" + url
    elif re.match(r"^(?:www\.|doi\.org/|[A-Za-z0-9.-]+\.[A-Za-z]{2,}/)", url):
        url = "https://" + url

    parsed = urlparse(url)
    if parsed.scheme and parsed.scheme.lower() not in {"http", "https"}:
        return None
    if not parsed.scheme or not parsed.netloc:
        return None

    return parsed._replace(scheme="https", netloc=parsed.netloc.casefold(), fragment="").geturl()


def looks_like_pdf_url(url: str | None) -> bool:
    """Docstring."""
    normalized = normalize_candidate_url(url)
    if not normalized:
        return False

    normalized_url = strip_query(normalized).lower()
    query = urlparse(normalized).query.casefold()
    if normalized_url.endswith(NON_PDF_EXTENSIONS):
        return False

    return (
        normalized_url.endswith(".pdf")
        or "/pdf" in normalized_url
        or "/articlepdf" in normalized_url
        or "/pdfdirect/" in normalized_url
        or "/servlets/purl/" in normalized_url
        or "pdf=render" in normalized.casefold()
        or ".pdf" in query
        or re.search(r"(?:^|[&;])(?:type|format|output|view|filetype)=pdf(?:$|[&;])", query) is not None
        or re.search(r"(?:^|[&;])download=(?:1|true|yes)(?:$|[&;])", query) is not None
    )


def is_shadow_library_url(url: str | None) -> bool:
    """Docstring."""
    normalized = normalize_candidate_url(url)
    if not normalized:
        return False
    host = urlparse(normalized).netloc.casefold()
    return any(domain in host for domain in SHADOW_LIBRARY_DOMAINS)


def candidate_urls_from_landing_url(url: str | None) -> list[str]:
    """Docstring."""
    normalized = normalize_candidate_url(url)
    if not normalized:
        return []

    parsed = urlparse(normalized)
    normalized_url = strip_query(normalized)
    candidates: list[str] = []

    if parsed.netloc.endswith("arxiv.org") and "/abs/" in parsed.path:
        candidates.append(normalized_url.replace("/abs/", "/pdf/"))

    if parsed.netloc.endswith("ncbi.nlm.nih.gov") and "/pmc/articles/" in parsed.path:
        candidates.append(normalized_url.rstrip("/") + "/pdf/")

    osti_match = re.search(r"/biblio/(\d+)", parsed.path)
    if parsed.netloc.endswith("osti.gov") and osti_match:
        candidates.append(f"https://www.osti.gov/servlets/purl/{osti_match.group(1)}")

    if parsed.netloc.endswith("mdpi.com") and not normalized_url.endswith("/pdf"):
        candidates.append(normalized_url.rstrip("/") + "/pdf")

    if parsed.netloc.endswith("frontiersin.org") and "/articles/" in parsed.path:
        candidates.append(normalized_url.rstrip("/") + "/pdf")

    doi_match = re.search(r"(/doi)/(?:full|abs|abstract)?/?(10\.\d{4,9}/.+)$", parsed.path, flags=re.IGNORECASE)
    if doi_match and "/doi/pdf/" not in parsed.path.casefold() and "/doi/epdf/" not in parsed.path.casefold():
        candidates.append(urljoin(normalized, f"{doi_match.group(1)}/pdf/{doi_match.group(2)}"))

    springer_match = re.search(r"^/article/(10\.\d{4,9}/.+)$", parsed.path, flags=re.IGNORECASE)
    if parsed.netloc.endswith("link.springer.com") and springer_match:
        candidates.append(f"https://link.springer.com/content/pdf/{springer_match.group(1)}.pdf")

    nature_match = re.search(r"^/articles/([^/?#]+)$", parsed.path, flags=re.IGNORECASE)
    if parsed.netloc.endswith("nature.com") and nature_match and not nature_match.group(1).casefold().endswith(".pdf"):
        candidates.append(f"https://www.nature.com/articles/{nature_match.group(1)}.pdf")

    return candidates


def list_values(value: Any) -> list[Any]:
    """Return a list for list-or-singleton API fields."""
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def extend_pdf_candidate_urls(urls: list[str | None], value: Any) -> None:
    """Append a URL and any legal OA PDF heuristics derived from its landing page."""
    normalized = normalize_candidate_url(value)
    if not normalized:
        return
    urls.append(normalized)
    urls.extend(candidate_urls_from_landing_url(normalized))


def append_pdf_candidate(
    candidates: list[PdfCandidate],
    value: Any,
    candidate_source: str,
    *,
    include_publisher_rules: bool = True,
) -> None:
    """Append a normalized legal PDF candidate and derived publisher-rule URLs."""
    normalized = normalize_candidate_url(value)
    if not normalized or is_shadow_library_url(normalized):
        return
    if looks_like_pdf_url(normalized):
        candidates.append(PdfCandidate(normalized, candidate_source))
    if include_publisher_rules:
        for derived_url in candidate_urls_from_landing_url(normalized):
            normalized_derived = normalize_candidate_url(derived_url)
            if (
                normalized_derived
                and looks_like_pdf_url(normalized_derived)
                and not is_shadow_library_url(normalized_derived)
            ):
                candidates.append(PdfCandidate(normalized_derived, "publisher_rule"))


def unique_pdf_candidate_details(candidates: list[PdfCandidate]) -> list[PdfCandidate]:
    """Deduplicate candidate URLs while preserving priority and source."""
    seen: set[str] = set()
    result: list[PdfCandidate] = []
    for candidate in candidates:
        normalized = normalize_candidate_url(candidate.url)
        if not normalized or normalized in seen:
            continue
        if is_shadow_library_url(normalized) or not looks_like_pdf_url(normalized):
            continue
        seen.add(normalized)
        result.append(PdfCandidate(normalized, candidate.candidate_source))
    return result


def candidate_host_priority(url: str) -> int:
    """Rank hosts by likely legal OA reliability before publisher direct links."""
    normalized = normalize_candidate_url(url) or url
    parsed = urlparse(normalized)
    host = parsed.netloc.casefold()
    path = parsed.path.casefold()
    publisher_hosts = (
        "onlinelibrary.wiley.com",
        "sciencedirect.com",
        "cell.com",
        "pubs.acs.org",
        "link.springer.com",
        "nature.com",
        "tandfonline.com",
        "ieeexplore.ieee.org",
        "publisher.test",
    )
    if host.endswith("arxiv.org"):
        return 0
    if host.endswith("ncbi.nlm.nih.gov") or host.endswith("pmc.ncbi.nlm.nih.gov"):
        return 1
    if "europepmc.org" in host or host.endswith("ebi.ac.uk"):
        return 2
    if host.endswith("osti.gov"):
        return 3
    if host.endswith("content.openalex.org"):
        return 4
    if any(host == publisher or host.endswith(f".{publisher}") for publisher in publisher_hosts):
        return 30
    repository_tokens = (
        "repo",
        "repository",
        "dspace",
        "eprints",
        "escholarship",
        "institutional",
        "archive",
        "zenodo",
        "figshare",
        "osf.io",
        "hal.science",
        "pubmedcentral",
    )
    if host.endswith(".edu") or host.endswith(".gov") or any(token in host or token in path for token in repository_tokens):
        return 5
    if "doaj.org" in host:
        return 6
    return 10


def candidate_source_priority(candidate_source: str) -> int:
    """Rank metadata sources by expected legal OA reliability."""
    priorities = {
        "arxiv_pdf": 0,
        "pmc_direct": 1,
        "europe_pmc_fullTextUrl": 2,
        "openalex_content_api": 3,
        "doaj_fulltext": 5,
        "landing_page_meta": 8,
        "unpaywall_url_for_pdf": 10,
        "openalex_pdf_url": 10,
        "openalex_landing": 11,
        "unpaywall_landing": 11,
        "publisher_rule": 12,
    }
    return priorities.get(candidate_source, 20)


def prioritize_pdf_candidate_details(candidates: list[PdfCandidate]) -> list[PdfCandidate]:
    """Prefer legal OA repositories before publisher direct links to reduce blocks."""
    unique = unique_pdf_candidate_details(candidates)
    indexed = list(enumerate(unique))
    indexed.sort(
        key=lambda item: (
            candidate_host_priority(item[1].url),
            candidate_source_priority(item[1].candidate_source),
            item[0],
        )
    )
    return [candidate for _index, candidate in indexed]


def candidate_details_to_urls(candidates: list[PdfCandidate]) -> list[str]:
    """Return the legacy URL-only candidate representation."""
    return [candidate.url for candidate in candidates]


def candidate_details_for_metadata(candidates: list[PdfCandidate]) -> list[dict[str, str]]:
    """Return candidate provenance records suitable for metadata JSONL."""
    return [
        {"url": candidate.url, "candidate_source": candidate.candidate_source}
        for candidate in candidates
    ]


def candidate_source_for_url(candidates: list[PdfCandidate], url: str | None) -> str | None:
    """Return the candidate source matching a URL."""
    normalized = normalize_candidate_url(url)
    if not normalized:
        return None
    for candidate in candidates:
        if normalize_candidate_url(candidate.url) == normalized:
            return candidate.candidate_source
    return None


def candidate_details_for_urls(
    urls: list[str],
    known_candidates: list[PdfCandidate],
    default_source: str = "landing_page_meta",
) -> list[dict[str, str]]:
    """Build metadata candidate details for a legacy URL list."""
    details: list[PdfCandidate] = []
    for url in urls:
        normalized = normalize_candidate_url(url)
        if not normalized:
            continue
        details.append(PdfCandidate(normalized, candidate_source_for_url(known_candidates, normalized) or default_source))
    return candidate_details_for_metadata(unique_pdf_candidate_details(details))


def add_unique_pdf_candidates(target: list[PdfCandidate], additions: list[PdfCandidate]) -> None:
    """Append candidates that are not already present in a candidate queue."""
    seen = {normalize_candidate_url(candidate.url) for candidate in target}
    for candidate in additions:
        normalized = normalize_candidate_url(candidate.url)
        if not normalized or normalized in seen:
            continue
        if is_shadow_library_url(normalized) or not looks_like_pdf_url(normalized):
            continue
        target.append(PdfCandidate(normalized, candidate.candidate_source))
        seen.add(normalized)
    target[:] = prioritize_pdf_candidate_details(target)


def add_semantic_candidates_by_priority(
    candidate_details: list[PdfCandidate],
    semantic_urls: list[str],
) -> None:
    """Insert Semantic Scholar enrichment after direct OA PDFs and before PMC/EPMC/DOAJ."""
    additions = [
        PdfCandidate(url, "semantic_scholar_openAccessPdf")
        for url in semantic_urls
    ]
    additions = [
        candidate
        for candidate in unique_pdf_candidate_details(additions)
        if candidate_source_for_url(candidate_details, candidate.url) is None
    ]
    if not additions:
        return

    later_sources = {
        "pmc_direct",
        "europe_pmc_fullTextUrl",
        "doaj_fulltext",
        "landing_page_meta",
        "landing_page_anchor",
        "publisher_rule",
    }
    insert_at = next(
        (
            index
            for index, candidate in enumerate(candidate_details)
            if candidate.candidate_source in later_sources
        ),
        len(candidate_details),
    )
    candidate_details[insert_at:insert_at] = additions


def is_known_oa_record(record: dict[str, Any], unpaywall: dict[str, Any] | None = None) -> bool:
    """Return whether metadata marks a record as open access."""
    open_access = record.get("open_access") or {}
    if isinstance(open_access, dict) and open_access.get("is_oa"):
        return True
    if unpaywall and unpaywall.get("is_oa"):
        return True
    if record.get("literature_source") in {SOURCE_ARXIV, SOURCE_DOAJ}:
        return True
    if extract_arxiv_id(record) or extract_pmcid(record):
        return True
    for link in ((record.get("fullTextUrlList") or {}).get("fullTextUrl") or []):
        if isinstance(link, dict) and link.get("availabilityCode") == "OA":
            return True
    return False


def openalex_record_allows_content_api(record: dict[str, Any]) -> bool:
    """Return whether OpenAlex metadata says its legal content endpoint may have a PDF."""
    has_content = record.get("has_content")
    if isinstance(has_content, dict) and has_content.get("pdf"):
        return True

    content_urls = record.get("content_urls")
    if isinstance(content_urls, dict) and content_urls.get("pdf"):
        return True

    open_access = record.get("open_access") or {}
    if isinstance(open_access, dict) and open_access.get("is_oa"):
        return True

    best_oa_location = record.get("best_oa_location")
    if isinstance(best_oa_location, dict) and (best_oa_location.get("is_oa") or best_oa_location):
        return True

    return any(
        isinstance(location, dict) and location.get("is_oa")
        for location in record.get("locations") or []
    )


def add_openalex_content_api_candidate(candidates: list[PdfCandidate], record: dict[str, Any]) -> None:
    """Add OpenAlex's official per-work content endpoint when OA metadata allows it."""
    work_id = extract_openalex_work_id(record.get("openalex_id") or record.get("id"))
    if not work_id or not openalex_record_allows_content_api(record):
        return
    append_pdf_candidate(
        candidates,
        f"https://content.openalex.org/works/{work_id}.pdf",
        "openalex_content_api",
        include_publisher_rules=False,
    )


def add_openalex_location_candidate_details(candidates: list[PdfCandidate], location: Any) -> None:
    """Collect OpenAlex direct PDF candidates from one location object."""
    if not isinstance(location, dict):
        return
    append_pdf_candidate(candidates, location.get("pdf_url"), "openalex_pdf_url")
    if location.get("is_oa"):
        append_pdf_candidate(candidates, location.get("landing_page_url"), "openalex_landing")


def add_unpaywall_location_candidate_details(candidates: list[PdfCandidate], location: Any) -> None:
    """Collect Unpaywall PDF and landing-derived candidates from one location object."""
    if not isinstance(location, dict):
        return
    append_pdf_candidate(candidates, location.get("url_for_pdf"), "unpaywall_url_for_pdf")
    append_pdf_candidate(candidates, location.get("url"), "unpaywall_landing")


def add_europe_pmc_candidate_details(candidates: list[PdfCandidate], record: dict[str, Any]) -> None:
    """Collect Europe PMC OA PDF fullTextUrlList candidates."""
    full_text_urls = (record.get("fullTextUrlList") or {}).get("fullTextUrl") or []
    for link in full_text_urls:
        if not isinstance(link, dict):
            continue
        if link.get("availabilityCode") != "OA":
            continue
        if str(link.get("documentStyle") or "").casefold() == "pdf":
            append_pdf_candidate(candidates, link.get("url"), "europe_pmc_fullTextUrl")


def add_doaj_candidate_details(candidates: list[PdfCandidate], record: dict[str, Any]) -> None:
    """Collect DOAJ fulltext and PDF candidates from raw and normalized records."""
    for url in record.get("doaj_fulltext_links") or []:
        append_pdf_candidate(candidates, url, "doaj_fulltext")
    bibjson = record.get("bibjson") or {}
    for link in bibjson.get("link") or []:
        if not isinstance(link, dict):
            continue
        link_type = str(link.get("type") or "").casefold()
        content_type = str(link.get("content_type") or "").casefold()
        if link_type == "fulltext" or "pdf" in content_type:
            append_pdf_candidate(candidates, link.get("url"), "doaj_fulltext")


def add_arxiv_candidate_details(candidates: list[PdfCandidate], record: dict[str, Any]) -> None:
    """Collect arXiv direct PDF candidates from IDs and landing URLs."""
    arxiv_id = extract_arxiv_id(record)
    if arxiv_id:
        append_pdf_candidate(candidates, f"https://arxiv.org/pdf/{arxiv_id}", "arxiv_pdf", include_publisher_rules=False)
    for key in ("id", "source_record_id", "url", "pdf_url"):
        normalized = normalize_candidate_url(record.get(key))
        if normalized and urlparse(normalized).netloc.endswith("arxiv.org"):
            append_pdf_candidate(candidates, normalized, "arxiv_pdf")


def add_pmc_direct_candidate_details(candidates: list[PdfCandidate], record: dict[str, Any]) -> None:
    """Collect direct PMC official PDF candidates."""
    pmcid = extract_pmcid(record)
    if pmcid:
        append_pdf_candidate(
            candidates,
            f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/pdf/",
            "pmc_direct",
            include_publisher_rules=False,
        )


def record_direct_pdf_source(record: dict[str, Any]) -> str:
    """Return candidate_source for direct PDF fields on a normalized source record."""
    source = record.get("literature_source")
    if source == SOURCE_ARXIV:
        return "arxiv_pdf"
    if source == SOURCE_EUROPE_PMC:
        return "europe_pmc_fullTextUrl"
    if source == SOURCE_DOAJ:
        return "doaj_fulltext"
    if source == SOURCE_CROSSREF:
        return "publisher_rule"
    return "openalex_pdf_url"


def record_landing_source(record: dict[str, Any]) -> str:
    """Return candidate_source for landing-page fields on a normalized source record."""
    return "openalex_landing" if record.get("literature_source") in {None, SOURCE_OPENALEX} else "publisher_rule"


def add_record_location_candidate_details(
    candidates: list[PdfCandidate],
    location: Any,
    record: dict[str, Any],
) -> None:
    """Collect direct and landing-derived candidates from a source-normalized location."""
    if not isinstance(location, dict):
        return
    append_pdf_candidate(candidates, location.get("pdf_url"), record_direct_pdf_source(record))
    if location.get("is_oa") or record.get("literature_source") != SOURCE_OPENALEX:
        append_pdf_candidate(candidates, location.get("landing_page_url"), record_landing_source(record))


def add_openalex_location_candidates(urls: list[str | None], location: Any) -> None:
    """Collect PDF candidates from one OpenAlex location object."""
    if not isinstance(location, dict):
        return
    extend_pdf_candidate_urls(urls, location.get("pdf_url"))
    if location.get("is_oa"):
        extend_pdf_candidate_urls(urls, location.get("landing_page_url"))


def add_unpaywall_location_candidates(urls: list[str | None], location: Any) -> None:
    """Collect PDF candidates from one Unpaywall location object."""
    if not isinstance(location, dict):
        return
    extend_pdf_candidate_urls(urls, location.get("url_for_pdf"))
    extend_pdf_candidate_urls(urls, location.get("url"))


def add_europe_pmc_candidates(urls: list[str | None], record: dict[str, Any]) -> None:
    """Collect Europe PMC OA PDF fullTextUrlList candidates."""
    full_text_urls = (record.get("fullTextUrlList") or {}).get("fullTextUrl") or []
    for link in full_text_urls:
        if not isinstance(link, dict):
            continue
        if link.get("availabilityCode") != "OA":
            continue
        if str(link.get("documentStyle") or "").casefold() == "pdf":
            extend_pdf_candidate_urls(urls, link.get("url"))


def add_doaj_candidates(urls: list[str | None], record: dict[str, Any]) -> None:
    """Collect DOAJ fulltext and PDF candidates from raw and normalized records."""
    for url in record.get("doaj_fulltext_links") or []:
        extend_pdf_candidate_urls(urls, url)
    bibjson = record.get("bibjson") or {}
    for link in bibjson.get("link") or []:
        if not isinstance(link, dict):
            continue
        link_type = str(link.get("type") or "").casefold()
        content_type = str(link.get("content_type") or "").casefold()
        if link_type == "fulltext" or "pdf" in content_type:
            extend_pdf_candidate_urls(urls, link.get("url"))


def add_arxiv_candidates(urls: list[str | None], record: dict[str, Any]) -> None:
    """Collect arXiv PDF candidates from IDs and landing URLs."""
    arxiv_id = extract_arxiv_id(record)
    if arxiv_id:
        urls.append(f"https://arxiv.org/pdf/{arxiv_id}")
    for key in ("id", "source_record_id", "url", "pdf_url"):
        extend_pdf_candidate_urls(urls, record.get(key))


def unique_urls(urls: list[str | None]) -> list[str]:
    """Docstring."""
    seen: set[str] = set()
    result: list[str] = []
    for url in urls:
        if not url:
            continue
        normalized = str(url).strip()
        if not normalized:
            continue
        parsed = urlparse(normalized)
        key = normalized
        if parsed.scheme in {"http", "https"}:
            key = parsed._replace(scheme="https", netloc=parsed.netloc.casefold()).geturl()
        if key in seen:
            continue
        seen.add(key)
        result.append(normalized)
    return result


def unique_candidate_urls(urls: list[str | None]) -> list[str]:
    """Return normalized, deduplicated absolute HTTP(S) candidate URLs."""
    seen: set[str] = set()
    result: list[str] = []
    for url in urls:
        normalized = normalize_candidate_url(url)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def resolve_record_pdf_paths(record: dict[str, Any], meta_path: Path) -> list[Path]:
    """Docstring."""
    local_pdf_path = record.get("local_pdf_path")
    if not local_pdf_path:
        return []

    path = Path(local_pdf_path)
    if path.is_absolute():
        return [path]

    candidates = [
        meta_path.parent / path,
        BASE_DIR / path,
        Path.cwd() / path,
    ]
    normalized_parts = path.parts
    if normalized_parts and normalized_parts[0].lower() == LITERATURE_DOWNLOAD_DIR.name.lower():
        candidates.append(BASE_DIR / Path(*normalized_parts[1:]))

    result: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key not in seen:
            seen.add(key)
            result.append(candidate)
    return result


RETRYABLE_DOWNLOAD_STATUSES = {
    "",
    "blocked_or_login",
    "download_disabled",
    "failed",
    "file_error",
    "invalid_pdf",
    "no_candidate",
    "not_open_access",
    "not_pdf",
    "request_error",
    "stopped",
    "too_small",
}


def parse_iso_datetime(value: Any) -> datetime | None:
    """Parse an ISO timestamp stored in metadata."""
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def record_has_pdf_lookup_key(record: dict[str, Any]) -> bool:
    """Return whether a record has enough metadata to try the OA PDF resolver."""
    if normalize_doi(record.get("doi") or record.get("normalized_doi")):
        return True
    if record.get("openalex_id") or extract_openalex_work_id(record.get("id")):
        return True
    if extract_pmcid(record) or extract_arxiv_id(record):
        return True
    if record.get("source_record_id") or record.get("source_url") or record.get("url"):
        return True
    if record.get("pdf_url") or record.get("pdf_candidates"):
        return True
    open_access = record.get("open_access") or {}
    if isinstance(open_access, dict) and (open_access.get("oa_url") or open_access.get("is_oa")):
        return True
    return False


def record_has_valid_local_pdf(
    record: dict[str, Any],
    meta_path: Path | None,
    min_pdf_bytes: int,
) -> bool:
    """Validate the explicitly recorded local PDF path when path context exists."""
    if not record.get("local_pdf_path"):
        return False
    if meta_path is None:
        return True
    return any(validate_existing_pdf(path, min_pdf_bytes) for path in resolve_record_pdf_paths(record, meta_path))


def record_needs_pdf_retry(
    record: dict[str, Any],
    *,
    meta_path: Path | None = None,
    min_pdf_bytes: int = 1024,
    resolver_version: str = PDF_RESOLVER_VERSION,
    now: datetime | None = None,
) -> bool:
    """Return whether a missing-PDF record should re-enter the OA resolver."""
    if record_has_valid_local_pdf(record, meta_path, min_pdf_bytes):
        return False
    if not record_has_pdf_lookup_key(record):
        return False

    status = str(record.get("download_status") or "").strip()
    saved_resolver_version = str(record.get("resolver_version") or "").strip()
    resolver_changed = saved_resolver_version != resolver_version
    if resolver_changed:
        return True

    try:
        attempts = int(record.get("pdf_retry_attempts") or 0)
    except (TypeError, ValueError):
        attempts = 0

    last_retry_at = parse_iso_datetime(record.get("last_pdf_retry_at"))
    current_time = now or datetime.now()
    cooldown_elapsed = not last_retry_at or current_time - last_retry_at >= PDF_RETRY_COOLDOWN

    if status in RETRYABLE_DOWNLOAD_STATUSES:
        if status in PERMANENT_FAILURE_STATUSES:
            return attempts < MAX_PERMANENT_PDF_RETRY_ATTEMPTS and cooldown_elapsed
        if attempts >= MAX_PDF_RETRY_ATTEMPTS and not cooldown_elapsed:
            return False
        return True

    open_access = record.get("open_access") or {}
    unpaywall = record.get("unpaywall") or {}
    return bool(
        (isinstance(open_access, dict) and open_access.get("is_oa"))
        or (isinstance(unpaywall, dict) and unpaywall.get("is_oa"))
        or record.get("pdf_candidates")
    )


def pdf_sha256(path: Path) -> str:
    """Return the SHA-256 digest for a local PDF file."""
    digest = hashlib.sha256()
    with path.open("rb") as fin:
        for chunk in iter(lambda: fin.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def first_valid_pdf_path(paths: list[Path], min_pdf_bytes: int) -> Path | None:
    """Return the first valid PDF path from compatible metadata locations."""
    for path in paths:
        if validate_existing_pdf(path, min_pdf_bytes):
            return path
    return None


def record_pdf_urls(record: dict[str, Any]) -> list[str]:
    """Collect normalized PDF URLs already associated with a record."""
    urls: list[str | None] = [record.get("pdf_url"), record.get("download_source_url")]
    urls.extend(record.get("pdf_candidates") or [])
    return [
        url
        for url in unique_candidate_urls(urls)
        if looks_like_pdf_url(url) and not is_shadow_library_url(url)
    ]


def index_pdf_path(
    existing_index: ExistingIndex,
    record: dict[str, Any],
    path: Path,
    urls: list[str] | None = None,
) -> None:
    """Add a local PDF path to all duplicate-detection indexes."""
    canonical = canonical_record_key(record)
    if canonical:
        existing_index.canonical_keys.add(canonical)
        existing_index.downloaded_canonical_keys.add(canonical)
        existing_index.canonical_pdf_paths.setdefault(canonical, str(path))

    try:
        digest = pdf_sha256(path)
    except OSError:
        digest = ""
    if digest:
        existing_index.pdf_sha256_paths.setdefault(digest, str(path))

    for url in urls if urls is not None else record_pdf_urls(record):
        existing_index.pdf_url_keys.add(url)
        existing_index.pdf_url_paths.setdefault(url, str(path))


def reuse_duplicate_content_pdf(result: DownloadResult, existing_index: ExistingIndex) -> DownloadResult:
    """Reuse an existing PDF when a new download has identical bytes."""
    if not result.path:
        return result
    path = Path(result.path)
    try:
        digest = pdf_sha256(path)
    except OSError:
        return result
    existing_path = existing_index.pdf_sha256_paths.get(digest)
    if not existing_path:
        existing_index.pdf_sha256_paths[digest] = str(path)
        return result

    existing = Path(existing_path)
    if existing.resolve() == path.resolve():
        return result
    try:
        path.unlink(missing_ok=True)
        size_bytes = existing.stat().st_size if existing.exists() else result.size_bytes
    except OSError:
        size_bytes = result.size_bytes
    return DownloadResult(
        path=str(existing),
        status="duplicate_content_reused",
        source_url=result.source_url,
        reason=result.reason,
        size_bytes=size_bytes,
    )


def existing_pdf_for_candidates(existing_index: ExistingIndex, candidates: list[str]) -> str | None:
    """Return a local PDF path already known for any candidate URL."""
    for candidate in candidates:
        normalized = normalize_candidate_url(candidate)
        if normalized and normalized in existing_index.pdf_url_paths:
            return existing_index.pdf_url_paths[normalized]
    return None


def load_existing_index(meta_path: Path, min_pdf_bytes: int, out_dir: Path) -> ExistingIndex:
    """Docstring."""
    keys: set[str] = set()
    downloaded_keys: set[str] = set()
    retry_pdf_keys: set[str] = set()
    existing_index = ExistingIndex(keys, downloaded_keys, retry_pdf_keys)
    if not meta_path.exists():
        return existing_index

    with meta_path.open("r", encoding="utf-8") as fin:
        for line_no, line in enumerate(fin, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                logging.warning("Skipping invalid JSONL line %s in %s", line_no, meta_path)
                continue

            key = record_key(record)
            canonical = canonical_record_key(record)
            if canonical:
                existing_index.canonical_keys.add(canonical)
            if key:
                keys.add(key)
                fallback_out_dirs = [out_dir]
                keyword = record.get("keyword")
                if keyword:
                    fallback_out_dirs.insert(0, keyword_pdf_dir(str(keyword), out_dir))
                fallback_pdf_paths = []
                doi = normalize_doi(record.get("doi") or record.get("normalized_doi"))
                if doi:
                    fallback_pdf_paths.extend(path_for_pdf(doi, folder) for folder in fallback_out_dirs)
                source_record_id = record.get("source_record_id")
                if source_record_id:
                    fallback_pdf_paths.extend(path_for_pdf(source_record_id, folder) for folder in fallback_out_dirs)
                openalex_id = record.get("openalex_id") or record.get("id")
                if openalex_id:
                    fallback_pdf_paths.extend(path_for_pdf(openalex_id, folder) for folder in fallback_out_dirs)

                fallback_pdf_paths = resolve_record_pdf_paths(record, meta_path) + fallback_pdf_paths

                valid_path = first_valid_pdf_path(fallback_pdf_paths, min_pdf_bytes)
                if valid_path:
                    downloaded_keys.add(key)
                    retry_pdf_keys.discard(key)
                    index_pdf_path(existing_index, record, valid_path)
                elif key not in downloaded_keys and record_needs_pdf_retry(
                    record,
                    meta_path=meta_path,
                    min_pdf_bytes=min_pdf_bytes,
                ):
                    retry_pdf_keys.add(key)
            elif canonical:
                valid_path = first_valid_pdf_path(resolve_record_pdf_paths(record, meta_path), min_pdf_bytes)
                if valid_path:
                    index_pdf_path(existing_index, record, valid_path)

    return existing_index


def search_openalex(
    session: requests.Session,
    keyword: str,
    config: CrawlConfig,
    cursor: str = "*",
) -> dict[str, Any]:
    """Docstring."""
    filters = [
        "type:article",
        f"from_publication_date:{config.from_date}",
        f"to_publication_date:{config.to_date}",
    ]
    if config.oa_only:
        filters.append("is_oa:true")

    params = {
        "search": keyword,
        "filter": ",".join(filters),
        "per-page": config.per_page,
        "cursor": cursor,
        "select": OPENALEX_SELECT,
    }
    if config.email:
        params["mailto"] = config.email
    if config.sort:
        params["sort"] = config.sort

    response = session.get(OPENALEX_URL, params=params, timeout=(15, 45))
    response.raise_for_status()
    data = response.json()
    for item in data.get("results", []):
        item["literature_source"] = SOURCE_OPENALEX
        item["source_record_id"] = item.get("id")
    return data


def clean_markup_text(value: Any) -> str:
    """Docstring."""
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", str(value or "")))).strip()


def search_europe_pmc(
    session: requests.Session,
    keyword: str,
    config: CrawlConfig,
    cursor: str = "*",
) -> dict[str, Any]:
    """Docstring."""
    query = f"({keyword}) AND FIRST_PDATE:[{config.from_date} TO {config.to_date}]"
    if config.oa_only:
        query = f"OPEN_ACCESS:Y AND {query}"
    response = session.get(
        EUROPE_PMC_URL,
        params={
            "query": query,
            "format": "json",
            "resultType": "core",
            "pageSize": config.per_page,
            "cursorMark": cursor,
        },
        timeout=(15, 45),
    )
    response.raise_for_status()
    data = response.json()
    normalized: list[dict[str, Any]] = []
    for item in (data.get("resultList") or {}).get("result", []):
        full_text_urls = (item.get("fullTextUrlList") or {}).get("fullTextUrl", [])
        oa_urls = [
            link.get("url")
            for link in full_text_urls
            if link.get("availabilityCode") == "OA" and link.get("url")
        ]
        pdf_urls = [
            link.get("url")
            for link in full_text_urls
            if link.get("availabilityCode") == "OA"
            and str(link.get("documentStyle") or "").casefold() == "pdf"
            and link.get("url")
        ]
        pmcid = item.get("pmcid")
        if not pmcid and str(item.get("source") or "").casefold() == "pmc":
            raw_id = str(item.get("id") or "")
            if re.fullmatch(r"\d+", raw_id):
                pmcid = f"PMC{raw_id}"
            elif re.fullmatch(r"PMC\d+", raw_id, flags=re.IGNORECASE):
                pmcid = raw_id.upper()
        source_record_id = f"{item.get('source') or 'unknown'}:{item.get('id') or pmcid or item.get('doi')}"
        publication_date = (
            item.get("firstPublicationDate")
            or item.get("electronicPublicationDate")
            or (item.get("journalInfo") or {}).get("printPublicationDate")
            or (f"{item.get('pubYear')}-01-01" if item.get("pubYear") else None)
        )
        normalized.append(
            {
                "id": f"europepmc:{source_record_id}",
                "source_record_id": f"{SOURCE_EUROPE_PMC}:{source_record_id}",
                "literature_source": SOURCE_EUROPE_PMC,
                "pmcid": pmcid,
                "doi": item.get("doi"),
                "title": clean_markup_text(item.get("title")),
                "publication_date": publication_date,
                "publication_year": item.get("pubYear"),
                "cited_by_count": item.get("citedByCount"),
                "authorships": [
                    {"author": {"display_name": author.get("fullName")}}
                    for author in (item.get("authorList") or {}).get("author", [])
                    if author.get("fullName")
                ],
                "abstract": clean_markup_text(item.get("abstractText")),
                "primary_location": {
                    "pdf_url": pdf_urls[0] if pdf_urls else None,
                    "landing_page_url": oa_urls[0] if oa_urls else None,
                },
                "open_access": {
                    "is_oa": item.get("isOpenAccess") == "Y",
                    "oa_url": (pdf_urls or oa_urls or [None])[0],
                },
                "fullTextUrlList": item.get("fullTextUrlList") or {},
            }
        )
    next_cursor = data.get("nextCursorMark")
    if not normalized or next_cursor == cursor:
        next_cursor = None
    return {"results": normalized, "meta": {"next_cursor": next_cursor}}


def arxiv_query(keyword: str) -> str:
    """Docstring."""
    terms = keyword_terms(keyword)
    return " AND ".join(f"all:{term}" for term in terms) or f'all:"{keyword}"'


def search_arxiv(
    session: requests.Session,
    keyword: str,
    config: CrawlConfig,
    cursor: str = "0",
) -> dict[str, Any]:
    """Docstring."""
    start = int(cursor or 0)
    response = session.get(
        ARXIV_URL,
        params={
            "search_query": arxiv_query(keyword),
            "start": start,
            "max_results": config.per_page,
            "sortBy": "relevance",
            "sortOrder": "descending",
        },
        timeout=(15, 45),
    )
    response.raise_for_status()
    root = ET.fromstring(response.text)
    namespaces = {
        "atom": "http://www.w3.org/2005/Atom",
        "opensearch": "http://a9.com/-/spec/opensearch/1.1/",
        "arxiv": "http://arxiv.org/schemas/atom",
    }
    entries = root.findall("atom:entry", namespaces)
    total = int(root.findtext("opensearch:totalResults", "0", namespaces))
    normalized: list[dict[str, Any]] = []
    for entry in entries:
        published = entry.findtext("atom:published", "", namespaces)
        if published and not config.from_date <= published[:10] <= config.to_date:
            continue
        source_record_id = entry.findtext("atom:id", "", namespaces)
        links = {
            link.get("title") or link.get("rel"): link.get("href")
            for link in entry.findall("atom:link", namespaces)
            if link.get("href")
        }
        pdf_url = links.get("pdf")
        landing_url = links.get("alternate")
        normalized.append(
            {
                "id": source_record_id,
                "source_record_id": f"{SOURCE_ARXIV}:{source_record_id}",
                "literature_source": SOURCE_ARXIV,
                "doi": entry.findtext("arxiv:doi", None, namespaces),
                "title": clean_markup_text(entry.findtext("atom:title", "", namespaces)),
                "publication_date": published[:10] or None,
                "publication_year": published[:4] or None,
                "cited_by_count": None,
                "authorships": [
                    {"author": {"display_name": author.findtext("atom:name", "", namespaces)}}
                    for author in entry.findall("atom:author", namespaces)
                ],
                "abstract": clean_markup_text(entry.findtext("atom:summary", "", namespaces)),
                "primary_location": {
                    "pdf_url": pdf_url,
                    "landing_page_url": landing_url,
                },
                "open_access": {"is_oa": True, "oa_url": pdf_url or landing_url},
            }
        )
    next_start = start + len(entries)
    next_cursor = str(next_start) if entries and next_start < total else None
    return {"results": normalized, "meta": {"next_cursor": next_cursor}}


def first_value(value: Any) -> Any:
    """Docstring."""
    if isinstance(value, list):
        return value[0] if value else None
    return value


def date_from_parts(value: Any) -> tuple[str | None, int | None]:
    """Docstring."""
    if not isinstance(value, dict):
        return None, None
    date_time = value.get("date-time")
    if isinstance(date_time, str) and len(date_time) >= 10:
        year = int(date_time[:4]) if date_time[:4].isdigit() else None
        return date_time[:10], year

    parts = first_value(value.get("date-parts"))
    if not isinstance(parts, list) or not parts:
        return None, None
    try:
        year = int(parts[0])
        month = int(parts[1]) if len(parts) > 1 else 1
        day = int(parts[2]) if len(parts) > 2 else 1
    except (TypeError, ValueError):
        return None, None
    return f"{year:04d}-{month:02d}-{day:02d}", year


def publication_date_from_crossref(item: dict[str, Any]) -> tuple[str | None, int | None]:
    """Docstring."""
    for key in ("published-print", "published-online", "published", "issued", "created"):
        publication_date, publication_year = date_from_parts(item.get(key))
        if publication_date:
            return publication_date, publication_year
    return None, None


def record_in_config_date_range(publication_date: str | None, publication_year: Any, config: CrawlConfig) -> bool:
    """Docstring."""
    if publication_date:
        return config.from_date <= publication_date[:10] <= config.to_date
    if publication_year:
        try:
            year = int(publication_year)
        except (TypeError, ValueError):
            return True
        return int(config.from_date[:4]) <= year <= int(config.to_date[:4])
    return True


def open_license_from_urls(urls: list[str]) -> bool:
    """Docstring."""
    indicators = ("creativecommons.org", "openaccess", "open-access", "publicdomain", "cc0")
    return any(any(indicator in url.casefold() for indicator in indicators) for url in urls)


def normalize_issn_list(values: Any) -> list[str]:
    """Docstring."""
    raw_values = values if isinstance(values, list) else [values]
    normalized: list[str] = []
    for value in raw_values:
        if not value:
            continue
        text = str(value).strip().upper()
        if re.fullmatch(r"\d{8}|\d{7}X", text):
            text = f"{text[:4]}-{text[4:]}"
        if text and text not in normalized:
            normalized.append(text)
    return normalized


def normalize_crossref_item(item: dict[str, Any]) -> dict[str, Any]:
    """Docstring."""
    doi = item.get("DOI")
    source_record_id = normalize_doi(doi) or item.get("URL") or item.get("member")
    publication_date, publication_year = publication_date_from_crossref(item)
    container_titles = item.get("container-title") or []
    journal_title = first_value(container_titles)
    issns = normalize_issn_list(item.get("ISSN") or item.get("issn-type"))
    licenses = item.get("license") or []
    license_urls = unique_urls([license_item.get("URL") for license_item in licenses if isinstance(license_item, dict)])
    links = item.get("link") or []
    resource = item.get("resource") or {}
    primary_resource = resource.get("primary") if isinstance(resource, dict) else {}
    resource_url = primary_resource.get("URL") if isinstance(primary_resource, dict) else None
    pdf_urls = unique_candidate_urls([
        *[
            link.get("URL")
            for link in links
            if isinstance(link, dict)
            and (
                "pdf" in str(link.get("content-type") or "").casefold()
                or looks_like_pdf_url(link.get("URL"))
            )
            and link.get("URL")
        ],
        resource_url if looks_like_pdf_url(resource_url) else None,
    ])
    landing_url = item.get("URL") or resource_url
    oa_url = (pdf_urls or license_urls or [landing_url or None])[0]

    return {
        "id": f"crossref:{source_record_id}",
        "source_record_id": f"{SOURCE_CROSSREF}:{source_record_id}",
        "literature_source": SOURCE_CROSSREF,
        "doi": doi,
        "title": clean_markup_text(first_value(item.get("title"))),
        "publication_date": publication_date,
        "publication_year": publication_year,
        "cited_by_count": item.get("is-referenced-by-count"),
        "authorships": [
            {"author": {"display_name": clean_markup_text(" ".join(filter(None, [author.get("given"), author.get("family")])) or author.get("name"))}}
            for author in item.get("author") or []
            if isinstance(author, dict) and (author.get("given") or author.get("family") or author.get("name"))
        ],
        "abstract": clean_markup_text(item.get("abstract")),
        "primary_location": {
            "pdf_url": pdf_urls[0] if pdf_urls else None,
            "landing_page_url": landing_url,
            "source": {
                "display_name": journal_title,
                "issn": issns,
                "issn_l": item.get("ISSN-L") or (issns[0] if issns else None),
                "publisher": item.get("publisher"),
            },
        },
        "open_access": {
            "is_oa": open_license_from_urls(license_urls),
            "oa_url": oa_url,
            "license_urls": license_urls,
        },
        "license": licenses,
        "publisher": item.get("publisher"),
        "container-title": container_titles,
        "issns": issns,
    }


def search_crossref(
    session: requests.Session,
    keyword: str,
    config: CrawlConfig,
    cursor: str = "*",
) -> dict[str, Any]:
    """Docstring."""
    filters = [
        "type:journal-article",
        f"from-pub-date:{config.from_date}",
        f"until-pub-date:{config.to_date}",
    ]
    if config.oa_only:
        filters.append("has-license:true")

    params = {
        "query.bibliographic": keyword,
        "filter": ",".join(filters),
        "rows": min(config.per_page, 1000),
        "cursor": cursor or "*",
    }
    if config.email:
        params["mailto"] = config.email
    if config.sort == "publication_date:desc":
        params["sort"] = "published"
        params["order"] = "desc"

    response = session.get(CROSSREF_URL, params=params, timeout=(15, 45))
    response.raise_for_status()
    message = response.json().get("message") or {}
    normalized = [
        normalize_crossref_item(item)
        for item in message.get("items") or []
        if isinstance(item, dict)
    ]
    next_cursor = message.get("next-cursor") if normalized else None
    if next_cursor == cursor:
        next_cursor = None
    return {"results": normalized, "meta": {"next_cursor": next_cursor}}


def doaj_identifier_values(identifiers: list[dict[str, Any]], wanted_types: set[str]) -> list[str]:
    """Docstring."""
    values: list[str] = []
    for identifier in identifiers:
        if not isinstance(identifier, dict):
            continue
        identifier_type = str(identifier.get("type") or "").casefold()
        identifier_value = identifier.get("id")
        if identifier_type in wanted_types and identifier_value:
            values.append(str(identifier_value))
    return values


def doaj_publication_date(bibjson: dict[str, Any]) -> tuple[str | None, int | None]:
    """Docstring."""
    year = bibjson.get("year")
    try:
        publication_year = int(year)
    except (TypeError, ValueError):
        return None, None
    month = bibjson.get("month") or 1
    try:
        publication_month = int(month)
    except (TypeError, ValueError):
        publication_month = 1
    return f"{publication_year:04d}-{publication_month:02d}-01", publication_year


def normalize_doaj_item(item: dict[str, Any]) -> dict[str, Any]:
    """Docstring."""
    bibjson = item.get("bibjson") or {}
    identifiers = bibjson.get("identifier") or []
    doi = first_value(doaj_identifier_values(identifiers, {"doi"}))
    issns = normalize_issn_list(doaj_identifier_values(identifiers, {"issn", "pissn", "eissn"}))
    journal = bibjson.get("journal") or {}
    journal_issns = normalize_issn_list([journal.get("issn"), journal.get("eissn")])
    all_issns = unique_urls([*issns, *journal_issns])
    publication_date, publication_year = doaj_publication_date(bibjson)
    links = bibjson.get("link") or []
    fulltext_links = [
        link.get("url")
        for link in links
        if isinstance(link, dict)
        and str(link.get("type") or "").casefold() == "fulltext"
        and link.get("url")
    ]
    pdf_urls = [
        link.get("url")
        for link in links
        if isinstance(link, dict)
        and str(link.get("type") or "").casefold() == "fulltext"
        and (
            "pdf" in str(link.get("content_type") or "").casefold()
            or str(link.get("url") or "").casefold().endswith(".pdf")
        )
        and link.get("url")
    ]
    source_record_id = item.get("id") or normalize_doi(doi) or first_value(fulltext_links)
    licenses = bibjson.get("license") or []
    license_urls = unique_urls([license_item.get("url") for license_item in licenses if isinstance(license_item, dict)])
    oa_url = (pdf_urls or fulltext_links or [None])[0]

    return {
        "id": f"doaj:{source_record_id}",
        "source_record_id": f"{SOURCE_DOAJ}:{source_record_id}",
        "literature_source": SOURCE_DOAJ,
        "doi": doi,
        "title": clean_markup_text(bibjson.get("title")),
        "publication_date": publication_date,
        "publication_year": publication_year,
        "cited_by_count": None,
        "authorships": [
            {"author": {"display_name": clean_markup_text(author.get("name"))}}
            for author in bibjson.get("author") or []
            if isinstance(author, dict) and author.get("name")
        ],
        "abstract": clean_markup_text(bibjson.get("abstract")),
        "primary_location": {
            "pdf_url": pdf_urls[0] if pdf_urls else None,
            "landing_page_url": oa_url,
            "source": {
                "display_name": journal.get("title"),
                "issn": all_issns,
                "issn_l": all_issns[0] if all_issns else None,
                "publisher": journal.get("publisher"),
            },
        },
        "open_access": {
            "is_oa": True,
            "oa_url": oa_url,
            "license_urls": license_urls,
        },
        "license": licenses,
        "publisher": journal.get("publisher"),
        "journal": journal.get("title"),
        "issns": all_issns,
        "doaj_fulltext_links": unique_candidate_urls(fulltext_links),
    }


def search_doaj(
    session: requests.Session,
    keyword: str,
    config: CrawlConfig,
    cursor: str = "1",
) -> dict[str, Any]:
    """Docstring."""
    try:
        page = max(1, int(cursor or "1"))
    except ValueError:
        page = 1
    page_size = min(config.per_page, 100)
    response = session.get(
        f"{DOAJ_URL}/{quote(keyword)}",
        params={"page": page, "pageSize": page_size},
        timeout=(15, 45),
    )
    response.raise_for_status()
    data = response.json()
    normalized = [
        normalized_item
        for item in data.get("results") or []
        if isinstance(item, dict)
        for normalized_item in [normalize_doaj_item(item)]
        if record_in_config_date_range(normalized_item.get("publication_date"), normalized_item.get("publication_year"), config)
    ]
    total = data.get("total")
    try:
        has_next = bool(total and page * page_size < int(total))
    except (TypeError, ValueError):
        has_next = bool(normalized)
    return {"results": normalized, "meta": {"next_cursor": str(page + 1) if has_next else None}}


def search_literature_source(
    session: requests.Session,
    source: str,
    keyword: str,
    config: CrawlConfig,
    cursor: str,
) -> dict[str, Any]:
    """Docstring."""
    if source == SOURCE_OPENALEX:
        return search_openalex(session, keyword, config, cursor)
    if source == SOURCE_EUROPE_PMC:
        return search_europe_pmc(session, keyword, config, cursor)
    if source == SOURCE_ARXIV:
        return search_arxiv(session, keyword, config, cursor)
    if source == SOURCE_CROSSREF:
        return search_crossref(session, keyword, config, cursor)
    if source == SOURCE_DOAJ:
        return search_doaj(session, keyword, config, cursor)
    raise ValueError(f"Unsupported literature source: {source}")


def source_maps() -> list[dict[str, str]]:
    """Docstring."""
    return [{"key": key, "label": label} for key, label in SOURCE_LABELS.items()]


def reconstruct_abstract(inv_index: dict[str, list[int]] | None) -> str:
    """Docstring."""
    if not inv_index:
        return ""

    words = [
        (position, word)
        for word, positions in inv_index.items()
        for position in positions
    ]
    words.sort(key=lambda item: item[0])
    return " ".join(word for _, word in words)


def normalize_search_term(term: str) -> str:
    """Docstring."""
    term = term.casefold()
    aliases = {
        "li": "lithium",
        "libs": "lithium",
        "na": "sodium",
    }
    if term in aliases:
        return aliases[term]
    if len(term) > 4 and term.endswith("ies"):
        return term[:-3] + "y"
    if len(term) > 3 and term.endswith("s") and not term.endswith("ss"):
        return term[:-1]
    return term


def search_terms(text: str) -> list[str]:
    """Docstring."""
    return [normalize_search_term(term) for term in re.findall(r"[a-z0-9]+", text.casefold())]


def keyword_terms(keyword: str) -> list[str]:
    """Docstring."""
    stopwords = {
        "a",
        "an",
        "and",
        "as",
        "at",
        "based",
        "by",
        "for",
        "from",
        "in",
        "of",
        "on",
        "or",
        "the",
        "to",
        "using",
        "via",
        "with",
    }
    terms: list[str] = []
    seen: set[str] = set()
    for term in search_terms(keyword):
        if term in stopwords or term in seen:
            continue
        seen.add(term)
        terms.append(term)
    return terms


def work_search_text(item: dict[str, Any]) -> str:
    """Docstring."""
    fields = [
        item.get("title"),
        item.get("display_name"),
        item.get("abstract"),
        reconstruct_abstract(item.get("abstract_inverted_index")),
    ]
    return " ".join(str(field) for field in fields if field)


def keyword_match_details(
    keyword: str,
    item: dict[str, Any],
    min_match_ratio: float,
) -> tuple[bool, float, list[str]]:
    """Docstring."""
    terms = keyword_terms(keyword)
    if not terms:
        return keyword.casefold() in work_search_text(item).casefold(), 0.0, []

    text_terms = search_terms(work_search_text(item))
    canonical_text = " ".join(text_terms)
    canonical_keyword = " ".join(terms)
    if canonical_keyword and canonical_keyword in canonical_text:
        return True, 1.0, []

    text_term_set = set(text_terms)
    matched = [term for term in terms if term in text_term_set]
    ratio = len(matched) / len(terms)
    required_matches = len(terms) if len(terms) <= 2 else max(2, int(len(terms) * min_match_ratio + 0.999))
    missing = [term for term in terms if term not in text_term_set]
    return len(matched) >= required_matches, ratio, missing


def record_matches_keyword(keyword: str, item: dict[str, Any], config: CrawlConfig) -> bool:
    """Docstring."""
    if not config.strict_keyword_match:
        return True
    matched, _ratio, _missing = keyword_match_details(keyword, item, config.min_keyword_match_ratio)
    return matched


def record_passes_relevance_filters(
    item: dict[str, Any],
    config: CrawlConfig,
    topic_pack: dict[str, Any] | None = None,
    journal_pack: dict[str, Any] | None = None,
) -> tuple[bool, int, str | None]:
    """Docstring."""
    if config.journal_whitelist_only and config.journal_pack:
        if not record_matches_resolved_journal_pack(item, config, journal_pack):
            return False, 0, "journal_not_whitelisted"

    if not config.strict_keyword_match or not config.topic_pack or config.min_topic_score <= 0:
        return True, 0, None

    resolved_topic_pack = topic_pack or resolve_topic_pack(config, config.effective_keywords)
    score = score_topic_relevance(item, topic_pack=resolved_topic_pack)
    if score < config.min_topic_score:
        return False, score, "low_topic_score"
    return True, score, None


def enrich_record_with_journal_metrics(
    item: dict[str, Any],
    resolver: JournalMetricResolver | None = None,
) -> dict[str, Any]:
    """Attach normalized journal and local impact-factor fields to a search record."""
    if resolver is not None:
        attach_journal_metric(item, resolver.resolve(item))
        return {
            "journal_title": item.get("journal_title"),
            "journal_issns": item.get("journal_issns") or [],
            "journal_issn_l": item.get("journal_issn_l"),
            "impact_factor": item.get("impact_factor"),
            "impact_factor_year": item.get("impact_factor_year"),
            "impact_factor_source": item.get("impact_factor_source"),
            "impact_factor_metric": item.get("impact_factor_metric"),
            "impact_factor_quartile": item.get("impact_factor_quartile"),
            "impact_factor_unknown": bool(item.get("impact_factor_unknown")),
        }
    match = match_journal_metric(item)
    fields = match.as_record_fields()
    item.update(fields)
    item["journal_name"] = item.get("journal_title") or ""
    item["journal_impact_value"] = item.get("impact_factor")
    item["journal_impact_metric"] = item.get("impact_factor_metric") or ""
    item["journal_impact_year"] = item.get("impact_factor_year")
    item["journal_metric_source"] = item.get("impact_factor_source") or ""
    return fields


def record_passes_impact_factor_filter(
    item: dict[str, Any],
    config: CrawlConfig,
    resolver: JournalMetricResolver | None = None,
) -> tuple[bool, dict[str, Any]]:
    """Return whether a record passes the configured minimum impact factor.

    Records with unknown impact factor are retained so an incomplete local metrics
    table does not silently hide relevant literature.
    """
    fields = enrich_record_with_journal_metrics(item, resolver)
    passes = metric_passes_impact_factor_filter(
        item,
        config.min_impact_factor,
        include_unknown=config.include_unknown_impact_factor,
    )
    return passes, fields


def record_matches_resolved_journal_pack(
    item: dict[str, Any],
    config: CrawlConfig,
    journal_pack: dict[str, Any] | None,
) -> bool:
    """Return whether a record matches the configured journal allow-list."""
    if config.journal_pack == "li_sulfur":
        return is_whitelisted_journal(item, selected_journals=config.selected_journals)
    resolved = journal_pack or resolve_journal_pack(config, [item])
    return journal_pack_match_score(item, resolved) > 0


RELEVANCE_LEVELS = (
    ("keyword_only", 0, "关键词提及即可"),
    ("loose", 4, "宽松"),
    ("balanced", 6, "均衡"),
    ("strict", 9, "严格"),
    ("very_strict", 12, "极严格"),
)


def relevance_level_for_score(score: int, keyword_matched: bool = True) -> str:
    """Return the highest relevance level passed by a topic score."""
    if not keyword_matched:
        return "unmatched"
    level = "keyword_only"
    for key, threshold, _label in RELEVANCE_LEVELS:
        if score >= threshold:
            level = key
    return level


def relevance_label(level: str) -> str:
    """Return a user-facing Chinese label for a relevance level."""
    if level == "unmatched":
        return "未命中关键词"
    for key, _threshold, label in RELEVANCE_LEVELS:
        if key == level:
            return label
    return level or "未知"


def keyword_matched_fields(keyword: str, item: dict[str, Any], min_match_ratio: float) -> list[str]:
    """Return title/abstract fields that match a keyword."""
    fields: list[str] = []
    title_item = {"title": item.get("title") or item.get("display_name")}
    abstract_item = {
        "abstract": item.get("abstract")
        or item.get("abstract_text")
        or item.get("abstractText")
        or item.get("description")
        or reconstruct_abstract(item.get("abstract_inverted_index"))
    }
    if keyword_match_details(keyword, title_item, min_match_ratio)[0]:
        fields.append("title")
    if keyword_match_details(keyword, abstract_item, min_match_ratio)[0]:
        fields.append("abstract")
    return fields


def build_relevance_info(
    keyword: str,
    item: dict[str, Any],
    config: CrawlConfig,
    topic_pack: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build explainable relevance metadata for a record."""
    matched_keywords: list[str] = []
    matched_fields: list[str] = []
    for candidate in config.effective_keywords:
        matched, _ratio, _missing = keyword_match_details(candidate, item, config.min_keyword_match_ratio)
        if not matched:
            continue
        matched_keywords.append(candidate)
        for field in keyword_matched_fields(candidate, item, config.min_keyword_match_ratio):
            if field not in matched_fields:
                matched_fields.append(field)

    if not matched_keywords:
        matched, _ratio, _missing = keyword_match_details(keyword, item, config.min_keyword_match_ratio)
        if matched:
            matched_keywords.append(keyword)
            matched_fields = keyword_matched_fields(keyword, item, config.min_keyword_match_ratio)

    resolved_topic_pack = topic_pack or resolve_topic_pack(config, config.effective_keywords)
    score = score_topic_relevance(item, topic_pack=resolved_topic_pack)
    keyword_matched = bool(matched_keywords)
    level = relevance_level_for_score(score, keyword_matched)
    passed_levels = [
        key
        for key, threshold, _label in RELEVANCE_LEVELS
        if keyword_matched and score >= threshold
    ]
    reasons = []
    if matched_keywords:
        reasons.append("标题或摘要命中关键词")
    if score > 0:
        reasons.append(f"主题信号分 {score}")
    if not reasons:
        reasons.append("未命中当前关键词规则")
    return {
        "relevance_score": score,
        "relevance_level": level,
        "relevance_label": relevance_label(level),
        "relevance_passed_levels": passed_levels,
        "matched_keywords": matched_keywords,
        "matched_fields": matched_fields,
        "relevance_reasons": reasons,
    }


def sort_records_by_resolved_packs(
    records: list[dict[str, Any]],
    topic_pack: dict[str, Any],
    journal_pack: dict[str, Any],
) -> list[dict[str, Any]]:
    """Sort search results by topic score and OA journal recommendation bonus."""
    for item in records:
        item["topic_score"] = score_topic_relevance(item, topic_pack=topic_pack)
        item["journal_pack_score"] = journal_pack_match_score(item, journal_pack)
    return sorted(
        records,
        key=lambda item: (
            int(item.get("topic_score") or 0) + int(item.get("journal_pack_score") or 0),
            int(item.get("cited_by_count") or 0),
        ),
        reverse=True,
    )


def extract_authors(item: dict[str, Any], limit: int = 12) -> list[str]:
    """Docstring."""
    authors: list[str] = []
    for authorship in item.get("authorships") or []:
        author_name = (authorship.get("author") or {}).get("display_name")
        if author_name:
            authors.append(author_name)
        if len(authors) >= limit:
            break
    return authors


def extract_pdf_text(pdf_path: Path, max_pages: int = 4) -> str:
    """Extract text from the first pages of a downloaded PDF."""
    try:
        import fitz

        chunks: list[str] = []
        with fitz.open(pdf_path) as document:
            for page_index in range(min(max_pages, len(document))):
                text = document.load_page(page_index).get_text("text")
                if text:
                    chunks.append(text)
        return "\n".join(chunks)
    except Exception:
        return ""


def _clean_extracted_text(value: Any) -> str:
    return re.sub(r"\s+", " ", html.unescape(str(value or ""))).strip()


def extract_abstract_from_text(text: str) -> str:
    """Extract an abstract-like paragraph from raw PDF text."""
    if not text:
        return ""
    normalized = text.replace("\r", "\n")
    match = re.search(
        r"(?is)\babstract\b\s*[:.\-]?\s*(.+?)(?=\n\s*(?:keywords?|index terms|introduction|1\s*\.?\s*introduction|background)\b)",
        normalized,
    )
    if not match:
        return ""
    abstract = _clean_extracted_text(match.group(1))
    return abstract[:2400].strip()


def extract_keywords_from_text(text: str) -> list[str]:
    """Extract explicit Keywords/Index Terms lines from raw PDF text."""
    if not text:
        return []
    match = re.search(
        r"(?is)\b(?:keywords?|index terms)\b\s*[:.\-]?\s*(.+?)(?=\n\s*(?:introduction|1\s*\.?\s*introduction|abstract|background)\b)",
        text.replace("\r", "\n"),
    )
    if not match:
        return []
    raw = _clean_extracted_text(match.group(1))
    return _unique_keyword_labels(re.split(r"[,;•·|]", raw))


def _unique_keyword_labels(values: list[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _clean_extracted_text(value)
        text = re.sub(r"^[\-\u2010-\u2015\s]+|[\.\s]+$", "", text)
        if not text or len(text) > 80:
            continue
        key = keyword_group_key(text)
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


def keyword_group_key(value: Any) -> str:
    """Return a stable key for grouping similar literature keywords."""
    terms = keyword_terms(str(value or ""))
    if not terms:
        return ""
    return " ".join(terms)


def keyword_group_label(value: Any) -> str:
    text = _clean_extracted_text(value)
    return text if text else str(value or "").strip()


def generate_extracted_keywords(
    keyword: str,
    title: str,
    abstract: str,
    explicit_keywords: list[str],
    matched_keywords: list[str] | None = None,
    limit: int = 10,
) -> list[str]:
    """Build display keywords from explicit PDF keywords, matched user terms, and text phrases."""
    candidates: list[Any] = [*explicit_keywords, *(matched_keywords or []), keyword]
    text = f"{title}. {abstract}"
    candidates.extend(
        match.group(0)
        for match in re.finditer(
            r"\b[a-z][a-z0-9]*(?:[- ][a-z0-9]+){1,4}\b",
            text.casefold(),
        )
    )
    result = _unique_keyword_labels(candidates)
    return result[:limit]


def make_content_summary(title: str, abstract: str, max_chars: int = 360) -> str:
    """Build a lightweight summary from source metadata only."""
    text = _clean_extracted_text(abstract)
    if not text:
        return _clean_extracted_text(title)[:max_chars]
    sentence = re.split(r"(?<=[.!?])\s+", text, maxsplit=1)[0]
    if len(sentence) < 80 and len(text) > len(sentence):
        sentence = text[:max_chars]
    return sentence[:max_chars].strip()


def summarize_content(abstract: str, title: str = "") -> str:
    return make_content_summary(title, abstract, max_chars=420)


def generate_keyword_groups(
    record: dict[str, Any],
    extracted_keywords: list[str],
    user_keywords: list[str] | str,
    max_groups: int = 6,
) -> list[str]:
    """Return stable keyword group labels for metadata and library filters."""
    values: list[Any] = [*extracted_keywords]
    if isinstance(user_keywords, str):
        values.append(user_keywords)
    else:
        values.extend(user_keywords)
    record_keywords = record.get("keywords") or record.get("concepts") or []
    if isinstance(record_keywords, str):
        values.extend(re.split(r"[,;|]", record_keywords))
    else:
        values.extend(record_keywords)
    groups: list[str] = []
    seen: set[str] = set()
    for value in _unique_keyword_labels(values):
        key = keyword_group_key(value)
        if not key or key in seen:
            continue
        seen.add(key)
        groups.append(keyword_group_label(value))
        if len(groups) >= max_groups:
            break
    return groups


def content_fields_for_record(
    keyword: str,
    item: dict[str, Any],
    download: DownloadResult,
    meta_path: Path,
    relevance_info: dict[str, Any] | None,
) -> dict[str, Any]:
    """Return abstract, extracted PDF abstract, display keywords, and a short summary."""
    source_abstract = _clean_extracted_text(item.get("abstract") or reconstruct_abstract(item.get("abstract_inverted_index")))
    extracted_abstract = ""
    explicit_keywords: list[str] = list(item.get("extracted_keywords") or [])
    abstract = source_abstract or extracted_abstract
    matched_keywords = list((relevance_info or {}).get("matched_keywords") or [])
    extracted_keywords = generate_extracted_keywords(
        keyword,
        str(item.get("title") or item.get("display_name") or ""),
        abstract,
        explicit_keywords,
        matched_keywords,
    )
    content_summary = make_content_summary(str(item.get("title") or item.get("display_name") or ""), abstract)
    keyword_groups = generate_keyword_groups(item, extracted_keywords, [keyword, *matched_keywords])
    return {
        "abstract": abstract,
        "extracted_abstract": extracted_abstract,
        "extracted_keywords": extracted_keywords,
        "content_summary": content_summary,
        "summary_text": content_summary,
        "keyword_groups": keyword_groups,
        "topic_tags": keyword_groups,
    }


def query_unpaywall(
    session: requests.Session,
    doi: str | None,
    email: str,
) -> dict[str, Any] | None:
    """Docstring."""
    doi = normalize_doi(doi)
    if not doi:
        return None

    response = session.get(
        f"{UNPAYWALL_URL}/{quote(doi)}",
        params={"email": email},
        timeout=(15, 45),
    )
    if response.status_code == 404:
        return None

    response.raise_for_status()

    data = response.json()
    best = data.get("best_oa_location") or {}
    all_locations = data.get("oa_locations") or []
    pdf_urls = unique_candidate_urls([best.get("url_for_pdf")] + [loc.get("url_for_pdf") for loc in all_locations])
    landing_urls = unique_candidate_urls([best.get("url")] + [loc.get("url") for loc in all_locations])

    return {
        "is_oa": data.get("is_oa"),
        "oa_status": data.get("oa_status"),
        "license": best.get("license"),
        "pdf_url": best.get("url_for_pdf"),
        "landing_url": best.get("url"),
        "pdf_urls": pdf_urls,
        "landing_urls": landing_urls,
        "best_oa_location": best,
        "oa_locations": all_locations,
        "host_type": best.get("host_type"),
        "version": best.get("version"),
    }


def query_openalex_work(
    session: requests.Session,
    record: dict[str, Any],
    config: CrawlConfig,
) -> dict[str, Any] | None:
    """Refresh OA location metadata from OpenAlex by work ID or DOI."""
    work_id = extract_openalex_work_id(record.get("openalex_id") or record.get("id"))
    doi = normalize_doi(record.get("doi") or record.get("normalized_doi"))
    if work_id:
        url = f"{OPENALEX_URL}/{work_id}"
    elif doi:
        url = f"{OPENALEX_URL}/doi:{quote(doi)}"
    else:
        return None

    params = {"select": OPENALEX_SELECT}
    if config.email:
        params["mailto"] = config.email
    response = session.get(url, params=params, timeout=(15, 45))
    if response.status_code == 404:
        return None
    response.raise_for_status()
    data = response.json()
    data["literature_source"] = SOURCE_OPENALEX
    data["source_record_id"] = data.get("id")
    return data


class LandingPdfLinkParser(HTMLParser):
    """Extract likely PDF links from an OA landing page."""

    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.candidates: list[PdfCandidate] = []
        self._anchor_href: str | None = None
        self._anchor_text: list[str] = []
        self._script_type: str | None = None
        self._script_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {name.casefold(): value or "" for name, value in attrs}
        tag_name = tag.casefold()
        name = values.get("name", "").casefold()
        prop = values.get("property", "").casefold()
        rel = values.get("rel", "").casefold()
        content = values.get("content", "")
        href = values.get("href", "")
        link_type = values.get("type", "").casefold()

        if tag_name == "meta" and (name == "citation_pdf_url" or prop == "citation_pdf_url"):
            self._append(content, "landing_page_meta")
        if tag_name == "meta" and name == "dc.identifier" and ".pdf" in content.casefold():
            self._append(content, "landing_page_meta")
        if tag_name == "link" and "alternate" in rel and "application/pdf" in link_type:
            self._append(href, "landing_page_meta")
        if tag_name == "link" and "pdf" in link_type:
            self._append(href, "landing_page_meta")
        if tag_name in {"iframe", "embed", "object"}:
            embedded_url = values.get("src") or values.get("data")
            embedded_absolute_url = urljoin(self.base_url, html.unescape(str(embedded_url or "").strip()))
            if "pdf" in link_type or looks_like_pdf_url(embedded_absolute_url):
                self._append(embedded_url, "landing_page_anchor")
        if tag_name == "a":
            self._anchor_href = href
            self._anchor_text = [
                values.get("title", ""),
                values.get("aria-label", ""),
            ]
            if looks_like_pdf_url(href):
                self._append(href, "landing_page_anchor")
        if tag_name == "script":
            self._script_type = link_type
            self._script_text = []

    def handle_data(self, data: str) -> None:
        if self._anchor_href is not None:
            self._anchor_text.append(data)
        if self._script_type and "ld+json" in self._script_type:
            self._script_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag_name = tag.casefold()
        if tag_name == "a" and self._anchor_href is not None:
            text = " ".join(self._anchor_text).casefold()
            if any(label in text for label in ("pdf", "download pdf", "full text pdf", "article pdf")):
                self._append(self._anchor_href, "landing_page_anchor")
            self._anchor_href = None
            self._anchor_text = []
        if tag_name == "script" and self._script_type and "ld+json" in self._script_type:
            extract_jsonld_pdf_candidates(self.base_url, "\n".join(self._script_text), self.candidates)
            self._script_type = None
            self._script_text = []

    def _append(self, value: str | None, candidate_source: str) -> None:
        if not value:
            return
        append_pdf_candidate(
            self.candidates,
            urljoin(self.base_url, html.unescape(str(value).strip())),
            candidate_source,
            include_publisher_rules=False,
        )


def extract_jsonld_pdf_candidates(base_url: str, json_text: str, candidates: list[PdfCandidate]) -> None:
    """Extract JSON-LD contentUrl PDF references."""
    try:
        data = json.loads(html.unescape(json_text))
    except (TypeError, ValueError):
        return

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key in {"contentUrl", "associatedMedia"}:
                    if isinstance(child, str):
                        append_pdf_candidate(candidates, urljoin(base_url, child), "landing_page_meta", include_publisher_rules=False)
                    else:
                        walk(child)
                elif key == "encoding":
                    walk(child)
                else:
                    walk(child)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(data)


def extract_pdf_candidate_details_from_html(base_url: str, html_text: str) -> list[PdfCandidate]:
    """Extract PDF-like URLs with provenance from landing-page metadata and links."""
    parser = LandingPdfLinkParser(base_url)
    html_text = str(html_text or "")[:HTML_LANDING_PAGE_MAX_BYTES]
    try:
        parser.feed(html_text)
    except Exception:
        logging.debug("Landing page HTML parsing failed: %s", base_url, exc_info=True)

    candidates = list(parser.candidates)
    for match in re.finditer(r'"(?:contentUrl)"\s*:\s*"([^"]+)"', html_text, flags=re.IGNORECASE):
        append_pdf_candidate(candidates, urljoin(base_url, html.unescape(match.group(1))), "landing_page_meta", include_publisher_rules=False)
    for match in re.finditer(r"citation_pdf_url[^>]+content=['\"]([^'\"]+)['\"]", html_text, flags=re.IGNORECASE):
        append_pdf_candidate(candidates, urljoin(base_url, html.unescape(match.group(1))), "landing_page_meta", include_publisher_rules=False)

    return unique_pdf_candidate_details(candidates)


def extract_pdf_candidates_from_html(base_url: str, html_text: str) -> list[str]:
    """Extract legal PDF URLs from landing-page metadata and links."""
    return candidate_details_to_urls(extract_pdf_candidate_details_from_html(base_url, html_text))


def extract_pdf_urls_from_landing_html(base_url: str, html_text: str) -> list[str]:
    """Backward-compatible alias for landing page PDF extraction."""
    return extract_pdf_candidates_from_html(base_url, html_text)


def landing_page_urls_for_record(record: dict[str, Any], unpaywall: dict[str, Any] | None) -> list[str]:
    """Collect OA landing pages that may advertise PDF metadata."""
    if not is_known_oa_record(record, unpaywall):
        return []

    open_access = record.get("open_access") or {}
    primary_location = record.get("primary_location") or {}
    best_oa_location = record.get("best_oa_location") or {}
    urls: list[str | None] = [
        primary_location.get("landing_page_url") if isinstance(primary_location, dict) else None,
        best_oa_location.get("landing_page_url") if isinstance(best_oa_location, dict) else None,
        open_access.get("oa_url") if isinstance(open_access, dict) else None,
        record.get("landing_url"),
        record.get("source_url"),
        record.get("url"),
    ]
    doi = normalize_doi(record.get("doi") or record.get("normalized_doi"))
    if doi:
        urls.append(f"https://doi.org/{doi}")
    if unpaywall:
        urls.append(unpaywall.get("landing_url"))
        urls.extend(unpaywall.get("landing_urls") or [])
        best = unpaywall.get("best_oa_location") or {}
        if isinstance(best, dict):
            urls.append(best.get("url"))
        for location in unpaywall.get("oa_locations") or []:
            if isinstance(location, dict):
                urls.append(location.get("url"))

    return [
        url
        for url in unique_candidate_urls(urls)
        if not looks_like_pdf_url(url) and not is_shadow_library_url(url)
    ]


def resolve_landing_page_pdf_candidates(
    record: dict[str, Any],
    unpaywall: dict[str, Any] | None,
    session: requests.Session,
    config: CrawlConfig,
) -> list[str]:
    """Fetch OA landing pages and extract advertised PDF URLs."""
    return candidate_details_to_urls(resolve_landing_page_pdf_candidate_details(record, unpaywall, session, config))


def resolve_landing_page_pdf_candidate_details(
    record: dict[str, Any],
    unpaywall: dict[str, Any] | None,
    session: requests.Session,
    config: CrawlConfig,
    stats: CrawlStats | None = None,
) -> list[PdfCandidate]:
    """Fetch OA landing pages and extract advertised PDF candidates with provenance."""
    get = getattr(session, "get", None)
    if not callable(get):
        return []

    candidates: list[PdfCandidate] = []
    for landing_url in landing_page_urls_for_record(record, unpaywall)[:4]:
        if stop_requested(config):
            return unique_pdf_candidate_details(candidates)
        emit_pdf_progress(
            config,
            stats,
            "pdf_landing_page",
            f"正在解析开放获取页面：{host_label(landing_url)}",
            f"Resolving OA landing page: {host_label(landing_url)}",
            detail=landing_url,
        )
        try:
            response = get(landing_url, timeout=PDF_LANDING_TIMEOUT, allow_redirects=True)
        except (requests.RequestException, TypeError):
            logging.debug("Could not fetch OA landing page: %s", landing_url, exc_info=True)
            continue
        status_code = getattr(response, "status_code", 200)
        if status_code and (status_code < 200 or status_code >= 400):
            continue
        headers = getattr(response, "headers", {}) or {}
        content_type = str(headers.get("content-type") or headers.get("Content-Type") or "").casefold()
        if content_type and not any(token in content_type for token in ("text/html", "application/xhtml", "text/plain")):
            continue
        text = getattr(response, "text", "")
        if not text and getattr(response, "content", None):
            text = response.content[:HTML_LANDING_PAGE_MAX_BYTES].decode("utf-8", errors="ignore")
        final_url = normalize_candidate_url(getattr(response, "url", None)) or landing_url
        for derived_url in candidate_urls_from_landing_url(final_url):
            append_pdf_candidate(candidates, derived_url, "publisher_rule", include_publisher_rules=False)
        if text:
            candidates.extend(extract_pdf_candidate_details_from_html(final_url, str(text)))
    return unique_pdf_candidate_details(candidates)


def semantic_scholar_lookup_id(record: dict[str, Any]) -> str | None:
    """Return a Semantic Scholar Graph API paper ID for stable OA lookup."""
    doi = normalize_doi(record.get("doi") or record.get("normalized_doi"))
    if doi:
        return f"DOI:{doi}"
    arxiv_id = normalize_arxiv_id(
        record.get("arxiv_id")
        or record.get("source_record_id")
        or record.get("id")
        or record.get("url")
    )
    if arxiv_id:
        return f"ARXIV:{arxiv_id}"
    return None

def fetch_semantic_scholar_pdf_candidates(
    session: requests.Session,
    record: dict[str, Any],
    config: CrawlConfig,
    stats: CrawlStats | None = None,
) -> list[str]:
    """Resolve legal OA PDFs through Semantic Scholar openAccessPdf metadata."""
    paper_id = semantic_scholar_lookup_id(record)
    get = getattr(session, "get", None)
    if not paper_id or not callable(get):
        return []
    if stop_requested(config):
        return []
    headers: dict[str, str] = {}
    api_key = os.environ.get("SEMANTIC_SCHOLAR_API_KEY")
    if api_key:
        headers["x-api-key"] = api_key
    elif config.request_delay > 0:
        if sleep_or_stop(min(config.request_delay, 1.0), config):
            return []
    emit_pdf_progress(
        config,
        stats,
        "pdf_semantic_scholar",
        "正在补查 Semantic Scholar 开放 PDF",
        "Checking Semantic Scholar open PDF metadata",
        detail=paper_id,
    )
    try:
        kwargs: dict[str, Any] = {
            "params": {"fields": "paperId,title,isOpenAccess,openAccessPdf,externalIds,url"},
            "timeout": PDF_API_TIMEOUT,
        }
        if headers:
            kwargs["headers"] = headers
        response = get(
            f"{SEMANTIC_SCHOLAR_PAPER_URL}/{quote(paper_id, safe=':')}",
            **kwargs,
        )
    except (requests.RequestException, TypeError):
        logging.debug("Semantic Scholar OA lookup failed: %s", paper_id, exc_info=True)
        return []

    status_code = getattr(response, "status_code", 200)
    if status_code == 404 or status_code == 429:
        return []
    if status_code and (status_code < 200 or status_code >= 400):
        return []
    try:
        data = response.json()
    except Exception:
        return []
    if not isinstance(data, dict) or data.get("isOpenAccess") is not True:
        return []
    open_pdf = data.get("openAccessPdf") if isinstance(data, dict) else None
    url = open_pdf.get("url") if isinstance(open_pdf, dict) else None
    return [
        candidate
        for candidate in unique_candidate_urls([url])
        if looks_like_pdf_url(candidate) and not is_shadow_library_url(candidate)
    ]


def resolve_semantic_scholar_pdf_candidates(
    record: dict[str, Any],
    session: requests.Session,
    config: CrawlConfig,
) -> list[str]:
    """Backward-compatible Semantic Scholar OA PDF resolver."""
    return fetch_semantic_scholar_pdf_candidates(session, record, config)


def iter_pdf_candidates(
    item: dict[str, Any],
    unpaywall: dict[str, Any] | None,
) -> list[str]:
    """Return legal OA PDF candidates in stable priority order."""
    return candidate_details_to_urls(iter_pdf_candidate_details(item, unpaywall))


def iter_pdf_candidate_details(
    item: dict[str, Any],
    unpaywall: dict[str, Any] | None,
) -> list[PdfCandidate]:
    """Return legal OA PDF candidates with provenance in stable priority order."""
    open_access = item.get("open_access") or {}
    primary_location = item.get("primary_location") or {}
    best_oa_location = item.get("best_oa_location") or {}
    is_oa_record = is_known_oa_record(item, unpaywall)
    direct_candidates: list[PdfCandidate] = []
    candidates: list[PdfCandidate] = []
    publisher_candidates: list[PdfCandidate] = []

    add_arxiv_candidate_details(candidates, item)
    add_openalex_content_api_candidate(candidates, item)

    append_pdf_candidate(direct_candidates, item.get("pdf_url"), record_direct_pdf_source(item), include_publisher_rules=False)
    for url in item.get("pdf_candidates") or []:
        append_pdf_candidate(direct_candidates, url, record_direct_pdf_source(item), include_publisher_rules=False)

    add_record_location_candidate_details(direct_candidates, primary_location, item)
    add_record_location_candidate_details(direct_candidates, best_oa_location, item)
    for location in item.get("locations") or []:
        add_record_location_candidate_details(direct_candidates, location, item)

    if is_oa_record:
        append_pdf_candidate(direct_candidates, open_access.get("oa_url"), record_landing_source(item), include_publisher_rules=False)

    if unpaywall:
        add_unpaywall_location_candidate_details(direct_candidates, unpaywall.get("best_oa_location"))
        for location in unpaywall.get("oa_locations") or []:
            add_unpaywall_location_candidate_details(direct_candidates, location)
        append_pdf_candidate(direct_candidates, unpaywall.get("pdf_url"), "unpaywall_url_for_pdf", include_publisher_rules=False)
        for pdf_url in unpaywall.get("pdf_urls") or []:
            append_pdf_candidate(direct_candidates, pdf_url, "unpaywall_url_for_pdf", include_publisher_rules=False)

    candidates.extend(direct_candidates)
    add_pmc_direct_candidate_details(candidates, item)
    add_europe_pmc_candidate_details(candidates, item)
    add_doaj_candidate_details(candidates, item)

    if is_oa_record:
        for landing_url in (
            primary_location.get("landing_page_url"),
            best_oa_location.get("landing_page_url"),
        ):
            for derived_url in candidate_urls_from_landing_url(landing_url):
                append_pdf_candidate(publisher_candidates, derived_url, "publisher_rule", include_publisher_rules=False)
        for key in ("source_url", "url", "landing_url", "download_source_url"):
            for derived_url in candidate_urls_from_landing_url(item.get(key)):
                append_pdf_candidate(publisher_candidates, derived_url, "publisher_rule", include_publisher_rules=False)
    if unpaywall:
        for landing_url in unpaywall.get("landing_urls") or []:
            for derived_url in candidate_urls_from_landing_url(landing_url):
                append_pdf_candidate(publisher_candidates, derived_url, "publisher_rule", include_publisher_rules=False)

    candidates.extend(publisher_candidates)
    return prioritize_pdf_candidate_details(candidates)


def verify_pdf_url_with_head(
    session: requests.Session,
    url: str,
    config: CrawlConfig,
    stats: CrawlStats | None = None,
) -> tuple[bool, str | None]:
    """Docstring."""
    if is_shadow_library_url(url):
        return False, "shadow_library"
    if not looks_like_pdf_url(url):
        return False, "not_pdf"
    if stop_requested(config):
        return False, "stopped"

    head = getattr(session, "head", None)
    if not callable(head):
        return True, None

    emit_pdf_progress(
        config,
        stats,
        "pdf_head_check",
        f"正在检查 PDF 候选：{host_label(url)}",
        f"Checking PDF candidate: {host_label(url)}",
        detail=url,
    )
    try:
        response = head(url, timeout=PDF_HEAD_TIMEOUT, allow_redirects=True)
    except requests.RequestException:
        # Some publishers reject HEAD while serving the PDF through GET. Let the
        # streamed download validate content type, bytes, and PDF structure.
        return True, "head_unavailable"

    status_code = getattr(response, "status_code", None)
    if status_code in {401, 402, 403}:
        # Some OA hosts block HEAD for bot/access-control reasons while serving
        # the PDF through GET. Let the streamed GET classify real 401/403/login
        # responses as blocked_or_login.
        return True, "head_blocked_or_login"
    if status_code in {405, 429}:
        return True, None
    if status_code and (status_code < 200 or status_code >= 400):
        return False, "request_failed"

    headers = getattr(response, "headers", {}) or {}
    content_type = str(headers.get("content-type") or headers.get("Content-Type") or "").casefold()
    if "application/pdf" in content_type or content_type.startswith("application/octet-stream"):
        return True, None
    if any(token in content_type for token in ("text/html", "image/", "application/xml", "text/xml")):
        return False, "not_pdf"
    return True, None


def looks_like_blocked_or_login_content(content_type: str, first_chunk: bytes) -> bool:
    """Detect common HTML login, subscription, and access-denied responses."""
    lowered_type = content_type.casefold()
    if "text/html" not in lowered_type and "application/xhtml" not in lowered_type:
        return False
    sample = first_chunk[:8192].decode("utf-8", errors="ignore").casefold()
    blocked_tokens = (
        "login",
        "log in",
        "sign in",
        "subscribe",
        "subscription",
        "purchase",
        "access denied",
        "institutional access",
        "captcha",
        "cloudflare",
        "cf-browser-verification",
        "checking your browser",
        "paywall",
    )
    return any(token in sample for token in blocked_tokens)


def head_rejection_allows_get_sniff(reason: str | None) -> bool:
    """Return whether a HEAD rejection is weak enough to verify with GET."""
    return reason in {"not_pdf", "head_unavailable", "head_blocked_or_login"}


def resolve_open_access_pdf(
    record: dict[str, Any],
    session: requests.Session,
    config: CrawlConfig,
    stats: CrawlStats | None = None,
) -> PdfResolution:
    """Docstring."""
    unpaywall = record.get("unpaywall")
    unpaywall_data = unpaywall if isinstance(unpaywall, dict) else None
    candidate_details = iter_pdf_candidate_details(record, unpaywall_data)
    if not candidate_details:
        candidate_details = [
            PdfCandidate(url, "semantic_scholar_openAccessPdf")
            for url in fetch_semantic_scholar_pdf_candidates(session, record, config, stats)
        ]
    if not candidate_details:
        candidate_details = resolve_landing_page_pdf_candidate_details(record, unpaywall_data, session, config, stats)
    candidates = candidate_details_to_urls(candidate_details)
    metadata_details = candidate_details_for_metadata(candidate_details)
    if not candidates:
        return PdfResolution(None, [], "no_oa_pdf" if config.oa_only else "no_candidate", [])

    emit_pdf_progress(
        config,
        stats,
        "pdf_candidates",
        f"找到 {len(candidates)} 个合法 OA PDF 候选，开始校验",
        f"Found {len(candidates)} legal OA PDF candidate(s); verifying",
        detail=str(len(candidates)),
    )
    last_reason: str | None = None
    rejection_reasons: dict[str, str] = {}
    for url in candidates:
        if stop_requested(config):
            return PdfResolution(None, candidates, "stopped", metadata_details, rejection_reasons)
        ok, reason = verify_pdf_url_with_head(session, url, config, stats)
        if ok:
            return PdfResolution(url, candidates, None, metadata_details, rejection_reasons)
        last_reason = reason
        if reason:
            rejection_reasons[url] = reason
        logging.debug("Rejected OA PDF candidate before download: %s | %s", reason, url)

    api_candidate_details = [
        PdfCandidate(url, "semantic_scholar_openAccessPdf")
        for url in fetch_semantic_scholar_pdf_candidates(session, record, config, stats)
        if url not in candidates
    ]
    for candidate in api_candidate_details:
        candidate_details.append(candidate)
        candidates.append(candidate.url)
        metadata_details = candidate_details_for_metadata(candidate_details)
        url = candidate.url
        if stop_requested(config):
            return PdfResolution(None, candidates, "stopped", metadata_details, rejection_reasons)
        ok, reason = verify_pdf_url_with_head(session, url, config, stats)
        if ok:
            return PdfResolution(url, candidates, None, metadata_details, rejection_reasons)
        last_reason = reason
        if reason:
            rejection_reasons[url] = reason
        logging.debug("Rejected Semantic Scholar PDF candidate before download: %s | %s", reason, url)

    landing_candidate_details = [
        candidate
        for candidate in resolve_landing_page_pdf_candidate_details(record, unpaywall_data, session, config, stats)
        if candidate.url not in candidates
    ]
    for candidate in landing_candidate_details:
        candidate_details.append(candidate)
        candidates.append(candidate.url)
        metadata_details = candidate_details_for_metadata(candidate_details)
        url = candidate.url
        if stop_requested(config):
            return PdfResolution(None, candidates, "stopped", metadata_details, rejection_reasons)
        ok, reason = verify_pdf_url_with_head(session, url, config, stats)
        if ok:
            return PdfResolution(url, candidates, None, metadata_details, rejection_reasons)
        last_reason = reason
        if reason:
            rejection_reasons[url] = reason
        logging.debug("Rejected landing-page PDF candidate before download: %s | %s", reason, url)

    return PdfResolution(None, candidates, last_reason or "not_pdf", metadata_details, rejection_reasons)


def validate_existing_pdf(path: Path, min_pdf_bytes: int) -> bool:
    """Docstring."""
    try:
        if not path.exists() or path.stat().st_size < min_pdf_bytes:
            return False
        with path.open("rb") as fin:
            if b"%PDF-" not in fin.read(4096):
                return False
            fin.seek(max(0, path.stat().st_size - 4096))
            if b"%%EOF" not in fin.read():
                return False
        try:
            import fitz
        except ImportError:
            return True
        with fitz.open(path) as document:
            return bool(document.is_pdf and document.page_count > 0)
    except (OSError, RuntimeError, ValueError):
        return False


def is_arxiv_pdf_url(url: str | None) -> bool:
    """Return whether a URL targets arXiv's PDF endpoint."""
    normalized = normalize_candidate_url(url)
    if not normalized:
        return False
    parsed = urlparse(normalized)
    return parsed.netloc.endswith("arxiv.org") and parsed.path.startswith("/pdf/")


def enforce_arxiv_download_delay(config: CrawlConfig) -> bool:
    """Keep arXiv PDF downloads single-paced with at least three seconds between GETs."""
    now = time.monotonic()
    last = getattr(enforce_arxiv_download_delay, "_last_download_at", None)
    if last is not None:
        remaining = ARXIV_MIN_DOWNLOAD_INTERVAL - (now - float(last))
        if remaining > 0 and sleep_or_stop(remaining, config):
            return True
    setattr(enforce_arxiv_download_delay, "_last_download_at", time.monotonic())
    return stop_requested(config)


def response_content_type(response: Any) -> str:
    """Return a response content type independent of header casing."""
    headers = getattr(response, "headers", {}) or {}
    return str(headers.get("content-type") or headers.get("Content-Type") or "").lower()


def response_content_disposition(response: Any) -> str:
    """Return a response content disposition independent of header casing."""
    headers = getattr(response, "headers", {}) or {}
    return str(headers.get("content-disposition") or headers.get("Content-Disposition") or "").lower()


def content_disposition_names_pdf(content_disposition: str) -> bool:
    """Return whether Content-Disposition explicitly names a PDF attachment."""
    return bool(re.search(r"filename\*?=[^;]*\.pdf(?:[\"']|\s|;|$)", content_disposition.casefold()))


def limited_html_from_response(first_chunk: bytes, chunks: Any) -> str:
    """Read up to the landing-page HTML cap from a streamed response."""
    body = bytearray(first_chunk[:HTML_LANDING_PAGE_MAX_BYTES])
    for chunk in chunks:
        if not chunk:
            continue
        remaining = HTML_LANDING_PAGE_MAX_BYTES - len(body)
        if remaining <= 0:
            break
        body.extend(chunk[:remaining])
        if len(body) >= HTML_LANDING_PAGE_MAX_BYTES:
            break
    return bytes(body).decode("utf-8", errors="ignore")


def download_pdf(
    session: requests.Session,
    pdf_url: str,
    doi_or_url: str,
    config: CrawlConfig,
    out_dir: Path | None = None,
    candidate_source: str | None = None,
    stats: CrawlStats | None = None,
) -> DownloadResult:
    """Docstring."""
    if stop_requested(config):
        return DownloadResult(None, "stopped", pdf_url, candidate_source=candidate_source)
    if is_shadow_library_url(pdf_url):
        return DownloadResult(None, "failed", pdf_url, "shadow_library", candidate_source=candidate_source, failure_reason="shadow_library")
    if is_arxiv_pdf_url(pdf_url) and enforce_arxiv_download_delay(config):
        return DownloadResult(None, "stopped", pdf_url, candidate_source=candidate_source)

    target_dir = out_dir or config.out_dir
    target_dir.mkdir(parents=True, exist_ok=True)
    path = path_for_pdf(doi_or_url, target_dir)
    if validate_existing_pdf(path, config.min_pdf_bytes):
        return DownloadResult(
            path=str(path),
            status="already_exists",
            source_url=pdf_url,
            size_bytes=path.stat().st_size,
            candidate_source=candidate_source,
        )

    tmp_path = path.with_suffix(".part")
    try:
        last_result: DownloadResult | None = None
        for attempt in range(3):
            if stop_requested(config):
                return DownloadResult(None, "stopped", pdf_url, candidate_source=candidate_source)
            emit_pdf_progress(
                config,
                stats,
                "pdf_get",
                f"正在下载 PDF 候选：{host_label(pdf_url)}（第 {attempt + 1} 次）",
                f"Downloading PDF candidate from {host_label(pdf_url)} (attempt {attempt + 1})",
                detail=pdf_url,
            )
            with session.get(
                pdf_url,
                timeout=PDF_DOWNLOAD_TIMEOUT,
                stream=True,
                allow_redirects=True,
            ) as response:
                status_code = getattr(response, "status_code", None)
                content_type = response_content_type(response)
                content_disposition = response_content_disposition(response)
                final_url = normalize_candidate_url(getattr(response, "url", None)) or pdf_url
                if status_code in {401, 402, 403}:
                    return DownloadResult(None, "blocked_or_login", pdf_url, f"http_{status_code}", candidate_source=candidate_source, http_status=status_code, content_type=content_type, final_url=final_url, failure_reason="blocked_or_login")
                if status_code == 429:
                    retry_after = getattr(response, "headers", {}).get("Retry-After") if getattr(response, "headers", None) else None
                    try:
                        delay = float(retry_after) if retry_after else 2 ** attempt
                    except (TypeError, ValueError):
                        delay = 2 ** attempt
                    last_result = DownloadResult(None, "request_error", pdf_url, f"http_{status_code}", candidate_source=candidate_source, http_status=status_code, content_type=content_type, final_url=final_url, failure_reason="rate_limited")
                    emit_pdf_progress(
                        config,
                        stats,
                        "pdf_rate_limited",
                        f"PDF 来源限流，稍后重试：{host_label(pdf_url)}",
                        f"PDF host rate-limited the request; retrying: {host_label(pdf_url)}",
                        detail=pdf_url,
                    )
                    if attempt < 2 and not sleep_or_stop(delay, config):
                        continue
                    return last_result
                if status_code not in {200, 206}:
                    return DownloadResult(None, "request_error", pdf_url, f"http_{status_code}", candidate_source=candidate_source, http_status=status_code, content_type=content_type, final_url=final_url, failure_reason=f"http_{status_code}")

                chunks = response.iter_content(chunk_size=PDF_CHUNK_SIZE)
                first_chunk = next(chunks, b"")
                first_4kb = first_chunk[:4096]
                looks_like_html_body = (
                    first_chunk.lstrip().lower().startswith(b"<!doctype html")
                    or first_chunk.lstrip().lower().startswith(b"<html")
                )
                if looks_like_html_body:
                    if looks_like_blocked_or_login_content(content_type or "text/html", first_chunk):
                        return DownloadResult(None, "blocked_or_login", pdf_url, content_type or "html_login", candidate_source=candidate_source, http_status=status_code, content_type=content_type, final_url=final_url, failure_reason="blocked_or_login")
                    html_text = limited_html_from_response(first_chunk, chunks)
                    discovered = extract_pdf_candidates_from_html(final_url, html_text)
                    if discovered:
                        emit_pdf_progress(
                            config,
                            stats,
                            "pdf_discovered",
                            f"页面中发现新的 PDF 链接：{len(discovered)} 个",
                            f"Discovered {len(discovered)} PDF link(s) in the landing page",
                            detail=final_url,
                        )
                    return DownloadResult(None, "not_pdf", pdf_url, content_type or "html", candidate_source=candidate_source, http_status=status_code, content_type=content_type, final_url=final_url, failure_reason="html_landing_page", discovered_candidates=discovered)
                is_pdf_response = (
                    b"%PDF-" in first_4kb
                    or "pdf" in content_type
                    or content_type.startswith("application/octet-stream")
                    or content_disposition_names_pdf(content_disposition)
                )
                if not is_pdf_response:
                    if looks_like_blocked_or_login_content(content_type, first_chunk):
                        return DownloadResult(None, "blocked_or_login", pdf_url, content_type or "html_login", candidate_source=candidate_source, http_status=status_code, content_type=content_type, final_url=final_url, failure_reason="blocked_or_login")
                    if "text/html" in content_type or "application/xhtml" in content_type:
                        html_text = limited_html_from_response(first_chunk, chunks)
                        discovered = extract_pdf_candidates_from_html(final_url, html_text)
                        if discovered:
                            emit_pdf_progress(
                                config,
                                stats,
                                "pdf_discovered",
                                f"页面中发现新的 PDF 链接：{len(discovered)} 个",
                                f"Discovered {len(discovered)} PDF link(s) in the landing page",
                                detail=final_url,
                            )
                        return DownloadResult(None, "not_pdf", pdf_url, content_type or "html", candidate_source=candidate_source, http_status=status_code, content_type=content_type, final_url=final_url, failure_reason="html_landing_page", discovered_candidates=discovered)
                    return DownloadResult(None, "not_pdf", pdf_url, content_type or "missing_content_type", candidate_source=candidate_source, http_status=status_code, content_type=content_type, final_url=final_url, failure_reason="not_pdf")

                with tmp_path.open("wb") as fout:
                    if first_chunk:
                        fout.write(first_chunk)
                    for chunk in chunks:
                        if stop_requested(config):
                            return DownloadResult(None, "stopped", pdf_url, candidate_source=candidate_source, http_status=status_code, content_type=content_type, final_url=final_url, failure_reason="stopped")
                        if chunk:
                            fout.write(chunk)
                break
        else:
            return last_result or DownloadResult(None, "request_error", pdf_url, candidate_source=candidate_source, failure_reason="request_error")

        size = tmp_path.stat().st_size
        if size < config.min_pdf_bytes:
            tmp_path.unlink(missing_ok=True)
            return DownloadResult(None, "too_small", pdf_url, f"{size}_bytes", candidate_source=candidate_source, failure_reason="too_small")

        if not validate_existing_pdf(tmp_path, config.min_pdf_bytes):
            tmp_path.unlink(missing_ok=True)
            return DownloadResult(None, "invalid_pdf", pdf_url, candidate_source=candidate_source, failure_reason="invalid_pdf")

        tmp_path.replace(path)
        return DownloadResult(str(path), "downloaded", pdf_url, size_bytes=size, candidate_source=candidate_source)

    except requests.RequestException as exc:
        return DownloadResult(None, "request_error", pdf_url, str(exc), candidate_source=candidate_source, failure_reason="request_error")
    except OSError as exc:
        return DownloadResult(None, "file_error", pdf_url, str(exc), candidate_source=candidate_source, failure_reason="file_error")
    finally:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)


def download_first_available_pdf(
    session: requests.Session,
    item: dict[str, Any],
    unpaywall: dict[str, Any] | None,
    doi_or_url: str,
    config: CrawlConfig,
    out_dir: Path | None = None,
    stats: CrawlStats | None = None,
) -> tuple[DownloadResult, list[str]]:
    """Docstring."""
    record = dict(item)
    if unpaywall:
        record["unpaywall"] = unpaywall
    resolution = resolve_open_access_pdf(record, session, config, stats)
    candidate_details = [
        PdfCandidate(detail["url"], detail["candidate_source"])
        for detail in resolution.candidate_details
        if detail.get("url") and detail.get("candidate_source")
    ]
    if not candidate_details:
        candidate_details = [PdfCandidate(url, "publisher_rule") for url in resolution.candidates]
    candidates = candidate_details_to_urls(candidate_details)
    allow_get_sniff = bool(candidates and resolution.reason == "not_pdf")
    if not resolution.url and not allow_get_sniff:
        return DownloadResult(None, "failed", reason=resolution.reason), candidates

    start_index = candidates.index(resolution.url) if resolution.url else 0
    if resolution.url:
        resolved_index = candidates.index(resolution.url)
        if any(
            head_rejection_allows_get_sniff(resolution.candidate_rejection_reasons.get(url))
            for url in candidates[:resolved_index]
        ):
            start_index = 0
            allow_get_sniff = True
    last_result = DownloadResult(None, "failed", reason=resolution.reason)
    index = start_index
    tried_urls: set[str] = set()
    semantic_expanded = False
    landing_expanded = False
    while True:
        while index < len(candidates):
            pdf_url = candidates[index]
            candidate_source = candidate_source_for_url(candidate_details, pdf_url)
            index += 1
            normalized_pdf_url = normalize_candidate_url(pdf_url) or pdf_url
            if normalized_pdf_url in tried_urls:
                continue
            tried_urls.add(normalized_pdf_url)
            if stop_requested(config):
                return DownloadResult(None, "stopped"), candidates
            head_rejection_reason = resolution.candidate_rejection_reasons.get(pdf_url)
            should_sniff_after_head = head_rejection_allows_get_sniff(head_rejection_reason)
            if pdf_url != resolution.url and not allow_get_sniff and not should_sniff_after_head:
                ok, reason = verify_pdf_url_with_head(session, pdf_url, config, stats)
                if not ok:
                    if head_rejection_allows_get_sniff(reason):
                        should_sniff_after_head = True
                    else:
                        last_result = DownloadResult(None, "failed", pdf_url, reason, candidate_source=candidate_source, failure_reason=reason)
                        emit_pdf_progress(
                            config,
                            stats,
                            "pdf_candidate_rejected",
                            f"跳过不可用 PDF 候选：{reason or 'unknown'}",
                            f"Skipped unusable PDF candidate: {reason or 'unknown'}",
                            detail=pdf_url,
                        )
                        continue
            if stats is not None:
                stats.pdf_download_attempted += 1
            emit_pdf_progress(
                config,
                stats,
                "pdf_candidate_download",
                f"尝试 PDF 候选 {index}/{len(candidates)}：{host_label(pdf_url)}",
                f"Trying PDF candidate {index}/{len(candidates)}: {host_label(pdf_url)}",
                detail=pdf_url,
            )
            result = download_pdf(session, pdf_url, doi_or_url, config, out_dir, candidate_source, stats)
            if result.path:
                return result, candidates
            for discovered_url in result.discovered_candidates:
                normalized = normalize_candidate_url(discovered_url)
                if not normalized or normalized in candidates or is_shadow_library_url(normalized) or not looks_like_pdf_url(normalized):
                    continue
                candidate_details.append(PdfCandidate(normalized, "landing_page_meta"))
            candidate_details = prioritize_pdf_candidate_details(candidate_details)
            candidates = candidate_details_to_urls(candidate_details)
            index = 0
            allow_get_sniff = allow_get_sniff or bool(result.discovered_candidates)
            last_result = result
            emit_pdf_progress(
                config,
                stats,
                "pdf_candidate_failed",
                f"PDF 候选失败，继续尝试下一个：{result.reason or result.status}",
                f"PDF candidate failed; trying the next one: {result.reason or result.status}",
                detail=pdf_url,
            )
            logging.debug("PDF candidate failed: %s | %s | %s", result.status, result.reason, pdf_url)

        if not semantic_expanded:
            semantic_expanded = True
            before = len(candidate_details)
            add_unique_pdf_candidates(
                candidate_details,
                [
                    PdfCandidate(url, "semantic_scholar_openAccessPdf")
                    for url in fetch_semantic_scholar_pdf_candidates(session, record, config, stats)
                ],
            )
            candidates = candidate_details_to_urls(candidate_details)
            if len(candidate_details) > before:
                allow_get_sniff = True
                index = 0
                continue

        if not landing_expanded:
            landing_expanded = True
            before = len(candidate_details)
            add_unique_pdf_candidates(
                candidate_details,
                resolve_landing_page_pdf_candidate_details(record, unpaywall, session, config, stats),
            )
            candidates = candidate_details_to_urls(candidate_details)
            if len(candidate_details) > before:
                allow_get_sniff = True
                index = 0
                continue

        break

    return last_result, candidates


def fallback_pdf_paths_for_record(record: dict[str, Any], meta_path: Path, out_dir: Path) -> list[Path]:
    """Return all compatible local PDF paths that may belong to a metadata record."""
    paths = resolve_record_pdf_paths(record, meta_path)
    fallback_out_dirs = [out_dir]
    keyword = record.get("keyword")
    if keyword:
        fallback_out_dirs.insert(0, keyword_pdf_dir(str(keyword), out_dir))

    identifiers = [
        normalize_doi(record.get("doi") or record.get("normalized_doi")),
        record.get("source_record_id"),
        record.get("openalex_id") or record.get("id"),
        extract_arxiv_id(record),
    ]
    for identifier in identifiers:
        if identifier:
            paths.extend(path_for_pdf(str(identifier), folder) for folder in fallback_out_dirs)

    result: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = str(path)
        if key not in seen:
            seen.add(key)
            result.append(path)
    return result


def record_has_any_valid_pdf(record: dict[str, Any], meta_path: Path, out_dir: Path, min_pdf_bytes: int) -> bool:
    """Return whether any explicit or legacy PDF path for a record is valid."""
    return any(validate_existing_pdf(path, min_pdf_bytes) for path in fallback_pdf_paths_for_record(record, meta_path, out_dir))


def refresh_record_oa_metadata(
    record: dict[str, Any],
    session: requests.Session,
    config: CrawlConfig,
) -> dict[str, Any]:
    """Refresh OA fields from Unpaywall/OpenAlex when stable identifiers exist."""
    refreshed = dict(record)
    doi = normalize_doi(refreshed.get("doi") or refreshed.get("normalized_doi"))
    if doi:
        try:
            unpaywall = query_unpaywall(session, doi, config.email)
            if unpaywall:
                refreshed["unpaywall"] = unpaywall
        except requests.RequestException as exc:
            logging.warning("Backfill continuing without refreshed Unpaywall data: %s | %s", doi, exc)

    try:
        openalex = query_openalex_work(session, refreshed, config)
    except requests.RequestException as exc:
        logging.warning("Backfill continuing without refreshed OpenAlex data: %s | %s", record_key(refreshed), exc)
        openalex = None

    if openalex:
        for key in ("id", "doi", "primary_location", "best_oa_location", "locations", "open_access"):
            if openalex.get(key) is not None:
                refreshed[key] = openalex.get(key)
        refreshed["openalex_id"] = openalex.get("id") or refreshed.get("openalex_id")
        refreshed["source_record_id"] = refreshed.get("source_record_id") or openalex.get("id")
    return refreshed


def next_pdf_retry_attempt(record: dict[str, Any]) -> int:
    """Return the next retry attempt number for metadata append records."""
    try:
        return int(record.get("pdf_retry_attempts") or 0) + 1
    except (TypeError, ValueError):
        return 1


def backfill_download_status(
    record: dict[str, Any],
    result: DownloadResult,
    candidates: list[str],
    unpaywall: dict[str, Any] | None,
) -> str:
    """Map resolver/download results to explicit backfill status values."""
    if result.path:
        return "downloaded"
    if not candidates:
        return "no_candidate" if is_known_oa_record(record, unpaywall) else "not_open_access"
    if result.status in {
        "no_candidate",
        "not_open_access",
        "not_pdf",
        "too_small",
        "request_error",
        "blocked_or_login",
        "invalid_pdf",
        "stopped",
        "file_error",
    }:
        return result.status
    if result.reason in {"not_pdf", "blocked_or_login", "too_small", "invalid_pdf", "no_candidate", "not_open_access"}:
        return str(result.reason)
    return "request_error" if result.status == "failed" else result.status


def append_backfill_record(
    fout: TextIO,
    record: dict[str, Any],
    result: DownloadResult,
    candidates: list[str],
    status: str,
    config: CrawlConfig,
) -> None:
    """Append a metadata-compatible status update without rewriting older records."""
    updated = dict(record)
    updated["pdf_candidates"] = candidates
    updated["pdf_candidate_details"] = candidate_details_for_urls(
        candidates,
        iter_pdf_candidate_details(record, record.get("unpaywall") if isinstance(record.get("unpaywall"), dict) else None),
    )
    updated["download_status"] = status
    updated["download_reason"] = None if result.path else result.reason or status
    updated["download_source_url"] = result.source_url
    updated["resolver_version"] = PDF_RESOLVER_VERSION
    updated["last_candidate_url"] = None if result.path else result.source_url
    updated["candidate_source"] = result.candidate_source
    updated["http_status"] = result.http_status
    updated["content_type"] = result.content_type
    updated["final_url"] = result.final_url
    updated["failure_reason"] = None if result.path else result.failure_reason or result.reason or status
    updated["pdf_retry_attempts"] = next_pdf_retry_attempt(record)
    updated["last_pdf_retry_at"] = datetime.now().isoformat(timespec="seconds")
    updated["last_pdf_failure_reason"] = None if result.path else result.reason or status
    if result.path:
        updated["local_pdf_path"] = display_path(Path(result.path), config.meta_path.parent)
        updated["local_pdf_size_bytes"] = result.size_bytes
    else:
        updated["local_pdf_path"] = None
        updated["local_pdf_size_bytes"] = None
    append_jsonl_record(fout, updated)


def emit_backfill_progress(
    config: CrawlConfig,
    stats: CrawlStats,
    message: str,
    progress_callback: Callable[[Any, str], None] | None,
) -> None:
    """Emit progress for metadata PDF backfill."""
    callback = progress_callback or config.progress_callback
    if not callback:
        return
    try:
        callback(stats, message)
    except Exception:
        logging.exception("Backfill progress callback failed.")


def backfill_stop_requested(config: CrawlConfig, stop_event: Any = None) -> bool:
    """Return whether the metadata backfill should stop."""
    return bool((stop_event is not None and stop_event.is_set()) or stop_requested(config))


def backfill_missing_pdfs_from_metadata(
    config: CrawlConfig,
    progress_callback: Callable[[Any, str], None] | None = None,
    stop_event: Any = None,
) -> CrawlStats:
    """Scan existing metadata and fill missing legal OA PDFs without crawl state."""
    configure_logging(config.log_level)
    config.out_dir.mkdir(parents=True, exist_ok=True)
    config.meta_path.parent.mkdir(parents=True, exist_ok=True)

    stats = CrawlStats()
    if not config.meta_path.exists():
        logging.info("Backfill skipped; metadata file does not exist: %s", config.meta_path)
        emit_backfill_progress(
            config,
            stats,
            localized(
                config,
                "PDF 补全已跳过：元数据文件不存在。",
                "Backfill skipped: metadata file does not exist.",
                "Backfill skipped: metadata file does not exist.",
            ),
            progress_callback,
        )
        return stats

    latest_records: dict[str, dict[str, Any]] = {}
    anonymous_records: list[dict[str, Any]] = []
    with config.meta_path.open("r", encoding="utf-8") as fin:
        for line_no, line in enumerate(fin, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                logging.warning("Skipping invalid metadata JSONL line during backfill: %s", line_no)
                continue
            stats.backfill_scanned_records += 1
            key = record_key(record)
            if key:
                latest_records[key] = record
            else:
                anonymous_records.append(record)

    records = list(latest_records.values()) + anonymous_records
    stats.existing_records = len(records)
    session = build_session(config.email)
    logging.info("Backfill scanned %s metadata lines; %s latest records to inspect.", stats.backfill_scanned_records, len(records))
    emit_backfill_progress(
        config,
        stats,
        localized(
            config,
            f"PDF 补全已扫描 {stats.backfill_scanned_records} 行元数据；将检查 {len(records)} 条记录。",
            f"Backfill scanned {stats.backfill_scanned_records} metadata lines; inspecting {len(records)} records.",
            f"Backfill scanned {stats.backfill_scanned_records} metadata lines; inspecting {len(records)} records.",
        ),
        progress_callback,
    )

    try:
        with config.meta_path.open("a", encoding="utf-8") as fout:
            for record in records:
                if backfill_stop_requested(config, stop_event):
                    break
                if record_has_any_valid_pdf(record, config.meta_path, config.out_dir, config.min_pdf_bytes):
                    continue
                stats.backfill_missing_pdf_records += 1
                if not record_needs_pdf_retry(
                    record,
                    meta_path=config.meta_path,
                    min_pdf_bytes=config.min_pdf_bytes,
                ):
                    note_pdf_failure(stats, "retry_not_eligible", backfill=True)
                    continue

                stats.retried_existing_records += 1
                refreshed = refresh_record_oa_metadata(record, session, config)
                unpaywall = refreshed.get("unpaywall") if isinstance(refreshed.get("unpaywall"), dict) else None
                candidates = iter_pdf_candidates(refreshed, unpaywall)
                stats.pdf_candidates_found += len(candidates)

                doi_or_url = (
                    normalize_doi(refreshed.get("doi") or refreshed.get("normalized_doi"))
                    or refreshed.get("openalex_id")
                    or refreshed.get("source_record_id")
                    or extract_arxiv_id(refreshed)
                    or refreshed.get("title")
                    or record_key(refreshed)
                    or "metadata-backfill"
                )
                if not candidates:
                    result = DownloadResult(None, "no_candidate")
                    status = backfill_download_status(refreshed, result, candidates, unpaywall)
                    append_backfill_record(fout, refreshed, result, candidates, status, config)
                    note_pdf_failure(stats, status, backfill=True)
                    continue

                result, candidates = download_first_available_pdf(
                    session,
                    refreshed,
                    unpaywall,
                    str(doi_or_url),
                    config,
                    config.out_dir,
                    stats,
                )
                status = backfill_download_status(refreshed, result, candidates, unpaywall)
                append_backfill_record(fout, refreshed, result, candidates, status, config)
                if result.path:
                    note_pdf_download(stats, backfill=True)
                else:
                    note_pdf_failure(stats, result.reason or status, backfill=True)

                emit_backfill_progress(
                    config,
                    stats,
                    localized(
                        config,
                        (
                            f"PDF 补全：已扫描={stats.backfill_scanned_records}，"
                            f"缺失={stats.backfill_missing_pdf_records}，"
                            f"候选={stats.pdf_candidates_found}，"
                            f"已下载={stats.backfill_downloaded_pdfs}，"
                            f"失败={stats.backfill_failed_pdfs}。"
                        ),
                        (
                            f"Backfill scanned={stats.backfill_scanned_records}, "
                            f"missing={stats.backfill_missing_pdf_records}, "
                            f"candidates={stats.pdf_candidates_found}, "
                            f"downloaded={stats.backfill_downloaded_pdfs}, "
                            f"failed={stats.backfill_failed_pdfs}."
                        ),
                        (
                            f"Backfill scanned={stats.backfill_scanned_records}, "
                            f"missing={stats.backfill_missing_pdf_records}, "
                            f"candidates={stats.pdf_candidates_found}, "
                            f"downloaded={stats.backfill_downloaded_pdfs}, "
                            f"failed={stats.backfill_failed_pdfs}."
                        ),
                    ),
                    progress_callback,
                )
                if sleep_or_stop(config.request_delay, config):
                    break
    finally:
        session.close()

    logging.info(
        "Backfill summary: scanned=%s missing=%s candidates=%s attempted=%s downloaded=%s failed=%s reasons=%s",
        stats.backfill_scanned_records,
        stats.backfill_missing_pdf_records,
        stats.pdf_candidates_found,
        stats.pdf_download_attempted,
        stats.backfill_downloaded_pdfs,
        stats.backfill_failed_pdfs,
        stats.backfill_failure_reasons,
    )
    emit_backfill_progress(config, stats, format_backfill_finished_message(config, stats), progress_callback)
    return stats


def is_open_access(item: dict[str, Any], unpaywall: dict[str, Any] | None) -> bool:
    """Docstring."""
    return bool(
        (unpaywall and unpaywall.get("is_oa"))
        or (item.get("open_access") or {}).get("is_oa")
    )


def build_record(
    keyword: str,
    item: dict[str, Any],
    unpaywall: dict[str, Any] | None,
    download: DownloadResult,
    pdf_candidates: list[str],
    meta_path: Path,
    relevance_info: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Docstring."""
    doi = normalize_doi(item.get("doi"))
    local_pdf_path = None
    if download.path:
        local_pdf_path = display_path(Path(download.path), meta_path.parent)
    retry_attempts = 1 if download.status not in {"download_disabled", "not_open_access"} else 0
    if "impact_factor_unknown" not in item:
        enrich_record_with_journal_metrics(item)
    content_fields = content_fields_for_record(keyword, item, download, meta_path, relevance_info)
    record = {
        "keyword": keyword,
        "literature_source": item.get("literature_source") or SOURCE_OPENALEX,
        "source_record_id": item.get("source_record_id") or item.get("id"),
        "canonical_record_key": canonical_record_key(item),
        "openalex_id": item.get("id") if item.get("literature_source") in {None, SOURCE_OPENALEX} else None,
        "doi": item.get("doi"),
        "normalized_doi": doi,
        "title": item.get("title") or item.get("display_name"),
        "publication_date": item.get("publication_date"),
        "publication_year": item.get("publication_year"),
        "cited_by_count": item.get("cited_by_count"),
        "authors": extract_authors(item),
        "abstract": content_fields["abstract"],
        "extracted_abstract": content_fields["extracted_abstract"],
        "extracted_keywords": content_fields["extracted_keywords"],
        "content_summary": content_fields["content_summary"],
        "summary_text": content_fields["summary_text"],
        "keyword_groups": content_fields["keyword_groups"],
        "topic_tags": content_fields["topic_tags"],
        "journal_title": item.get("journal_title"),
        "journal_issns": item.get("journal_issns") or [],
        "journal_issn_l": item.get("journal_issn_l"),
        "impact_factor": item.get("impact_factor"),
        "impact_factor_year": item.get("impact_factor_year"),
        "impact_factor_source": item.get("impact_factor_source"),
        "impact_factor_metric": item.get("impact_factor_metric"),
        "impact_factor_quartile": item.get("impact_factor_quartile"),
        "impact_factor_unknown": bool(item.get("impact_factor_unknown")),
        "journal_name": item.get("journal_name") or item.get("journal_title"),
        "journal_impact_value": item.get("journal_impact_value", item.get("impact_factor")),
        "journal_impact_metric": item.get("journal_impact_metric") or item.get("impact_factor_metric"),
        "journal_impact_year": item.get("journal_impact_year", item.get("impact_factor_year")),
        "journal_metric_source": item.get("journal_metric_source") or item.get("impact_factor_source"),
        "open_access": item.get("open_access"),
        "unpaywall": unpaywall,
        "pdf_candidates": pdf_candidates,
        "pdf_candidate_details": candidate_details_for_urls(pdf_candidates, iter_pdf_candidate_details(item, unpaywall)),
        "download_status": download.status,
        "download_reason": download.reason,
        "download_source_url": download.source_url,
        "last_candidate_url": None if download.path else download.source_url,
        "candidate_source": download.candidate_source,
        "http_status": download.http_status,
        "content_type": download.content_type,
        "final_url": download.final_url,
        "failure_reason": None if download.path else download.failure_reason or download.reason or download.status,
        "local_pdf_path": local_pdf_path,
        "local_pdf_size_bytes": download.size_bytes,
        "pdf_retry_attempts": retry_attempts,
        "last_pdf_retry_at": datetime.now().isoformat(timespec="seconds") if retry_attempts else None,
        "resolver_version": PDF_RESOLVER_VERSION,
        "last_pdf_failure_reason": None if download.path else download.reason or download.status,
    }
    if relevance_info:
        record.update(relevance_info)
    return record


def should_stop(stats: CrawlStats, config: CrawlConfig) -> bool:
    """Docstring."""
    return (
        stop_requested(config)
        or (config.max_records is not None and stats.added_records >= config.max_records)
    )


def save_keyword_state(
    source: str,
    keyword: str,
    config: CrawlConfig,
    crawl_state: dict[str, CrawlStateEntry],
    next_cursor: str | None,
    completed_pages: int,
    exhausted: bool,
) -> None:
    """Docstring."""
    crawl_state[state_key(keyword, config, source)] = CrawlStateEntry(
        next_cursor=next_cursor,
        completed_pages=completed_pages,
        exhausted=exhausted,
    )
    if config.resume:
        save_crawl_state(config.state_path, crawl_state)


def all_results_already_seen(
    results: list[dict[str, Any]],
    existing_index: ExistingIndex,
    retry_missing_pdfs: bool,
) -> bool:
    """Docstring."""
    if not results:
        return False

    for item in results:
        key = record_key(item)
        canonical = canonical_record_key(item)
        if not key and not canonical:
            return False
        if key and key not in existing_index.keys:
            if not canonical or canonical not in existing_index.canonical_keys:
                return False
        if not key and canonical and canonical not in existing_index.canonical_keys:
            return False
        if retry_missing_pdfs and key in existing_index.retry_pdf_keys:
            return False
        if retry_missing_pdfs and canonical and canonical not in existing_index.downloaded_canonical_keys and key not in existing_index.downloaded_keys:
            return False
    return True


def crawl_keyword(
    session: requests.Session,
    source: str,
    keyword: str,
    existing_index: ExistingIndex,
    fout: TextIO,
    config: CrawlConfig,
    stats: CrawlStats,
    crawl_state: dict[str, CrawlStateEntry],
) -> None:
    """Docstring."""
    topic_pack = resolve_topic_pack(config, config.effective_keywords)
    configured_metric_source = str(config.journal_metric_source or "local_then_openalex").strip() or "local_then_openalex"
    metric_source = configured_metric_source if config.min_impact_factor is not None else "local_csv"
    if config.min_impact_factor is None and configured_metric_source in {"openalex", "local_then_openalex"}:
        metric_source = configured_metric_source
    journal_metric_resolver = JournalMetricResolver(
        local_csv=config.journal_metric_csv,
        source=metric_source,
        session=session,
        email=config.email,
    )
    key = state_key(keyword, config, source)
    state_entry = crawl_state.get(key, CrawlStateEntry())
    if config.resume and state_entry.exhausted:
        logging.info("Skipping exhausted source and keyword: %s | %s", source, keyword)
        emit_source_progress(
            config,
            stats,
            source,
            keyword,
            "skipped",
            f"{SOURCE_LABELS.get(source, source)} already exhausted for keyword: {keyword}",
            f"{SOURCE_LABELS.get(source, source)} already exhausted for keyword: {keyword}",
            f"{SOURCE_LABELS.get(source, source)} already exhausted for keyword: {keyword}",
        )
        return

    initial_cursor = "0" if source == SOURCE_ARXIV else "1" if source == SOURCE_DOAJ else "*"
    cursor = state_entry.next_cursor if config.resume and state_entry.next_cursor else initial_cursor
    completed_pages = state_entry.completed_pages if config.resume else 0
    if cursor != initial_cursor:
        logging.info(
            "Resuming: %s | %s | after %s completed pages",
            source,
            keyword,
            completed_pages,
        )
    source_label = SOURCE_LABELS.get(source, source)
    emit_source_progress(
        config,
        stats,
        source,
        keyword,
        "preparing",
        f"Preparing {source_label}: {keyword}",
        f"Preparing {source_label}: {keyword}",
        f"Preparing {source_label}: {keyword}",
    )

    for page in range(config.max_pages_per_keyword):
        if should_stop(stats, config):
            return

        page_no = completed_pages + page + 1
        logging.info("Searching: %s | %s | page %s", source, keyword, page_no)
        emit_source_progress(
            config,
            stats,
            source,
            keyword,
            "searching",
            f"Searching {source_label}: {keyword} page {page_no}",
            f"Searching {source_label}: {keyword} page {page_no}",
            f"Searching {source_label}: {keyword} page {page_no}",
            detail=f"page {page_no}",
        )
        data = search_literature_source(session, source, keyword, config, cursor=cursor)
        results = data.get("results", [])
        stats.fetched_items += len(results)
        stats.fetched_items_total += len(results)
        stats.fetched_by_source[source] = stats.fetched_by_source.get(source, 0) + len(results)
        cursor = data.get("meta", {}).get("next_cursor")
        journal_pack = resolve_journal_pack(config, results)
        results = sort_records_by_resolved_packs(results, topic_pack, journal_pack)
        emit_source_progress(
            config,
            stats,
            source,
            keyword,
            "fetched",
            f"Fetched {len(results)} records from {source_label}: {keyword} page {page_no}",
            f"Fetched {len(results)} records from {source_label}: {keyword} page {page_no}",
            f"Fetched {len(results)} records from {source_label}: {keyword} page {page_no}",
            detail=f"{len(results)} records",
        )

        if (
            config.fast_forward_existing_pages
            and all_results_already_seen(results, existing_index, config.retry_missing_pdfs)
        ):
            stats.skipped_duplicates += len(results)
            logging.info("Fast-forwarding already indexed page: %s | page %s", keyword, page_no)
            emit_source_progress(
                config,
                stats,
                source,
                keyword,
                "fast_forward",
                f"Fast-forwarded {source_label} already indexed page {page_no}",
                f"Fast-forwarded {source_label} already indexed page {page_no}",
                f"Fast-forwarded {source_label} already indexed page {page_no}",
                detail=f"page {page_no}",
            )
            save_keyword_state(
                source,
                keyword,
                config,
                crawl_state,
                cursor,
                page_no,
                exhausted=not bool(cursor),
            )
            if not cursor:
                break
            if sleep_or_stop(config.page_delay, config):
                return
            continue

        for item in results:
            if should_stop(stats, config):
                return

            key = record_key(item)
            if not key:
                stats.skipped_without_key += 1
                continue
            if config.strict_keyword_match:
                matched, ratio, missing = keyword_match_details(
                    keyword,
                    item,
                    config.min_keyword_match_ratio,
                )
                if not matched:
                    stats.skipped_irrelevant += 1
                    stats.skipped_by_keyword_match += 1
                    logging.info(
                        "Skipping low-relevance record: %s | keyword=%s | ratio=%.2f | missing=%s",
                        item.get("title") or item.get("display_name") or key,
                        keyword,
                        ratio,
                        ",".join(missing),
                    )
                    continue
            passes_relevance, topic_score, relevance_reason = record_passes_relevance_filters(
                item,
                config,
                topic_pack=topic_pack,
                journal_pack=journal_pack,
            )
            if not passes_relevance:
                stats.skipped_irrelevant += 1
                if relevance_reason == "low_topic_score":
                    stats.skipped_by_topic_score += 1
                logging.info(
                    "Skipping domain-irrelevant record: %s | keyword=%s | reason=%s | topic_score=%s | threshold=%s",
                    item.get("title") or item.get("display_name") or key,
                    keyword,
                    relevance_reason,
                    topic_score,
                    config.min_topic_score,
                )
                continue
            passes_impact_factor, journal_fields = record_passes_impact_factor_filter(item, config, journal_metric_resolver)
            if journal_fields.get("impact_factor") is None:
                stats.impact_factor_unknown_records += 1
                stats.journal_metric_missing += 1
            else:
                stats.impact_factor_known_records += 1
                stats.journal_metric_resolved += 1
            if not passes_impact_factor:
                stats.skipped_irrelevant += 1
                stats.skipped_by_impact_factor += 1
                logging.info(
                    "Skipping low-impact-factor record: %s | journal=%s | impact_factor=%s | threshold=%s",
                    item.get("title") or item.get("display_name") or key,
                    journal_fields.get("journal_title") or "unknown",
                    journal_fields.get("impact_factor"),
                    config.min_impact_factor,
                )
                continue
            canonical = canonical_record_key(item)
            is_existing_record = key in existing_index.keys
            has_downloaded_pdf = key in existing_index.downloaded_keys
            if is_existing_record and (has_downloaded_pdf or not config.retry_missing_pdfs):
                stats.skipped_duplicates += 1
                continue

            if is_existing_record:
                stats.retried_existing_records += 1
            else:
                existing_index.keys.add(key)
            if canonical:
                existing_index.canonical_keys.add(canonical)

            download = DownloadResult(None, "not_open_access")
            pdf_candidates: list[str] = []
            unpaywall = None
            duplicate_pdf_path = existing_index.canonical_pdf_paths.get(canonical or "")

            try:
                doi = normalize_doi(item.get("doi"))
                if doi:
                    try:
                        unpaywall = query_unpaywall(session, doi, config.email)
                    except requests.RequestException as exc:
                        stats.request_failures += 1
                        logging.warning("Continuing without Unpaywall data: %s | %s", key, exc)

                if is_open_access(item, unpaywall):
                    stats.open_access_records += 1
                    if config.download_pdfs:
                        doi_or_url = doi or item.get("id") or item.get("title") or ""
                        if duplicate_pdf_path:
                            duplicate_path = Path(duplicate_pdf_path)
                            download = DownloadResult(
                                str(duplicate_path),
                                "duplicate_reused",
                                size_bytes=duplicate_path.stat().st_size if duplicate_path.exists() else None,
                            )
                            existing_index.downloaded_keys.add(key)
                            if canonical:
                                existing_index.downloaded_canonical_keys.add(canonical)
                        else:
                            pdf_candidates = iter_pdf_candidates(item, unpaywall)
                            duplicate_by_url = existing_pdf_for_candidates(existing_index, pdf_candidates)
                            if duplicate_by_url:
                                duplicate_path = Path(duplicate_by_url)
                                download = DownloadResult(
                                    str(duplicate_path),
                                    "duplicate_reused",
                                    source_url=next((url for url in pdf_candidates if normalize_candidate_url(url) in existing_index.pdf_url_paths), None),
                                    size_bytes=duplicate_path.stat().st_size if duplicate_path.exists() else None,
                                )
                                existing_index.downloaded_keys.add(key)
                                if canonical:
                                    existing_index.downloaded_canonical_keys.add(canonical)
                                    existing_index.canonical_pdf_paths.setdefault(canonical, str(duplicate_path))
                        if download.path:
                            stats.skipped_duplicates += 1
                            index_pdf_path(existing_index, item, Path(download.path), pdf_candidates)
                        else:
                            emit_source_progress(
                                config,
                                stats,
                                source,
                                keyword,
                                "downloading_pdf",
                                f"Resolving and downloading PDF from {source_label}: {item.get('title') or item.get('display_name') or key}",
                                f"Resolving and downloading PDF from {source_label}: {item.get('title') or item.get('display_name') or key}",
                                f"Resolving and downloading PDF from {source_label}: {item.get('title') or item.get('display_name') or key}",
                                detail=str(item.get("title") or item.get("display_name") or key),
                            )
                            download, pdf_candidates = download_first_available_pdf(
                                session,
                                item,
                                unpaywall,
                                doi_or_url,
                                config,
                                keyword_pdf_dir(keyword, config.out_dir),
                                stats,
                            )
                            download = reuse_duplicate_content_pdf(download, existing_index)
                        stats.pdf_candidates_found += len(pdf_candidates)
                        if download.path:
                            if download.status not in {"duplicate_reused", "duplicate_content_reused"}:
                                note_pdf_download(stats)
                            existing_index.downloaded_keys.add(key)
                            index_pdf_path(existing_index, item, Path(download.path), pdf_candidates)
                            existing_index.retry_pdf_keys.discard(key)
                            emit_source_progress(
                                config,
                                stats,
                                source,
                                keyword,
                                "downloaded_pdf",
                                f"Downloaded PDF from {source_label}: {item.get('title') or item.get('display_name')}",
                                f"Downloaded PDF from {source_label}: {item.get('title') or item.get('display_name')}",
                                f"Downloaded PDF from {source_label}: {item.get('title') or item.get('display_name')}",
                                detail=str(download.source_url or ""),
                            )
                        elif pdf_candidates:
                            note_pdf_failure(stats, download.reason or download.status)
                            existing_index.retry_pdf_keys.add(key)
                            emit_source_progress(
                                config,
                                stats,
                                source,
                                keyword,
                                "pdf_failed",
                                f"PDF download failed from {source_label}: {download.status} {download.reason or ''}".strip(),
                                f"PDF download failed from {source_label}: {download.status} {download.reason or ''}".strip(),
                                f"PDF download failed from {source_label}: {download.status} {download.reason or ''}".strip(),
                                detail=download.reason or download.status,
                            )
                        else:
                            note_pdf_failure(stats, download.reason or download.status)
                            existing_index.retry_pdf_keys.add(key)
                    else:
                        pdf_candidates = iter_pdf_candidates(item, unpaywall)
                        stats.pdf_candidates_found += len(pdf_candidates)
                        download = DownloadResult(None, "download_disabled")
                        existing_index.retry_pdf_keys.add(key)
                else:
                    stats.skipped_not_oa += 1

                should_write = (
                    (not is_existing_record)
                    or config.write_retry_records
                )
                if should_write:
                    relevance_info = build_relevance_info(keyword, item, config, topic_pack)
                    record = build_record(
                        keyword,
                        item,
                        unpaywall,
                        download,
                        pdf_candidates,
                        config.meta_path,
                        relevance_info,
                    )
                    append_jsonl_record(fout, record)
                    stats.added_records += 1
                    emit_source_progress(
                        config,
                        stats,
                        source,
                        keyword,
                        "saved_metadata",
                        f"Saved metadata from {source_label}: {record.get('title') or key}",
                        f"Saved metadata from {source_label}: {record.get('title') or key}",
                        f"Saved metadata from {source_label}: {record.get('title') or key}",
                        detail=str(record.get("title") or key),
                    )
            except requests.RequestException as exc:
                stats.request_failures += 1
                logging.warning("Skipping record after request failure: %s | %s", key, exc)
                emit_source_progress(
                    config,
                    stats,
                    source,
                    keyword,
                    "request_failed",
                    f"Request failed in {source_label}; continuing with next record: {exc}",
                    f"Request failed in {source_label}; continuing with next record: {exc}",
                    f"Request failed in {source_label}; continuing with next record: {exc}",
                    detail=str(exc),
                )
            except Exception:
                logging.exception("Skipping record after unexpected failure: %s", key)
                emit_source_progress(
                    config,
                    stats,
                    source,
                    keyword,
                    "record_failed",
                    f"Unexpected record error in {source_label}; continuing with next record.",
                    f"Unexpected record error in {source_label}; continuing with next record.",
                    f"Unexpected record error in {source_label}; continuing with next record.",
                    detail=str(key),
                )

            if sleep_or_stop(config.request_delay, config):
                return

        if not cursor:
            save_keyword_state(source, keyword, config, crawl_state, None, page_no, exhausted=True)
            break

        save_keyword_state(source, keyword, config, crawl_state, cursor, page_no, exhausted=False)

        if sleep_or_stop(config.page_delay, config):
            return


def load_keywords(keywords_arg: str | None, keywords_file: Path | None) -> list[str] | None:
    """Docstring."""
    if keywords_file:
        with keywords_file.open("r", encoding="utf-8") as fin:
            keywords = []
            for line in fin:
                keyword = line.strip()
                if keyword and not keyword.startswith("#"):
                    keywords.append(keyword)
            return keywords

    if keywords_arg:
        return [keyword.strip() for keyword in keywords_arg.split(";") if keyword.strip()]

    return None


def log_summary(stats: CrawlStats) -> None:
    """Log a diagnostic crawl summary."""
    logging.info(
        "Crawl summary: existing=%s fetched_total=%s fetched_by_source=%s added=%s "
        "duplicates=%s no_key=%s irrelevant=%s keyword_filtered=%s topic_filtered=%s impact_filtered=%s "
        "journal_metric_resolved=%s journal_metric_missing=%s "
        "not_oa=%s oa=%s pdf_candidates=%s pdf_attempted=%s pdf_downloaded=%s "
        "pdf_failed=%s pdf_failure_reasons=%s retried_existing=%s request_failures=%s",
        stats.existing_records,
        stats.fetched_items_total or stats.fetched_items,
        stats.fetched_by_source,
        stats.added_records,
        stats.skipped_duplicates,
        stats.skipped_without_key,
        stats.skipped_irrelevant,
        stats.skipped_by_keyword_match,
        stats.skipped_by_topic_score,
        stats.skipped_by_impact_factor,
        stats.journal_metric_resolved,
        stats.journal_metric_missing,
        stats.skipped_not_oa,
        stats.open_access_records,
        stats.pdf_candidates_found,
        stats.pdf_download_attempted,
        stats.pdf_downloaded or stats.downloaded_pdfs,
        stats.pdf_failed or stats.failed_pdfs,
        stats.pdf_failure_reasons,
        stats.retried_existing_records,
        stats.request_failures,
    )


def merge_backfill_stats(stats: CrawlStats, backfill_stats: CrawlStats) -> None:
    """Merge automatic backfill counters into the crawl-round stats."""
    stats.backfill_scanned_records += backfill_stats.backfill_scanned_records
    stats.backfill_missing_pdf_records += backfill_stats.backfill_missing_pdf_records
    stats.backfill_downloaded_pdfs += backfill_stats.backfill_downloaded_pdfs
    stats.backfill_failed_pdfs += backfill_stats.backfill_failed_pdfs
    stats.pdf_candidates_found += backfill_stats.pdf_candidates_found
    stats.pdf_download_attempted += backfill_stats.pdf_download_attempted
    stats.downloaded_pdfs += backfill_stats.downloaded_pdfs
    stats.pdf_downloaded += backfill_stats.pdf_downloaded
    stats.failed_pdfs += backfill_stats.failed_pdfs
    stats.pdf_failed += backfill_stats.pdf_failed
    stats.retried_existing_records += backfill_stats.retried_existing_records
    for reason, count in backfill_stats.backfill_failure_reasons.items():
        stats.backfill_failure_reasons[reason] = stats.backfill_failure_reasons.get(reason, 0) + count
    for reason, count in backfill_stats.pdf_failure_reasons.items():
        stats.pdf_failure_reasons[reason] = stats.pdf_failure_reasons.get(reason, 0) + count


def format_reason_counts(reasons: dict[str, int], limit: int = 8) -> str:
    """Return a compact sorted reason counter for UI summaries."""
    if not reasons:
        return "{}"
    top = sorted(reasons.items(), key=lambda item: (-item[1], item[0]))[:limit]
    return "{" + ", ".join(f"{key}: {count}" for key, count in top) + "}"


def run_once(config: CrawlConfig) -> CrawlStats:
    """Docstring."""
    config.out_dir.mkdir(parents=True, exist_ok=True)
    config.meta_path.parent.mkdir(parents=True, exist_ok=True)
    config.state_path.parent.mkdir(parents=True, exist_ok=True)

    existing_index = load_existing_index(config.meta_path, config.min_pdf_bytes, config.out_dir)
    crawl_state = load_crawl_state(config.state_path) if config.resume else {}
    stats = CrawlStats(existing_records=len(existing_index.keys))
    logging.info(
        "Loaded %s existing records, %s with valid PDFs from %s",
        len(existing_index.keys),
        len(existing_index.downloaded_keys),
        config.meta_path,
    )
    if config.resume:
        logging.info("Loaded %s crawl state entries from %s", len(crawl_state), config.state_path)
    emit_progress(config, stats, localized(config, "Loaded existing metadata and resume state", "Loaded existing metadata and resume state", "Loaded existing metadata and resume state"))

    session = build_session(config.email)
    try:
        with config.meta_path.open("a", encoding="utf-8") as fout:
            for source in config.effective_sources:
                for keyword in config.effective_keywords:
                    if should_stop(stats, config):
                        break
                    try:
                        crawl_keyword(session, source, keyword, existing_index, fout, config, stats, crawl_state)
                    except requests.RequestException as exc:
                        stats.request_failures += 1
                        logging.warning("Skipping source and keyword after request failure: %s | %s | %s", source, keyword, exc)
                        emit_source_progress(
                            config,
                            stats,
                            source,
                            keyword,
                            "source_failed",
                            f"Source request failed for {SOURCE_LABELS.get(source, source)}; continuing with next item: {exc}",
                            f"Source request failed for {SOURCE_LABELS.get(source, source)}; continuing with next item: {exc}",
                            f"Source request failed for {SOURCE_LABELS.get(source, source)}; continuing with next item: {exc}",
                            detail=str(exc),
                        )
    finally:
        session.close()

    if (
        config.download_pdfs
        and config.auto_backfill_missing_pdfs
        and not stop_requested(config)
        and not should_stop(stats, config)
    ):
        emit_progress(
            config,
            stats,
            localized(
                config,
                "正在根据已保存元数据自动补全缺失 PDF。",
                "Starting automatic missing-PDF backfill from saved metadata.",
                "Starting automatic missing-PDF backfill from saved metadata.",
            ),
        )
        backfill_stats = backfill_missing_pdfs_from_metadata(config, progress_callback=config.progress_callback)
        merge_backfill_stats(stats, backfill_stats)

    log_summary(stats)
    emit_progress(config, stats, format_round_finished_message(config, stats))
    return stats


def format_round_finished_message(config: CrawlConfig, stats: CrawlStats) -> str:
    """Return a diagnostic crawl summary for logs and the UI."""
    fetched_total = stats.fetched_items_total or stats.fetched_items
    pdf_downloaded = stats.pdf_downloaded or stats.downloaded_pdfs
    pdf_failed = stats.pdf_failed or stats.failed_pdfs
    lines = [
        "Crawl round finished.",
        f"Fetched total: {fetched_total}; by source: {stats.fetched_by_source}.",
        f"Metadata records saved this round: {stats.added_records}; duplicate skips: {stats.skipped_duplicates}; missing-key skips: {stats.skipped_without_key}.",
        f"Filter skips: total={stats.skipped_irrelevant}, keyword={stats.skipped_by_keyword_match}, topic_score={stats.skipped_by_topic_score}, impact_factor={stats.skipped_by_impact_factor}, not_oa={stats.skipped_not_oa}.",
        f"Impact-factor metrics: known={stats.journal_metric_resolved}, unknown={stats.journal_metric_missing}.",
        f"PDF files downloaded this round: {pdf_downloaded}; candidates={stats.pdf_candidates_found}; attempts={stats.pdf_download_attempted}; failed={pdf_failed}.",
    ]
    if stats.backfill_scanned_records:
        lines.append(
            localized(
                config,
                (
                    "自动缺失 PDF 补全："
                    f"已扫描={stats.backfill_scanned_records}，缺失={stats.backfill_missing_pdf_records}，"
                    f"已下载={stats.backfill_downloaded_pdfs}，失败={stats.backfill_failed_pdfs}。"
                ),
                (
                    "Automatic missing-PDF backfill: "
                    f"scanned={stats.backfill_scanned_records}, missing={stats.backfill_missing_pdf_records}, "
                    f"downloaded={stats.backfill_downloaded_pdfs}, failed={stats.backfill_failed_pdfs}."
                ),
                (
                    "Automatic missing-PDF backfill: "
                    f"scanned={stats.backfill_scanned_records}, missing={stats.backfill_missing_pdf_records}, "
                    f"downloaded={stats.backfill_downloaded_pdfs}, failed={stats.backfill_failed_pdfs}."
                ),
            )
        )
    if stats.pdf_failure_reasons:
        lines.append(f"Top PDF failure reasons: {format_reason_counts(stats.pdf_failure_reasons)}.")
    if stats.backfill_failure_reasons:
        lines.append(
            localized(
                config,
                f"主要补全失败原因：{format_reason_counts(stats.backfill_failure_reasons)}。",
                f"Top backfill failure reasons: {format_reason_counts(stats.backfill_failure_reasons)}.",
                f"Top backfill failure reasons: {format_reason_counts(stats.backfill_failure_reasons)}.",
            )
        )
    if stats.retried_existing_records:
        lines.append(f"Existing metadata records retried for PDF: {stats.retried_existing_records}.")
    if stats.request_failures:
        lines.append(f"Source/API request failures: {stats.request_failures}.")
    if config.loop:
        minutes = config.loop_sleep / 60
        lines.append(f"Loop mode is enabled. The next round will start in about {minutes:.0f} minutes.")
    else:
        lines.append("The task has ended. Use these counters to identify low API yield, duplicate-heavy pages, strict filters, missing PDF candidates, or download failures.")
    return "\n".join(lines)


def format_backfill_finished_message(config: CrawlConfig, stats: CrawlStats) -> str:
    """Return a UI/log summary for metadata PDF backfill."""
    if config.language == "zh":
        lines = [
            "元数据 PDF 补全完成。",
            f"已扫描元数据行数：{stats.backfill_scanned_records}；缺失本地 PDF 的记录：{stats.backfill_missing_pdf_records}。",
            f"找到 PDF 候选：{stats.pdf_candidates_found}；下载尝试：{stats.pdf_download_attempted}。",
            f"已下载 PDF：{stats.backfill_downloaded_pdfs}；失败 PDF：{stats.backfill_failed_pdfs}。",
        ]
    else:
        lines = [
            "Metadata PDF backfill finished.",
            f"Scanned metadata lines: {stats.backfill_scanned_records}; missing local PDFs: {stats.backfill_missing_pdf_records}.",
            f"PDF candidates found: {stats.pdf_candidates_found}; download attempts: {stats.pdf_download_attempted}.",
            f"Downloaded PDFs: {stats.backfill_downloaded_pdfs}; failed PDFs: {stats.backfill_failed_pdfs}.",
        ]
    if stats.backfill_failure_reasons:
        if config.language == "zh":
            lines.append(f"主要补全失败原因：{format_reason_counts(stats.backfill_failure_reasons)}。")
        else:
            lines.append(f"Top backfill failure reasons: {format_reason_counts(stats.backfill_failure_reasons)}.")
    return "\n".join(lines)

def deadline_from_config(config: CrawlConfig) -> datetime | None:
    """Docstring."""
    if config.max_runtime_hours is None:
        return None
    return datetime.now() + timedelta(hours=config.max_runtime_hours)


def sleep_until_next_loop(seconds: float, deadline: datetime | None, config: CrawlConfig) -> bool:
    """Docstring."""
    if deadline and datetime.now() >= deadline:
        return False

    sleep_seconds = seconds
    if deadline:
        remaining = (deadline - datetime.now()).total_seconds()
        sleep_seconds = min(seconds, max(0, remaining))

    if sleep_seconds > 0:
        logging.info("Sleeping %.0f seconds before next crawl round.", sleep_seconds)
        if sleep_or_stop(sleep_seconds, config):
            return False
    return (not deadline or datetime.now() < deadline) and not stop_requested(config)


def main(config: CrawlConfig) -> None:
    """Docstring."""
    configure_logging(config.log_level)
    validate_config(config)
    config.out_dir.mkdir(parents=True, exist_ok=True)
    config.meta_path.parent.mkdir(parents=True, exist_ok=True)
    config.state_path.parent.mkdir(parents=True, exist_ok=True)
    deadline = deadline_from_config(config)
    round_no = 1

    while True:
        if stop_requested(config):
            logging.info("Stop requested before crawl round %s.", round_no)
            break
        logging.info("Starting crawl round %s.", round_no)
        run_once(config)

        if not config.loop or stop_requested(config):
            break
        if not sleep_until_next_loop(config.loop_sleep, deadline, config):
            break
        round_no += 1


def validate_config(config: CrawlConfig) -> None:
    """Docstring."""
    config.email = config.email.strip()
    if not config.email:
        raise ValueError("--email is required. Please enter your own contact email.")
    if not EMAIL_PATTERN.fullmatch(config.email):
        raise ValueError("--email must be a valid email address.")
    config.sources = list(dict.fromkeys(config.effective_sources))
    if not config.sources:
        raise ValueError("Select at least one literature source.")
    invalid_sources = [source for source in config.sources if source not in SOURCE_LABELS]
    if invalid_sources:
        raise ValueError(f"Unsupported literature source: {', '.join(invalid_sources)}")

    try:
        from_date = datetime.strptime(config.from_date, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError("--from-date must be in YYYY-MM-DD format.") from exc
    try:
        to_date = datetime.strptime(config.to_date, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError("--to-date must be in YYYY-MM-DD format.") from exc
    if to_date < from_date:
        raise ValueError("--to-date must be greater than or equal to --from-date.")

    if config.max_pages_per_keyword < 1:
        raise ValueError("--pages must be at least 1.")
    if not 1 <= config.per_page <= 200:
        raise ValueError("--per-page must be between 1 and 200.")
    if config.min_topic_score < 0:
        raise ValueError("--min-topic-score must be zero or greater.")
    if config.min_impact_factor is not None and config.min_impact_factor < 0:
        raise ValueError("--min-impact-factor must be zero or greater.")
    if config.max_records is not None and config.max_records < 1:
        raise ValueError("--max-records must be at least 1.")
    if config.request_delay < 0 or config.page_delay < 0 or config.loop_sleep < 0:
        raise ValueError("Delay values cannot be negative.")
    if config.min_pdf_bytes < 1:
        raise ValueError("--min-pdf-bytes must be at least 1.")
    if not 0 < config.min_keyword_match_ratio <= 1:
        raise ValueError("--min-keyword-match-ratio must be greater than 0 and at most 1.")
    if config.max_runtime_hours is not None and config.max_runtime_hours <= 0:
        raise ValueError("--max-runtime-hours must be greater than 0.")

