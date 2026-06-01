from __future__ import annotations

import base64
import hashlib
import io
import json
import re
import sqlite3
import sys
import tempfile
import threading
import unittest
from contextlib import closing
from datetime import date
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication, QUrl
from PySide6.QtGui import QImage
from PySide6.QtQml import QQmlComponent, QQmlEngine

from omnilit_qt.controllers import (
    AppController,
    AuthController,
    PreferencesController,
    DEFAULT_UPDATE_MANIFEST_URL,
    DOWNLOAD_FORM_SETTING,
    TRANSLATION_FORM_SETTING,
    DownloadController,
    TranslationController,
    UpdateController,
)
from omnilit_qt.app import _center_window_frame_on_current_screen, _center_window_on_cursor_screen, _shutdown_background_tasks
from omnilit_qt.background_tasks import ManagedWorker
from omnilit_qt.date_utils import month_grid, parse_iso_date, shift_month
from omnilit_qt.i18n import LocaleController, tr
from omnilit_qt.paths import AppPaths, MIGRATION_MARKER, _macos_bundle_sibling
from omnilit_qt.secrets import PLAIN_PREFIX, protect_secret, unprotect_secret
from omnilit_qt.services import AccountStore, PASSWORD_SCHEME, build_download_config, import_resource_module
from omnilit_qt.support import decrypt_api_key, encrypt_api_key, glossary_catalog, load_encrypted_key, write_encrypted_key


ROOT = Path(__file__).resolve().parent.parent


class AppPathsTests(unittest.TestCase):
    def test_migrate_legacy_data_copies_without_overwriting(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            legacy = base / "legacy"
            data = base / "data"
            resource = base / "resource"
            (legacy / "Download").mkdir(parents=True)
            (legacy / "Download" / "pdfs").mkdir(parents=True)
            (legacy / "Translate").mkdir(parents=True)
            (legacy / "accounts.sqlite3").write_text("legacy-db", encoding="utf-8")
            (legacy / "Download" / "crawl_state.json").write_text("legacy-state", encoding="utf-8")
            (legacy / "Download" / "pdfs" / "legacy.pdf").write_text("legacy-pdf", encoding="utf-8")
            (legacy / "Translate" / "APIKey.enc").write_text("legacy-key", encoding="utf-8")
            data.mkdir()
            (data / "accounts.sqlite3").write_text("existing-db", encoding="utf-8")
            (data / "Download" / "pdfs").mkdir(parents=True)
            (data / "Download" / "pdfs" / "keep.pdf").write_text("existing-pdf", encoding="utf-8")
            paths = AppPaths(resource, data, legacy)

            copied = paths.migrate_legacy_data()

            self.assertEqual((data / "accounts.sqlite3").read_text(encoding="utf-8"), "existing-db")
            self.assertEqual((data / "Download" / "crawl_state.json").read_text(encoding="utf-8"), "legacy-state")
            self.assertEqual((data / "Download" / "pdfs" / "legacy.pdf").read_text(encoding="utf-8"), "legacy-pdf")
            self.assertEqual((data / "Download" / "pdfs" / "keep.pdf").read_text(encoding="utf-8"), "existing-pdf")
            self.assertIn("Download/crawl_state.json", copied)
            self.assertTrue((data / MIGRATION_MARKER).exists())
            self.assertEqual(paths.migrate_legacy_data(), [])

    def test_environment_override_has_priority(self) -> None:
        with tempfile.TemporaryDirectory() as temp, patch.dict("os.environ", {"OMNILIT_DATA_DIR": temp}):
            self.assertEqual(AppPaths.discover().data_root, Path(temp).resolve())

    def test_data_directory_initialization_does_not_create_legacy_translation_out(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            paths = AppPaths(root / "resource", root / "data", ())
            paths.ensure_data_dirs()
            self.assertTrue(paths.data("Translate", "pdf").is_dir())
            self.assertFalse(paths.data("Translate", "out").exists())

    def test_macos_bundle_uses_app_sibling(self) -> None:
        executable = Path("/Applications/OmniLit.app/Contents/MacOS/OmniLit")
        self.assertEqual(_macos_bundle_sibling(executable), Path("/Applications"))

    def test_writable_glossary_directory_keeps_custom_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            paths = AppPaths(ROOT, Path(temp), ())
            paths.ensure_data_dirs()
            custom = paths.glossary_dir / "custom.csv"
            custom.write_text("source,target\nalpha,阿尔法\n", encoding="utf-8")
            paths.ensure_data_dirs()
            names = {item["name"] for item in glossary_catalog(paths.glossary_dir)}
            self.assertIn("00_general_academic.csv", names)
            self.assertIn("custom.csv", names)


class AccountStoreTests(unittest.TestCase):
    def test_register_and_login_use_versioned_pbkdf2(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = AccountStore(Path(temp) / "accounts.sqlite3")
            store.register("alice", "secret12")
            self.assertTrue(store.login("alice", "secret12"))
            with closing(sqlite3.connect(store.db_path)) as conn:
                encoded = conn.execute("SELECT password_hash FROM users WHERE username = 'alice'").fetchone()[0]
            self.assertTrue(str(encoded).startswith(PASSWORD_SCHEME + "$"))
            self.assertEqual(store.setting("remember_username"), "alice")

    def test_legacy_hash_is_upgraded_after_login(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = AccountStore(Path(temp) / "accounts.sqlite3")
            salt = "abcd"
            legacy_hash = hashlib.sha256(("secret12" + salt).encode("utf-8")).hexdigest()
            with closing(sqlite3.connect(store.db_path)) as conn:
                conn.execute(
                    "INSERT INTO users(username, password_hash, salt) VALUES(?, ?, ?)",
                    ("legacy", legacy_hash, salt),
                )
                conn.commit()
            self.assertTrue(store.login("legacy", "secret12"))
            with closing(sqlite3.connect(store.db_path)) as conn:
                encoded = conn.execute("SELECT password_hash FROM users WHERE username = 'legacy'").fetchone()[0]
            self.assertTrue(str(encoded).startswith(PASSWORD_SCHEME + "$"))

    def test_real_tk_pbkdf2_hash_is_upgraded_after_login(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = AccountStore(Path(temp) / "accounts.sqlite3")
            salt = "0123456789abcdef0123456789abcdef"
            legacy_hash = hashlib.pbkdf2_hmac("sha256", b"secret12", bytes.fromhex(salt), 260_000).hex()
            with closing(sqlite3.connect(store.db_path)) as conn:
                conn.execute("INSERT INTO users(username, password_hash, salt) VALUES(?, ?, ?)", ("tk-user", legacy_hash, salt))
                conn.commit()
            self.assertTrue(store.login("tk-user", "secret12"))
            with closing(sqlite3.connect(store.db_path)) as conn:
                encoded = conn.execute("SELECT password_hash FROM users WHERE username = 'tk-user'").fetchone()[0]
            self.assertTrue(str(encoded).startswith(PASSWORD_SCHEME + "$"))

    def test_setting_can_be_deleted(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = AccountStore(Path(temp) / "accounts.sqlite3")
            store.set_setting("sample", "value")
            store.delete_setting("sample")
            self.assertEqual(store.setting("sample"), "")


class KeySupportTests(unittest.TestCase):
    def test_encrypt_and_decrypt_round_trip(self) -> None:
        payload = encrypt_api_key("sk-test", "password")
        self.assertNotIn("sk-test", payload)
        self.assertEqual(decrypt_api_key(payload, "password"), "sk-test")

    def test_write_and_load_encrypted_key(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "UserAPIKey.enc"
            write_encrypted_key(path, "sk-local", "password")
            self.assertEqual(load_encrypted_key(path, "password"), "sk-local")


class LoginSecretTests(unittest.TestCase):
    def test_secret_round_trip(self) -> None:
        payload = protect_secret("secret12")
        self.assertNotIn("secret12", payload)
        self.assertEqual(unprotect_secret(payload), "secret12")

    def test_plain_compatibility_fallback_round_trip(self) -> None:
        with patch("omnilit_qt.secrets.os.name", "posix"):
            payload = protect_secret("secret12")
        self.assertTrue(payload.startswith(PLAIN_PREFIX))
        self.assertEqual(unprotect_secret(payload), "secret12")

    def test_login_page_has_no_initial_status_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = AccountStore(Path(temp) / "accounts.sqlite3")
            locale = LocaleController(store)
            paths = AppPaths(ROOT, Path(temp), ())
            controller = AuthController(AppController(paths, locale), store, locale)
            self.assertEqual(controller.statusText, "")


class WindowPlacementTests(unittest.TestCase):
    def test_window_is_centered_on_screen_containing_startup_cursor(self) -> None:
        class Rect:
            def x(self) -> int:
                return 1920

            def y(self) -> int:
                return 100

            def width(self) -> int:
                return 1600

            def height(self) -> int:
                return 900

        class Screen:
            @staticmethod
            def availableGeometry() -> Rect:
                return Rect()

        class App:
            cursor = None

            def screenAt(self, cursor):
                self.cursor = cursor
                return Screen()

            @staticmethod
            def primaryScreen():
                raise AssertionError("screenAt should select the cursor screen")

        class Window:
            screen = None
            position = None

            @staticmethod
            def width() -> int:
                return 472

            @staticmethod
            def height() -> int:
                return 580

            def setScreen(self, screen) -> None:
                self.screen = screen

            def resize(self, width: int, height: int) -> None:
                raise AssertionError("startup centering should not resize the QML-managed window")

            def setPosition(self, x: int, y: int) -> None:
                self.position = (x, y)

        app = App()
        window = Window()
        cursor = object()
        with patch("omnilit_qt.app.QCursor.pos", return_value=cursor):
            _center_window_on_cursor_screen(app, window)
        self.assertIs(app.cursor, cursor)
        self.assertIsInstance(window.screen, Screen)
        self.assertEqual(window.position, (2484, 260))

    def test_native_window_frame_is_centered_inside_current_screen_work_area(self) -> None:
        class Rect:
            def __init__(self, x: int, y: int, width: int, height: int):
                self._x = x
                self._y = y
                self._width = width
                self._height = height

            def x(self) -> int:
                return self._x

            def y(self) -> int:
                return self._y

            def width(self) -> int:
                return self._width

            def height(self) -> int:
                return self._height

        class Screen:
            @staticmethod
            def availableGeometry() -> Rect:
                return Rect(1920, 40, 1600, 860)

        class Window:
            position = None

            @staticmethod
            def screen() -> Screen:
                return Screen()

            @staticmethod
            def frameGeometry() -> Rect:
                return Rect(0, 0, 1380, 940)

            def setFramePosition(self, position) -> None:
                self.position = (position.x(), position.y())

        window = Window()
        _center_window_frame_on_current_screen(window)
        self.assertEqual(window.position, (2030, 40))


class LocaleTests(unittest.TestCase):
    def test_language_is_persisted(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = AccountStore(Path(temp) / "accounts.sqlite3")
            locale = LocaleController(store)
            locale.setLanguage("en")
            self.assertEqual(store.setting("language"), "en")
            self.assertEqual(LocaleController(store).text("login"), "Sign in")

    def test_update_message_supports_english(self) -> None:
        self.assertEqual(tr("en", "download_done"), "Download job finished.")

    def test_qml_dynamic_text_uses_current_language(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = AccountStore(Path(temp) / "accounts.sqlite3")
            locale = LocaleController(store)
            self.assertEqual(locale.formatText("selected_count", {"count": 3}), "已选择 3 个")
            locale.setLanguage("en")
            self.assertEqual(locale.formatText("welcome", {"username": "alice"}), "Welcome back, alice")

    def test_qml_i18n_proxy_refreshes_binding_immediately(self) -> None:
        app = QCoreApplication.instance() or QCoreApplication([])
        with tempfile.TemporaryDirectory() as temp:
            store = AccountStore(Path(temp) / "accounts.sqlite3")
            locale = LocaleController(store)
            engine = QQmlEngine()
            engine.rootContext().setContextProperty("localeController", locale)
            component = QQmlComponent(engine)
            component.setData(
                b'import QtQuick\nimport "."\nQtObject { property I18n i18n: I18n {}; property string label: i18n.text("login") }',
                QUrl.fromLocalFile(str(ROOT / "ui" / "qml" / "_i18n_test.qml")),
            )
            target = component.create()
            self.assertIsNotNone(target, component.errorString())
            self.assertEqual(target.property("label"), "登录")
            locale.setLanguage("en")
            app.processEvents()
            self.assertEqual(target.property("label"), "Sign in")
            target.deleteLater()
            engine.deleteLater()


class DatePickerTests(unittest.TestCase):
    def test_month_grid_has_42_cells_and_crosses_month(self) -> None:
        grid = month_grid(2026, 5)
        self.assertEqual(len(grid), 42)
        self.assertLess(grid[0], date(2026, 5, 1))
        self.assertGreater(grid[-1], date(2026, 5, 31))

    def test_iso_parse_and_month_shift_keep_boundary(self) -> None:
        self.assertEqual(parse_iso_date("2026-05-31"), date(2026, 5, 31))
        self.assertEqual(shift_month(date(2026, 1, 31), 1), date(2026, 2, 28))


class DownloadConfigTests(unittest.TestCase):
    def test_advanced_download_config_maps_to_core(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            paths = AppPaths(ROOT, Path(temp) / "data", ROOT)
            _core, config = build_download_config(
                paths,
                {
                    "keywords": "alpha\nbeta",
                    "outputDir": str(Path(temp) / "download"),
                    "pageDelay": "1.5",
                    "minPdfBytes": "4096",
                    "retryMissingPdfs": False,
                    "writeRetryRecords": True,
                    "strictKeywordMatch": False,
                    "minKeywordMatchRatio": "0.4",
                    "loop": True,
                    "loopSleep": "45",
                    "maxRuntimeHours": "2.5",
                    "fastForwardExistingPages": False,
                    "sources": ["openalex", "europe_pmc", "arxiv"],
                },
                lambda: False,
                lambda _stats, _message: None,
            )
            self.assertEqual(config.keywords, ["alpha", "beta"])
            self.assertEqual(config.page_delay, 1.5)
            self.assertEqual(config.min_pdf_bytes, 4096)
            self.assertFalse(config.retry_missing_pdfs)
            self.assertTrue(config.write_retry_records)
            self.assertFalse(config.strict_keyword_match)
            self.assertEqual(config.min_keyword_match_ratio, 0.4)
            self.assertTrue(config.loop)
            self.assertEqual(config.loop_sleep, 45)
            self.assertEqual(config.max_runtime_hours, 2.5)
            self.assertFalse(config.fast_forward_existing_pages)
            self.assertEqual(config.sources, ["openalex", "europe_pmc", "arxiv"])
            self.assertEqual(config.language, "zh")

    def test_download_config_preserves_task_language(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            paths = AppPaths(ROOT, Path(temp) / "data", ROOT)
            _core, config = build_download_config(paths, {}, lambda: False, lambda _stats, _message: None, "en")
            self.assertEqual(config.language, "en")

    def test_download_config_rejects_empty_source_selection(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            paths = AppPaths(ROOT, Path(temp) / "data", ROOT)
            core, config = build_download_config(paths, {"sources": []}, lambda: False, lambda _stats, _message: None)
            config.email = "qa@example.com"
            with self.assertRaisesRegex(ValueError, "Select at least one literature source"):
                core.validate_config(config)

    def test_download_controller_uses_complete_loop_aware_entrypoint(self) -> None:
        class FakeCore:
            called = False

            @staticmethod
            def validate_config(_config) -> None:
                return None

            @classmethod
            def main(cls, _config) -> None:
                cls.called = True

        class InstantWorker:
            def __init__(self, *, target, **_kwargs):
                self.target = target

            def start(self) -> None:
                self.target()

            def update_state(self, *_args, **_kwargs) -> None:
                return None

        with tempfile.TemporaryDirectory() as temp:
            paths = AppPaths(ROOT, Path(temp), ())
            store = AccountStore(paths.data("accounts.sqlite3"))
            locale = LocaleController(store)
            controller = DownloadController(AppController(paths, locale), paths, store, locale)
            with patch("omnilit_qt.download_controller.build_download_config", return_value=(FakeCore, object())), patch(
                "omnilit_qt.download_controller.ManagedWorker", InstantWorker
            ):
                self.assertTrue(controller.start({"loop": True}))
            self.assertTrue(FakeCore.called)
            self.assertFalse(controller.running)

    def test_download_controller_exposes_active_keyword_summary(self) -> None:
        class FakeCore:
            @staticmethod
            def validate_config(_config) -> None:
                return None

        class HoldingWorker:
            def __init__(self, *, target, **_kwargs):
                self.target = target

            def start(self) -> None:
                return None

        with tempfile.TemporaryDirectory() as temp:
            paths = AppPaths(ROOT, Path(temp), ())
            store = AccountStore(paths.data("accounts.sqlite3"))
            locale = LocaleController(store)
            controller = DownloadController(AppController(paths, locale), paths, store, locale)
            with patch("omnilit_qt.download_controller.build_download_config", return_value=(FakeCore, object())), patch(
                "omnilit_qt.download_controller.ManagedWorker", HoldingWorker
            ):
                self.assertTrue(controller.start({"keywords": "alpha\nbeta,gamma,delta"}))
            expected_keywords = "alpha、beta、gamma" + tr("zh", "keyword_count_suffix", count=4)
            self.assertEqual(controller.activeTaskText, tr("zh", "downloading_keywords", keywords=expected_keywords))


class FormPersistenceTests(unittest.TestCase):
    def test_download_form_settings_restore_after_controller_restart(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            paths = AppPaths(ROOT, Path(temp), ())
            store = AccountStore(paths.data("accounts.sqlite3"))
            locale = LocaleController(store)
            controller = DownloadController(AppController(paths, locale), paths, store, locale)
            controller.saveConfig(
                {
                    "email": "reader@example.com",
                    "sources": ["openalex", "arxiv"],
                    "maxPages": 7,
                    "advancedVisible": True,
                    "ignored": "not-saved",
                }
            )

            restored = DownloadController(AppController(paths, locale), paths, store, locale).savedConfig

            self.assertEqual(restored["email"], "reader@example.com")
            self.assertEqual(restored["sources"], ["openalex", "arxiv"])
            self.assertEqual(restored["maxPages"], 7)
            self.assertTrue(restored["advancedVisible"])
            self.assertNotIn("ignored", restored)
            self.assertTrue(store.setting(DOWNLOAD_FORM_SETTING))

    def test_translation_form_settings_restore_without_api_key(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            paths = AppPaths(ROOT, Path(temp), ())
            store = AccountStore(paths.data("accounts.sqlite3"))
            locale = LocaleController(store)
            controller = TranslationController(AppController(paths, locale), paths, store, locale)
            controller.saveConfig(
                {
                    "inputDir": "input-pdfs",
                    "outputDir": "translated",
                    "model": "deepseek-test",
                    "profileIndex": 2,
                    "glossaryPaths": ["glossary.csv"],
                    "apiKey": "sk-must-not-be-saved",
                }
            )

            restored = TranslationController(AppController(paths, locale), paths, store, locale).savedConfig
            stored_json = store.setting(TRANSLATION_FORM_SETTING)

            self.assertEqual(restored["translationDir"], "input-pdfs")
            self.assertNotIn("inputDir", restored)
            self.assertNotIn("outputDir", restored)
            self.assertEqual(restored["model"], "deepseek-test")
            self.assertEqual(restored["profileIndex"], 2)
            self.assertNotIn("apiKey", restored)
            self.assertNotIn("sk-must-not-be-saved", stored_json)


class TranslationDeploymentKeyTests(unittest.TestCase):
    def test_deployment_key_save_loads_current_session_and_preserves_priority(self) -> None:
        class FakeCore:
            @staticmethod
            def find_pdf_files(input_dir):
                return [input_dir / "sample.pdf"]

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            paths = AppPaths(root / "resource", root / "data", ())
            store = AccountStore(paths.data("accounts.sqlite3"))
            locale = LocaleController(store)
            controller = TranslationController(AppController(paths, locale), paths, store, locale)
            input_dir = root / "input"
            input_dir.mkdir()

            self.assertFalse(controller.defaultKeyExists)
            self.assertFalse(controller.saveDefaultKey("sk-deploy", "password", "different"))
            self.assertIn("不一致", controller.statusText)
            self.assertTrue(controller.saveDefaultKey("sk-deploy", "password", "password"))
            self.assertTrue(controller.defaultKeyExists)
            self.assertTrue(controller.defaultKeyLoaded)
            self.assertEqual(controller.defaultKeySource, controller.defaultKeyPath)
            self.assertEqual(load_encrypted_key(Path(controller.defaultKeyPath), "password"), "sk-deploy")

            with patch("omnilit_qt.translation_controller.import_resource_module", return_value=FakeCore):
                _core, args, _pdfs = controller._build_config({"inputDir": str(input_dir)}, "zh")
                self.assertEqual(args.api_key, "sk-deploy")
                self.assertEqual(args.input, str(input_dir))
                self.assertEqual(args.output, str(input_dir))
                controller._user_key = "sk-user"
                _core, args, _pdfs = controller._build_config({"inputDir": str(input_dir)}, "zh")
                self.assertEqual(args.api_key, "sk-user")
                _core, args, _pdfs = controller._build_config({"inputDir": str(input_dir), "apiKey": "sk-current"}, "zh")
                self.assertEqual(args.api_key, "sk-current")

    def test_deployment_key_unlock_reports_missing_file_and_wrong_password(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            paths = AppPaths(root / "resource", root / "data", ())
            store = AccountStore(paths.data("accounts.sqlite3"))
            locale = LocaleController(store)
            controller = TranslationController(AppController(paths, locale), paths, store, locale)

            self.assertFalse(controller.unlockDefaultKey("password"))
            self.assertIn("未配置部署 Key", controller.statusText)
            self.assertTrue(controller.saveDefaultKey("sk-deploy", "password", "password"))

            fresh = TranslationController(AppController(paths, locale), paths, store, locale)
            self.assertFalse(fresh.unlockDefaultKey("wrong"))
            self.assertIn("解锁失败", fresh.statusText)


class TranslationPendingDocumentsTests(unittest.TestCase):
    def test_pending_documents_scan_and_add_duplicate_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            paths = AppPaths(root / "resource", root / "data", ())
            store = AccountStore(paths.data("accounts.sqlite3"))
            locale = LocaleController(store)
            controller = TranslationController(AppController(paths, locale), paths, store, locale)
            translation_dir = root / "translations"
            source_dir = root / "source"
            translation_dir.mkdir()
            source_dir.mkdir()
            (translation_dir / "b.PDF").write_bytes(b"%PDF-b")
            (translation_dir / "a.pdf").write_bytes(b"%PDF-a")
            (translation_dir / "notes.txt").write_text("ignore", encoding="utf-8")
            source = source_dir / "a.pdf"
            source.write_bytes(b"%PDF-copy")

            controller.refreshPendingDocuments(str(translation_dir))
            self.assertEqual([item["name"] for item in controller.pendingDocuments], ["a.pdf", "b.PDF"])
            self.assertEqual(controller.pendingDocumentCount, 2)
            self.assertTrue(all(item["sizeText"] and item["modifiedText"] for item in controller.pendingDocuments))

            with patch("omnilit_qt.translation_controller.QFileDialog.getOpenFileNames", return_value=([str(source)], "")):
                controller.addDocuments(str(translation_dir))
            self.assertTrue((translation_dir / "a_2.pdf").exists())
            self.assertEqual(controller.pendingDocumentCount, 3)

    def test_active_translation_task_uses_current_pdf_name(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            paths = AppPaths(root / "resource", root / "data", ())
            store = AccountStore(paths.data("accounts.sqlite3"))
            locale = LocaleController(store)
            controller = TranslationController(AppController(paths, locale), paths, store, locale)
            controller._running = True
            controller._on_document("paper.pdf")
            self.assertEqual(controller.activeTaskText, tr("zh", "translating_document", document="paper.pdf"))


class DownloadCoreTests(unittest.TestCase):
    def test_pdf_download_writes_only_valid_pdf_content(self) -> None:
        core = import_resource_module(AppPaths(ROOT, ROOT, ()), "Download", "literature_download_core")

        class Response:
            status_code = 200
            headers = {"content-type": "application/pdf"}

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            @staticmethod
            def iter_content(chunk_size):
                del chunk_size
                yield b"%PDF-1.7\n"
                yield b"translated-download-check"

        class Session:
            @staticmethod
            def get(*_args, **_kwargs):
                return Response()

        with tempfile.TemporaryDirectory() as temp:
            config = core.CrawlConfig(out_dir=Path(temp), min_pdf_bytes=8)
            result = core.download_pdf(Session(), "https://example.test/paper.pdf", "10.1/test", config)
            self.assertEqual(result.status, "downloaded")
            self.assertTrue(Path(result.path).read_bytes().startswith(b"%PDF"))

    def test_unpaywall_failure_falls_back_to_openalex_metadata(self) -> None:
        core = import_resource_module(AppPaths(ROOT, ROOT, ()), "Download", "literature_download_core")
        item = {
            "id": "https://openalex.org/W1",
            "doi": "https://doi.org/10.1/test",
            "title": "Fallback open access record",
            "open_access": {"is_oa": True, "oa_url": "https://example.test/paper.pdf"},
        }
        config = core.CrawlConfig(
            email="qa@example.com",
            keywords=["fallback"],
            max_pages_per_keyword=1,
            request_delay=0,
            page_delay=0,
            download_pdfs=False,
            strict_keyword_match=False,
            resume=False,
        )
        stats = core.CrawlStats()
        output = io.StringIO()
        existing = core.ExistingIndex(set(), set(), set())
        with patch.object(core, "search_openalex", return_value={"results": [item], "meta": {"next_cursor": None}}), patch.object(
            core, "query_unpaywall", side_effect=core.requests.HTTPError("422")
        ):
            core.crawl_keyword(object(), core.SOURCE_OPENALEX, "fallback", existing, output, config, stats, {})
        record = json.loads(output.getvalue())
        self.assertEqual(stats.request_failures, 1)
        self.assertEqual(stats.added_records, 1)
        self.assertIsNone(record["unpaywall"])
        self.assertEqual(record["pdf_candidates"], ["https://example.test/paper.pdf"])

    def test_europe_pmc_search_normalizes_open_pdf(self) -> None:
        core = import_resource_module(AppPaths(ROOT, ROOT, ()), "Download", "literature_download_core")

        class Response:
            @staticmethod
            def raise_for_status() -> None:
                return None

            @staticmethod
            def json() -> dict:
                return {
                    "nextCursorMark": "next",
                    "resultList": {
                        "result": [{
                            "source": "PMC",
                            "id": "PMC1",
                            "title": "<i>Open</i> article",
                            "isOpenAccess": "Y",
                            "fullTextUrlList": {"fullTextUrl": [{
                                "availabilityCode": "OA",
                                "documentStyle": "pdf",
                                "url": "https://europepmc.org/articles/PMC1?pdf=render",
                            }]},
                        }]
                    },
                }

        class Session:
            @staticmethod
            def get(*_args, **_kwargs):
                return Response()

        data = core.search_europe_pmc(Session(), "battery", core.CrawlConfig(), "*")
        item = data["results"][0]
        self.assertEqual(item["literature_source"], core.SOURCE_EUROPE_PMC)
        self.assertEqual(core.iter_pdf_candidates(item, None), ["https://europepmc.org/articles/PMC1?pdf=render"])

    def test_arxiv_search_normalizes_atom_pdf(self) -> None:
        core = import_resource_module(AppPaths(ROOT, ROOT, ()), "Download", "literature_download_core")

        class Response:
            text = """<?xml version="1.0"?>
            <feed xmlns="http://www.w3.org/2005/Atom" xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">
              <opensearch:totalResults>1</opensearch:totalResults>
              <entry>
                <id>http://arxiv.org/abs/2601.00001v1</id>
                <published>2026-01-02T00:00:00Z</published>
                <title>Battery preprint</title>
                <summary>Open preprint summary</summary>
                <author><name>Researcher</name></author>
                <link title="pdf" href="https://arxiv.org/pdf/2601.00001v1"/>
                <link rel="alternate" href="https://arxiv.org/abs/2601.00001v1"/>
              </entry>
            </feed>"""

            @staticmethod
            def raise_for_status() -> None:
                return None

        class Session:
            @staticmethod
            def get(*_args, **_kwargs):
                return Response()

        data = core.search_arxiv(Session(), "battery", core.CrawlConfig(from_date="2026-01-01"), "0")
        item = data["results"][0]
        self.assertEqual(item["literature_source"], core.SOURCE_ARXIV)
        self.assertEqual(core.iter_pdf_candidates(item, None), ["https://arxiv.org/pdf/2601.00001v1"])


class TranslationCoreTests(unittest.TestCase):
    def test_document_output_folder_name_is_cross_platform_safe(self) -> None:
        core = import_resource_module(AppPaths(ROOT, ROOT, ()), "Translate", "literature_translate_core")
        self.assertEqual(core.safe_document_folder_name('  paper<>:"/\\|?*  .pdf'), "paper_________")
        self.assertEqual(core.safe_document_folder_name("CON.pdf"), "CON_")
        self.assertEqual(core.safe_document_folder_name(" .pdf"), "untitled_document")

    def test_translation_batches_publish_live_preview(self) -> None:
        core = import_resource_module(AppPaths(ROOT, ROOT, ()), "Translate", "literature_translate_core")
        segment = core.Segment("s1", 0, "body", "Preview source paragraph.", [], True)
        previews: list[dict[str, str]] = []
        with tempfile.TemporaryDirectory() as temp:
            translations = core.translate_segments(
                [segment],
                core.CopyTranslator(),
                core.TranslationCache(Path(temp) / "cache.json"),
                context="",
                target_lang="zh",
                glossary_text="",
                batch_size=1,
                max_batch_chars=1000,
                preview_callback=previews.append,
            )
        self.assertGreaterEqual(len(previews), 2)
        self.assertEqual(previews[-1], translations)
        self.assertIn("Preview source paragraph.", core.translation_preview_text([segment], translations))

    def test_layout_only_translation_accepts_uppercase_pdf_suffix(self) -> None:
        core = import_resource_module(AppPaths(ROOT, ROOT, ()), "Translate", "literature_translate_core")
        import fitz

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            input_dir, output_dir = root / "input", root / "output"
            input_dir.mkdir()
            document = fitz.open()
            page = document.new_page()
            page.insert_text((72, 72), "A compact layout-only translation check.")
            document.save(input_dir / "SAMPLE.PDF")
            document.close()
            self.assertEqual(
                core.main(
                    [
                        "--input",
                        str(input_dir),
                        "--output",
                        str(output_dir),
                        "--translator",
                        "copy",
                        "--max-pages",
                        "1",
                        "--no-summary-page",
                    ]
                ),
                0,
            )
            outputs = list((output_dir / "SAMPLE").glob("*.pdf"))
            self.assertEqual(len(outputs), 1)
            self.assertTrue(outputs[0].with_suffix(".report.json").exists())
            self.assertTrue((output_dir / "SAMPLE" / "cache" / "translation_cache.json").exists())


class UpdateCoreTests(unittest.TestCase):
    @staticmethod
    def _signed_manifest_data(update_core):
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        private_key = Ed25519PrivateKey.generate()
        public_key = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        data = {
            "version": "0.0.10",
            "download_url": "https://example.test/OmniLit.exe",
            "sha256": hashlib.sha256(b"signed-release").hexdigest(),
        }
        data["signature"] = {
            "algorithm": "ed25519",
            "key_id": "test-release-key",
            "value": base64.b64encode(private_key.sign(update_core.canonical_manifest_bytes(data))).decode("ascii"),
        }
        return data, base64.b64encode(public_key).decode("ascii")

    def test_version_and_sha256_verification(self) -> None:
        update_dir = ROOT / "Update"
        if str(update_dir) not in sys.path:
            sys.path.insert(0, str(update_dir))
        import update_core

        self.assertGreater(update_core.version_tuple("0.0.10"), update_core.version_tuple("0.0.9"))
        with tempfile.TemporaryDirectory() as temp:
            package = Path(temp) / "OmniLit.exe"
            package.write_bytes(b"qt-only-update")
            expected = hashlib.sha256(b"qt-only-update").hexdigest()
            self.assertTrue(update_core.verify_sha256(package, expected))
            self.assertFalse(update_core.verify_sha256(package, "0" * 64))

    def test_same_version_server_sha256_change_triggers_update(self) -> None:
        update_dir = ROOT / "Update"
        if str(update_dir) not in sys.path:
            sys.path.insert(0, str(update_dir))
        import update_core

        local_sha256 = hashlib.sha256(b"installed").hexdigest()
        remote_sha256 = hashlib.sha256(b"server-release").hexdigest()
        manifest = update_core.UpdateManifest("0.0.10", "https://example.test/OmniLit.exe", remote_sha256)
        with patch.object(update_core, "fetch_manifest", return_value=manifest):
            result = update_core.check_for_update("https://example.test/update_manifest.json", "0.0.10", current_sha256=local_sha256)
        self.assertFalse(result.is_newer)
        self.assertTrue(result.sha256_changed)
        self.assertTrue(result.update_available)
        self.assertIn("SHA256", result.status)

    def test_same_version_matching_sha256_is_latest(self) -> None:
        update_dir = ROOT / "Update"
        if str(update_dir) not in sys.path:
            sys.path.insert(0, str(update_dir))
        import update_core

        digest = hashlib.sha256(b"same-release").hexdigest()
        manifest = update_core.UpdateManifest("0.0.10", "https://example.test/OmniLit.exe", digest)
        with patch.object(update_core, "fetch_manifest", return_value=manifest):
            result = update_core.check_for_update("https://example.test/update_manifest.json", "0.0.10", current_sha256=digest)
        self.assertFalse(result.update_available)
        self.assertEqual(result.status, "已是最新版本。")

    def test_manifest_requires_valid_sha256(self) -> None:
        update_dir = ROOT / "Update"
        if str(update_dir) not in sys.path:
            sys.path.insert(0, str(update_dir))
        import update_core

        with self.assertRaises(ValueError):
            update_core.UpdateManifest.from_dict({"version": "0.0.10", "download_url": "https://example.test/OmniLit.exe"})

    def test_manifest_requires_a_trusted_ed25519_signature(self) -> None:
        update_dir = ROOT / "Update"
        if str(update_dir) not in sys.path:
            sys.path.insert(0, str(update_dir))
        import update_core

        data, public_key = self._signed_manifest_data(update_core)
        with patch.dict(update_core.TRUSTED_MANIFEST_PUBLIC_KEYS, {"test-release-key": public_key}, clear=True):
            manifest = update_core.UpdateManifest.from_dict(data)
        self.assertEqual(manifest.signature_key_id, "test-release-key")

    def test_manifest_rejects_missing_or_tampered_signature(self) -> None:
        update_dir = ROOT / "Update"
        if str(update_dir) not in sys.path:
            sys.path.insert(0, str(update_dir))
        import update_core

        data, public_key = self._signed_manifest_data(update_core)
        unsigned = {key: value for key, value in data.items() if key != "signature"}
        with self.assertRaisesRegex(ValueError, "unsigned"):
            update_core.UpdateManifest.from_dict(unsigned)

        data["download_url"] = "https://attacker.example.invalid/OmniLit.exe"
        with patch.dict(update_core.TRUSTED_MANIFEST_PUBLIC_KEYS, {"test-release-key": public_key}, clear=True):
            with self.assertRaisesRegex(ValueError, "signature verification failed"):
                update_core.UpdateManifest.from_dict(data)

    def test_download_rejects_manifest_that_was_not_verified(self) -> None:
        update_dir = ROOT / "Update"
        if str(update_dir) not in sys.path:
            sys.path.insert(0, str(update_dir))
        import update_core

        manifest = update_core.UpdateManifest(
            "0.0.10",
            "https://example.test/OmniLit.exe",
            hashlib.sha256(b"unsigned-release").hexdigest(),
        )
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, "not trusted"):
                update_core.download_update(manifest, Path(temp))

    def test_cancelled_update_download_does_not_leave_temporary_file(self) -> None:
        update_dir = ROOT / "Update"
        if str(update_dir) not in sys.path:
            sys.path.insert(0, str(update_dir))
        import update_core

        manifest = update_core.UpdateManifest(
            "0.0.10",
            "https://example.test/OmniLit.exe",
            hashlib.sha256(b"cancelled-release").hexdigest(),
            signature_key_id="omnilit-release-2026-01",
        )
        with tempfile.TemporaryDirectory() as temp:
            target_dir = Path(temp)
            with patch.object(update_core.urllib.request, "urlopen") as urlopen:
                with self.assertRaisesRegex(RuntimeError, "cancelled"):
                    update_core.download_update(
                        manifest,
                        target_dir,
                        language="en",
                        stop_callback=lambda: True,
                    )
            urlopen.assert_not_called()
            self.assertFalse(list(target_dir.glob("*.download")))

    def test_repository_manifest_has_a_valid_release_signature(self) -> None:
        update_dir = ROOT / "Update"
        if str(update_dir) not in sys.path:
            sys.path.insert(0, str(update_dir))
        import update_core

        data = json.loads((ROOT / "update_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(update_core.verify_manifest_signature(data), "omnilit-release-2026-01")


class UpdateControllerTests(unittest.TestCase):
    def test_check_ignores_legacy_manifest_url_setting(self) -> None:
        validated: list[str] = []
        checked: list[str] = []

        class FakeResult:
            status = "checked"
            manifest = None
            is_newer = False

        class FakeCore:
            @staticmethod
            def validate_remote_url(url, *, label):
                del label
                validated.append(url)
                return url

            @staticmethod
            def check_for_update(url, _version, *, current_sha256, language):
                self.assertEqual(current_sha256, "")
                del language
                checked.append(url)
                return FakeResult()

        class InstantWorker:
            def __init__(self, *, target, **_kwargs):
                self.target = target

            def start(self) -> None:
                self.target()

            def update_state(self, *_args, **_kwargs) -> None:
                return None

        with tempfile.TemporaryDirectory() as temp:
            paths = AppPaths(ROOT, Path(temp), ())
            store = AccountStore(paths.data("accounts.sqlite3"))
            store.set_setting("manifest_url", "https://legacy.example.invalid/custom.json")
            locale = LocaleController(store)
            controller = UpdateController(AppController(paths, locale), paths, store, locale)

            with patch("omnilit_qt.update_controller.import_resource_module", return_value=FakeCore), patch(
                "omnilit_qt.update_controller.ManagedWorker", InstantWorker
            ):
                controller.check()

            self.assertEqual(validated, [DEFAULT_UPDATE_MANIFEST_URL])
            self.assertEqual(checked, [DEFAULT_UPDATE_MANIFEST_URL])
            self.assertEqual(store.setting("manifest_url"), "https://legacy.example.invalid/custom.json")


class BackgroundTaskTests(unittest.TestCase):
    def test_managed_worker_is_non_daemon_cancellable_and_persists_final_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            state_path = Path(temp) / "task_state" / "download.json"
            cancel_event = threading.Event()
            started = threading.Event()

            def target() -> None:
                started.set()
                cancel_event.wait(2)

            worker = ManagedWorker(
                name="TestDownload",
                target=target,
                state_path=state_path,
                cancel_event=cancel_event,
                metadata={"kind": "download"},
            )
            self.assertFalse(worker.daemon)
            worker.start()
            self.assertTrue(started.wait(1))
            worker.request_cancel()
            self.assertTrue(worker.join(1))

            state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(state["status"], "cancelled")
            self.assertTrue(state["cancellation_requested"])
            self.assertEqual(state["metadata"], {"kind": "download"})
            self.assertFalse(state_path.with_suffix(".json.tmp").exists())

    def test_app_shutdown_waits_for_all_background_controllers(self) -> None:
        calls: list[tuple[str, float]] = []

        class FakeController:
            def __init__(self, name: str, result: bool = True):
                self.name = name
                self.result = result

            def shutdown(self, timeout: float) -> bool:
                calls.append((self.name, timeout))
                return self.result

        self.assertFalse(
            _shutdown_background_tasks(
                FakeController("download"),
                FakeController("translation", result=False),
                FakeController("update"),
                timeout=3.5,
            )
        )
        self.assertEqual(calls, [("download", 3.5), ("translation", 3.5), ("update", 3.5)])


class QtOnlyTests(unittest.TestCase):
    def test_controller_implementations_are_split_by_responsibility(self) -> None:
        controller_dir = ROOT / "omnilit_qt"
        aggregate = (controller_dir / "controllers.py").read_text(encoding="utf-8")
        self.assertLess(len(aggregate.splitlines()), 60)
        for name in (
            "app_controller.py",
            "auth_controller.py",
            "preferences_controller.py",
            "download_controller.py",
            "translation_controller.py",
            "update_controller.py",
        ):
            self.assertTrue((controller_dir / name).is_file(), name)
        self.assertIn("from .auth_controller import AuthController", aggregate)
        self.assertNotIn("class AuthController", aggregate)

    def test_background_workers_are_non_daemon_and_shutdown_is_wired(self) -> None:
        background = (ROOT / "omnilit_qt" / "background_tasks.py").read_text(encoding="utf-8")
        app = (ROOT / "omnilit_qt" / "app.py").read_text(encoding="utf-8")
        active_sources = "\n".join(
            (ROOT / "omnilit_qt" / name).read_text(encoding="utf-8")
            for name in ("download_controller.py", "translation_controller.py", "update_controller.py")
        )
        self.assertIn("daemon=False", background)
        self.assertNotIn("daemon=True", active_sources)
        self.assertIn("app.aboutToQuit.connect", app)
        self.assertIn("_shutdown_background_tasks(download, translation, updater)", app)

    def test_active_sources_do_not_reference_tkinter(self) -> None:
        files = [
            ROOT / "omnilit_qt_app.py",
            ROOT / "encrypt_default_key.py",
            *sorted((ROOT / "omnilit_qt").glob("*.py")),
            *sorted((ROOT / "ui" / "qml").glob("*.qml")),
            ROOT / "build_omnilit_exe.bat",
            ROOT / "build_omnilit_macos.sh",
        ]
        for path in files:
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("tkinter", text.lower(), path)
            self.assertNotIn("--legacy-tk", text.lower(), path)

    def test_clickable_qml_controls_use_pointing_cursor(self) -> None:
        qml_dir = ROOT / "ui" / "qml"
        pill_button = (qml_dir / "PillButton.qml").read_text(encoding="utf-8")
        self.assertIn("Qt.PointingHandCursor", pill_button)
        self.assertIn("anchors.centerIn: parent", pill_button)
        self.assertIn("Qt.PointingHandCursor", (qml_dir / "Workspace.qml").read_text(encoding="utf-8"))
        self.assertIn("Qt.PointingHandCursor", (qml_dir / "DatePickerField.qml").read_text(encoding="utf-8"))

    def test_compact_pages_keep_status_and_directory_actions_visible(self) -> None:
        qml_dir = ROOT / "ui" / "qml"
        stats = (qml_dir / "StatCard.qml").read_text(encoding="utf-8")
        download = (qml_dir / "DownloadPage.qml").read_text(encoding="utf-8")
        translation = (qml_dir / "TranslationPage.qml").read_text(encoding="utf-8")
        workspace = (qml_dir / "Workspace.qml").read_text(encoding="utf-8")
        self.assertIn("Layout.preferredHeight: 84", stats)
        self.assertNotIn("Layout.preferredHeight: 76", download)
        self.assertIn("translationController.openDirectory(translationDir.text)", translation)
        self.assertIn("navigationButton.hovered || navigationButton.activeFocus ? theme.navHover", workspace)

    def test_translation_page_uses_one_directory_pending_list_and_scroll_preserving_preview(self) -> None:
        translation = (ROOT / "ui" / "qml" / "TranslationPage.qml").read_text(encoding="utf-8")
        self.assertIn("id: translationDir", translation)
        self.assertNotIn("id: outputDir", translation)
        self.assertIn("translationDir.text=settings.translationDir || settings.inputDir || translationController.defaultInputDir", translation)
        self.assertIn("translationController.pendingDocuments", translation)
        self.assertIn("translationController.addDocuments(translationDir.text)", translation)
        self.assertIn("function onChanged() { root.syncPreview() }", translation)
        self.assertIn("let oldY=flick.contentY", translation)
        self.assertIn("let wasAtBottom=oldY >= maxY - 12", translation)
        self.assertNotIn("text: translationController.previewText", translation)

    def test_workspace_uses_drawer_pages_for_account_controls_and_active_task_tooltips(self) -> None:
        workspace = (ROOT / "ui" / "qml" / "Workspace.qml").read_text(encoding="utf-8")
        self.assertNotIn("languageExpanded", workspace)
        self.assertNotIn("avatarExpanded", workspace)
        self.assertNotIn("statusExpanded", workspace)
        self.assertNotIn("panelHeight", workspace)
        self.assertIn("onClicked: root.drawerPage = 3", workspace)
        self.assertIn("root.drawerPage = 4", workspace)
        self.assertIn("onClicked: root.drawerPage = 5", workspace)
        self.assertIn("downloadController.activeTaskText", workspace)
        self.assertIn("translationController.activeTaskText", workspace)
        self.assertIn('model: ["status_online", "status_focused", "status_writing", "status_away"]', workspace)
        self.assertIn('"🟢", "☕", "📚", "🎯", "🌙", "🚫", "✍️", "🔬"', workspace)
        self.assertIn("preferencesController.setAvatarStatus(status)", workspace)

    def test_navigation_hover_uses_dynamic_semantic_colors(self) -> None:
        qml_dir = ROOT / "ui" / "qml"
        theme = (qml_dir / "Theme.qml").read_text(encoding="utf-8")
        workspace = (qml_dir / "Workspace.qml").read_text(encoding="utf-8")
        self.assertIn("readonly property color navHover: mix(accent, surfaceSoft", theme)
        self.assertIn("readonly property color navPressed: mix(accent, surfaceSoft", theme)
        self.assertIn("readonly property color navSelected: mix(accent, surfaceSoft", theme)
        self.assertIn("navigationButton.down ? theme.navPressed", workspace)
        self.assertIn("ColorAnimation { duration: motion.normal; easing.type: Easing.OutCubic }", workspace)
        self.assertNotIn("#f1f5f9", workspace)

    def test_translation_feature_is_named_literature_translation(self) -> None:
        from omnilit_qt.i18n import TEXTS

        self.assertEqual(TEXTS["nav_translate"], ("文献翻译", "Literature translation"))
        self.assertEqual(TEXTS["translate_title"], ("文献翻译", "Literature translation"))

    def test_qml_uses_shared_responsive_layout_metrics(self) -> None:
        qml_dir = ROOT / "ui" / "qml"
        main = (qml_dir / "Main.qml").read_text(encoding="utf-8")
        metrics = (qml_dir / "LayoutMetrics.qml").read_text(encoding="utf-8")
        workspace = (qml_dir / "Workspace.qml").read_text(encoding="utf-8")
        download = (qml_dir / "DownloadPage.qml").read_text(encoding="utf-8")
        translation = (qml_dir / "TranslationPage.qml").read_text(encoding="utf-8")
        self.assertIn("Screen.desktopAvailableWidth", main)
        self.assertIn("Screen.desktopAvailableHeight", main)
        self.assertIn("readonly property bool compact", metrics)
        self.assertIn("readonly property bool narrow", metrics)
        self.assertIn("Layout.preferredWidth: root.sidebarWidth", workspace)
        self.assertIn("id: formScroll", download)
        self.assertIn("columns: metrics.narrow ? 2 : 4", download)
        self.assertIn("id: formScroll", translation)
        self.assertIn("columns: metrics.narrow ? 1 : 2", translation)
        self.assertTrue((qml_dir / "Theme.qml").exists())
        self.assertTrue((qml_dir / "PageHeading.qml").exists())
        self.assertTrue((qml_dir / "SoftProgressBar.qml").exists())
        self.assertTrue((qml_dir / "SoftTextArea.qml").exists())

    def test_auth_window_is_compact_and_language_switch_is_inside_title_row(self) -> None:
        qml_dir = ROOT / "ui" / "qml"
        main = (qml_dir / "Main.qml").read_text(encoding="utf-8")
        auth = (qml_dir / "AuthPage.qml").read_text(encoding="utf-8")
        self.assertIn("readonly property int authWindowWidth: 472", main)
        self.assertIn("readonly property int authWindowHeight: 580", main)
        self.assertIn("maximumWidth = authWindowWidth", main)
        self.assertIn("maximumHeight = authWindowHeight", main)
        self.assertIn("savedWorkspaceWidth ||", main)
        self.assertIn("savedWorkspaceHeight ||", main)
        self.assertNotIn("registerMode ?", auth.split("height: Math.min(", 1)[1].split("\n", 1)[0])
        self.assertNotIn("GradientStop", auth)
        self.assertNotIn("radius: width / 2", auth)
        title_row = auth.split("id: titleRow", 1)[1].split("Rectangle { Layout.fillWidth", 1)[0]
        self.assertIn("id: languageButton", title_row)
        self.assertIn("localeController.toggleLanguage()", title_row)
        self.assertEqual(auth.count("localeController.toggleLanguage()"), 1)
        auth_field = (qml_dir / "AuthTextField.qml").read_text(encoding="utf-8")
        self.assertIn("border.color: control.activeFocus ? theme.accent : theme.border", auth_field)
        self.assertIn('iconName: "user"', auth)
        self.assertEqual(auth.count('iconName: "lock"'), 2)
        self.assertNotIn("height: 3", auth)
        mode_switch = auth.split("id: modeSwitch", 1)[1].split("Item { Layout.fillHeight", 1)[0]
        self.assertIn("Layout.preferredHeight: 44", mode_switch)
        self.assertIn("color: modeSwitch.hovered ? theme.accentSoft : theme.surface", mode_switch)
        self.assertIn("border.color: modeSwitch.hovered ? theme.accent : theme.border", mode_switch)

    def test_login_recenters_the_native_window_frame_from_python(self) -> None:
        main = (ROOT / "ui" / "qml" / "Main.qml").read_text(encoding="utf-8")
        app = (ROOT / "omnilit_qt" / "app.py").read_text(encoding="utf-8")
        self.assertNotIn("function centerWindow", main)
        self.assertIn("frame = window.frameGeometry()", app)
        self.assertIn("window.setFramePosition(", app)
        self.assertIn("QTimer.singleShot(120", app)
        self.assertIn("auth.authenticated.connect(lambda: _schedule_window_frame_center(window))", app)

    def test_workspace_dashboard_is_removed(self) -> None:
        qml_dir = ROOT / "ui" / "qml"
        workspace = (qml_dir / "Workspace.qml").read_text(encoding="utf-8")
        self.assertNotIn('"nav_home"', workspace)
        self.assertNotIn("HomePage", workspace)
        self.assertFalse((qml_dir / "HomePage.qml").exists())

    def test_default_key_page_is_merged_into_translation_advanced_options(self) -> None:
        qml_dir = ROOT / "ui" / "qml"
        app = (ROOT / "omnilit_qt" / "app.py").read_text(encoding="utf-8")
        workspace = (qml_dir / "Workspace.qml").read_text(encoding="utf-8")
        translation = (qml_dir / "TranslationPage.qml").read_text(encoding="utf-8")
        self.assertIn('{ label: "nav_download", icon: "download" }', workspace)
        self.assertIn('{ label: "nav_translate", icon: "translate" }', workspace)
        self.assertNotIn('{ label: "nav_update"', workspace)
        self.assertNotIn("KeyPage", workspace)
        self.assertFalse((qml_dir / "KeyPage.qml").exists())
        self.assertNotIn("keyController", app)
        self.assertIn("property bool deploymentKeyAdvancedVisible: false", translation)
        self.assertIn("translationController.saveDefaultKey(apiKey.text", translation)

    def test_update_page_has_no_editable_manifest_url(self) -> None:
        qml = (ROOT / "ui" / "qml" / "UpdatePage.qml").read_text(encoding="utf-8")
        self.assertNotIn("manifestUrl", qml)
        self.assertNotIn("setManifestUrl", qml)
        self.assertNotIn("id: manifest", qml)

    def test_workspace_uses_avatar_drawer_and_vector_power_logout(self) -> None:
        qml_dir = ROOT / "ui" / "qml"
        workspace = (qml_dir / "Workspace.qml").read_text(encoding="utf-8")
        vector_icon = (qml_dir / "VectorIcon.qml").read_text(encoding="utf-8")
        self.assertIn("Layout.preferredWidth: root.sidebarWidth", workspace)
        self.assertIn("readonly property int sidebarCollapsedWidth: 72", (qml_dir / "LayoutMetrics.qml").read_text(encoding="utf-8"))
        self.assertIn("readonly property int sidebarExpandedWidth: 208", (qml_dir / "LayoutMetrics.qml").read_text(encoding="utf-8"))
        self.assertIn("id: accountDrawer", workspace)
        self.assertIn("Popup.CloseOnEscape | Popup.CloseOnPressOutside", workspace)
        self.assertEqual(workspace.count("UpdatePage {}"), 0)
        self.assertEqual(workspace.count("UpdatePage {"), 1)
        self.assertIn('name: "power"', workspace)
        self.assertIn("authController.logout()", workspace)
        self.assertIn("PathSvg", vector_icon)

    def test_workspace_shell_uses_branded_sidebar_and_shared_drawer_components(self) -> None:
        qml_dir = ROOT / "ui" / "qml"
        auth = (qml_dir / "AuthPage.qml").read_text(encoding="utf-8")
        theme = (qml_dir / "Theme.qml").read_text(encoding="utf-8")
        workspace = (qml_dir / "Workspace.qml").read_text(encoding="utf-8")
        self.assertTrue((qml_dir / "AvatarStatusBadge.qml").exists())
        self.assertTrue((qml_dir / "DrawerMenuItem.qml").exists())
        self.assertTrue((qml_dir / "DrawerPageHeader.qml").exists())
        self.assertIn("theme.sidebarSurface", workspace)
        self.assertIn('text: "RESEARCH DESK"', workspace)
        self.assertIn("AvatarStatusBadge {", workspace)
        self.assertIn("DrawerMenuItem {", workspace)
        self.assertIn("DrawerPageHeader {", workspace)
        self.assertIn("readonly property color surfaceElevated", theme)
        self.assertIn('i18n.text(registerMode ? "auth_register_desc" : "auth_login_desc")', auth)

    def test_sidebar_uses_modern_tooltips_and_switchable_labels(self) -> None:
        qml_dir = ROOT / "ui" / "qml"
        workspace = (qml_dir / "Workspace.qml").read_text(encoding="utf-8")
        tooltip = (qml_dir / "ModernToolTip.qml").read_text(encoding="utf-8")
        self.assertNotIn("ToolTip.visible", workspace)
        self.assertIn("ModernToolTip {", workspace)
        self.assertIn("visible: root.sidebarExpanded", workspace)
        self.assertIn("preferencesController.toggleSidebarExpanded()", workspace)
        self.assertIn("color: theme.tooltipSurface", tooltip)
        self.assertIn("color: theme.tooltipText", tooltip)

    def test_drawer_language_switch_uses_themed_choice_row(self) -> None:
        workspace = (ROOT / "ui" / "qml" / "Workspace.qml").read_text(encoding="utf-8")
        drawer_home = workspace[workspace.index("id: accountDrawer"):workspace.index("id: appearanceEntry")]
        self.assertIn("onClicked: root.drawerPage = 5", drawer_home)
        self.assertNotIn("AppearanceChoiceRow {", drawer_home)
        self.assertIn('label: i18n.text("interface_language")', workspace)
        self.assertIn("selectedValue: localeController.language", workspace)
        self.assertIn("onSelected: value => localeController.setLanguage(value)", workspace)
        self.assertNotIn("ComboBox {", drawer_home)

    def test_uploaded_images_use_high_quality_cache_busting_rendering(self) -> None:
        workspace = (ROOT / "ui" / "qml" / "Workspace.qml").read_text(encoding="utf-8")
        avatar = (ROOT / "ui" / "qml" / "RoundedAvatar.qml").read_text(encoding="utf-8")
        background = (ROOT / "ui" / "qml" / "WorkspaceBackground.qml").read_text(encoding="utf-8")
        controller = (ROOT / "omnilit_qt" / "preferences_controller.py").read_text(encoding="utf-8")
        self.assertGreaterEqual(workspace.count("cache: false") + avatar.count("cache: false") + background.count("cache: false"), 2)
        self.assertGreaterEqual(workspace.count("smooth: true") + avatar.count("smooth: true") + background.count("smooth: true"), 2)
        self.assertGreaterEqual(workspace.count("mipmap: true") + avatar.count("mipmap: true") + background.count("mipmap: true"), 2)
        self.assertIn('url.setQuery(f"v={stat.st_mtime_ns}-{stat.st_size}")', controller)

    def test_night_theme_palette_and_rounded_avatar_status_are_wired(self) -> None:
        qml_dir = ROOT / "ui" / "qml"
        main = (qml_dir / "Main.qml").read_text(encoding="utf-8")
        theme = (qml_dir / "Theme.qml").read_text(encoding="utf-8")
        workspace = (qml_dir / "Workspace.qml").read_text(encoding="utf-8")
        avatar = (qml_dir / "RoundedAvatar.qml").read_text(encoding="utf-8")
        vector_icon = (qml_dir / "VectorIcon.qml").read_text(encoding="utf-8")
        self.assertIn("palette.text: theme.text", main)
        self.assertIn("palette.placeholderText: theme.disabledText", main)
        self.assertIn('workspaceOverlay: dark ? "#d90b1220" : "#b8f8fafc"', theme)
        self.assertIn('{ value: "auto_night", label: "theme_auto_night" }', workspace)
        self.assertIn("preferencesController.localTimezoneName", workspace)
        self.assertIn("preferencesController.setAvatarStatus(status)", workspace)
        self.assertIn("MultiEffect {", avatar)
        self.assertIn("maskEnabled: true", avatar)
        self.assertIn("logoutButton.hovered ? theme.error : theme.accent", workspace)
        self.assertIn('if (iconName === "power")', vector_icon)

    def test_academic_appearance_system_is_wired(self) -> None:
        qml_dir = ROOT / "ui" / "qml"
        theme = (qml_dir / "Theme.qml").read_text(encoding="utf-8")
        workspace = (qml_dir / "Workspace.qml").read_text(encoding="utf-8")
        background = (qml_dir / "WorkspaceBackground.qml").read_text(encoding="utf-8")
        preview = (qml_dir / "AppearancePreview.qml").read_text(encoding="utf-8")
        motion = (qml_dir / "Motion.qml").read_text(encoding="utf-8")
        controller = (ROOT / "omnilit_qt" / "preferences_controller.py").read_text(encoding="utf-8")
        for preset in ("scholar_light", "manuscript_sepia", "library_dark", "journal_blue", "arxiv_minimal", "nature_green"):
            self.assertIn(preset, theme)
        self.assertIn("AppearancePreview {", workspace)
        self.assertIn("preferencesController.themePresets", workspace)
        self.assertIn("preferencesController.setBackgroundOpacity", workspace)
        self.assertIn("preferencesController.setReduceMotion", workspace)
        self.assertIn("MultiEffect {", background)
        self.assertIn("blurEnabled: preferencesController.backgroundBlur > 0", background)
        self.assertIn("Attention Is All You Need", preview)
        self.assertIn("DOI 10.5555/3295222.3295349", preview)
        self.assertIn("theme.reduceMotion ? 0", motion)
        self.assertIn('THEME_PRESET_SETTING = "appearance/theme"', controller)

    def test_task_pages_use_internal_scrolling_only(self) -> None:
        qml_dir = ROOT / "ui" / "qml"
        for name in ("DownloadPage.qml", "TranslationPage.qml"):
            text = (qml_dir / name).read_text(encoding="utf-8")
            self.assertTrue(text.startswith("import QtQuick"), name)
            self.assertIn("\nItem {\n    id: root", text, name)
            self.assertNotIn("id: scroll", text, name)
        self.assertNotIn("scroll.", (qml_dir / "DownloadPage.qml").read_text(encoding="utf-8"))

    def test_task_page_settings_are_saved_automatically(self) -> None:
        qml_dir = ROOT / "ui" / "qml"
        download = (qml_dir / "DownloadPage.qml").read_text(encoding="utf-8")
        translation = (qml_dir / "TranslationPage.qml").read_text(encoding="utf-8")
        for text in (download, translation):
            self.assertIn("id: saveSettingsTimer; interval: 350", text)
            self.assertIn("if(!root.restoringSettings) saveSettingsTimer.restart()", text)
        self.assertIn("onSelectedSourcesChanged: scheduleSave()", download)
        self.assertIn("onSelectedGlossariesChanged: scheduleSave()", translation)
        self.assertNotIn('onClicked: downloadController.saveConfig(config())', download)
        self.assertNotIn('onClicked: translationController.saveConfig(config())', translation)

    def test_english_ui_translations_do_not_mix_chinese(self) -> None:
        from omnilit_qt.i18n import TEXTS

        allowed = {"language"}
        mixed = {key: english for key, (_chinese, english) in TEXTS.items() if key not in allowed and re.search(r"[\u4e00-\u9fff]", english)}
        self.assertEqual(mixed, {})


class PreferencesControllerTests(unittest.TestCase):
    @staticmethod
    def _write_image(path: Path, color: int = 0xff2563eb) -> None:
        image = QImage(4, 4, QImage.Format_ARGB32)
        image.fill(color)
        assert image.save(str(path))

    def _controllers(self, root: Path):
        paths = AppPaths(ROOT, root, ())
        store = AccountStore(paths.data("accounts.sqlite3"))
        locale = LocaleController(store)
        auth = AuthController(AppController(paths, locale), store, locale)
        return paths, store, auth, PreferencesController(paths, store, auth)

    def test_theme_accent_and_background_persist_and_clear(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            image_path = root / "background.png"
            self._write_image(image_path)
            paths, store, auth, preferences = self._controllers(root)

            preferences.setThemeMode("dark")
            preferences.setAccentName("purple")
            self.assertTrue(preferences.uploadWorkspaceBackground(str(image_path)))

            restored = PreferencesController(paths, store, auth)
            self.assertEqual(restored.themeMode, "dark")
            self.assertEqual(restored.effectiveThemeMode, "dark")
            self.assertEqual(restored.accentName, "purple")
            copied = Path(QUrl(restored.workspaceBackgroundUrl).toLocalFile())
            self.assertEqual(copied.parent, paths.data("ui"))
            self.assertTrue(copied.is_file())

            restored.clearWorkspaceBackground()
            restored.setThemeMode("invalid")
            restored.setAccentName("invalid")
            self.assertEqual(restored.workspaceBackgroundUrl, "")
            self.assertEqual(restored.themeMode, "light")
            self.assertEqual(restored.accentName, "blue")

    def test_avatars_are_isolated_by_username_and_clear_to_initial(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            alice_image = root / "alice.png"
            bob_image = root / "bob.png"
            self._write_image(alice_image)
            self._write_image(bob_image, 0xffdb2777)
            _paths, store, auth, preferences = self._controllers(root)
            store.register("alice", "secret12")
            store.register("bob", "secret12")

            self.assertTrue(auth.login("alice", "secret12"))
            self.assertTrue(preferences.uploadAvatar(str(alice_image)))
            alice_url = preferences.avatarUrl
            self.assertEqual(preferences.avatarInitial, "A")

            auth.logout()
            self.assertTrue(auth.login("bob", "secret12"))
            self.assertEqual(preferences.avatarUrl, "")
            self.assertTrue(preferences.uploadAvatar(str(bob_image)))
            self.assertNotEqual(preferences.avatarUrl, alice_url)
            preferences.clearAvatar()
            self.assertEqual(preferences.avatarUrl, "")
            self.assertEqual(preferences.avatarInitial, "B")

            auth.logout()
            self.assertTrue(auth.login("alice", "secret12"))
            self.assertEqual(preferences.avatarUrl, alice_url)

    def test_invalid_image_is_not_saved(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            invalid = root / "invalid.png"
            invalid.write_text("not an image", encoding="utf-8")
            _paths, store, auth, preferences = self._controllers(root)
            self.assertFalse(preferences.uploadWorkspaceBackground(str(invalid)))
            self.assertEqual(preferences.workspaceBackgroundUrl, "")
            self.assertEqual(store.setting("ui_workspace_background"), "")

    def test_sidebar_mode_is_persisted(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            paths, store, auth, preferences = self._controllers(Path(temp))
            self.assertFalse(preferences.sidebarExpanded)
            preferences.toggleSidebarExpanded()
            self.assertTrue(preferences.sidebarExpanded)
            self.assertTrue(PreferencesController(paths, store, auth).sidebarExpanded)

    def test_overwritten_image_url_changes_to_refresh_qml_cache(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            image_path = root / "background.png"
            self._write_image(image_path)
            _paths, _store, _auth, preferences = self._controllers(root)
            self.assertTrue(preferences.uploadWorkspaceBackground(str(image_path)))
            first_url = preferences.workspaceBackgroundUrl

            self._write_image(image_path, 0xffdb2777)
            self.assertTrue(preferences.uploadWorkspaceBackground(str(image_path)))
            self.assertNotEqual(preferences.workspaceBackgroundUrl, first_url)

    def test_auto_night_uses_local_hour_boundaries(self) -> None:
        self.assertTrue(PreferencesController._is_night_hour(0))
        self.assertTrue(PreferencesController._is_night_hour(5))
        self.assertTrue(PreferencesController._is_night_hour(6))
        self.assertFalse(PreferencesController._is_night_hour(7))
        self.assertFalse(PreferencesController._is_night_hour(17))
        self.assertFalse(PreferencesController._is_night_hour(18))
        self.assertTrue(PreferencesController._is_night_hour(22))
        self.assertTrue(PreferencesController._is_night_hour(23))
        self.assertTrue(PreferencesController._is_night_time(23 * 60, "22:00", "07:00"))
        self.assertFalse(PreferencesController._is_night_time(12 * 60, "22:00", "07:00"))

    def test_academic_appearance_preferences_persist_and_reset(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            paths, store, _auth, preferences = self._controllers(Path(temp))
            preferences.setThemePreset("manuscript_sepia")
            preferences.setCustomAccentColor("#123abc")
            preferences.setFontSize("large")
            preferences.setDensity("relaxed")
            preferences.setRadius("subtle")
            preferences.setPdfBackground("gray")
            preferences.setTranslationLineHeight("comfortable")
            preferences.setBackgroundMode("grid")
            preferences.setBackgroundOpacity(0.65)
            preferences.setBackgroundBlur(12)
            preferences.setHighContrast(True)
            preferences.setReduceMotion(True)
            preferences.setThemeMode("auto_night")
            preferences.setAutoNightStart("21:30")
            preferences.setAutoNightEnd("06:45")

            restored = PreferencesController(paths, store, _auth)
            self.assertEqual(restored.themePreset, "manuscript_sepia")
            self.assertEqual(restored.accentName, "custom")
            self.assertEqual(restored.accentColor, "#123abc")
            self.assertEqual(restored.fontSizeBase, 15)
            self.assertAlmostEqual(restored.densityScale, 1.14)
            self.assertEqual(restored.radiusBase, 7)
            self.assertEqual(restored.pdfBackgroundColor, "#f1f5f9")
            self.assertAlmostEqual(restored.translationLineHeightValue, 1.75)
            self.assertEqual(restored.backgroundMode, "grid")
            self.assertAlmostEqual(restored.backgroundOpacity, 0.65)
            self.assertEqual(restored.backgroundBlur, 12)
            self.assertTrue(restored.highContrast)
            self.assertTrue(restored.reduceMotion)
            self.assertEqual(restored.autoNightStart, "21:30")
            self.assertEqual(restored.autoNightEnd, "06:45")

            restored.resetAppearance()
            self.assertEqual(restored.themeMode, "light")
            self.assertEqual(restored.themePreset, "scholar_light")
            self.assertEqual(restored.accentName, "blue")
            self.assertEqual(restored.backgroundMode, "solid")
            self.assertFalse(restored.highContrast)
            self.assertFalse(restored.reduceMotion)

    def test_background_upload_switches_mode_and_extracts_accent(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            image_path = root / "background.png"
            self._write_image(image_path)
            _paths, _store, _auth, preferences = self._controllers(root)
            self.assertTrue(preferences.uploadWorkspaceBackground(str(image_path)))
            self.assertEqual(preferences.backgroundMode, "image")
            preferences.extractAccentFromBackground()
            self.assertEqual(preferences.accentName, "custom")
            self.assertEqual(preferences.accentColor, "#2563eb")

    def test_avatar_status_is_persisted_per_account(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            _paths, store, auth, preferences = self._controllers(Path(temp))
            store.register("alice", "secret12")
            store.register("bob", "secret12")

            self.assertTrue(auth.login("alice", "secret12"))
            preferences.setAvatarStatus("📚")
            self.assertEqual(preferences.avatarStatus, "📚")

            auth.logout()
            self.assertTrue(auth.login("bob", "secret12"))
            self.assertEqual(preferences.avatarStatus, "")
            preferences.setAvatarStatus("☕")
            self.assertEqual(preferences.avatarStatus, "☕")

            auth.logout()
            self.assertTrue(auth.login("alice", "secret12"))
            self.assertEqual(preferences.avatarStatus, "📚")
            preferences.setAvatarStatus("")
            self.assertEqual(preferences.avatarStatus, "")


if __name__ == "__main__":
    unittest.main()
