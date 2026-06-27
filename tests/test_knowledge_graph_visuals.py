from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
QML_DIR = Path(__file__).parents[1] / "ui" / "qml"


class KnowledgeGraphVisualTests(unittest.TestCase):
    def test_view_exposes_obsidian_style_settings_and_circular_nodes(self) -> None:
        view = (QML_DIR / "KnowledgeGraphView.qml").read_text(encoding="utf-8")
        for token in (
            'property bool settingsOpen: true',
            'property bool showArrows: false',
            'property bool showLabels: false',
            'property bool dimUnrelated: true',
            'property real textFadeThreshold: 1.15',
            "readonly property color graphBackground: theme.canvas",
            "border.color: theme.border",
            "GraphSettingsPanel {",
            "GraphLegend {",
            "GraphEvidenceBadge {",
            "id: backgroundCanvas",
            "createRadialGradient",
            "function nodeRadius(",
            "width: r * 2",
            "radius: width / 2",
            "function edgeOpacity(",
            "function confidenceColor(",
            "function nodeGlyph(",
            "function resetGraphSettings()",
        ):
            self.assertIn(token, view)
        self.assertIn("root.showLabels", view)
        self.assertIn("root.graphScale >= root.textFadeThreshold", view)
        self.assertIn("root.linkThickness", view)
        self.assertIn("root.showArrows", view)

    def test_graph_controls_use_i18n_and_disperse_radial_layout(self) -> None:
        view = (QML_DIR / "KnowledgeGraphView.qml").read_text(encoding="utf-8")
        for token in (
            "I18n { id: i18n }",
            'i18n.text("graph_style_overview")',
            'i18n.text("graph_density_compact")',
            'i18n.text("graph_depth_tooltip")',
            'i18n.text("graph_empty_filter")',
            'i18n.text("graph_page")',
            "root.radialPoint(index, root.centerNodeId(), 0.22)",
            "root.radialPoint(index, root.centerNodeId(), 0.25)",
            "var ringJitter = (depthValue % 2) * 0.17",
            "var radius = Math.min(0.48, 0.24 + (depthValue - 1) * ringStep)",
            "var crowdOffset = peers > 10",
        ):
            self.assertIn(token, view)
        for hardcoded in (
            'model: ["Overview", "Academic", "Radial", "Focus"]',
            'text: "Review"',
            'text: "Fit graph"',
            'text: "Fullscreen"',
            'text: "No nodes in the current filter"',
        ):
            self.assertNotIn(hardcoded, view)

    def test_view_keeps_existing_navigation_layout_and_selection_contracts(self) -> None:
        view = (QML_DIR / "KnowledgeGraphView.qml").read_text(encoding="utf-8")
        for token in (
            'property string displayStyle: "overview"',
            'styleValues: ["overview", "academic", "radial", "focus"]',
            "function neighborhood(", "function overviewPoint(", "function radialPoint(",
            "function academicPoint(", "function edgeAt(", "function nodeOpacity(",
            "function edgeControlPoint(", "quadraticCurveTo", "distanceToCurve",
            "fullscreenRequested", "displayStyleRequested", "knowledgeGraphController.setDensity",
        ):
            self.assertIn(token, view)
        self.assertIn('root.displayStyle === "focus"', view)

    def test_settings_panel_has_live_graph_controls(self) -> None:
        panel = (QML_DIR / "GraphSettingsPanel.qml").read_text(encoding="utf-8")
        for token in (
            "Theme { id: theme }", "I18n { id: i18n }", "color: theme.surfaceElevated", "border.color: theme.border",
            'i18n.text("graph_settings")', 'i18n.text("graph_arrows")',
            'i18n.text("graph_labels")', 'i18n.text("graph_dim_unrelated")',
            'i18n.text("graph_node_size")', 'i18n.text("graph_link_thickness")',
            "signal resetRequested()", "Slider", "Switch",
            "onValueChanged: root.textFadeThreshold = value",
            "onValueChanged: root.nodeSizeScale = value",
            "onValueChanged: root.linkThickness = value",
        ):
            self.assertIn(token, panel)
        self.assertNotIn("onMoved:", panel)
        for hardcoded in ('text: "Graph settings"', 'text: "Arrows"', 'text: "Labels"', 'text: "Animate"'):
            self.assertNotIn(hardcoded, panel)

    def test_graph_interactions_refresh_layout_immediately(self) -> None:
        view = (QML_DIR / "KnowledgeGraphView.qml").read_text(encoding="utf-8")
        for token in (
            "property int layoutRevision: 0",
            "readonly property var displayNodes: root.visibleNodesForRevision(root.layoutRevision)",
            "function onChanged() { root.refreshGraphLayout() }",
            "function refreshGraphLayout()",
            "root.layoutRevision += 1",
            "property real r: root.layoutRevision, root.nodeRadius(modelData)",
            "x: root.layoutRevision, root.centerX(index) - r",
            "onDoubleClicked:",
            "Behavior on x",
            "Behavior on y",
            "onShowLabelsChanged: {",
            "onTextFadeThresholdChanged: {",
            "onNodeSizeScaleChanged: {",
            "onAnimateLayoutChanged: {",
        ):
            self.assertIn(token, view)

    def test_fit_graph_uses_visible_bounds_and_settings_panel_space(self) -> None:
        view = (QML_DIR / "KnowledgeGraphView.qml").read_text(encoding="utf-8")
        for token in (
            "function fitGraph()",
            "var minX = Number.POSITIVE_INFINITY",
            "var radius = root.nodeRadius(root.displayNodes[i]) + 18",
            "var panelReserve = root.settingsOpen ? Math.min(settingsPanel.width + 56, width * 0.38) : 0",
            "var availableWidth = Math.max(160, width - panelReserve - padding * 2)",
            "var targetScale = Math.min(availableWidth / boundsWidth, availableHeight / boundsHeight)",
            "var scaledGraphCenterX = (graphCenterX - width / 2) * root.graphScale + width / 2",
            "root.panX = targetCenterX - scaledGraphCenterX",
        ):
            self.assertIn(token, view)

    def test_i18n_has_graph_keys_for_supported_languages(self) -> None:
        i18n = (ROOT / "omnilit_qt" / "i18n.py").read_text(encoding="utf-8")
        for token in (
            '"graph_style_overview": ("总览", "Overview")',
            '"graph_settings": ("图谱设置", "Graph settings")',
            '"graph_empty_filter": ("当前筛选下没有节点", "No nodes in the current filter")',
            '"graph_style_overview": "Обзор"',
            '"graph_settings": "Настройки графа"',
            '"graph_empty_filter": "Нет узлов в текущем фильтре"',
        ):
            self.assertIn(token, i18n)

    def test_page_has_fullscreen_split_view_quality_footer_and_shared_style(self) -> None:
        page = (QML_DIR / "KnowledgeGraphPage.qml").read_text(encoding="utf-8")
        for token in (
            "id: fullscreenGraph", "parent: Overlay.overlay",
            "KnowledgeGraphPanel {", "edge_evidence_coverage",
            "relation_needs_review_count", "searchQuery: root.searchQuery",
            'property string graphDisplayStyle: "overview"',
            "displayStyle: root.graphDisplayStyle", "onDisplayStyleRequested",
        ):
            self.assertIn(token, page)

    def test_comparison_page_reuses_same_graph_view_style(self) -> None:
        compare_page = (QML_DIR / "LiteratureCompareGraphPage.qml").read_text(encoding="utf-8")
        self.assertIn('property string graphDisplayStyle: "overview"', compare_page)
        self.assertIn("displayStyle: root.graphDisplayStyle", compare_page)
        self.assertIn("onDisplayStyleRequested", compare_page)

    def test_detail_card_surfaces_provenance_and_relation_reason(self) -> None:
        card = (QML_DIR / "GraphNodeCard.qml").read_text(encoding="utf-8")
        for token in (
            "normalized_label", "canonical_id", "extraction_method", "source_section",
            "confidence_reason", "relation_method", "direction_reason", "relation_evidence",
            "review_reasons", "Review reasons", "modelData.section", "modelData.extraction_method",
        ):
            self.assertIn(token, card)

    def test_new_graph_visual_components_surface_review_and_evidence(self) -> None:
        legend = (QML_DIR / "GraphLegend.qml").read_text(encoding="utf-8")
        badge = (QML_DIR / "GraphEvidenceBadge.qml").read_text(encoding="utf-8")
        for token in ("reviewCount()", "evidenceCount()", "nodes.length", "edges.length", "typeColor"):
            self.assertIn(token, legend)
        for token in ("property int count", "property real confidence", "property bool needsReview"):
            self.assertIn(token, badge)


if __name__ == "__main__":
    unittest.main()
