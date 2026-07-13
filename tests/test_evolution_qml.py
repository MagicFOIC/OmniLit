from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
QML_DIR = ROOT / "ui" / "qml"


class EvolutionQmlTests(unittest.TestCase):
    def test_topic_page_exposes_range_playback_paths_and_window_graph(self) -> None:
        page = (QML_DIR / "TopicMapPage.qml").read_text(encoding="utf-8")
        for token in (
            'property string viewMode: "topics"', "时间演化", "setEvolutionRange", "resetEvolutionRange",
            "startEvolutionPlayback", "advanceEvolutionPlayback", "EvolutionTimeline {",
            "关键引文路径", "关键转折点", "查看当前时间窗口图谱", "evolutionGraphRequested",
            "缺失年份", "时间冲突引文",
        ):
            self.assertIn(token, page)

    def test_timeline_is_keyboard_navigable_and_links_papers(self) -> None:
        timeline = (QML_DIR / "EvolutionTimeline.qml").read_text(encoding="utf-8")
        for token in (
            "Keys.onPressed", "Qt.Key_Right", "Qt.Key_Left", "paperRequested", "yearRequested",
            "关键论文", "turningPoints", "citations", "playbackYear",
        ):
            self.assertIn(token, timeline)

    def test_library_opens_evolution_graph_and_returns_to_timeline(self) -> None:
        library = (QML_DIR / "LiteratureLibraryPage.qml").read_text(encoding="utf-8")
        graph_page = (QML_DIR / "KnowledgeGraphPage.qml").read_text(encoding="utf-8")
        for token in (
            "onEvolutionGraphRequested", "function openEvolutionGraph", "topicMapController.evolutionGraph",
            "knowledgeGraphController.loadTopicGraph(graph)", "graphReturnToTopicMap",
            "knowledgeGraphController.selectLiteratureRecord",
        ):
            self.assertIn(token, library)
        self.assertIn("evolution_graph", graph_page)
        self.assertIn("!root.topicGraphMode", graph_page)


if __name__ == "__main__":
    unittest.main()
