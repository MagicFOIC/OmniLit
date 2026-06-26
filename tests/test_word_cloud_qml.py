from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


class WordCloudQmlTests(unittest.TestCase):
    def test_single_and_filtered_library_entries_are_wired(self) -> None:
        qml_dir = ROOT / "ui" / "qml"
        library = (qml_dir / "LiteratureLibraryPage.qml").read_text(encoding="utf-8")
        reader = (qml_dir / "LiteratureReaderPage.qml").read_text(encoding="utf-8")
        page = (qml_dir / "WordCloudPage.qml").read_text(encoding="utf-8")
        view = (qml_dir / "WordCloudView.qml").read_text(encoding="utf-8")
        app = (ROOT / "omnilit_qt" / "app.py").read_text(encoding="utf-8")
        self.assertIn("onClicked: root.openLibraryWordCloud()", library)
        self.assertIn("wordCloudController.generateForRecords(records)", library)
        self.assertIn("wordCloudController.generateForRecord", library)
        self.assertIn("wordCloudController.hasCloud", library)
        self.assertIn("knowledgeGraphController.hasGraph", library)
        self.assertIn('property string readerReturnTarget: ""', library)
        self.assertIn("root.closeReader()", library)
        self.assertIn('root.readerReturnTarget = root.wordCloudOpen ? "wordcloud"', library)
        self.assertIn("signal wordCloudRequested", reader)
        self.assertIn("WordCloudPage", library)
        self.assertIn("WordCloudView", page)
        self.assertIn("Repeater", view)
        self.assertIn("primaryNodeId", view)
        self.assertIn("modelData.category", view)
        self.assertIn("selectGraphNodeForTerm", page)
        self.assertIn("nodeRefs", page)
        self.assertIn("signal graphRequested(string recordId, string nodeId, string keyword)", page)
        self.assertIn("pendingGraphNodeId", library)
        self.assertIn("knowledgeGraphController.selectNode(root.pendingGraphNodeId)", library)
        self.assertIn('"wordCloudController": word_cloud', app)
        self.assertIn("word_cloud.setKnowledgeGraphController(knowledge_graph)", app)

    def test_graph_view_uses_precomputed_layout_and_density(self) -> None:
        view = (ROOT / "ui" / "qml" / "KnowledgeGraphView.qml").read_text(encoding="utf-8")
        page = (ROOT / "ui" / "qml" / "KnowledgeGraphPage.qml").read_text(encoding="utf-8")
        self.assertIn("property var graphLayout", view)
        self.assertIn('property string displayStyle: "overview"', view)
        self.assertIn("function academicPoint(", view)
        self.assertIn("function radialPoint(", view)
        self.assertIn("knowledgeGraphController.setDensity", view)
        self.assertIn("root.adjacency[selected]", view)
        self.assertIn("ctx.lineTo", view)
        self.assertIn("filterCounts: knowledgeGraphController.filterCounts", page)
        self.assertNotIn("id: edgeCanvas", page)


if __name__ == "__main__":
    unittest.main()
