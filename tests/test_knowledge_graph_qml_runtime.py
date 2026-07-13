from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import QCoreApplication, QUrl
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlComponent, QQmlContext, QQmlEngine
    from omnilit_qt.knowledge_graph_controller import KnowledgeGraphController
    from omnilit_qt.topic_map_controller import TopicMapController
except ModuleNotFoundError:  # pragma: no cover - optional runtime
    QCoreApplication = QGuiApplication = None


ROOT = Path(__file__).parents[1]
QML_DIR = ROOT / "ui" / "qml"


class FakePaths:
    def __init__(self, root: Path) -> None:
        self.root = root

    def data(self, *parts: str) -> Path:
        return self.root.joinpath(*parts)

    content = data
    runtime = data


@unittest.skipUnless(QGuiApplication is not None, "PySide6 is not installed in this environment")
class KnowledgeGraphQmlRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        existing = QCoreApplication.instance()
        if existing is not None and not isinstance(existing, QGuiApplication):
            raise unittest.SkipTest("A non-GUI Qt application already exists; run this runtime test standalone.")
        cls.app = existing or QGuiApplication([])
        cls.temp = tempfile.TemporaryDirectory()
        paths = FakePaths(Path(cls.temp.name))
        cls.graph_controller = KnowledgeGraphController(None, paths, None, None)
        cls.topic_controller = TopicMapController(None, paths, None, None)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.graph_controller.shutdown(0.1)
        cls.topic_controller.shutdown(0.1)
        cls.temp.cleanup()

    def test_core_pages_compile_and_instantiate_with_real_controllers(self) -> None:
        engine = QQmlEngine()
        engine.addImportPath(str(QML_DIR))
        context = QQmlContext(engine.rootContext())
        context.setContextProperty("knowledgeGraphController", self.graph_controller)
        context.setContextProperty("topicMapController", self.topic_controller)
        instances = []
        for filename in ("KnowledgeGraphPage.qml", "TopicMapPage.qml"):
            component = QQmlComponent(engine, QUrl.fromLocalFile(str(QML_DIR / filename)))
            self.assertEqual(component.status(), QQmlComponent.Ready, "\n".join(error.toString() for error in component.errors()))
            instance = component.create(context)
            self.assertIsNotNone(instance, "\n".join(error.toString() for error in component.errors()))
            instances.append(instance)
        self.app.processEvents()
        # Some Qt Quick roots self-destruct when their transient dialog/window
        # resources are released during event processing. The engine owns any
        # remaining instances, so explicit deletion is neither required nor
        # portable across PySide versions.
