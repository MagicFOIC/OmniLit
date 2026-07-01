from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from Download import literature_download_core as core
from Download.api_config import (
    ENV_DOAJ_PROXY_ENABLED,
    ENV_SOURCE_API_PROXY_URL,
    SOURCE_ARXIV,
    SOURCE_DOAJ,
    SOURCE_OPENALEX,
    SOURCE_SEMANTIC_SCHOLAR,
    LiteratureApiSettings,
    default_source_config,
)
from omnilit_qt.paths import AppPaths
from omnilit_qt.services import AccountStore, build_download_config
from omnilit_qt.source_api_config import (
    SOURCE_API_SETTING,
    api_key_path,
    clear_source_api_key,
    load_source_api_settings,
    save_source_api_settings,
    source_api_statuses,
)


ROOT = Path(__file__).resolve().parent.parent


class Response:
    status_code = 200
    headers: dict[str, str] = {}
    text = "{}"

    @staticmethod
    def raise_for_status() -> None:
        return None

    @staticmethod
    def json() -> dict:
        return {"results": [], "meta": {"next_cursor": None}, "message": {"items": []}, "total": 0}


class RecordingSession:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.headers = {"User-Agent": "OmniLit/1.0"}

    def get(self, url: str, **kwargs):
        self.calls.append({"url": url, **kwargs})
        return Response()


class SourceApiConfigTests(unittest.TestCase):
    def test_openalex_key_falls_back_to_standard_env_name(self) -> None:
        with patch.dict("os.environ", {"OPENALEX_API_KEY": "standard-openalex"}, clear=True):
            settings = core.default_literature_api_settings("qa@example.com")

        self.assertEqual(settings.openalex_api_key, "standard-openalex")
        self.assertEqual(settings.source(SOURCE_OPENALEX).api_key, "standard-openalex")

    def test_openalex_omnilit_env_name_takes_precedence(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "OMNILIT_OPENALEX_API_KEY": "omnilit-openalex",
                "OPENALEX_API_KEY": "standard-openalex",
            },
            clear=True,
        ):
            settings = core.default_literature_api_settings("qa@example.com")

        self.assertEqual(settings.openalex_api_key, "omnilit-openalex")
        self.assertEqual(settings.source(SOURCE_OPENALEX).api_key, "omnilit-openalex")

    def test_openalex_key_is_added_to_request_params(self) -> None:
        session = RecordingSession()
        settings = LiteratureApiSettings(openalex_api_key="oa-secret", sources={SOURCE_OPENALEX: default_source_config(SOURCE_OPENALEX)})
        config = core.CrawlConfig(email="qa@example.com", api_settings=settings, request_delay=0)

        core.search_openalex(session, "battery", config)

        params = session.calls[0]["params"]
        self.assertEqual(params["api_key"], "oa-secret")
        self.assertEqual(params["mailto"], "qa@example.com")

    def test_proxy_url_defaults_route_sensitive_sources_without_client_key(self) -> None:
        with patch.dict(
            "os.environ",
            {
                ENV_SOURCE_API_PROXY_URL: "https://proxy.omnilit.test/source",
                ENV_DOAJ_PROXY_ENABLED: "1",
                "OMNILIT_OPENALEX_API_KEY": "client-openalex",
                "OMNILIT_DOAJ_API_KEY": "client-doaj",
                "OMNILIT_SEMANTIC_SCHOLAR_API_KEY": "client-s2",
            },
            clear=True,
        ):
            settings = core.default_literature_api_settings("qa@example.com")

        self.assertEqual(settings.source(SOURCE_OPENALEX).base_url, "https://proxy.omnilit.test/source/search/openalex")
        self.assertEqual(settings.source(SOURCE_SEMANTIC_SCHOLAR).base_url, "https://proxy.omnilit.test/source/lookup/semantic-scholar")
        self.assertEqual(settings.source(SOURCE_DOAJ).base_url, "https://proxy.omnilit.test/source/search/doaj-premium")

        session = RecordingSession()
        config = core.CrawlConfig(email="qa@example.com", api_settings=settings, request_delay=0)
        core.search_openalex(session, "battery", config)
        self.assertEqual(session.calls[0]["url"], "https://proxy.omnilit.test/source/search/openalex")
        self.assertNotIn("api_key", session.calls[0]["params"])

    def test_crossref_mailto_is_added_to_params_and_user_agent(self) -> None:
        session = RecordingSession()
        settings = LiteratureApiSettings(crossref_mailto="crossref@example.com")
        config = core.CrawlConfig(email="qa@example.com", api_settings=settings, request_delay=0)

        core.search_crossref(session, "battery", config)

        params = session.calls[0]["params"]
        headers = session.calls[0]["headers"]
        self.assertEqual(params["mailto"], "crossref@example.com")
        self.assertIn("mailto:crossref@example.com", headers["User-Agent"])

    def test_doaj_key_is_optional(self) -> None:
        session = RecordingSession()
        config = core.CrawlConfig(api_settings=LiteratureApiSettings(), request_delay=0)

        core.search_doaj(session, "battery", config)

        self.assertNotIn("api_key", session.calls[0]["params"])

        keyed = RecordingSession()
        settings = LiteratureApiSettings(doaj_api_key="doaj-secret", sources={SOURCE_DOAJ: default_source_config(SOURCE_DOAJ)})
        core.search_doaj(keyed, "battery", core.CrawlConfig(api_settings=settings, request_delay=0))
        self.assertEqual(keyed.calls[0]["params"]["api_key"], "doaj-secret")

    def test_semantic_scholar_uses_configured_key_not_environment(self) -> None:
        class SemanticResponse(Response):
            @staticmethod
            def json() -> dict:
                return {"isOpenAccess": True, "openAccessPdf": {"url": "https://s2.test/open.pdf"}}

        class SemanticSession(RecordingSession):
            def get(self, url: str, **kwargs):
                self.calls.append({"url": url, **kwargs})
                return SemanticResponse()

        settings = LiteratureApiSettings(semantic_scholar_api_key="s2-saved", sources={SOURCE_SEMANTIC_SCHOLAR: default_source_config(SOURCE_SEMANTIC_SCHOLAR)})
        session = SemanticSession()
        with patch.dict("os.environ", {"OMNILIT_SEMANTIC_SCHOLAR_API_KEY": "s2-env"}):
            result = core.fetch_semantic_scholar_pdf_candidates(
                session,
                {"doi": "10.1234/example"},
                core.CrawlConfig(api_settings=settings, request_delay=0),
            )

        self.assertEqual(result, ["https://s2.test/open.pdf"])
        self.assertEqual(session.calls[0]["headers"]["x-api-key"], "s2-saved")

    def test_arxiv_source_rate_limiter_waits_at_least_three_seconds(self) -> None:
        core._SOURCE_RATE_LIMIT_LAST.clear()
        core._SOURCE_RATE_LIMIT_LAST[SOURCE_ARXIV] = core.time.monotonic()
        sleeps: list[float] = []

        with patch.object(core, "sleep_or_stop", side_effect=lambda seconds, _config: sleeps.append(seconds) and False):
            self.assertFalse(core.enforce_source_rate_limit(SOURCE_ARXIV, core.CrawlConfig()))

        self.assertTrue(sleeps)
        self.assertGreaterEqual(sleeps[0], 2.9)

    def test_redaction_masks_api_keys_in_errors(self) -> None:
        text = core.redact_sensitive_text("https://api.test/search?api_key=secret-value&x=1 token:abc")

        self.assertNotIn("secret-value", text)
        self.assertNotIn("abc", text)
        self.assertIn("api_key=***", text)

    def test_saved_form_config_does_not_include_sensitive_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            paths = AppPaths(ROOT, Path(temp) / "data", ROOT)
            store = AccountStore(Path(temp) / "accounts.sqlite3")
            save_source_api_settings(
                paths,
                store,
                {
                    "openalexApiKey": "oa-secret",
                    "doajApiKey": "doaj-secret",
                    "crossrefMailto": "crossref@example.com",
                },
                "qa@example.com",
            )

            saved = store.setting(SOURCE_API_SETTING, "{}")
            self.assertNotIn("oa-secret", saved)
            self.assertNotIn("doaj-secret", saved)
            self.assertTrue(api_key_path(paths, store, SOURCE_OPENALEX).exists())

            loaded = load_source_api_settings(paths, store, "qa@example.com")
            self.assertEqual(loaded.openalex_api_key, "oa-secret")
            statuses = source_api_statuses(paths, store, "qa@example.com")
            openalex_status = next(item for item in statuses if item["source"] == SOURCE_OPENALEX)
            self.assertTrue(openalex_status["hasKey"])
            self.assertEqual(openalex_status["maskedKey"], "********")
            self.assertNotIn("oa-secret", json.dumps(statuses))

            self.assertTrue(clear_source_api_key(paths, store, SOURCE_OPENALEX))
            self.assertFalse(api_key_path(paths, store, SOURCE_OPENALEX).exists())

    def test_build_download_config_accepts_api_settings(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            paths = AppPaths(ROOT, Path(temp) / "data", ROOT)
            settings = LiteratureApiSettings(openalex_api_key="oa-secret")
            _core, config = build_download_config(paths, {}, lambda: False, lambda *_args: None, api_settings=settings)

        self.assertIs(config.api_settings, settings)


if __name__ == "__main__":
    unittest.main()
