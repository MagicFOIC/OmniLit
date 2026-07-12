from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from Download.api_config import (
    ALL_CONFIG_SOURCES,
    ENV_API_KEYS,
    ENV_CONTACT_EMAIL,
    SECRET_SOURCES,
    SOURCE_ARXIV,
    SOURCE_CROSSREF,
    SOURCE_DOAJ,
    SOURCE_EUROPE_PMC,
    SOURCE_OPENALEX,
    SOURCE_SEMANTIC_SCHOLAR,
    LiteratureApiSettings,
    default_literature_api_settings,
    public_mapping,
    settings_from_mapping,
)

from .services import AccountStore, workdir_config
from .support import load_encrypted_key, write_encrypted_key


SOURCE_API_SETTING = "download/api_settings"
SOURCE_API_KEY_PASSWORD = "omnilit-literature-source-api-keys-v1"
SOURCE_KEY_FILES = {
    SOURCE_OPENALEX: "openalex.enc",
    SOURCE_DOAJ: "doaj.enc",
    SOURCE_SEMANTIC_SCHOLAR: "semantic_scholar.enc",
}
SOURCE_LABELS = {
    SOURCE_OPENALEX: "OpenAlex",
    SOURCE_EUROPE_PMC: "Europe PMC",
    SOURCE_ARXIV: "arXiv",
    SOURCE_CROSSREF: "Crossref",
    SOURCE_DOAJ: "DOAJ",
    SOURCE_SEMANTIC_SCHOLAR: "Semantic Scholar",
}


def api_key_dir(paths: Any, store: AccountStore) -> Path:
    return workdir_config(paths, store, "secrets", "download")


def api_key_path(paths: Any, store: AccountStore, source: str) -> Path:
    filename = SOURCE_KEY_FILES.get(source)
    if not filename:
        raise ValueError(f"Unsupported API key source: {source}")
    return api_key_dir(paths, store) / filename


def load_source_api_settings(paths: Any, store: AccountStore, contact_email: str = "") -> LiteratureApiSettings:
    raw = _load_public_settings(store)
    settings = settings_from_mapping(raw, contact_email or store.contact_email())
    _apply_secret_keys(paths, store, settings)
    return settings


def save_source_api_settings(paths: Any, store: AccountStore, settings_map: dict[str, Any], contact_email: str = "") -> LiteratureApiSettings:
    incoming = dict(settings_map or {})
    existing = load_source_api_settings(paths, store, contact_email)
    public = _load_public_settings(store)

    crossref_mailto = str(incoming.get("crossrefMailto") or incoming.get("crossref_mailto") or "").strip()
    europe_pmc_email = str(incoming.get("europePmcEmail") or incoming.get("europe_pmc_email") or "").strip()
    public["crossrefMailto"] = crossref_mailto or str(contact_email or store.contact_email() or os.getenv(ENV_CONTACT_EMAIL, "")).strip()
    public["europePmcEmail"] = europe_pmc_email or str(contact_email or store.contact_email() or os.getenv(ENV_CONTACT_EMAIL, "")).strip()
    public_sources = dict(public.get("sources") or {})
    incoming_sources = incoming.get("sources") if isinstance(incoming.get("sources"), dict) else {}
    for source in ALL_CONFIG_SOURCES:
        current = dict(public_sources.get(source) or {})
        raw_source = incoming_sources.get(source) if isinstance(incoming_sources, dict) else {}
        raw_source = raw_source if isinstance(raw_source, dict) else {}
        for key in ("enabled", "baseUrl", "base_url", "rateLimit", "rate_limit", "timeout", "maxRetries", "max_retries", "singleConnection", "single_connection"):
            if key in raw_source:
                current[key] = raw_source[key]
        public_sources[source] = current
    public["sources"] = public_sources
    store.set_setting(SOURCE_API_SETTING, json.dumps(public, ensure_ascii=False, sort_keys=True))

    for source in SECRET_SOURCES:
        key_value = _incoming_key(incoming, source)
        if key_value:
            write_encrypted_key(api_key_path(paths, store, source), key_value, SOURCE_API_KEY_PASSWORD)

    refreshed = load_source_api_settings(paths, store, contact_email)
    for source in SECRET_SOURCES:
        if not refreshed.api_key_for(source) and existing.api_key_for(source):
            refreshed.source(source).api_key = existing.api_key_for(source)
    return refreshed


def clear_source_api_key(paths: Any, store: AccountStore, source: str) -> bool:
    if source not in SECRET_SOURCES:
        return False
    path = api_key_path(paths, store, source)
    if path.exists():
        path.unlink()
    return True


def source_api_statuses(paths: Any, store: AccountStore, contact_email: str = "") -> list[dict[str, Any]]:
    settings = load_source_api_settings(paths, store, contact_email)
    result: list[dict[str, Any]] = []
    for source in ALL_CONFIG_SOURCES:
        config = settings.source(source)
        configured = _source_configured(source, settings)
        result.append(
            {
                "source": source,
                "key": source,
                "label": SOURCE_LABELS.get(source, source),
                "enabled": config.enabled,
                "configured": configured,
                "hasKey": bool(settings.api_key_for(source)),
                "maskedKey": "********" if settings.api_key_for(source) else "",
                "status": "configured" if configured else "not_configured",
                "message": _status_message(source, configured),
            }
        )
    return result


def public_source_api_settings(paths: Any, store: AccountStore, contact_email: str = "") -> dict[str, Any]:
    settings = load_source_api_settings(paths, store, contact_email)
    result = public_mapping(settings)
    for source in SECRET_SOURCES:
        result[f"{_camel_source(source)}HasKey"] = bool(settings.api_key_for(source))
        result[f"{_camel_source(source)}MaskedKey"] = "********" if settings.api_key_for(source) else ""
    return result


def _load_public_settings(store: AccountStore) -> dict[str, Any]:
    try:
        raw = json.loads(store.setting(SOURCE_API_SETTING, "{}"))
    except (TypeError, json.JSONDecodeError):
        raw = {}
    return raw if isinstance(raw, dict) else {}


def _apply_secret_keys(paths: Any, store: AccountStore, settings: LiteratureApiSettings) -> None:
    for source in SECRET_SOURCES:
        encrypted = _read_saved_key(paths, store, source)
        env_value = os.getenv(ENV_API_KEYS[source], "").strip()
        value = encrypted or env_value
        if source == SOURCE_OPENALEX:
            settings.openalex_api_key = value
        elif source == SOURCE_DOAJ:
            settings.doaj_api_key = value
        elif source == SOURCE_SEMANTIC_SCHOLAR:
            settings.semantic_scholar_api_key = value
        settings.source(source).api_key = value


def _read_saved_key(paths: Any, store: AccountStore, source: str) -> str:
    try:
        path = api_key_path(paths, store, source)
        if not path.exists():
            return ""
        return load_encrypted_key(path, SOURCE_API_KEY_PASSWORD).strip()
    except Exception:
        return ""


def _incoming_key(settings_map: dict[str, Any], source: str) -> str:
    names = {
        SOURCE_OPENALEX: ("openalexApiKey", "openalex_api_key"),
        SOURCE_DOAJ: ("doajApiKey", "doaj_api_key"),
        SOURCE_SEMANTIC_SCHOLAR: ("semanticScholarApiKey", "semantic_scholar_api_key"),
    }.get(source, ())
    for name in names:
        value = str(settings_map.get(name) or "").strip()
        if value:
            return value
    sources = settings_map.get("sources") if isinstance(settings_map.get("sources"), dict) else {}
    source_map = sources.get(source) if isinstance(sources, dict) else {}
    if isinstance(source_map, dict):
        return str(source_map.get("apiKey") or source_map.get("api_key") or "").strip()
    return ""


def _source_configured(source: str, settings: LiteratureApiSettings) -> bool:
    if source in {SOURCE_OPENALEX, SOURCE_DOAJ}:
        return bool(settings.api_key_for(source))
    if source == SOURCE_CROSSREF:
        return bool(settings.contact_for(source, settings.crossref_mailto))
    if source == SOURCE_EUROPE_PMC:
        return bool(settings.contact_for(source, settings.europe_pmc_email))
    if source == SOURCE_ARXIV:
        return True
    if source == SOURCE_SEMANTIC_SCHOLAR:
        return bool(settings.api_key_for(source))
    return False


def _status_message(source: str, configured: bool) -> str:
    if source == SOURCE_ARXIV:
        return "No API key; enforced 3 second single-connection rate limit."
    if source == SOURCE_OPENALEX and not configured:
        return "Optional for small tests; recommended for production OpenAlex calls."
    if source == SOURCE_DOAJ and not configured:
        return "Public search works anonymously; premium metadata key is optional."
    if source in {SOURCE_CROSSREF, SOURCE_EUROPE_PMC} and not configured:
        return "Uses the global contact email when configured."
    if source == SOURCE_SEMANTIC_SCHOLAR and not configured:
        return "Optional OA PDF fallback key is not configured."
    return "Configured." if configured else "Not configured."


def _camel_source(source: str) -> str:
    if source == SOURCE_OPENALEX:
        return "openalex"
    if source == SOURCE_DOAJ:
        return "doaj"
    if source == SOURCE_SEMANTIC_SCHOLAR:
        return "semanticScholar"
    return source
