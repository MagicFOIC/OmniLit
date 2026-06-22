from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    from PySide6.QtCore import QCoreApplication
    from omnilit_qt.word_cloud_controller import WordCloudController
except ModuleNotFoundError:
    QCoreApplication = None
    WordCloudController = None

from tests.test_knowledge_graph_controller import FakePaths, InstantWorker


@unittest.skipUnless(WordCloudController is not None, "PySide6 is not installed")
class WordCloudControllerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._qt_app = QCoreApplication.instance() or QCoreApplication([])

    def test_single_and_library_clouds_use_separate_caches(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            controller = WordCloudController(None, FakePaths(Path(temp)), None, None)
            record = {"recordId": "p1", "title": "Graph Learning", "localPdfPath": "paper.pdf", "keywordsText": "graph; learning"}
            with patch("omnilit_qt.word_cloud_controller.ManagedWorker", InstantWorker):
                self.assertTrue(controller.generateForRecord("p1", record, "paper.pdf"))
                self.assertEqual(controller.currentScope, "record")
                self.assertTrue(controller.cloud["terms"])
                term = controller.cloud["terms"][0]
                self.assertTrue(controller.selectTerm(term["normalized"]))
                self.assertEqual(controller.selectedTerm["normalized"], term["normalized"])
                record_path = controller._record_cloud_path("p1")
                self.assertTrue(record_path.is_file())
                self.assertTrue(controller.hasCloud("p1"))
                self.assertTrue(controller.generateForRecords([record]))
                self.assertEqual(controller.currentScope, "library")
                self.assertTrue(controller._collection_path(controller.currentKey).is_file())
                self.assertNotEqual(record_path, controller._collection_path(controller.currentKey))
