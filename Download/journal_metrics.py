from __future__ import annotations

import csv
import json
import logging
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import quote


METRICS_CSV_PATH = Path(__file__).resolve().with_name("journal_metrics.csv")
OPENALEX_SOURCES_URL = "https://api.openalex.org/sources"

_WORD_RE = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class JournalMetric:
    journal_title: str
    issn: str | list[str]
    issn_l: str
    impact_factor: float | None
    metric_year: int | None
    source: str
    quartile: str
    metric_name: str = "impact_factor"

    @property
    def issns(self) -> tuple[str, ...]:
        return _metric_issns(self.issn)


@dataclass(frozen=True)
class JournalMetricMatch:
    journal_title: str
    journal_issns: tuple[str, ...]
    impact_factor: float | None
    impact_factor_year: int | None
    impact_factor_source: str
    impact_factor_quartile: str
    impact_factor_unknown: bool
    journal_issn_l: str = ""
    impact_factor_metric: str = ""

    def as_record_fields(self) -> dict[str, Any]:
        return {
            "journal_title": self.journal_title,
            "journal_issns": list(self.journal_issns),
            "journal_issn_l": self.journal_issn_l,
            "impact_factor": self.impact_factor,
            "impact_factor_year": self.impact_factor_year,
            "impact_factor_source": self.impact_factor_source,
            "impact_factor_metric": self.impact_factor_metric,
            "impact_factor_quartile": self.impact_factor_quartile,
            "impact_factor_unknown": self.impact_factor_unknown,
        }


def normalize_issn(value: Any) -> str:
    text = str(value or "").strip().upper()
    if not text:
        return ""
    text = re.sub(r"[^0-9X]", "", text)
    if re.fullmatch(r"\d{7}[\dX]", text):
        return f"{text[:4]}-{text[4:]}"
    return ""


def normalize_journal_name(value: Any) -> str:
    return _WORD_RE.sub(" ", str(value or "").casefold().replace("&", " and ")).strip()


def _split_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value or "")
    return [item.strip() for item in re.split(r"[;,|]", text) if item.strip()]


def _parse_float(value: Any) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _parse_int(value: Any) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def _metric_issns(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        values = _split_values(value)
    elif isinstance(value, (list, tuple, set)):
        values = list(value)
    else:
        values = []
    return tuple(dict.fromkeys(normalized for item in values if (normalized := normalize_issn(item))))


def _as_metric(row: dict[str, str]) -> JournalMetric | None:
    title = str(row.get("journal_title") or row.get("title") or row.get("journal") or "").strip()
    issns = _metric_issns(row.get("issn"))
    issn_l = normalize_issn(row.get("issn_l")) or (issns[0] if issns else "")
    if not title and not issns and not issn_l:
        return None
    return JournalMetric(
        journal_title=title,
        issn=list(issns),
        issn_l=issn_l,
        impact_factor=_parse_float(row.get("impact_factor")),
        metric_year=_parse_int(row.get("metric_year")),
        source=str(row.get("source") or "local_csv").strip(),
        quartile=str(row.get("quartile") or "").strip(),
        metric_name=str(row.get("metric_name") or "impact_factor").strip() or "impact_factor",
    )


@lru_cache(maxsize=8)
def load_journal_metrics(csv_path: str | Path = METRICS_CSV_PATH) -> tuple[JournalMetric, ...]:
    path = Path(csv_path)
    if not path.exists():
        return ()
    with path.open("r", encoding="utf-8-sig", newline="") as fin:
        reader = csv.DictReader(fin)
        metrics = [_as_metric(row) for row in reader]
    return tuple(metric for metric in metrics if metric is not None)


def journal_values_from_record(record: dict[str, Any]) -> tuple[str, tuple[str, ...]]:
    names: list[str] = []
    issns: list[str] = []

    for key in ("journal_title", "journal", "journalTitle", "container-title", "container_title", "source_title"):
        for value in _split_values(record.get(key)):
            names.append(value)

    for key in ("journal_issns", "issn", "issns", "ISSN", "ISSNs", "journal_issn"):
        for value in _split_values(record.get(key)):
            normalized = normalize_issn(value)
            if normalized:
                issns.append(normalized)

    primary_source = ((record.get("primary_location") or {}).get("source") or {})
    host_venue = record.get("host_venue") or {}
    journal_info = record.get("journalInfo") or {}
    bibjson = record.get("bibjson") or {}
    bibjson_journal = bibjson.get("journal") or {}

    for container in (primary_source, host_venue, journal_info, bibjson_journal):
        for key in ("display_name", "name", "title", "journal", "journalTitle"):
            for value in _split_values(container.get(key)):
                names.append(value)
        for key in ("issn", "issns", "issn_l", "ISSN", "eissn", "pissn"):
            for value in _split_values(container.get(key)):
                normalized = normalize_issn(value)
                if normalized:
                    issns.append(normalized)

    unique_names = [name for name in dict.fromkeys(names) if name]
    unique_issns = tuple(dict.fromkeys(issns))
    return (unique_names[0] if unique_names else ""), unique_issns


def _journal_issn_l_from_record(record: dict[str, Any], journal_issns: tuple[str, ...]) -> str:
    for key in ("journal_issn_l", "issn_l", "ISSN-L"):
        normalized = normalize_issn(record.get(key))
        if normalized:
            return normalized

    primary_source = ((record.get("primary_location") or {}).get("source") or {})
    host_venue = record.get("host_venue") or {}
    journal_info = record.get("journalInfo") or {}
    bibjson = record.get("bibjson") or {}
    bibjson_journal = bibjson.get("journal") or {}
    for container in (primary_source, host_venue, journal_info, bibjson_journal):
        normalized = normalize_issn(container.get("issn_l") or container.get("issnL"))
        if normalized:
            return normalized
    return journal_issns[0] if journal_issns else ""


def _source_id_from_record(record: dict[str, Any]) -> str:
    for key in ("source_id", "openalex_source_id", "journal_source_id"):
        value = str(record.get(key) or "").strip()
        if value:
            return value
    primary_source = ((record.get("primary_location") or {}).get("source") or {})
    host_venue = record.get("host_venue") or {}
    for container in (primary_source, host_venue):
        value = str(container.get("id") or container.get("openalex_id") or "").strip()
        if value:
            return value
    return ""


def _metric_cache_key(record: dict[str, Any]) -> str:
    journal_title, journal_issns = journal_values_from_record(record)
    issn_l = _journal_issn_l_from_record(record, journal_issns)
    source_id = _source_id_from_record(record)
    parts = {
        "source_id": source_id,
        "issn_l": issn_l,
        "issns": journal_issns,
        "journal_title": normalize_journal_name(journal_title),
    }
    return json.dumps(parts, ensure_ascii=False, sort_keys=True)


def _find_local_metric(record: dict[str, Any], metrics: tuple[JournalMetric, ...]) -> JournalMetric | None:
    journal_title, journal_issns = journal_values_from_record(record)
    record_issns = set(journal_issns)
    issn_l = _journal_issn_l_from_record(record, journal_issns)
    if issn_l:
        record_issns.add(issn_l)
    record_name = normalize_journal_name(journal_title)

    for metric in metrics:
        metric_issns = set(metric.issns)
        if metric.issn_l:
            metric_issns.add(metric.issn_l)
        if record_issns and metric_issns.intersection(record_issns):
            return metric

    for metric in metrics:
        if record_name and normalize_journal_name(metric.journal_title) == record_name:
            return metric
    return None


def _openalex_source_id(value: str) -> str:
    text = str(value or "").strip().rstrip("/")
    if not text:
        return ""
    return text.rsplit("/", 1)[-1]


def _openalex_metric_from_source(data: dict[str, Any]) -> JournalMetric | None:
    summary_stats = data.get("summary_stats") or {}
    impact_factor = _parse_float(summary_stats.get("2yr_mean_citedness"))
    title = str(data.get("display_name") or data.get("display_name_alternatives") or "").strip()
    issns = _metric_issns(data.get("issn"))
    issn_l = normalize_issn(data.get("issn_l")) or (issns[0] if issns else "")
    if impact_factor is None and not title and not issns and not issn_l:
        return None
    return JournalMetric(
        journal_title=title,
        issn=list(issns),
        issn_l=issn_l,
        impact_factor=impact_factor,
        metric_year=None,
        source="openalex",
        quartile="",
        metric_name="openalex_2yr_mean_citedness",
    )


def fetch_openalex_source_metric(
    session,
    *,
    issn_l: str = "",
    issn: str = "",
    source_id: str = "",
    journal_title: str = "",
    email: str = "",
) -> JournalMetric | None:
    """Fetch an OpenAlex Sources metric as an open approximation, not official JCR IF."""
    params: dict[str, str] = {}
    if email:
        params["mailto"] = email

    source_key = _openalex_source_id(source_id)
    if source_key:
        response = session.get(f"{OPENALEX_SOURCES_URL}/{quote(source_key)}", params=params, timeout=20)
        response.raise_for_status()
        return _openalex_metric_from_source(response.json() or {})

    filter_value = ""
    normalized_issn_l = normalize_issn(issn_l)
    normalized_issn = normalize_issn(issn)
    if normalized_issn_l:
        filter_value = f"issn_l:{normalized_issn_l}"
    elif normalized_issn:
        filter_value = f"issn:{normalized_issn}"
    elif journal_title:
        params["search"] = str(journal_title).strip()
    else:
        return None

    if filter_value:
        params["filter"] = filter_value
    response = session.get(OPENALEX_SOURCES_URL, params=params, timeout=20)
    response.raise_for_status()
    payload = response.json() or {}
    results = payload.get("results") or []
    if not results:
        return None
    return _openalex_metric_from_source(results[0] or {})


class JournalMetricResolver:
    def __init__(
        self,
        *,
        local_csv: Path | None = None,
        source: str = "local_then_openalex",
        session=None,
        email: str = "",
        cache_path: Path | None = None,
    ):
        self.local_csv = local_csv or METRICS_CSV_PATH
        self.source = source
        self.session = session
        self.email = email
        self.cache_path = cache_path
        self._memory_cache: dict[str, JournalMetric | None] = {}
        self._local_metrics = load_journal_metrics(self.local_csv)

    def resolve(self, record: dict[str, Any]) -> JournalMetric | None:
        """Resolve a journal metric, preferring local CSV and falling back to OpenAlex."""
        cache_key = _metric_cache_key(record)
        if cache_key in self._memory_cache:
            return self._memory_cache[cache_key]

        metric = None
        if self.source in {"local", "local_csv", "local_only", "local_then_openalex"}:
            metric = _find_local_metric(record, self._local_metrics)
        if metric is None and self.source in {"openalex", "openalex_only", "local_then_openalex"}:
            metric = self._resolve_openalex(record)

        self._memory_cache[cache_key] = metric
        return metric

    def _resolve_openalex(self, record: dict[str, Any]) -> JournalMetric | None:
        journal_title, journal_issns = journal_values_from_record(record)
        issn_l = _journal_issn_l_from_record(record, journal_issns)
        source_id = _source_id_from_record(record)
        session = self.session
        if session is None:
            import requests

            session = requests.Session()
            self.session = session
        for normalized_issn in journal_issns or ("",):
            try:
                metric = fetch_openalex_source_metric(
                    session,
                    issn_l=issn_l,
                    issn=normalized_issn,
                    source_id=source_id,
                    journal_title=journal_title,
                    email=self.email,
                )
            except Exception as exc:  # pragma: no cover - defensive network fallback.
                logging.debug("OpenAlex journal metric lookup failed: %s", exc)
                metric = None
            if metric is not None:
                return metric
            if source_id or issn_l:
                break
        return None


def attach_journal_metric(record: dict[str, Any], metric: JournalMetric | None) -> dict[str, Any]:
    """Attach normalized journal metric fields and legacy aliases to a record."""
    journal_title, record_issns = journal_values_from_record(record)
    metric_issns = metric.issns if metric is not None else ()
    journal_issns = tuple(dict.fromkeys([*record_issns, *metric_issns]))
    journal_issn_l = (
        _journal_issn_l_from_record(record, record_issns)
        or (metric.issn_l if metric is not None else "")
        or (journal_issns[0] if journal_issns else "")
    )
    impact_factor = metric.impact_factor if metric is not None else None
    impact_factor_metric = metric.metric_name if metric is not None else ""
    impact_factor_year = metric.metric_year if metric is not None else None
    impact_factor_source = metric.source if metric is not None else ""
    impact_factor_quartile = metric.quartile if metric is not None else ""
    title = journal_title or (metric.journal_title if metric is not None else "")

    fields = {
        "journal_title": title,
        "journal_issns": list(journal_issns),
        "journal_issn_l": journal_issn_l,
        "impact_factor": impact_factor,
        "impact_factor_source": impact_factor_source,
        "impact_factor_metric": impact_factor_metric,
        "impact_factor_year": impact_factor_year,
        "impact_factor_quartile": impact_factor_quartile,
        "impact_factor_unknown": impact_factor is None,
        "journal_name": title,
        "journal_impact_value": impact_factor,
        "journal_impact_metric": impact_factor_metric,
        "journal_impact_year": impact_factor_year,
        "journal_metric_source": impact_factor_source,
    }
    record.update(fields)
    return record


def record_passes_impact_factor_filter(
    record: dict[str, Any],
    min_impact_factor: float | None,
    *,
    include_unknown: bool = True,
) -> bool:
    """Return whether a record passes a minimum impact-factor threshold."""
    if min_impact_factor is None:
        return True
    value = record.get("impact_factor")
    if value is None or str(value).strip() == "":
        return include_unknown
    try:
        return float(value) >= float(min_impact_factor)
    except (TypeError, ValueError):
        return include_unknown


def match_journal_metric(
    record: dict[str, Any],
    metrics: tuple[JournalMetric, ...] | None = None,
) -> JournalMetricMatch:
    journal_title, journal_issns = journal_values_from_record(record)
    metrics = metrics if metrics is not None else load_journal_metrics()
    metric = _find_local_metric(record, metrics)
    if metric is not None:
        return _match_from_metric(
            metric,
            journal_title or metric.journal_title,
            journal_issns or metric.issns,
            _journal_issn_l_from_record(record, journal_issns) or metric.issn_l,
        )

    return JournalMetricMatch(
        journal_title=journal_title,
        journal_issns=journal_issns,
        journal_issn_l=_journal_issn_l_from_record(record, journal_issns),
        impact_factor=None,
        impact_factor_year=None,
        impact_factor_source="",
        impact_factor_metric="",
        impact_factor_quartile="",
        impact_factor_unknown=True,
    )


def _match_from_metric(
    metric: JournalMetric,
    journal_title: str,
    journal_issns: tuple[str, ...],
    journal_issn_l: str = "",
) -> JournalMetricMatch:
    return JournalMetricMatch(
        journal_title=journal_title,
        journal_issns=journal_issns,
        journal_issn_l=journal_issn_l or metric.issn_l,
        impact_factor=metric.impact_factor,
        impact_factor_year=metric.metric_year,
        impact_factor_source=metric.source,
        impact_factor_metric=metric.metric_name,
        impact_factor_quartile=metric.quartile,
        impact_factor_unknown=metric.impact_factor is None,
    )
