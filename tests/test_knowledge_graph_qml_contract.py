from __future__ import annotations

import unittest
from pathlib import Path

try:
    from PySide6.QtCore import QCoreApplication, QUrl
    from PySide6.QtQml import QQmlComponent, QQmlEngine
except ModuleNotFoundError:  # pragma: no cover - depends on local Qt runtime.
    QUrl = None
    QQmlComponent = None
    QQmlEngine = None


QML_DIR = Path(__file__).parents[1] / "ui" / "qml"


@unittest.skipUnless(QQmlEngine is not None, "PySide6 is not installed in this environment")
class KnowledgeGraphQmlContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QCoreApplication.instance() or QCoreApplication([])

    def test_graph_components_parse_without_import_errors(self) -> None:
        engine = QQmlEngine()
        engine.addImportPath(str(QML_DIR))
        files = [
            "KnowledgeGraphView.qml",
            "KnowledgeGraphPage.qml",
            "KnowledgeGraphPanel.qml",
            "GraphFilterBar.qml",
            "GraphNodeCard.qml",
            "GraphSettingsPanel.qml",
            "GraphLegend.qml",
            "GraphMiniMap.qml",
            "GraphEvidenceBadge.qml",
        ]
        for name in files:
            path = QML_DIR / name
            if not path.exists():
                continue
            with self.subTest(name=name):
                component = QQmlComponent(engine, QUrl.fromLocalFile(str(path)))
                self.assertNotEqual(component.status(), QQmlComponent.Error, component.errorString())

    def test_knowledge_graph_view_keeps_existing_contract_tokens(self) -> None:
        view = (QML_DIR / "KnowledgeGraphView.qml").read_text(encoding="utf-8")
        for token in (
            "property var nodes",
            "property var edges",
            "property string searchQuery",
            "property string displayStyle",
            "signal nodeRequested",
            "signal edgeRequested",
            "function fitGraph()",
            "function resetView()",
        ):
            self.assertIn(token, view)


if __name__ == "__main__":
    unittest.main()
