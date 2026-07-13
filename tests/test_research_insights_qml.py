from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
QML_DIR = ROOT / "ui" / "qml"


class ResearchInsightsQmlTests(unittest.TestCase):
    def test_research_view_exposes_collaboration_importance_and_recommendation_evidence(self) -> None:
        view = (QML_DIR / "ResearchInsightsView.qml").read_text(encoding="utf-8")
        for token in (
            "作者合作", "机构合作", "推荐阅读", "Canvas {", "importanceScore", "bridgeScore",
            "作者覆盖", "机构覆盖", "显式任职", "warnings", "下一步最值得阅读",
            "基础论文", "跨主题桥梁", "前沿研究", "transition", "查看阅读路径图",
            "Accessible.name", "paperRequested", "graphRequested",
        ):
            self.assertIn(token, view)

    def test_topic_and_library_link_research_graph_and_reader(self) -> None:
        topic = (QML_DIR / "TopicMapPage.qml").read_text(encoding="utf-8")
        library = (QML_DIR / "LiteratureLibraryPage.qml").read_text(encoding="utf-8")
        graph = (QML_DIR / "KnowledgeGraphPage.qml").read_text(encoding="utf-8")
        for token in ("研究者与阅读", "ResearchInsightsView {", "researchNetwork", "researchGraphRequested", "recommendationRequested"):
            self.assertIn(token, topic)
        for token in (
            "onResearchGraphRequested", "openResearchNetworkGraph", "researchNetworkGraph",
            "onRecommendationRequested", "openRecommendedPaper", "openReader",
        ):
            self.assertIn(token, library)
        self.assertIn("research_network_graph", graph)


if __name__ == "__main__":
    unittest.main()
