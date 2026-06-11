from __future__ import annotations

import json
import tempfile
import time
import unittest
from pathlib import Path

from omnilit_qt.paths import AppPaths
from omnilit_qt.services import AccountStore

try:
    from PySide6.QtCore import QCoreApplication

    from omnilit_qt.app_controller import AppController
    from omnilit_qt.i18n import LocaleController
    from omnilit_qt.literature_library_controller import LiteratureLibraryController
except ModuleNotFoundError:  # pragma: no cover - depends on local Qt runtime.
    QCoreApplication = None
    AppController = None
    LocaleController = None
    LiteratureLibraryController = None


ROOT = Path(__file__).resolve().parent.parent


@unittest.skipUnless(LiteratureLibraryController is not None, "Qt dependencies are not installed")
class LiteratureKeywordGroupsTests(unittest.TestCase):
    def make_controller(self, root: Path) -> LiteratureLibraryController:
        QCoreApplication.instance() or QCoreApplication([])
        paths = AppPaths(ROOT, root, ())
        store = AccountStore(paths.data("accounts.sqlite3"))
        store.set_setting(
            "download_form_config",
            json.dumps(
                {
                    "outputDir": str(root / "Download"),
                    "keywords": "lithium-sulfur batteries\npolysulfide\nseparator",
                    "topicPack": None,
                    "minKeywordMatchRatio": "0.75",
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

    def seed_records(self, root: Path, records: list[dict]) -> None:
        download_root = root / "Download"
        download_root.mkdir(parents=True)
        (download_root / "metadata_battery.jsonl").write_text(
            "\n".join(json.dumps(record, ensure_ascii=False) for record in records) + "\n",
            encoding="utf-8",
        )

    def test_lithium_sulfur_aliases_collapse_to_one_group(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.seed_records(
                root,
                [
                    {
                        "keyword": "lithium-sulfur batteries",
                        "source_record_id": "W1",
                        "title": "Lithium-sulfur batteries with polysulfide control",
                        "abstract": "Lithium-sulfur batteries suppress polysulfides.",
                        "extracted_keywords": ["lithium-sulfur batteries"],
                    },
                    {
                        "keyword": "Li-S battery",
                        "source_record_id": "W2",
                        "title": "Li-S battery separator design",
                        "abstract": "A Li-S battery separator controls shuttle.",
                        "extracted_keywords": ["Li-S battery"],
                    },
                ],
            )
            controller = self.make_controller(root)

            self.assertTrue(controller.refresh())
            self.wait_for_idle(controller)

            option = next(item for item in controller.keywordGroupOptions if item["key"] == "lithium sulfur battery")
            self.assertEqual(option["count"], 2)

    def test_keyword_group_multiselect_union_and_clear(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.seed_records(
                root,
                [
                    {
                        "keyword": "polysulfide",
                        "source_record_id": "W-poly",
                        "title": "Polysulfide shuttle control",
                        "abstract": "Polysulfides are controlled by catalysts.",
                        "extracted_keywords": ["polysulfides"],
                    },
                    {
                        "keyword": "separator",
                        "source_record_id": "W-sep",
                        "title": "Separator coating for lithium batteries",
                        "abstract": "Separators reduce shuttle effects.",
                        "extracted_keywords": ["separators"],
                    },
                    {
                        "keyword": "cathode",
                        "source_record_id": "W-other",
                        "title": "Sulfur cathode host",
                        "abstract": "A cathode host improves cycling.",
                        "extracted_keywords": ["sulfur cathode"],
                    },
                ],
            )
            controller = self.make_controller(root)
            self.assertTrue(controller.refresh())
            self.wait_for_idle(controller)

            controller.setFilters("all", "all", "", ["polysulfide", "separator"])
            self.assertEqual(controller.filteredCount, 2)

            controller.setFilters("all", "all", "", [])
            self.assertEqual(controller.filteredCount, 3)

    def test_keyword_group_filter_stacks_with_search_and_pdf_status(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.seed_records(
                root,
                [
                    {
                        "keyword": "polysulfide",
                        "source_record_id": "W-alpha",
                        "title": "Alpha polysulfide control",
                        "abstract": "Polysulfide conversion in cells.",
                        "extracted_keywords": ["polysulfides"],
                        "download_status": "failed",
                    },
                    {
                        "keyword": "polysulfide",
                        "source_record_id": "W-beta",
                        "title": "Beta polysulfide control",
                        "abstract": "Polysulfide conversion in cells.",
                        "extracted_keywords": ["polysulfides"],
                        "download_status": "downloaded",
                    },
                    {
                        "keyword": "separator",
                        "source_record_id": "W-separator",
                        "title": "Alpha separator design",
                        "abstract": "Separators block shuttle.",
                        "extracted_keywords": ["separators"],
                        "download_status": "failed",
                    },
                ],
            )
            controller = self.make_controller(root)
            self.assertTrue(controller.refresh())
            self.wait_for_idle(controller)

            controller.setFilters("all", "failed", "alpha", ["polysulfide"])

            self.assertEqual(controller.filteredCount, 1)
            self.assertIn("Alpha polysulfide", controller.records[0]["title"])


if __name__ == "__main__":
    unittest.main()
