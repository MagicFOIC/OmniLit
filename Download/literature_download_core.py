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
UNPAYWALL_URL = "https://api.unpaywall.org/v2"
SOURCE_OPENALEX = "openalex"
SOURCE_EUROPE_PMC = "europe_pmc"
SOURCE_ARXIV = "arxiv"
SOURCE_LABELS = {
    SOURCE_OPENALEX: "OpenAlex",
    SOURCE_EUROPE_PMC: "Europe PMC",
    SOURCE_ARXIV: "arXiv",
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
PDF_CHUNK_SIZE = 1024 * 64
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@dataclass
class CrawlConfig:
    """集中保存下载任务参数。"""
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
        """返回有效关键词。参数：无。返回值：关键词列表。"""
        return self.keywords or DEFAULT_KEYWORDS

    @property
    def effective_sources(self) -> list[str]:
        """Return the selected literature sources in stable order."""
        return DEFAULT_SOURCES if self.sources is None else self.sources


def localized(config: CrawlConfig, zh: str, en: str, ru: str = "") -> str:
    """按任务启动时的语言选择日志。参数：下载配置、中英文。返回值：当前语言文本。"""
    return (ru or en) if config.language == "ru" else en if config.language == "en" else zh


@dataclass
class CrawlStats:
    """累计下载任务统计值。"""
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
    """保存已有元数据索引。"""
    keys: set[str]
    downloaded_keys: set[str]
    retry_pdf_keys: set[str]


@dataclass
class DownloadResult:
    """描述单个 PDF 下载结果。"""
    path: str | None
    status: str
    source_url: str | None = None
    reason: str | None = None
    size_bytes: int | None = None


@dataclass
class CrawlStateEntry:
    """描述单个关键词的断点状态。"""
    next_cursor: str | None = None
    completed_pages: int = 0
    exhausted: bool = False


def configure_logging(level: str) -> None:
    """功能：配置命令行日志级别。参数：level。返回值：None。"""
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
    """功能：检查下载任务是否收到停止请求。参数：config。返回值：bool。"""
    return bool(config.stop_callback and config.stop_callback())


def emit_progress(config: CrawlConfig, stats: Any, message: str) -> None:
    """功能：向界面上报下载统计和进度消息。参数：config、stats、message。返回值：None。"""
    if not config.progress_callback:
        return
    try:
        config.progress_callback(stats, message)
    except Exception:
        logging.exception("Progress callback failed.")


def sleep_or_stop(seconds: float, config: CrawlConfig) -> bool:
    """功能：等待指定秒数，并在停止请求到达时提前返回。参数：seconds、config。返回值：bool。"""
    if seconds <= 0:
        return stop_requested(config)

    end_time = time.monotonic() + seconds
    while time.monotonic() < end_time:
        if stop_requested(config):
            return True
        time.sleep(min(0.25, max(0, end_time - time.monotonic())))
    return stop_requested(config)


def state_key(keyword: str, config: CrawlConfig, source: str = SOURCE_OPENALEX) -> str:
    """功能：构造可稳定复用的抓取断点键。参数：keyword、config。返回值：str。"""
    parts = {
        "keyword": keyword,
        "from_date": config.from_date,
        "to_date": config.to_date,
        "oa_only": config.oa_only,
        "sort": config.sort,
        "per_page": config.per_page,
        "strict_keyword_match": config.strict_keyword_match,
        "min_keyword_match_ratio": config.min_keyword_match_ratio,
    }
    # Preserve historical OpenAlex state keys while isolating new source cursors.
    if source != SOURCE_OPENALEX:
        parts["source"] = source
    return json.dumps(parts, ensure_ascii=False, sort_keys=True)


def load_crawl_state(path: Path) -> dict[str, CrawlStateEntry]:
    """功能：读取并解析抓取断点状态。参数：path。返回值：dict[str, CrawlStateEntry]。"""
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
    """功能：原子写入抓取断点状态。参数：path、state。返回值：None。"""
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
    """Append one complete JSONL record and make it durable before reporting success."""
    fout.write(json.dumps(record, ensure_ascii=False) + "\n")
    fout.flush()
    try:
        os.fsync(fout.fileno())
    except (AttributeError, OSError):
        # In-memory streams used by callers and tests do not expose a descriptor.
        pass


def build_session(email: str) -> requests.Session:
    """功能：创建带联系邮箱和重试策略的 HTTP 会话。参数：email。返回值：requests.Session。"""
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
    """功能：规范化 DOI 文本。参数：doi。返回值：str | None。"""
    if not doi:
        return None
    doi = doi.strip()
    doi = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", doi, flags=re.IGNORECASE)
    doi = re.sub(r"^doi:\s*", "", doi, flags=re.IGNORECASE)
    return doi.lower() or None


def record_key(record: dict[str, Any]) -> str | None:
    """功能：生成文献记录的去重键。参数：record。返回值：str | None。"""
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
    """功能：生成适合文件系统使用的名称。参数：text。返回值：str。"""
    return hashlib.md5(text.encode("utf-8")).hexdigest() + ".pdf"


def path_for_pdf(doi_or_url: str, out_dir: Path) -> Path:
    """功能：根据 DOI 或地址生成 PDF 保存路径。参数：doi_or_url、out_dir。返回值：Path。"""
    return out_dir / safe_filename(doi_or_url)


def safe_keyword_folder_name(keyword: str) -> str:
    """Return a readable, collision-resistant folder name for one keyword."""
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
    """Return the keyword-specific PDF output directory."""
    return out_dir / safe_keyword_folder_name(keyword)


def display_path(path: Path, base_dir: Path) -> str:
    """功能：生成相对于数据目录的展示路径。参数：path、base_dir。返回值：str。"""
    try:
        return os.path.relpath(path.resolve(), base_dir.resolve())
    except ValueError:
        return str(path)


def strip_query(url: str) -> str:
    """功能：移除地址中的查询参数。参数：url。返回值：str。"""
    return url.split("?", 1)[0].split("#", 1)[0]


def looks_like_pdf_url(url: str | None) -> bool:
    """功能：判断地址是否像 PDF 下载链接。参数：url。返回值：bool。"""
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


def candidate_urls_from_landing_url(url: str | None) -> list[str]:
    """功能：从落地页地址派生候选 PDF 链接。参数：url。返回值：list[str]。"""
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
    """功能：按原始顺序去重地址列表。参数：urls。返回值：list[str]。"""
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
    """功能：解析历史记录中的 PDF 本地路径。参数：record、meta_path。返回值：list[Path]。"""
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
    """功能：判断历史记录是否需要重试 PDF 下载。参数：record。返回值：bool。"""
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
    """功能：载入历史元数据并建立去重索引。参数：meta_path、min_pdf_bytes、out_dir。返回值：ExistingIndex。"""
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
    """功能：请求 OpenAlex 单页搜索结果。参数：session、keyword、config、cursor。返回值：dict[str, Any]。"""
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
    """Convert API text fields containing lightweight markup to plain text."""
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", str(value or "")))).strip()


def search_europe_pmc(
    session: requests.Session,
    keyword: str,
    config: CrawlConfig,
    cursor: str = "*",
) -> dict[str, Any]:
    """Request and normalize one Europe PMC result page."""
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
    """Build an arXiv query from the significant keyword terms."""
    terms = keyword_terms(keyword)
    return " AND ".join(f"all:{term}" for term in terms) or f'all:"{keyword}"'


def search_arxiv(
    session: requests.Session,
    keyword: str,
    config: CrawlConfig,
    cursor: str = "0",
) -> dict[str, Any]:
    """Request and normalize one arXiv Atom result page."""
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


def search_literature_source(
    session: requests.Session,
    source: str,
    keyword: str,
    config: CrawlConfig,
    cursor: str,
) -> dict[str, Any]:
    """Dispatch a normalized search request to the selected literature source."""
    if source == SOURCE_OPENALEX:
        return search_openalex(session, keyword, config, cursor)
    if source == SOURCE_EUROPE_PMC:
        return search_europe_pmc(session, keyword, config, cursor)
    if source == SOURCE_ARXIV:
        return search_arxiv(session, keyword, config, cursor)
    raise ValueError(f"Unsupported literature source: {source}")


def source_maps() -> list[dict[str, str]]:
    """Return stable source labels for the Qt selector."""
    return [{"key": key, "label": label} for key, label in SOURCE_LABELS.items()]


def reconstruct_abstract(inv_index: dict[str, list[int]] | None) -> str:
    """功能：从 OpenAlex 倒排索引还原摘要。参数：inv_index。返回值：str。"""
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
    """功能：规范化关键词匹配文本。参数：term。返回值：str。"""
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
    """功能：拆分可用于匹配的检索词。参数：text。返回值：list[str]。"""
    return [normalize_search_term(term) for term in re.findall(r"[a-z0-9]+", text.casefold())]


def keyword_terms(keyword: str) -> list[str]:
    """功能：拆分用户关键词。参数：keyword。返回值：list[str]。"""
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
    """功能：拼接文献标题和摘要用于关键词匹配。参数：item。返回值：str。"""
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
    """功能：计算关键词匹配详情。参数：keyword、item、min_match_ratio。返回值：tuple[bool, float, list[str]]。"""
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
    """功能：判断文献是否满足关键词匹配阈值。参数：keyword、item、config。返回值：bool。"""
    if not config.strict_keyword_match:
        return True
    matched, _ratio, _missing = keyword_match_details(keyword, item, config.min_keyword_match_ratio)
    return matched


def extract_authors(item: dict[str, Any], limit: int = 12) -> list[str]:
    """功能：提取文献作者列表。参数：item、limit。返回值：list[str]。"""
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
    """功能：查询 Unpaywall 开放获取信息。参数：session、doi、email。返回值：dict[str, Any] | None。"""
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
    """功能：汇总文献和 Unpaywall 提供的 PDF 候选链接。参数：item、unpaywall。返回值：list[str]。"""
    open_access = item.get("open_access") or {}
    primary_location = item.get("primary_location") or {}
    urls = [
        *(unpaywall or {}).get("pdf_urls", []),
        (unpaywall or {}).get("pdf_url"),
        primary_location.get("pdf_url"),
        open_access.get("oa_url"),
    ]
    for landing_url in (unpaywall or {}).get("landing_urls", []):
        urls.extend(candidate_urls_from_landing_url(landing_url))
    urls.extend(candidate_urls_from_landing_url(open_access.get("oa_url")))
    urls.extend(candidate_urls_from_landing_url(primary_location.get("landing_page_url")))

    return [url for url in unique_urls(urls) if looks_like_pdf_url(url)]


def validate_existing_pdf(path: Path, min_pdf_bytes: int) -> bool:
    """功能：检查已有 PDF 是否完整可用。参数：path、min_pdf_bytes。返回值：bool。"""
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
    """功能：下载并校验单个 PDF 候选链接。参数：session、pdf_url、doi_or_url、config。返回值：DownloadResult。"""
    if stop_requested(config):
        return DownloadResult(None, "stopped", pdf_url)

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
    """功能：按顺序尝试候选链接直到成功下载 PDF。参数：session、item、unpaywall、doi_or_url、config。返回值：tuple[DownloadResult, list[str]]。"""
    candidates = iter_pdf_candidates(item, unpaywall)
    last_result = DownloadResult(None, "no_candidate")

    for pdf_url in candidates:
        if stop_requested(config):
            return DownloadResult(None, "stopped"), candidates
        result = download_pdf(session, pdf_url, doi_or_url, config, out_dir)
        if result.path:
            return result, candidates
        last_result = result
        logging.debug("PDF candidate failed: %s | %s | %s", result.status, result.reason, pdf_url)

    return last_result, candidates


def is_open_access(item: dict[str, Any], unpaywall: dict[str, Any] | None) -> bool:
    """功能：判断文献是否满足开放获取条件。参数：item、unpaywall。返回值：bool。"""
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
    """功能：组装可持久化的文献元数据记录。参数：keyword、item、unpaywall、download、pdf_candidates、meta_path。返回值：dict[str, Any]。"""
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
    """功能：判断抓取任务是否达到停止条件。参数：stats、config。返回值：bool。"""
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
    """功能：保存单个关键词的断点状态。参数：keyword、config、crawl_state、next_cursor、completed_pages、exhausted。返回值：None。"""
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
    """功能：判断当前页结果是否全部处理过。参数：results、existing_index、retry_missing_pdfs。返回值：bool。"""
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
    """功能：抓取单个关键词并持续保存元数据和断点。参数：session、keyword、existing_index、fout、config、stats、crawl_state。返回值：None。"""
    key = state_key(keyword, config, source)
    state_entry = crawl_state.get(key, CrawlStateEntry())
    if config.resume and state_entry.exhausted:
        logging.info("Skipping exhausted source and keyword: %s | %s", source, keyword)
        return

    initial_cursor = "0" if source == SOURCE_ARXIV else "*"
    cursor = state_entry.next_cursor if config.resume and state_entry.next_cursor else initial_cursor
    completed_pages = state_entry.completed_pages if config.resume else 0
    if cursor != initial_cursor:
        logging.info(
            "Resuming: %s | %s | after %s completed pages",
            source,
            keyword,
            completed_pages,
        )
    emit_progress(config, stats, localized(config, f"准备关键词：{keyword}", f"Preparing keyword: {keyword}", f"Подготовка ключевого слова: {keyword}"))

    for page in range(config.max_pages_per_keyword):
        if should_stop(stats, config):
            return

        page_no = completed_pages + page + 1
        logging.info("Searching: %s | %s | page %s", source, keyword, page_no)
        emit_progress(config, stats, localized(config, f"正在检索 {keyword} 第 {page_no} 页", f"Searching {keyword} page {page_no}", f"Поиск {keyword}, страница {page_no}"))
        data = search_literature_source(session, source, keyword, config, cursor=cursor)
        results = data.get("results", [])
        stats.fetched_items += len(results)
        cursor = data.get("meta", {}).get("next_cursor")
        emit_progress(config, stats, localized(config, f"已从 {keyword} 第 {page_no} 页获取 {len(results)} 条记录", f"Fetched {len(results)} records from {keyword} page {page_no}", f"Получено записей: {len(results)}; {keyword}, страница {page_no}"))

        if (
            config.fast_forward_existing_pages
            and all_results_already_seen(results, existing_index, config.retry_missing_pdfs)
        ):
            stats.skipped_duplicates += len(results)
            logging.info("Fast-forwarding already indexed page: %s | page %s", keyword, page_no)
            emit_progress(config, stats, localized(config, f"已跳过已有索引的第 {page_no} 页", f"Fast-forwarded already indexed page {page_no}", f"Пропущена индексированная страница {page_no}"))
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
                            emit_progress(config, stats, localized(config, f"已下载 PDF：{item.get('title') or item.get('display_name')}", f"Downloaded PDF: {item.get('title') or item.get('display_name')}", f"Загружен PDF: {item.get('title') or item.get('display_name')}"))
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
                    emit_progress(config, stats, localized(config, f"已保存元数据：{record.get('title') or key}", f"Saved metadata: {record.get('title') or key}", f"Сохранены метаданные: {record.get('title') or key}"))
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
    """功能：从命令行或文件载入关键词列表。参数：keywords_arg、keywords_file。返回值：list[str] | None。"""
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
    """功能：输出下载任务汇总统计。参数：stats。返回值：None。"""
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
    """功能：执行一轮完整下载任务。参数：config。返回值：CrawlStats。"""
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
    emit_progress(config, stats, localized(config, "已加载现有元数据和断点状态", "Loaded existing metadata and resume state", "Загружены метаданные и состояние продолжения"))

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
    emit_progress(config, stats, localized(config, "本轮抓取完成", "Crawl round finished", "Цикл сбора завершён"))
    return stats


def deadline_from_config(config: CrawlConfig) -> datetime | None:
    """功能：根据配置计算任务截止时间。参数：config。返回值：datetime | None。"""
    if config.max_runtime_hours is None:
        return None
    return datetime.now() + timedelta(hours=config.max_runtime_hours)


def sleep_until_next_loop(seconds: float, deadline: datetime | None, config: CrawlConfig) -> bool:
    """功能：等待下一轮任务并响应截止时间和停止请求。参数：seconds、deadline、config。返回值：bool。"""
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
    """功能：执行命令行入口流程。参数：config。返回值：None。"""
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
    """功能：校验下载任务配置边界。参数：config。返回值：None。"""
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
