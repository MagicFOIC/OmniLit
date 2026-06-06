from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any


METRICS_CSV_PATH = Path(__file__).resolve().with_name("journal_metrics.csv")

_WORD_RE = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class JournalMetric:
    journal_title: str
    issns: tuple[str, ...]
    issn_l: str
    impact_factor: float | None
    metric_year: str
    source: str
    quartile: str


@dataclass(frozen=True)
class JournalMetricMatch:
    journal_title: str
    journal_issns: tuple[str, ...]
    impact_factor: float | None
    impact_factor_year: str
    impact_factor_source: str
    impact_factor_quartile: str
    impact_factor_unknown: bool

    def as_record_fields(self) -> dict[str, Any]:
        return {
            "journal_title": self.journal_title,
            "journal_issns": list(self.journal_issns),
            "impact_factor": self.impact_factor,
            "impact_factor_year": self.impact_factor_year,
            "impact_factor_source": self.impact_factor_source,
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


def _as_metric(row: dict[str, str]) -> JournalMetric | None:
    title = str(row.get("journal_title") or row.get("title") or row.get("journal") or "").strip()
    issns = tuple(dict.fromkeys(normalize_issn(value) for value in _split_values(row.get("issn")) if normalize_issn(value)))
    issn_l = normalize_issn(row.get("issn_l")) or (issns[0] if issns else "")
    if not title and not issns and not issn_l:
        return None
    return JournalMetric(
        journal_title=title,
        issns=issns,
        issn_l=issn_l,
        impact_factor=_parse_float(row.get("impact_factor")),
        metric_year=str(row.get("metric_year") or "").strip(),
        source=str(row.get("source") or "").strip(),
        quartile=str(row.get("quartile") or "").strip(),
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


def match_journal_metric(
    record: dict[str, Any],
    metrics: tuple[JournalMetric, ...] | None = None,
) -> JournalMetricMatch:
    journal_title, journal_issns = journal_values_from_record(record)
    metrics = metrics if metrics is not None else load_journal_metrics()
    record_issns = set(journal_issns)
    record_name = normalize_journal_name(journal_title)

    for metric in metrics:
        metric_issns = set(metric.issns)
        if metric.issn_l:
            metric_issns.add(metric.issn_l)
        if record_issns and metric_issns.intersection(record_issns):
            return _match_from_metric(metric, journal_title or metric.journal_title, journal_issns or metric.issns)

    for metric in metrics:
        if record_name and normalize_journal_name(metric.journal_title) == record_name:
            return _match_from_metric(metric, journal_title or metric.journal_title, journal_issns or metric.issns)

    return JournalMetricMatch(
        journal_title=journal_title,
        journal_issns=journal_issns,
        impact_factor=None,
        impact_factor_year="",
        impact_factor_source="",
        impact_factor_quartile="",
        impact_factor_unknown=True,
    )


def _match_from_metric(metric: JournalMetric, journal_title: str, journal_issns: tuple[str, ...]) -> JournalMetricMatch:
    return JournalMetricMatch(
        journal_title=journal_title,
        journal_issns=journal_issns,
        impact_factor=metric.impact_factor,
        impact_factor_year=metric.metric_year,
        impact_factor_source=metric.source,
        impact_factor_quartile=metric.quartile,
        impact_factor_unknown=metric.impact_factor is None,
    )

