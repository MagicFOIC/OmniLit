from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
QML_DIR = ROOT / "ui" / "qml"


class NetworkAnalysisQmlTests(unittest.TestCase):
    def test_analysis_view_switches_methods_and_explains_coverage(self) -> None:
        view = (QML_DIR / "NetworkAnalysisView.qml").read_text(encoding="utf-8")
        for token in (
            "关键词密度", "共被引", "文献耦合", "核心论文", "桥接论文", "突现趋势", "主题增长",
            "referenceCoverage", "yearCoverage", "warnings", "explanation",
            "Canvas {", "density", "进入局部图谱", "Accessible.name",
        ):
            self.assertIn(token, view)

    def test_topic_page_and_library_open_structural_local_graph(self) -> None:
        page = (QML_DIR / "TopicMapPage.qml").read_text(encoding="utf-8")
        library = (QML_DIR / "LiteratureLibraryPage.qml").read_text(encoding="utf-8")
        graph_page = (QML_DIR / "KnowledgeGraphPage.qml").read_text(encoding="utf-8")
        for token in ("结构分析", "NetworkAnalysisView {", "networkAnalysis", "analysisGraphRequested"):
            self.assertIn(token, page)
        for token in ("onAnalysisGraphRequested", "openNetworkAnalysisGraph", "networkAnalysisGraph", "loadTopicGraph"):
            self.assertIn(token, library)
        self.assertIn("network_analysis_graph", graph_page)


if __name__ == "__main__":
    unittest.main()
