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
            "GraphReplayDocument.qml",
            "GraphLiteratureList.qml",
            "GraphPathPanel.qml",
            "GraphImageExportDialog.qml",
            "TopicBubbleMap.qml",
            "TopicMapPage.qml",
            "EvolutionTimeline.qml",
            "LiteratureCompareGraphPage.qml",
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

    def test_replay_page_connects_document_evidence_to_incremental_graph(self) -> None:
        page = (QML_DIR / "KnowledgeGraphPage.qml").read_text(encoding="utf-8")
        document = (QML_DIR / "GraphReplayDocument.qml").read_text(encoding="utf-8")
        for token in ("startReplay()", "advanceReplay()", "GraphReplayDocument {", "replayEvent:", "replayComplete"):
            self.assertIn(token, page)
        for token in ("evidenceHalo", "relationCues", "renderPageAsync", "evidencePointIn", "fullDocumentMode", "fullDocumentFlick", "pdfExtractionController.pageCount"):
            self.assertIn(token, document)
        for token in ("bezierCurveTo", "nodePointIn", "flightAnimation.restart()", "compactLayout"):
            self.assertIn(token, page)

    def test_progressive_exploration_is_wired_to_view_and_detail_panel(self) -> None:
        page = (QML_DIR / "KnowledgeGraphPage.qml").read_text(encoding="utf-8")
        panel = (QML_DIR / "KnowledgeGraphPanel.qml").read_text(encoding="utf-8")
        view = (QML_DIR / "KnowledgeGraphView.qml").read_text(encoding="utf-8")
        for token in ("explorationStats", "resetExploration(graphView.captureViewState())", "expandNeighbors(nodeId, relationMode, 12)"):
            self.assertIn(token, page)
        for token in ("按需展开邻居", "references", "cited_by", "institutions", "explorationStatus"):
            self.assertIn(token, panel)
        self.assertIn("signal expandRequested", view)
        self.assertIn('root.expandRequested(String(modelData.id || ""), "all")', view)

    def test_saved_views_capture_and_restore_canvas_state(self) -> None:
        page = (QML_DIR / "KnowledgeGraphPage.qml").read_text(encoding="utf-8")
        view = (QML_DIR / "KnowledgeGraphView.qml").read_text(encoding="utf-8")
        filter_bar = (QML_DIR / "GraphFilterBar.qml").read_text(encoding="utf-8")
        for token in ("savedViews", "saveView(", "restoreView(", "deleteView(", "onViewRestored", "saveViewPopup"):
            self.assertIn(token, page)
        for token in ("function captureViewState()", "function applyViewState(state", "graphScale", "panX", "showLabels"):
            self.assertIn(token, view)
        self.assertIn("property string searchText", filter_bar)
        self.assertIn("text: root.searchText", filter_bar)

    def test_recoverable_share_package_is_wired(self) -> None:
        page = (QML_DIR / "KnowledgeGraphPage.qml").read_text(encoding="utf-8")
        for token in ("生成分享包", "导入分享包", "exportSharePackage(", "importSharePackage(", "FileDialog"):
            self.assertIn(token, page)

    def test_year_topic_author_institution_and_venue_facets_are_wired(self) -> None:
        page = (QML_DIR / "KnowledgeGraphPage.qml").read_text(encoding="utf-8")
        filters = (QML_DIR / "GraphFilterBar.qml").read_text(encoding="utf-8")
        for token in ("facetOptions", "facetFilters", "setFacetFilter", "clearFacetFilters"):
            self.assertIn(token, page)
        for token in ('key: "year"', 'key: "topic"', 'key: "author"', 'key: "institution"', 'key: "venue"', "交集"):
            self.assertIn(token, filters)

    def test_topic_overview_shows_representative_authors_and_similarity_links(self) -> None:
        page = (QML_DIR / "TopicMapPage.qml").read_text(encoding="utf-8")
        bubbles = (QML_DIR / "TopicBubbleMap.qml").read_text(encoding="utf-8")
        for token in ("representativeAuthors", "代表作者", "topicLinks"):
            self.assertIn(token, page)
        for token in ("topicLinks", "similarityCanvas", "link.similarity", "fillText"):
            self.assertIn(token, bubbles)

    def test_evolution_lifecycle_representatives_and_speed_comparison_are_wired(self) -> None:
        page = (QML_DIR / "TopicMapPage.qml").read_text(encoding="utf-8")
        timeline = (QML_DIR / "EvolutionTimeline.qml").read_text(encoding="utf-8")
        for token in ("比较两个主题的发展速度", "topicSpeedComparisons", "splitSignalCount", "mergeSignalCount", "declineSignalCount"):
            self.assertIn(token, page)
        for token in ("representativePaper", "· 代表", "该主题该年度没有代表论文"):
            self.assertIn(token, timeline)

    def test_literature_list_is_bidirectionally_linked_and_keyboard_navigable(self) -> None:
        page = (QML_DIR / "KnowledgeGraphPage.qml").read_text(encoding="utf-8")
        table = (QML_DIR / "GraphLiteratureList.qml").read_text(encoding="utf-8")
        view = (QML_DIR / "KnowledgeGraphView.qml").read_text(encoding="utf-8")
        for token in ("GraphLiteratureList {", "literatureRows", "selectLiteratureNode", "setHoveredNode", "setLiteratureSort"):
            self.assertIn(token, page)
        for token in ("Keys.onPressed", "Qt.Key_Down", "Qt.Key_Return", "pageSize", "sortRequested", "nodeHovered"):
            self.assertIn(token, table)
        self.assertIn("effectiveHoveredNodeId", view)
        self.assertIn("function focusNode(nodeId)", view)
        comparison = (QML_DIR / "LiteratureCompareGraphPage.qml").read_text(encoding="utf-8")
        self.assertIn("GraphLiteratureList {", comparison)
        self.assertIn("graphView.focusNode(nodeId)", comparison)

    def test_main_literature_list_is_left_compact_sidebar_and_top_tools_collapse(self) -> None:
        page = (QML_DIR / "KnowledgeGraphPage.qml").read_text(encoding="utf-8")
        table = (QML_DIR / "GraphLiteratureList.qml").read_text(encoding="utf-8")
        filters = (QML_DIR / "GraphFilterBar.qml").read_text(encoding="utf-8")
        path = (QML_DIR / "GraphPathPanel.qml").read_text(encoding="utf-8")
        list_position = page.index("id: literatureList")
        graph_position = page.index("id: graphView")
        self.assertGreaterEqual(list_position, 0)
        self.assertLess(list_position, graph_position)
        self.assertIn("compactMode: true", page)
        self.assertNotIn("Layout.preferredHeight: visible ? Math.min(250", page)
        self.assertIn("property bool compactMode: false", table)
        self.assertIn("property bool facetsOpen: false", filters)
        self.assertIn("property bool expanded: false", path)
        self.assertIn("Layout.minimumHeight: implicitHeight", page)

    def test_shortest_path_controls_and_highlights_are_wired(self) -> None:
        page = (QML_DIR / "KnowledgeGraphPage.qml").read_text(encoding="utf-8")
        panel = (QML_DIR / "GraphPathPanel.qml").read_text(encoding="utf-8")
        view = (QML_DIR / "KnowledgeGraphView.qml").read_text(encoding="utf-8")
        comparison = (QML_DIR / "LiteratureCompareGraphPage.qml").read_text(encoding="utf-8")
        for token in ("GraphPathPanel {", "setPathStart", "setPathEnd", "computeShortestPath", "pathRelationTypes"):
            self.assertIn(token, page)
        for token in ("有向路径", "全部关系", "查看步骤", "modelData.explanation", "relationFilterRequested"):
            self.assertIn(token, panel)
        for token in ("pathNodeIds", "pathEdgeIds", "isPathNode", "isPathEdge", "theme.warning"):
            self.assertIn(token, view)
        self.assertIn("GraphPathPanel {", comparison)

    def test_history_controls_shortcuts_and_default_restore_are_wired(self) -> None:
        page = (QML_DIR / "KnowledgeGraphPage.qml").read_text(encoding="utf-8")
        comparison = (QML_DIR / "LiteratureCompareGraphPage.qml").read_text(encoding="utf-8")
        for token in ("StandardKey.Undo", "StandardKey.Redo", "knowledgeGraphController.undo(graphView.captureViewState())", "knowledgeGraphController.redo(graphView.captureViewState())", "恢复默认", "historyState.undoAction", "onHistoryRestored"):
            self.assertIn(token, page)
        for token in ("StandardKey.Undo", "StandardKey.Redo", "恢复默认", "onHistoryRestored"):
            self.assertIn(token, comparison)

    def test_lossless_image_export_is_wired_and_restores_the_view(self) -> None:
        page = (QML_DIR / "KnowledgeGraphPage.qml").read_text(encoding="utf-8")
        comparison = (QML_DIR / "LiteratureCompareGraphPage.qml").read_text(encoding="utf-8")
        view = (QML_DIR / "KnowledgeGraphView.qml").read_text(encoding="utf-8")
        dialog = (QML_DIR / "GraphImageExportDialog.qml").read_text(encoding="utf-8")
        for token in ("function exportPng", "grabToImage", "saveToFile", "exportMode", "applyViewState(savedView, true)"):
            self.assertIn(token, view)
        for token in ("validateImageExport", "prepareImageExport", "completeImageExport", "当前视口", "完整探索图谱", "透明背景"):
            self.assertIn(token, dialog)
        for content in (page, comparison):
            self.assertIn("GraphImageExportDialog {", content)
            self.assertIn("imageExportNodes", content)
            self.assertIn("导出图片", content)

    def test_layered_render_projection_is_wired_without_changing_export_graph(self) -> None:
        page = (QML_DIR / "KnowledgeGraphPage.qml").read_text(encoding="utf-8")
        comparison = (QML_DIR / "LiteratureCompareGraphPage.qml").read_text(encoding="utf-8")
        view = (QML_DIR / "KnowledgeGraphView.qml").read_text(encoding="utf-8")
        for token in ("renderNodes", "renderEdges", "renderLayout", "renderStatus", "setRenderViewport"):
            self.assertIn(token, page)
            self.assertIn(token, comparison)
        for token in ("renderViewportTimer", "renderViewportRequested", "focusCluster", "memberCount", "activeGraphLayout", "fullExportLayout"):
            self.assertIn(token, view)
        self.assertIn("fullExportNodes: knowledgeGraphController.imageExportNodes", page)


if __name__ == "__main__":
    unittest.main()
