# Copyright (c) 2026 magicfoic. All rights reserved.

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

try:
    from .journal_registry import get_oa_journal_pack, normalize_issn
    from .topic_packs import get_topic_pack
except ImportError:  # pragma: no cover - supports direct script-style imports.
    from journal_registry import get_oa_journal_pack, normalize_issn
    from topic_packs import get_topic_pack


_DASH_RE = re.compile(r"[\u2010\u2011\u2012\u2013\u2014\u2212]")
_SPACE_RE = re.compile(r"\s+")
_WORD_RE = re.compile(r"[^a-z0-9]+")
_LI_S_RE = re.compile(r"\b(lithium\s*[- ]\s*sulfur|li\s*[- ]\s*s|polysulfides?)\b", re.IGNORECASE)


def normalize_user_keywords(keywords: list[str]) -> list[str]:
    """Normalize user-entered keyword lines while preserving their intent."""
    normalized: list[str] = []
    seen: set[str] = set()
    for keyword in keywords or []:
        text = _SPACE_RE.sub(" ", _DASH_RE.sub("-", str(keyword or "")).strip())
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(text)
    return normalized


def build_topic_pack_from_keywords(keywords: list[str]) -> dict[str, Any]:
    """Build an auto topic pack from user keywords."""
    exact_terms = normalize_user_keywords(keywords)
    normalized_terms = _unique(
        term
        for keyword in exact_terms
        for term in _keyword_variants(keyword)
    )
    phrase_terms = _unique([*exact_terms, *normalized_terms])
    optional_expanded_terms: list[str] = []
    uses_li_sulfur_preset = _looks_like_li_sulfur(phrase_terms)
    if uses_li_sulfur_preset:
        optional_expanded_terms = [
            term for term in get_topic_pack("li_sulfur") if _term_key(term) not in {_term_key(item) for item in phrase_terms}
        ]

    return {
        "name": "auto",
        "type": "auto",
        "exact_terms": exact_terms,
        "normalized_terms": normalized_terms,
        "phrase_terms": phrase_terms,
        "optional_expanded_terms": optional_expanded_terms,
        "uses_li_sulfur_preset": uses_li_sulfur_preset,
    }


def build_journal_pack_from_records(records: list[dict], max_journals: int = 20) -> dict[str, Any]:
    """Build an OA journal recommendation pack from search records."""
    journals: dict[str, dict[str, Any]] = {}
    scores: defaultdict[str, float] = defaultdict(float)
    counts: defaultdict[str, int] = defaultdict(int)

    for record in records or []:
        if not _is_oa_record(record):
            continue
        name = _record_journal_name(record)
        issns = _record_issns(record)
        if not name and not issns:
            continue
        key = _journal_key(name, issns)
        topic_score = float(record.get("topic_score") or record.get("relevance_score") or 0)
        weight = 1.0 + max(topic_score, 0.0)
        counts[key] += 1
        scores[key] += weight
        current = journals.setdefault(
            key,
            {
                "name": name or (issns[0] if issns else "Unknown journal"),
                "issns": [],
                "count": 0,
                "score": 0.0,
            },
        )
        if name and not current.get("name"):
            current["name"] = name
        current["issns"] = _unique([*current.get("issns", []), *issns])

    ranked = sorted(journals.items(), key=lambda item: (-scores[item[0]], -counts[item[0]], item[1]["name"].casefold()))
    selected: list[dict[str, Any]] = []
    for key, journal in ranked[: max(0, max_journals)]:
        selected.append(
            {
                **journal,
                "count": counts[key],
                "score": round(scores[key], 3),
            }
        )

    return {"name": "auto", "type": "auto", "journals": selected}


def resolve_topic_pack(config: Any, keywords: list[str]) -> dict[str, Any]:
    """Resolve auto, preset, or custom topic pack settings."""
    pack_name = str(getattr(config, "topic_pack", None) or "auto").strip() or "auto"
    if pack_name == "li_sulfur":
        terms = get_topic_pack("li_sulfur")
        return {
            "name": "li_sulfur",
            "type": "preset",
            "exact_terms": terms,
            "normalized_terms": _unique(term for keyword in terms for term in _keyword_variants(keyword)),
            "phrase_terms": terms,
            "optional_expanded_terms": [],
            "uses_li_sulfur_preset": True,
        }
    if pack_name == "custom":
        pack = build_topic_pack_from_keywords(keywords)
        pack["name"] = "custom"
        pack["type"] = "custom"
        return pack
    return build_topic_pack_from_keywords(keywords)


def resolve_journal_pack(config: Any, records: list[dict]) -> dict[str, Any]:
    """Resolve auto, preset, or custom OA journal pack settings."""
    pack_name = str(getattr(config, "journal_pack", None) or "auto").strip() or "auto"
    if pack_name == "li_sulfur":
        return {"name": "li_sulfur", "type": "preset", "journals": get_oa_journal_pack("li_sulfur")}
    if pack_name == "custom":
        journals = [
            {"name": str(name).strip(), "issns": [], "count": 0, "score": 0.0}
            for name in (getattr(config, "selected_journals", None) or [])
            if str(name).strip()
        ]
        return {"name": "custom", "type": "custom", "journals": journals}
    return build_journal_pack_from_records(records)


def journal_pack_match_score(record: dict[str, Any], journal_pack: dict[str, Any] | None) -> int:
    """Score whether a record matches a resolved journal pack."""
    if not journal_pack:
        return 0
    record_names = {_normalize_name(name) for name in _record_journal_names(record)}
    record_issns = set(_record_issns(record))
    best = 0
    for journal in journal_pack.get("journals", []) or []:
        journal_issns = {normalize_issn(value) for value in journal.get("issns", [])}
        journal_issns.discard("")
        if record_issns and journal_issns.intersection(record_issns):
            best = max(best, 3)

        names = [journal.get("name", ""), *journal.get("aliases", [])]
        journal_names = {_normalize_name(name) for name in names if str(name).strip()}
        if record_names.intersection(journal_names):
            best = max(best, 2)
        elif _has_partial_name_match(record_names, journal_names):
            best = max(best, 1)
    return best


def _keyword_variants(keyword: str) -> list[str]:
    text = _SPACE_RE.sub(" ", _DASH_RE.sub("-", keyword).strip())
    variants = {text, text.replace("-", " ")}
    lower = text.casefold()
    if lower.endswith("ies"):
        variants.add(text[:-3] + "y")
        variants.add(text.replace("-", " ")[:-3] + "y")
    elif lower.endswith("s") and len(text) > 3:
        variants.add(text[:-1])
        variants.add(text.replace("-", " ")[:-1])
    if "polysulfides" in lower:
        variants.add(re.sub("polysulfides", "polysulfide", text, flags=re.IGNORECASE))
    if "lithium-sulfur" in lower:
        variants.add(text.replace("lithium-sulfur", "lithium sulfur"))
        variants.add(text.replace("lithium-sulfur", "Li-S"))
    return _unique(variants)


def _looks_like_li_sulfur(terms: list[str]) -> bool:
    return any(_LI_S_RE.search(term or "") for term in terms)


def _is_oa_record(record: dict[str, Any]) -> bool:
    open_access = record.get("open_access") or {}
    return bool(
        record.get("is_oa")
        or open_access.get("is_oa")
        or str(open_access.get("oa_status") or "").casefold() in {"gold", "green", "hybrid", "bronze"}
        or record.get("doaj_fulltext_links")
    )


def _record_journal_name(record: dict[str, Any]) -> str:
    names = _record_journal_names(record)
    return names[0] if names else ""


def _record_journal_names(record: dict[str, Any]) -> list[str]:
    values: list[Any] = []
    for key in ("journal", "journal_title", "journalTitle", "container-title", "container_title", "source_title"):
        values.extend(_as_list(record.get(key)))

    primary_source = ((record.get("primary_location") or {}).get("source") or {})
    host_venue = record.get("host_venue") or {}
    journal_info = record.get("journalInfo") or {}
    bibjson = record.get("bibjson") or {}
    bibjson_journal = bibjson.get("journal") or {}

    for container in (primary_source, host_venue, journal_info, bibjson_journal):
        for key in ("display_name", "name", "title", "journal", "journalTitle"):
            values.extend(_as_list(container.get(key)))

    return _unique(str(value).strip() for value in values if str(value).strip())


def _record_issns(record: dict[str, Any]) -> list[str]:
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

    return _unique(normalize_issn(value) for value in values if normalize_issn(value))


def _journal_key(name: str, issns: list[str]) -> str:
    return f"issn:{issns[0]}" if issns else f"name:{_normalize_name(name)}"


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


def _normalize_name(value: Any) -> str:
    return _WORD_RE.sub(" ", str(value).lower().replace("&", " and ")).strip()


def _term_key(value: Any) -> str:
    return _normalize_name(_DASH_RE.sub("-", str(value)))


def _has_partial_name_match(record_names: set[str], journal_names: set[str]) -> bool:
    for record_name in record_names:
        for journal_name in journal_names:
            if len(record_name) < 5 or len(journal_name) < 5:
                continue
            if record_name in journal_name or journal_name in record_name:
                return True
    return False


def _unique(values: Any) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result
