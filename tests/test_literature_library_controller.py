from __future__ import annotations

import json
import time
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from omnilit_qt.paths import AppPaths
from omnilit_qt.services import AccountStore, import_resource_module

try:
    import fitz
    from PySide6.QtCore import QCoreApplication

    from omnilit_qt.app_controller import AppController
    from omnilit_qt.i18n import LocaleController
    from omnilit_qt.literature_library_controller import LiteratureLibraryController
except ModuleNotFoundError:  # pragma: no cover - depends on local Qt runtime.
    fitz = None
    QCoreApplication = None
    AppController = None
    LocaleController = None
    LiteratureLibraryController = None


ROOT = Path(__file__).resolve().parent.parent


def write_sample_pdf(path: Path) -> None:
    document = fitz.open()
    page = document.new_page(width=240, height=320)
    page.insert_text((32, 48), "Sample literature PDF")
    document.save(path)
    document.close()


@unittest.skipUnless(LiteratureLibraryController is not None and fitz is not None, "Qt/PyMuPDF dependencies are not installed")
class LiteratureLibraryControllerTests(unittest.TestCase):
    def make_controller(self, root: Path) -> LiteratureLibraryController:
        QCoreApplication.instance() or QCoreApplication([])
        paths = AppPaths(ROOT, root, ())
        store = AccountStore(paths.data("accounts.sqlite3"))
        store.set_setting(
            "download_form_config",
            json.dumps(
                {
                    "outputDir": str(root / "Download"),
                    "keywords": "lithium-sulfur batteries\npolysulfide",
                    "minKeywordMatchRatio": "0.75",
                    "topicPack": "auto",
                }
            ),
        )
        locale = LocaleController(store)
        return LiteratureLibraryController(AppController(paths, locale), paths, store, locale)

    def wait_for_idle(self, controller: LiteratureLibraryController, timeout: float = 5.0) -> None:
        deadline = time.monotonic() + timeout
        while controller.loading and time.monotonic() < deadline:
            QCoreApplication.processEvents()
            time.sleep(0.01)
        QCoreApplication.processEvents()
        self.assertFalse(controller.loading)

    def wait_for_thumbnail(self, controller: LiteratureLibraryController, record_id: str, timeout: float = 5.0) -> str:
        deadline = time.monotonic() + timeout
        thumbnail = ""
        while time.monotonic() < deadline:
            QCoreApplication.processEvents()
            thumbnail = controller.thumbnailFor(record_id)
            if thumbnail:
                return thumbnail
            time.sleep(0.01)
        self.fail("thumbnail was not generated in time")

    def wait_for_preview(self, controller: LiteratureLibraryController, record_id: str, timeout: float = 5.0) -> str:
        deadline = time.monotonic() + timeout
        preview = ""
        while time.monotonic() < deadline:
            QCoreApplication.processEvents()
            preview = controller.previewFor(record_id)
            if preview:
                return preview
            time.sleep(0.01)
        self.fail("preview was not generated in time")

    def seed_metadata(self, root: Path) -> tuple[Path, Path]:
        download_root = root / "Download"
        pdf_dir = download_root / "pdfs"
        pdf_dir.mkdir(parents=True)
        pdf_path = pdf_dir / "sample.pdf"
        write_sample_pdf(pdf_path)
        metadata_path = download_root / "metadata_battery.jsonl"
        metadata_path.write_text(
            json.dumps(
                {
                    "keyword": "lithium-sulfur batteries",
                    "literature_source": "openalex",
                    "source_record_id": "https://openalex.org/W1",
                    "doi": "10.1000/example",
                    "title": "Lithium-sulfur batteries with improved separator design",
                    "abstract": "This paper discusses polysulfide shuttle control in rechargeable cells.",
                    "authors": ["A. Researcher"],
                    "publication_year": 2024,
                    "download_status": "downloaded",
                    "local_pdf_path": "pdfs/sample.pdf",
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        return metadata_path, pdf_path

    def seed_cleanup_metadata(self, root: Path) -> dict[str, Path | dict]:
        download_root = root / "Download"
        pdf_dir = download_root / "pdfs"
        pdf_dir.mkdir(parents=True)
        valid_pdf = pdf_dir / "valid.pdf"
        invalid_pdf = pdf_dir / "invalid.pdf"
        orphan_pdf = pdf_dir / "orphan.pdf"
        for path in (valid_pdf, invalid_pdf, orphan_pdf):
            write_sample_pdf(path)

        valid_record = {
            "keyword": "lithium-sulfur batteries",
            "literature_source": "openalex",
            "source_record_id": "https://openalex.org/W-valid",
            "doi": "10.1000/valid",
            "title": "Lithium-sulfur batteries with improved separator design",
            "abstract": "This paper discusses polysulfide shuttle control in rechargeable cells.",
            "authors": ["A. Researcher"],
            "publication_year": 2024,
            "download_status": "downloaded",
            "local_pdf_path": "pdfs/valid.pdf",
        }
        invalid_record = {
            "keyword": "lithium-sulfur batteries",
            "literature_source": "openalex",
            "source_record_id": "https://openalex.org/W-invalid",
            "doi": "10.1000/invalid",
            "title": "Unrelated plant biology article",
            "abstract": "This paper studies leaf color and soil humidity.",
            "authors": ["B. Researcher"],
            "publication_year": 2022,
            "download_status": "downloaded",
            "local_pdf_path": "pdfs/invalid.pdf",
        }
        metadata_path = download_root / "metadata_battery.jsonl"
        metadata_path.write_text(
            "\n".join(json.dumps(record, ensure_ascii=False) for record in (valid_record, invalid_record)) + "\n",
            encoding="utf-8",
        )

        controller = self.make_controller(root)
        core = import_resource_module(AppPaths(ROOT, root, ()), "Download", "literature_download_core")
        invalid_id = controller._record_identity(core, invalid_record)
        library_dir = download_root / "library" / "keyword_only"
        library_dir.mkdir(parents=True)
        library_pdf = library_dir / f"{invalid_id}_invalid.pdf"
        write_sample_pdf(library_pdf)
        thumbnail_dir = download_root / "library_thumbnails"
        thumbnail_dir.mkdir(parents=True)
        thumbnail = thumbnail_dir / f"{invalid_id}.png"
        thumbnail.write_bytes(b"not really a png")
        preview_dir = download_root / "library_previews"
        preview_dir.mkdir(parents=True)
        preview = preview_dir / f"{invalid_id}.png"
        preview.write_bytes(b"not really a preview")

        return {
            "metadata": metadata_path,
            "valid_pdf": valid_pdf,
            "invalid_pdf": invalid_pdf,
            "orphan_pdf": orphan_pdf,
            "library_pdf": library_pdf,
            "thumbnail": thumbnail,
            "preview": preview,
            "valid_record": valid_record,
            "invalid_record": invalid_record,
        }

    def test_loads_and_filters_relevance_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.seed_metadata(root)
            controller = self.make_controller(root)

            self.assertEqual(controller.totalCount, 0)
            self.assertFalse(controller.hasLoaded)
            self.assertTrue(controller.refresh())
            self.wait_for_idle(controller)

            self.assertEqual(controller.totalCount, 1)
            self.assertEqual(controller.filteredCount, 1)
            record = controller.records[0]
            self.assertEqual(record["relevance_level"], "strict")
            details = controller.detailsFor(record["recordId"])
            self.assertNotIn("abstract", record)
            self.assertIn("lithium-sulfur batteries", details["matchedKeywordsText"])
            self.assertIn("polysulfide", details["abstract"].casefold())
            self.assertTrue(record["localPdfPath"].endswith("sample.pdf"))

            controller.setFilters("very_strict", "all", "")
            self.assertEqual(controller.filteredCount, 0)
            controller.setFilters("strict", "downloaded", "separator")
            self.assertEqual(controller.filteredCount, 1)

    def test_recompute_writes_relevance_fields_to_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            metadata_path, _pdf_path = self.seed_metadata(root)
            controller = self.make_controller(root)

            self.assertTrue(controller.recomputeRelevance())
            self.wait_for_idle(controller)

            record = json.loads(metadata_path.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(record["relevance_level"], "strict")
            self.assertGreaterEqual(record["relevance_score"], 9)
            self.assertEqual(record["matched_fields"], ["title", "abstract"])

    def test_refresh_does_not_deep_validate_each_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.seed_metadata(root)
            controller = self.make_controller(root)
            core = import_resource_module(AppPaths(ROOT, root, ()), "Download", "literature_download_core")

            with mock.patch.object(core, "validate_existing_pdf", side_effect=AssertionError("deep PDF validation should be lazy")):
                self.assertTrue(controller.refresh())
                self.wait_for_idle(controller)

            self.assertEqual(controller.totalCount, 1)
            self.assertTrue(controller.records[0]["localPdfPath"].endswith("sample.pdf"))

    def test_thumbnail_and_organize_keep_original_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            metadata_path, pdf_path = self.seed_metadata(root)
            controller = self.make_controller(root)
            self.assertTrue(controller.refresh())
            self.wait_for_idle(controller)
            record = controller.records[0]

            thumbnail = controller.thumbnailFor(record["recordId"])
            self.assertEqual(thumbnail, "")
            thumbnail = self.wait_for_thumbnail(controller, record["recordId"])
            self.assertTrue(thumbnail.startswith("file:"))

            self.assertTrue(controller.organizeByRelevance())
            self.wait_for_idle(controller)
            self.assertTrue(pdf_path.exists())
            organized = list((root / "Download" / "library" / "strict").glob("*.pdf"))
            self.assertEqual(len(organized), 1)
            updated = json.loads(metadata_path.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(updated["organized_level"], "strict")
            self.assertTrue(Path(updated["organized_path"]).exists())

    def test_thumbnail_state_tracks_generating_ready_missing_and_failed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _metadata_path, pdf_path = self.seed_metadata(root)
            controller = self.make_controller(root)
            self.assertTrue(controller.refresh())
            self.wait_for_idle(controller)
            record = controller.records[0]
            record_id = record["recordId"]
            started = threading.Event()
            release = threading.Event()
            original_render = LiteratureLibraryController._render_pdf_first_page

            def delayed_render(path: Path, image_path: Path, max_width: int) -> str:
                started.set()
                release.wait(timeout=5.0)
                return original_render(path, image_path, max_width)

            with mock.patch.object(LiteratureLibraryController, "_render_pdf_first_page", side_effect=delayed_render):
                self.assertEqual(controller.thumbnailFor(record_id), "")
                self.assertTrue(started.wait(timeout=2.0))
                self.assertEqual(controller.thumbnailStateFor(record_id), "generating")
                release.set()
                thumbnail = self.wait_for_thumbnail(controller, record_id)

            self.assertTrue(thumbnail.startswith("file:"))
            self.assertEqual(controller.thumbnailStateFor(record_id), "ready")

            missing_record_id = "missing"
            controller._record_by_id[missing_record_id] = {"recordId": missing_record_id, "localPdfPath": ""}
            self.assertEqual(controller.thumbnailStateFor(missing_record_id), "missing_pdf")
            self.assertEqual(controller.thumbnailFor(missing_record_id), "")

            failed_record_id = "failed"
            controller._record_by_id[failed_record_id] = {"recordId": failed_record_id, "localPdfPath": str(pdf_path)}
            with mock.patch.object(LiteratureLibraryController, "_render_pdf_first_page", return_value=""):
                self.assertEqual(controller.thumbnailFor(failed_record_id), "")
                deadline = time.monotonic() + 5.0
                while controller.thumbnailStateFor(failed_record_id) == "generating" and time.monotonic() < deadline:
                    QCoreApplication.processEvents()
                    time.sleep(0.01)
                QCoreApplication.processEvents()

            self.assertEqual(controller.thumbnailStateFor(failed_record_id), "failed")
            self.assertEqual(controller.thumbnailFor(failed_record_id), "")

    def test_preview_generates_high_resolution_cache_lazily(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _metadata_path, pdf_path = self.seed_metadata(root)
            controller = self.make_controller(root)
            self.assertTrue(controller.refresh())
            self.wait_for_idle(controller)
            record = controller.records[0]

            self.assertEqual(controller.previewFor(record["recordId"]), "")
            preview = self.wait_for_preview(controller, record["recordId"])
            self.assertTrue(preview.startswith("file:"))
            preview_path = root / "Download" / "library_previews" / f"{record['recordId']}.png"
            self.assertTrue(preview_path.exists())
            self.assertEqual(controller.previewFor(record["recordId"]), preview)

            pdf_path.unlink()
            missing_record_id = "missing"
            controller._record_by_id[missing_record_id] = {"recordId": missing_record_id, "localPdfPath": str(pdf_path)}
            self.assertEqual(controller.previewFor(missing_record_id), "")

    def test_cleanup_preview_and_confirm_delete_old_pdfs(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            seeded = self.seed_cleanup_metadata(root)
            controller = self.make_controller(root)

            self.assertTrue(controller.previewCleanup())
            self.wait_for_idle(controller)

            self.assertTrue(controller.cleanupPending)
            paths = {Path(candidate["path"]) for candidate in controller.cleanupCandidates}
            self.assertNotIn(seeded["valid_pdf"], paths)
            self.assertIn(seeded["invalid_pdf"], paths)
            self.assertIn(seeded["orphan_pdf"], paths)
            self.assertIn(seeded["library_pdf"], paths)
            self.assertIn(seeded["thumbnail"], paths)
            self.assertIn(seeded["preview"], paths)
            self.assertGreaterEqual(controller.cleanupSummary["count"], 4)

            self.assertTrue(controller.confirmCleanup())
            self.wait_for_idle(controller)

            self.assertTrue(seeded["valid_pdf"].exists())
            self.assertFalse(seeded["invalid_pdf"].exists())
            self.assertFalse(seeded["orphan_pdf"].exists())
            self.assertFalse(seeded["library_pdf"].exists())
            self.assertFalse(seeded["thumbnail"].exists())
            self.assertFalse(seeded["preview"].exists())
            self.assertFalse(controller.cleanupPending)

            records = [json.loads(line) for line in seeded["metadata"].read_text(encoding="utf-8").splitlines()]
            valid = next(record for record in records if record["doi"] == "10.1000/valid")
            invalid = next(record for record in records if record["doi"] == "10.1000/invalid")
            self.assertEqual(valid["download_status"], "downloaded")
            self.assertEqual(valid["local_pdf_path"], "pdfs/valid.pdf")
            self.assertEqual(invalid["download_status"], "deleted_by_cleanup")
            self.assertIsNone(invalid["local_pdf_path"])
            self.assertIn("cleanup_deleted_at", invalid)
            self.assertIn("当前关键词", invalid["cleanup_reason"])


if __name__ == "__main__":
    unittest.main()
