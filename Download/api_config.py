from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any


SOURCE_OPENALEX = "openalex"
SOURCE_EUROPE_PMC = "europe_pmc"
SOURCE_ARXIV = "arxiv"
SOURCE_CROSSREF = "crossref"
SOURCE_DOAJ = "doaj"
SOURCE_SEMANTIC_SCHOLAR = "semantic_scholar"

DEFAULT_TIMEOUT_SECONDS = 45.0
DEFAULT_MAX_RETRIES = 2
DEFAULT_RATE_LIMITS = {
    SOURCE_OPENALEX: 0.1,
    SOURCE_EUROPE_PMC: 0.1,
    SOURCE_ARXIV: 3.0,
    SOURCE_CROSSREF: 1.0,
    SOURCE_DOAJ: 0.5,
    SOURCE_SEMANTIC_SCHOLAR: 1.0,
}
DEFAULT_SINGLE_CONNECTION = {SOURCE_ARXIV}
SECRET_SOURCES = {
    SOURCE_OPENALEX,
    SOURCE_DOAJ,
    SOURCE_SEMANTIC_SCHOLAR,
}
PUBLIC_SOURCES = (
    SOURCE_OPENALEX,
    SOURCE_EUROPE_PMC,
    SOURCE_ARXIV,
    SOURCE_CROSSREF,
    SOURCE_DOAJ,
)
ALL_CONFIG_SOURCES = (*PUBLIC_SOURCES, SOURCE_SEMANTIC_SCHOLAR)
ENV_API_KEYS = {
    SOURCE_OPENALEX: "OMNILIT_OPENALEX_API_KEY",
    SOURCE_DOAJ: "OMNILIT_DOAJ_API_KEY",
    SOURCE_SEMANTIC_SCHOLAR: "OMNILIT_SEMANTIC_SCHOLAR_API_KEY",
}
ENV_CONTACT_EMAIL = "OMNILIT_CONTACT_EMAIL"
ENV_SOURCE_API_PROXY_URL = "OMNILIT_SOURCE_API_PROXY_URL"
ENV_DOAJ_PROXY_ENABLED = "OMNILIT_DOAJ_PREMIUM_VIA_PROXY"
PROXY_PATHS = {
    SOURCE_OPENALEX: "/search/openalex",
    SOURCE_DOAJ: "/search/doaj-premium",
    SOURCE_SEMANTIC_SCHOLAR: "/lookup/semantic-scholar",
}


@dataclass
class SourceApiConfig:
    enabled: bool = True
    base_url: str = ""
    rate_limit: float | None = None
    timeout: float | None = None
    max_retries: int | None = None
    api_key: str = ""
    contact_email: str = ""
    single_connection: bool = False

    def effective_rate_limit(self, source: str) -> float:
        default = DEFAULT_RATE_LIMITS.get(source, 0.0)
        if self.rate_limit is None:
            return default
        return max(0.0, float(self.rate_limit))

    def effective_timeout(self) -> float:
        if self.timeout is None:
            return DEFAULT_TIMEOUT_SECONDS
        return max(1.0, float(self.timeout))

    def effective_max_retries(self) -> int:
        if self.max_retries is None:
            return DEFAULT_MAX_RETRIES
        return max(0, int(self.max_retries))


@dataclass
class LiteratureApiSettings:
    openalex_api_key: str = ""
    crossref_mailto: str = ""
    europe_pmc_email: str = ""
    doaj_api_key: str = ""
    semantic_scholar_api_key: str = ""
    sources: dict[str, SourceApiConfig] = field(default_factory=dict)

    def source(self, source: str) -> SourceApiConfig:
        if source not in self.sources:
            self.sources[source] = default_source_config(source)
        config = self.sources[source]
        if source == SOURCE_OPENALEX and self.openalex_api_key and not config.api_key:
            config.api_key = self.openalex_api_key
        elif source == SOURCE_DOAJ and self.doaj_api_key and not config.api_key:
            config.api_key = self.doaj_api_key
        elif source == SOURCE_SEMANTIC_SCHOLAR and self.semantic_scholar_api_key and not config.api_key:
            config.api_key = self.semantic_scholar_api_key
        elif source == SOURCE_CROSSREF and self.crossref_mailto and not config.contact_email:
            config.contact_email = self.crossref_mailto
        elif source == SOURCE_EUROPE_PMC and self.europe_pmc_email and not config.contact_email:
            config.contact_email = self.europe_pmc_email
        return config

    def contact_for(self, source: str, fallback: str = "") -> str:
        config = self.source(source)
        return (config.contact_email or fallback or "").strip()

    def api_key_for(self, source: str) -> str:
        return (self.source(source).api_key or "").strip()


def default_source_config(source: str) -> SourceApiConfig:
    return SourceApiConfig(
        enabled=True,
        base_url=default_proxy_base_url(source),
        rate_limit=DEFAULT_RATE_LIMITS.get(source, 0.0),
        timeout=DEFAULT_TIMEOUT_SECONDS,
        max_retries=DEFAULT_MAX_RETRIES,
        single_connection=source in DEFAULT_SINGLE_CONNECTION,
    )


def default_proxy_base_url(source: str) -> str:
    proxy_root = os.getenv(ENV_SOURCE_API_PROXY_URL, "").strip().rstrip("/")
    if not proxy_root:
        return ""
    if source == SOURCE_DOAJ and os.getenv(ENV_DOAJ_PROXY_ENABLED, "").strip().lower() not in {"1", "true", "yes", "on"}:
        return ""
    path = PROXY_PATHS.get(source)
    return f"{proxy_root}{path}" if path else ""


def default_literature_api_settings(contact_email: str = "") -> LiteratureApiSettings:
    contact = (contact_email or os.getenv(ENV_CONTACT_EMAIL, "")).strip()
    settings = LiteratureApiSettings(
        openalex_api_key=os.getenv(ENV_API_KEYS[SOURCE_OPENALEX], "").strip(),
        crossref_mailto=contact,
        europe_pmc_email=contact,
        doaj_api_key=os.getenv(ENV_API_KEYS[SOURCE_DOAJ], "").strip(),
        semantic_scholar_api_key=os.getenv(ENV_API_KEYS[SOURCE_SEMANTIC_SCHOLAR], "").strip(),
        sources={source: default_source_config(source) for source in ALL_CONFIG_SOURCES},
    )
    settings.sources[SOURCE_OPENALEX].api_key = settings.openalex_api_key
    settings.sources[SOURCE_DOAJ].api_key = settings.doaj_api_key
    settings.sources[SOURCE_SEMANTIC_SCHOLAR].api_key = settings.semantic_scholar_api_key
    settings.sources[SOURCE_CROSSREF].contact_email = settings.crossref_mailto
    settings.sources[SOURCE_EUROPE_PMC].contact_email = settings.europe_pmc_email
    return settings


def source_settings_from_mapping(value: dict[str, Any] | None) -> dict[str, SourceApiConfig]:
    result: dict[str, SourceApiConfig] = {}
    raw = value or {}
    for source in ALL_CONFIG_SOURCES:
        source_raw = raw.get(source) if isinstance(raw, dict) else {}
        source_raw = source_raw if isinstance(source_raw, dict) else {}
        default = default_source_config(source)
        result[source] = SourceApiConfig(
            enabled=bool(source_raw.get("enabled", default.enabled)),
            base_url=str(source_raw.get("base_url") or source_raw.get("baseUrl") or default.base_url).strip(),
            rate_limit=_optional_float(source_raw.get("rate_limit", source_raw.get("rateLimit", default.rate_limit))),
            timeout=_optional_float(source_raw.get("timeout", default.timeout)),
            max_retries=_optional_int(source_raw.get("max_retries", source_raw.get("maxRetries", default.max_retries))),
            api_key=str(source_raw.get("api_key") or source_raw.get("apiKey") or "").strip(),
            contact_email=str(source_raw.get("contact_email") or source_raw.get("contactEmail") or "").strip(),
            single_connection=bool(source_raw.get("single_connection", source_raw.get("singleConnection", default.single_connection))),
        )
    return result


def settings_from_mapping(value: dict[str, Any] | None, contact_email: str = "") -> LiteratureApiSettings:
    raw = value or {}
    settings = default_literature_api_settings(contact_email)
    settings.sources = source_settings_from_mapping(raw.get("sources") if isinstance(raw, dict) else {})
    settings.openalex_api_key = str(raw.get("openalex_api_key") or raw.get("openalexApiKey") or settings.openalex_api_key).strip()
    settings.crossref_mailto = str(raw.get("crossref_mailto") or raw.get("crossrefMailto") or settings.crossref_mailto).strip()
    settings.europe_pmc_email = str(raw.get("europe_pmc_email") or raw.get("europePmcEmail") or settings.europe_pmc_email).strip()
    settings.doaj_api_key = str(raw.get("doaj_api_key") or raw.get("doajApiKey") or settings.doaj_api_key).strip()
    settings.semantic_scholar_api_key = str(raw.get("semantic_scholar_api_key") or raw.get("semanticScholarApiKey") or settings.semantic_scholar_api_key).strip()
    return settings


def public_mapping(settings: LiteratureApiSettings) -> dict[str, Any]:
    return {
        "crossrefMailto": settings.crossref_mailto,
        "europePmcEmail": settings.europe_pmc_email,
        "sources": {
            source: {
                "enabled": config.enabled,
                "baseUrl": config.base_url,
                "rateLimit": config.effective_rate_limit(source),
                "timeout": config.effective_timeout(),
                "maxRetries": config.effective_max_retries(),
                "singleConnection": config.single_connection,
            }
            for source, config in settings.sources.items()
        },
    }


def _optional_float(value: Any) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    return float(value)


def _optional_int(value: Any) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    return int(value)
