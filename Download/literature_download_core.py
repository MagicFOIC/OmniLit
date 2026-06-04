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
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, TextIO
from urllib.parse import quote, urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

try:
    from .journal_registry import is_whitelisted_journal
    from .pack_builder import journal_pack_match_score, resolve_journal_pack, resolve_topic_pack
    from .topic_packs import score_topic_relevance
except ImportError:  # pragma: no cover - supports direct script execution.
    from journal_registry import is_whitelisted_journal
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
DEFAULT_SOURCES = [SOURCE_OPENALEX]
OPENALEX_SELECT = (
    "id,doi,title,display_name,publication_date,publication_year,"
    "cited_by_count,authorships,primary_location,open_access,"
    "abstract_inverted_index"
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
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


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
    strict_keyword_match: bool = True
    min_keyword_match_ratio: float = 0.75
    topic_pack: str | None = "auto"
    journal_pack: str | None = "auto"
    selected_journals: list[str] | None = None
    min_topic_score: int = 6
    journal_whitelist_only: bool = False
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
    added_records: int = 0
    skipped_duplicates: int = 0
    skipped_without_key: int = 0
    skipped_irrelevant: int = 0
    open_access_records: int = 0
    downloaded_pdfs: int = 0
    failed_pdfs: int = 0
    retried_existing_records: int = 0
    request_failures: int = 0


@dataclass
class ExistingIndex:
    """Docstring."""
    keys: set[str]
    downloaded_keys: set[str]
    retry_pdf_keys: set[str]


@dataclass
class DownloadResult:
    """Docstring."""
    path: str | None
    status: str
    source_url: str | None = None
    reason: str | None = None
    size_bytes: int | None = None


@dataclass
class PdfResolution:
    """Docstring."""
    url: str | None
    candidates: list[str]
    reason: str | None = None


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
        total=4,
        connect=4,
        read=2,
        backoff_factor=1.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)

    session = requests.Session()
    user_agent = "BatteryLiteratureCrawler/0.3"
    if email:
        user_agent = f"{user_agent} mailto:{email}"
    session.headers.update(
        {
            "User-Agent": user_agent,
            "Accept": "application/json, application/pdf;q=0.9, */*;q=0.5",
        }
    )
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


def looks_like_pdf_url(url: str | None) -> bool:
    """Docstring."""
    if not url:
        return False

    normalized_url = strip_query(url).lower()
    if normalized_url.endswith(NON_PDF_EXTENSIONS):
        return False

    return (
        normalized_url.endswith(".pdf")
        or "/pdf" in normalized_url
        or "/articlepdf" in normalized_url
        or "/pdfdirect/" in normalized_url
        or "/servlets/purl/" in normalized_url
        or "pdf=render" in url.casefold()
    )


def is_shadow_library_url(url: str | None) -> bool:
    """Docstring."""
    if not url:
        return False
    host = urlparse(url).netloc.casefold()
    return any(domain in host for domain in SHADOW_LIBRARY_DOMAINS)


def candidate_urls_from_landing_url(url: str | None) -> list[str]:
    """Docstring."""
    if not url:
        return []

    parsed = urlparse(url)
    normalized_url = strip_query(url)
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

    return candidates


def unique_urls(urls: list[str | None]) -> list[str]:
    """Docstring."""
    seen: set[str] = set()
    result: list[str] = []
    for url in urls:
        if not url:
            continue
        normalized = url.strip()
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
    "download_disabled",
    "failed",
    "file_error",
    "invalid_pdf",
    "no_candidate",
    "not_pdf",
    "request_error",
    "stopped",
    "too_small",
}


def record_needs_pdf_retry(record: dict[str, Any]) -> bool:
    """Docstring."""
    if record.get("local_pdf_path"):
        return False

    status = str(record.get("download_status") or "").strip()
    if status in RETRYABLE_DOWNLOAD_STATUSES:
        return True

    open_access = record.get("open_access") or {}
    unpaywall = record.get("unpaywall") or {}
    return bool(
        (isinstance(open_access, dict) and open_access.get("is_oa"))
        or (isinstance(unpaywall, dict) and unpaywall.get("is_oa"))
        or record.get("pdf_candidates")
    )


def load_existing_index(meta_path: Path, min_pdf_bytes: int, out_dir: Path) -> ExistingIndex:
    """Docstring."""
    keys: set[str] = set()
    downloaded_keys: set[str] = set()
    retry_pdf_keys: set[str] = set()
    if not meta_path.exists():
        return ExistingIndex(keys, downloaded_keys, retry_pdf_keys)

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

                if any(validate_existing_pdf(path, min_pdf_bytes) for path in fallback_pdf_paths):
                    downloaded_keys.add(key)
                    retry_pdf_keys.discard(key)
                elif key not in downloaded_keys and record_needs_pdf_retry(record):
                    retry_pdf_keys.add(key)

    return ExistingIndex(keys, downloaded_keys, retry_pdf_keys)


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
        source_record_id = f"{item.get('source') or 'unknown'}:{item.get('id') or item.get('pmcid') or item.get('doi')}"
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
    pdf_urls = unique_urls([
        link.get("URL")
        for link in links
        if isinstance(link, dict)
        and "pdf" in str(link.get("content-type") or "").casefold()
        and link.get("URL")
    ])
    landing_url = item.get("URL")
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
        "doaj_fulltext_links": unique_urls(fulltext_links),
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
    pdf_urls = unique_urls([best.get("url_for_pdf")] + [loc.get("url_for_pdf") for loc in all_locations])
    landing_urls = unique_urls([best.get("url")] + [loc.get("url") for loc in all_locations])

    return {
        "is_oa": data.get("is_oa"),
        "oa_status": data.get("oa_status"),
        "license": best.get("license"),
        "pdf_url": best.get("url_for_pdf"),
        "landing_url": best.get("url"),
        "pdf_urls": pdf_urls,
        "landing_urls": landing_urls,
        "host_type": best.get("host_type"),
        "version": best.get("version"),
    }


def iter_pdf_candidates(
    item: dict[str, Any],
    unpaywall: dict[str, Any] | None,
) -> list[str]:
    """Docstring."""
    open_access = item.get("open_access") or {}
    primary_location = item.get("primary_location") or {}
    is_oa_record = bool(open_access.get("is_oa") or (unpaywall or {}).get("is_oa"))
    urls = [
        primary_location.get("pdf_url"),
        open_access.get("oa_url"),
        (unpaywall or {}).get("pdf_url"),
        *(unpaywall or {}).get("pdf_urls", []),
        *item.get("doaj_fulltext_links", []),
    ]
    if is_oa_record:
        for landing_url in (unpaywall or {}).get("landing_urls", []):
            urls.extend(candidate_urls_from_landing_url(landing_url))
        urls.extend(candidate_urls_from_landing_url(open_access.get("oa_url")))
        urls.extend(candidate_urls_from_landing_url(primary_location.get("landing_page_url")))

    return [
        url
        for url in unique_urls(urls)
        if looks_like_pdf_url(url) and not is_shadow_library_url(url)
    ]


def verify_pdf_url_with_head(
    session: requests.Session,
    url: str,
    config: CrawlConfig,
) -> tuple[bool, str | None]:
    """Docstring."""
    del config
    if is_shadow_library_url(url):
        return False, "shadow_library"
    if not looks_like_pdf_url(url):
        return False, "not_pdf"

    head = getattr(session, "head", None)
    if not callable(head):
        return True, None

    try:
        response = head(url, timeout=(10, 30), allow_redirects=True)
    except requests.RequestException:
        return False, "request_failed"

    status_code = getattr(response, "status_code", None)
    if status_code in {401, 402, 403}:
        return False, "paywalled"
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


def resolve_open_access_pdf(
    record: dict[str, Any],
    session: requests.Session,
    config: CrawlConfig,
) -> PdfResolution:
    """Docstring."""
    unpaywall = record.get("unpaywall")
    candidates = iter_pdf_candidates(record, unpaywall if isinstance(unpaywall, dict) else None)
    if not candidates:
        return PdfResolution(None, [], "no_oa_pdf" if config.oa_only else "no_candidate")

    last_reason: str | None = None
    for url in candidates:
        ok, reason = verify_pdf_url_with_head(session, url, config)
        if ok:
            return PdfResolution(url, candidates, None)
        last_reason = reason
        logging.debug("Rejected OA PDF candidate before download: %s | %s", reason, url)

    return PdfResolution(None, candidates, last_reason or "not_pdf")


def validate_existing_pdf(path: Path, min_pdf_bytes: int) -> bool:
    """Docstring."""
    try:
        if not path.exists() or path.stat().st_size < min_pdf_bytes:
            return False
        with path.open("rb") as fin:
            if fin.read(4) != b"%PDF":
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


def download_pdf(
    session: requests.Session,
    pdf_url: str,
    doi_or_url: str,
    config: CrawlConfig,
    out_dir: Path | None = None,
) -> DownloadResult:
    """Docstring."""
    if stop_requested(config):
        return DownloadResult(None, "stopped", pdf_url)
    if is_shadow_library_url(pdf_url):
        return DownloadResult(None, "failed", pdf_url, "shadow_library")

    target_dir = out_dir or config.out_dir
    target_dir.mkdir(parents=True, exist_ok=True)
    path = path_for_pdf(doi_or_url, target_dir)
    if validate_existing_pdf(path, config.min_pdf_bytes):
        return DownloadResult(
            path=str(path),
            status="already_exists",
            source_url=pdf_url,
            size_bytes=path.stat().st_size,
        )

    tmp_path = path.with_suffix(".part")
    try:
        with session.get(
            pdf_url,
            timeout=(15, 45),
            stream=True,
            allow_redirects=True,
        ) as response:
            if response.status_code != 200:
                return DownloadResult(None, "failed", pdf_url, f"http_{response.status_code}")

            content_type = response.headers.get("content-type", "").lower()
            chunks = response.iter_content(chunk_size=PDF_CHUNK_SIZE)
            first_chunk = next(chunks, b"")
            if not first_chunk.startswith(b"%PDF") and "pdf" not in content_type:
                return DownloadResult(None, "not_pdf", pdf_url, content_type or "missing_content_type")

            with tmp_path.open("wb") as fout:
                if first_chunk:
                    fout.write(first_chunk)
                for chunk in chunks:
                    if stop_requested(config):
                        return DownloadResult(None, "stopped", pdf_url)
                    if chunk:
                        fout.write(chunk)

        size = tmp_path.stat().st_size
        if size < config.min_pdf_bytes:
            tmp_path.unlink(missing_ok=True)
            return DownloadResult(None, "too_small", pdf_url, f"{size}_bytes")

        if not validate_existing_pdf(tmp_path, config.min_pdf_bytes):
            tmp_path.unlink(missing_ok=True)
            return DownloadResult(None, "invalid_pdf", pdf_url)

        tmp_path.replace(path)
        return DownloadResult(str(path), "downloaded", pdf_url, size_bytes=size)

    except requests.RequestException as exc:
        return DownloadResult(None, "request_error", pdf_url, str(exc))
    except OSError as exc:
        return DownloadResult(None, "file_error", pdf_url, str(exc))
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
) -> tuple[DownloadResult, list[str]]:
    """Docstring."""
    record = dict(item)
    if unpaywall:
        record["unpaywall"] = unpaywall
    resolution = resolve_open_access_pdf(record, session, config)
    candidates = resolution.candidates
    if not resolution.url:
        return DownloadResult(None, "failed", reason=resolution.reason), candidates

    start_index = candidates.index(resolution.url)
    last_result = DownloadResult(None, "failed", reason=resolution.reason)
    for pdf_url in candidates[start_index:]:
        if stop_requested(config):
            return DownloadResult(None, "stopped"), candidates
        ok, reason = verify_pdf_url_with_head(session, pdf_url, config)
        if not ok:
            last_result = DownloadResult(None, "failed", pdf_url, reason)
            continue
        result = download_pdf(session, pdf_url, doi_or_url, config, out_dir)
        if result.path:
            return result, candidates
        last_result = result
        logging.debug("PDF candidate failed: %s | %s | %s", result.status, result.reason, pdf_url)

    return last_result, candidates


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
) -> dict[str, Any]:
    """Docstring."""
    doi = normalize_doi(item.get("doi"))
    local_pdf_path = None
    if download.path:
        local_pdf_path = display_path(Path(download.path), meta_path.parent)
    return {
        "keyword": keyword,
        "literature_source": item.get("literature_source") or SOURCE_OPENALEX,
        "source_record_id": item.get("source_record_id") or item.get("id"),
        "openalex_id": item.get("id") if item.get("literature_source") in {None, SOURCE_OPENALEX} else None,
        "doi": item.get("doi"),
        "normalized_doi": doi,
        "title": item.get("title") or item.get("display_name"),
        "publication_date": item.get("publication_date"),
        "publication_year": item.get("publication_year"),
        "cited_by_count": item.get("cited_by_count"),
        "authors": extract_authors(item),
        "abstract": item.get("abstract") or reconstruct_abstract(item.get("abstract_inverted_index")),
        "open_access": item.get("open_access"),
        "unpaywall": unpaywall,
        "pdf_candidates": pdf_candidates,
        "download_status": download.status,
        "download_reason": download.reason,
        "download_source_url": download.source_url,
        "local_pdf_path": local_pdf_path,
        "local_pdf_size_bytes": download.size_bytes,
    }


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
        if not key or key not in existing_index.keys:
            return False
        if retry_missing_pdfs and key in existing_index.retry_pdf_keys:
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
    key = state_key(keyword, config, source)
    state_entry = crawl_state.get(key, CrawlStateEntry())
    if config.resume and state_entry.exhausted:
        logging.info("Skipping exhausted source and keyword: %s | %s", source, keyword)
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
    emit_progress(config, stats, localized(config, f"Preparing keyword: {keyword}", f"Preparing keyword: {keyword}", f"Preparing keyword: {keyword}"))

    for page in range(config.max_pages_per_keyword):
        if should_stop(stats, config):
            return

        page_no = completed_pages + page + 1
        logging.info("Searching: %s | %s | page %s", source, keyword, page_no)
        emit_progress(config, stats, localized(config, f"Searching {keyword} page {page_no}", f"Searching {keyword} page {page_no}", f"Searching {keyword} page {page_no}"))
        data = search_literature_source(session, source, keyword, config, cursor=cursor)
        results = data.get("results", [])
        stats.fetched_items += len(results)
        cursor = data.get("meta", {}).get("next_cursor")
        journal_pack = resolve_journal_pack(config, results)
        results = sort_records_by_resolved_packs(results, topic_pack, journal_pack)
        emit_progress(config, stats, localized(config, f"Fetched {len(results)} records from {keyword} page {page_no}", f"Fetched {len(results)} records from {keyword} page {page_no}", f"Fetched {len(results)} records from {keyword} page {page_no}"))

        if (
            config.fast_forward_existing_pages
            and all_results_already_seen(results, existing_index, config.retry_missing_pdfs)
        ):
            stats.skipped_duplicates += len(results)
            logging.info("Fast-forwarding already indexed page: %s | page %s", keyword, page_no)
            emit_progress(config, stats, localized(config, f"Fast-forwarded already indexed page {page_no}", f"Fast-forwarded already indexed page {page_no}", f"Fast-forwarded already indexed page {page_no}"))
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
                logging.info(
                    "Skipping domain-irrelevant record: %s | keyword=%s | reason=%s | topic_score=%s | threshold=%s",
                    item.get("title") or item.get("display_name") or key,
                    keyword,
                    relevance_reason,
                    topic_score,
                    config.min_topic_score,
                )
                continue
            is_existing_record = key in existing_index.keys
            has_downloaded_pdf = key in existing_index.downloaded_keys
            if is_existing_record and (has_downloaded_pdf or not config.retry_missing_pdfs):
                stats.skipped_duplicates += 1
                continue

            if is_existing_record:
                stats.retried_existing_records += 1
            else:
                existing_index.keys.add(key)

            download = DownloadResult(None, "not_open_access")
            pdf_candidates: list[str] = []
            unpaywall = None

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
                        download, pdf_candidates = download_first_available_pdf(
                            session,
                            item,
                            unpaywall,
                            doi_or_url,
                            config,
                            keyword_pdf_dir(keyword, config.out_dir),
                        )
                        if download.path:
                            stats.downloaded_pdfs += 1
                            existing_index.downloaded_keys.add(key)
                            existing_index.retry_pdf_keys.discard(key)
                            emit_progress(config, stats, localized(config, f"Downloaded PDF: {item.get('title') or item.get('display_name')}", f"Downloaded PDF: {item.get('title') or item.get('display_name')}", f"Downloaded PDF: {item.get('title') or item.get('display_name')}"))
                        elif pdf_candidates:
                            stats.failed_pdfs += 1
                            existing_index.retry_pdf_keys.add(key)
                    else:
                        pdf_candidates = iter_pdf_candidates(item, unpaywall)
                        download = DownloadResult(None, "download_disabled")
                        existing_index.retry_pdf_keys.add(key)

                should_write = (
                    (not is_existing_record)
                    or config.write_retry_records
                )
                if should_write:
                    record = build_record(keyword, item, unpaywall, download, pdf_candidates, config.meta_path)
                    append_jsonl_record(fout, record)
                    stats.added_records += 1
                    emit_progress(config, stats, localized(config, f"Saved metadata: {record.get('title') or key}", f"Saved metadata: {record.get('title') or key}", f"Saved metadata: {record.get('title') or key}"))
            except requests.RequestException as exc:
                stats.request_failures += 1
                logging.warning("Skipping record after request failure: %s | %s", key, exc)
            except Exception:
                logging.exception("Skipping record after unexpected failure: %s", key)

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
    """Docstring."""
    logging.info(
        "Done. existing=%s fetched=%s added=%s duplicates=%s oa=%s pdfs=%s "
        "pdf_failures=%s retried=%s request_failures=%s no_key=%s irrelevant=%s",
        stats.existing_records,
        stats.fetched_items,
        stats.added_records,
        stats.skipped_duplicates,
        stats.open_access_records,
        stats.downloaded_pdfs,
        stats.failed_pdfs,
        stats.retried_existing_records,
        stats.request_failures,
        stats.skipped_without_key,
        stats.skipped_irrelevant,
    )


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
    finally:
        session.close()

    log_summary(stats)
    emit_progress(config, stats, localized(config, "Crawl round finished", "Crawl round finished", "Crawl round finished"))
    return stats


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
