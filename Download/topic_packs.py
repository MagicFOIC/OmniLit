# Copyright (c) 2026 magicfoic. All rights reserved.

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

try:
    from .journal_registry import is_whitelisted_journal
except ImportError:  # pragma: no cover - allows direct script-style imports.
    from journal_registry import is_whitelisted_journal


_TOPIC_PACKS: dict[str, list[str]] = {
    "li_sulfur": [
        "lithium-sulfur batteries",
        "lithium sulfur battery",
        "Li-S batteries",
        "lithium polysulfides",
        "polysulfides",
        "polysulfide shuttle",
        "shuttle effect",
        "LiPS",
        "Li2S6",
        "Li2S8",
        "sulfur cathode",
        "functional separator",
        "polysulfide adsorption",
        "polysulfide conversion",
        "catalytic conversion of polysulfides",
        "sulfur host",
        "carbon host",
        "electrocatalyst",
        "redox mediator",
    ],
}

_LITHIUM_SULFUR_TITLE_RE = re.compile(
    r"\b(lithium\s*[- ]\s*sulfur|li\s*[- ]\s*s)\s+(batter(?:y|ies)|cell|cells)?\b|"
    r"\b(batter(?:y|ies)|cell|cells)\s+(?:for|in|of)?\s*(lithium\s*[- ]\s*sulfur|li\s*[- ]\s*s)\b",
    re.IGNORECASE,
)
_POLYSULFIDE_RE = re.compile(r"\b(poly\s*sulfides?|polysulfides?|lips)\b", re.IGNORECASE)
_SHUTTLE_RE = re.compile(r"\b(shuttle effect|polysulfide shuttle|polysulfide shuttling)\b", re.IGNORECASE)
_BATTERY_COMPONENT_RE = re.compile(r"\b(sulfur cathode|functional separator|separator|electrolyte)\b", re.IGNORECASE)
_CATALYSIS_RE = re.compile(
    r"\b(adsorption|catalysis|catalytic conversion|electrocatalyst|electrocatalysis)\b",
    re.IGNORECASE,
)
_LITHIUM_SULFIDE_RE = re.compile(r"\bli\s*2\s*s\s*(?:4|6|8)?\b", re.IGNORECASE)


def get_topic_pack(pack_name: str = "li_sulfur") -> list[str]:
    """Return a copy of the configured topic terms."""
    try:
        return deepcopy(_TOPIC_PACKS[pack_name])
    except KeyError as exc:
        raise ValueError(f"Unknown topic pack: {pack_name}") from exc


def score_topic_relevance(record: dict[str, Any], topic_pack: str | dict[str, Any] = "li_sulfur") -> int:
    """Score record relevance for a preset or generated topic pack."""
    if isinstance(topic_pack, dict):
        if topic_pack.get("uses_li_sulfur_preset"):
            return _score_li_sulfur(record)
        return _score_generic_pack(record, topic_pack)

    if topic_pack != "li_sulfur":
        get_topic_pack(topic_pack)
        return 0

    return _score_li_sulfur(record)


def _score_li_sulfur(record: dict[str, Any]) -> int:
    """Score Li-S battery relevance from title, abstract, formulas, and OA journal fit."""

    title = _normalized_text(_first_text(record.get("title") or record.get("display_name")))
    abstract = _normalized_text(
        _first_text(
            record.get("abstract")
            or record.get("abstract_text")
            or record.get("abstractText")
            or record.get("description")
            or _abstract_from_inverted_index(record.get("abstract_inverted_index"))
        )
    )
    full_text = f"{title} {abstract}".strip()

    score = 0
    if _LITHIUM_SULFUR_TITLE_RE.search(title):
        score += 5
    if _POLYSULFIDE_RE.search(full_text):
        score += 4
    if _SHUTTLE_RE.search(full_text):
        score += 3
    if _BATTERY_COMPONENT_RE.search(full_text):
        score += 2
    if _CATALYSIS_RE.search(full_text):
        score += 2
    if _LITHIUM_SULFIDE_RE.search(full_text):
        score += 2
    if is_whitelisted_journal(record):
        score += 1
    return score


def _score_generic_pack(record: dict[str, Any], topic_pack: dict[str, Any]) -> int:
    title = _normalized_text(_first_text(record.get("title") or record.get("display_name"))).casefold()
    abstract = _normalized_text(
        _first_text(
            record.get("abstract")
            or record.get("abstract_text")
            or record.get("abstractText")
            or record.get("description")
            or _abstract_from_inverted_index(record.get("abstract_inverted_index"))
        )
    ).casefold()
    full_text = f"{title} {abstract}".strip()
    score = 0
    for term in topic_pack.get("phrase_terms", []) or []:
        normalized = _normalized_text(str(term)).casefold()
        if not normalized:
            continue
        if normalized in title:
            score = max(score, 6)
        elif normalized in abstract:
            score = max(score, 4)
    optional_hits = 0
    for term in topic_pack.get("optional_expanded_terms", []) or []:
        normalized = _normalized_text(str(term)).casefold()
        if normalized and normalized in full_text:
            optional_hits += 1
    return score + min(optional_hits * 2, 6)


def _first_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return str(value[0]) if value else ""
    return str(value)


def _normalized_text(value: str) -> str:
    return (
        value.replace("\u2010", "-")
        .replace("\u2011", "-")
        .replace("\u2012", "-")
        .replace("\u2013", "-")
        .replace("\u2014", "-")
        .replace("\u2212", "-")
    )


def _abstract_from_inverted_index(value: Any) -> str:
    if not isinstance(value, dict):
        return ""

    words: list[tuple[int, str]] = []
    for word, indexes in value.items():
        if not isinstance(indexes, list):
            continue
        for index in indexes:
            if isinstance(index, int):
                words.append((index, str(word)))
    return " ".join(word for _index, word in sorted(words))
