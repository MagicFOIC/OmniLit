# Copyright (c) 2026 magicfoic. All rights reserved.

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any


_ISSN_RE = re.compile(r"([0-9]{4})[-\s]?([0-9]{3}[0-9Xx])")
_WORD_RE = re.compile(r"[^a-z0-9]+")


_OA_JOURNAL_PACKS: dict[str, list[dict[str, Any]]] = {
    "li_sulfur": [
        {
            "name": "Batteries",
            "publisher": "MDPI",
            "issns": ["2313-0105"],
            "aliases": ["Batteries Basel"],
        },
        {
            "name": "RSC Advances",
            "publisher": "RSC",
            "issns": ["2046-2069"],
            "aliases": ["RSC Adv"],
        },
        {
            "name": "ACS Omega",
            "publisher": "ACS",
            "issns": [],
            "aliases": [],
        },
        {
            "name": "eScience",
            "publisher": "KeAi-Elsevier",
            "issns": ["2667-1417"],
            "aliases": ["eScience"],
        },
        {
            "name": "Frontiers in Energy Research",
            "publisher": "Frontiers",
            "issns": ["2296-598X"],
            "aliases": [],
        },
        {
            "name": "Frontiers in Chemistry",
            "publisher": "Frontiers",
            "issns": [],
            "aliases": [],
        },
        {
            "name": "Advanced Science",
            "publisher": "Wiley",
            "issns": [],
            "aliases": ["Advanced Science News"],
        },
        {
            "name": "Energy & Environmental Materials",
            "publisher": "Wiley",
            "issns": ["2575-0356"],
            "aliases": ["Energy and Environmental Materials"],
        },
        {
            "name": "Nano-Micro Letters",
            "publisher": "Springer Nature",
            "issns": [],
            "aliases": ["Nano Micro Letters", "Nano-Micro Lett"],
        },
        {
            "name": "Communications Materials",
            "publisher": "Nature Portfolio",
            "issns": ["2662-4443"],
            "aliases": ["Communication Materials"],
        },
        {
            "name": "Nature Communications",
            "publisher": "Nature Portfolio",
            "issns": [],
            "aliases": ["Nat Commun"],
        },
    ],
}


def get_oa_journal_pack(pack_name: str = "li_sulfur") -> list[dict[str, Any]]:
    """Return a copy of the configured OA journal allow-list pack."""
    try:
        return deepcopy(_OA_JOURNAL_PACKS[pack_name])
    except KeyError as exc:
        raise ValueError(f"Unknown OA journal pack: {pack_name}") from exc


def normalize_issn(value: Any) -> str:
    """Normalize an ISSN-like value to XXXX-XXXX, or return an empty string."""
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        for item in value:
            normalized = normalize_issn(item)
            if normalized:
                return normalized
        return ""
    match = _ISSN_RE.search(str(value).strip())
    if not match:
        return ""
    return f"{match.group(1)}-{match.group(2).upper()}"


def is_whitelisted_journal(record: dict[str, Any], selected_journals: list[str] | None = None) -> bool:
    """Return whether a record belongs to the Li-S OA journal allow-list."""
    return journal_match_score(record, selected_journals=selected_journals) > 0


def journal_match_score(record: dict[str, Any], selected_journals: list[str] | None = None) -> int:
    """Score an OA allow-list journal match by ISSN first, then journal name."""
    journals = _selected_journals(selected_journals)
    if not journals:
        return 0

    record_issns = _record_issns(record)
    record_names = _record_journal_names(record)
    normalized_names = {_normalize_name(name) for name in record_names if name}

    best = 0
    for journal in journals:
        journal_issns = {normalize_issn(value) for value in journal.get("issns", [])}
        journal_issns.discard("")
        if record_issns and journal_issns.intersection(record_issns):
            best = max(best, 3)

        candidates = [journal.get("name", ""), *journal.get("aliases", [])]
        normalized_candidates = {_normalize_name(name) for name in candidates if name}
        if normalized_candidates.intersection(normalized_names):
            best = max(best, 2)
        elif _has_partial_name_match(normalized_names, normalized_candidates):
            best = max(best, 1)

    return best


def _selected_journals(selected_journals: list[str] | None) -> list[dict[str, Any]]:
    journals = get_oa_journal_pack("li_sulfur")
    if selected_journals is None:
        return journals

    selected = {_normalize_name(name) for name in selected_journals if str(name).strip()}
    if not selected:
        return []

    filtered: list[dict[str, Any]] = []
    for journal in journals:
        names = [journal.get("name", ""), *journal.get("aliases", [])]
        normalized_names = {_normalize_name(name) for name in names if name}
        if selected.intersection(normalized_names):
            filtered.append(journal)
    return filtered


def _record_issns(record: dict[str, Any]) -> set[str]:
    values: list[Any] = []
    for key in ("issn", "issns", "ISSN", "ISSNs", "journal_issn", "journal_issns"):
        values.extend(_as_list(record.get(key)))

    primary_source = ((record.get("primary_location") or {}).get("source") or {})
    host_venue = record.get("host_venue") or {}
    journal_info = record.get("journalInfo") or {}
    bibjson = record.get("bibjson") or {}
    bibjson_journal = bibjson.get("journal") or {}

    for container in (primary_source, host_venue, journal_info, bibjson_journal):
        for key in ("issn", "issns", "issn_l", "ISSN"):
            values.extend(_as_list(container.get(key)))

    normalized = {normalize_issn(value) for value in values}
    normalized.discard("")
    return normalized


def _record_journal_names(record: dict[str, Any]) -> set[str]:
    values: list[Any] = []
    for key in (
        "journal",
        "journal_title",
        "journalTitle",
        "container-title",
        "container_title",
        "source_title",
        "publisher",
    ):
        values.extend(_as_list(record.get(key)))

    primary_source = ((record.get("primary_location") or {}).get("source") or {})
    host_venue = record.get("host_venue") or {}
    journal_info = record.get("journalInfo") or {}
    bibjson = record.get("bibjson") or {}
    bibjson_journal = bibjson.get("journal") or {}

    for container in (primary_source, host_venue, journal_info, bibjson_journal):
        for key in ("display_name", "name", "title", "journal", "journalTitle"):
            values.extend(_as_list(container.get(key)))

    return {str(value).strip() for value in values if str(value).strip()}


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


def _normalize_name(value: Any) -> str:
    text = str(value).lower().replace("&", " and ")
    return _WORD_RE.sub(" ", text).strip()


def _has_partial_name_match(record_names: set[str], journal_names: set[str]) -> bool:
    for record_name in record_names:
        for journal_name in journal_names:
            if len(record_name) < 5 or len(journal_name) < 5:
                continue
            if record_name in journal_name or journal_name in record_name:
                return True
    return False
