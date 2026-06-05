from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from omnilit_qt.paths import AppPaths
from omnilit_qt.services import AccountStore

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

    def test_loads_and_filters_relevance_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.seed_metadata(root)
            controller = self.make_controller(root)

            self.assertEqual(controller.totalCount, 1)
            self.assertEqual(controller.filteredCount, 1)
            record = controller.records[0]
            self.assertEqual(record["relevance_level"], "strict")
            self.assertIn("lithium-sulfur batteries", record["matched_keywords"])
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

            controller.recomputeRelevance()

            record = json.loads(metadata_path.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(record["relevance_level"], "strict")
            self.assertGreaterEqual(record["relevance_score"], 9)
            self.assertEqual(record["matched_fields"], ["title", "abstract"])

    def test_thumbnail_and_organize_keep_original_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            metadata_path, pdf_path = self.seed_metadata(root)
            controller = self.make_controller(root)
            record = controller.records[0]

            thumbnail = controller.thumbnailFor(record["recordId"])
            self.assertTrue(thumbnail.startswith("file:"))

            self.assertTrue(controller.organizeByRelevance())
            self.assertTrue(pdf_path.exists())
            organized = list((root / "Download" / "library" / "strict").glob("*.pdf"))
            self.assertEqual(len(organized), 1)
            updated = json.loads(metadata_path.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(updated["organized_level"], "strict")
            self.assertTrue(Path(updated["organized_path"]).exists())


if __name__ == "__main__":
    unittest.main()
