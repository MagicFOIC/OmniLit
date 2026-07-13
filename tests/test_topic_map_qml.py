from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
QML_DIR = ROOT / "ui" / "qml"


class TopicMapQmlTests(unittest.TestCase):
    def test_library_exposes_domain_map_and_local_graph_workflow(self) -> None:
        library = (QML_DIR / "LiteratureLibraryPage.qml").read_text(encoding="utf-8")
        for token in (
            "领域主题地图", "TopicMapPage {", "topicMapController.generateForRecords(records)",
            "literatureLibraryController.topicAnalysisRecords",
            "topicMapController.topicGraph", "knowledgeGraphController.loadTopicGraph(graph)",
            "graphReturnToTopicMap", "openTopicLocalGraph",
        ):
            self.assertIn(token, library)

    def test_topic_page_explains_clusters_growth_and_representatives(self) -> None:
        page = (QML_DIR / "TopicMapPage.qml").read_text(encoding="utf-8")
        bubbles = (QML_DIR / "TopicBubbleMap.qml").read_text(encoding="utf-8")
        for token in (
            "为什么形成该主题", "核心主题词", "子主题", "年度分布", "代表论文",
            "论文归类依据", "进入该主题的局部图谱", "assignmentsForTopic",
        ):
            self.assertIn(token, page)
        for token in ("Keys.onPressed", "topicRequested", "modelData.radius", "lowConfidence", "气泡"):
            self.assertIn(token, bubbles if token != "气泡" else page)

    def test_topic_controller_is_registered_and_shutdown(self) -> None:
        app = (ROOT / "omnilit_qt" / "app.py").read_text(encoding="utf-8")
        controllers = (ROOT / "omnilit_qt" / "controllers.py").read_text(encoding="utf-8")
        self.assertIn('"topicMapController": topic_map', app)
        self.assertIn("TopicMapController", controllers)
        self.assertIn("word_cloud, topic_map, translation", app)

    def test_derived_topic_graph_cannot_be_regenerated_as_a_single_paper(self) -> None:
        page = (QML_DIR / "KnowledgeGraphPage.qml").read_text(encoding="utf-8")
        self.assertIn("readonly property bool topicGraphMode", page)
        self.assertIn("visible: !root.narrowLayout && !root.topicGraphMode", page)


if __name__ == "__main__":
    unittest.main()
