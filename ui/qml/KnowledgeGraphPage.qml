import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: root

    property string recordId: ""
    property string pdfPath: ""
    property string title: ""
    property var record: ({})
    property bool comparisonMode: false
    property var comparisonRecords: []
    property string searchQuery: ""
    property string graphDisplayStyle: "overview"
    readonly property var nodes: knowledgeGraphController.nodes || []
    readonly property var edges: knowledgeGraphController.edges || []

    signal backRequested()
    signal evidenceRequested(string recordId, int page, var bbox, string elementId)

    Theme { id: theme }
    LayoutMetrics { id: metrics; viewportWidth: root.width; viewportHeight: root.height }

    Connections {
        target: knowledgeGraphController
        enabled: root.visible
        function onEvidenceFocusRequested(recordId, page, bbox, elementId) {
            root.evidenceRequested(recordId, page, bbox, elementId)
        }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 10

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 64
            radius: theme.radiusMedium
            color: theme.surface
            border.color: theme.border

            RowLayout {
                anchors.fill: parent
                anchors.margins: 10
                spacing: 8

                PillButton { text: "返回"; onClicked: root.backRequested() }
                Text {
                    Layout.fillWidth: true
                    text: "知识图谱 · " + (root.title || "当前文献")
                    color: theme.text
                    font.weight: Font.Bold
                    font.pixelSize: 18
                    elide: Text.ElideRight
                }
                Label {
                    text: knowledgeGraphController.cacheState === "fresh" ? "缓存最新" : knowledgeGraphController.cacheState === "refreshing" ? "后台更新" : "构建中"
                    color: knowledgeGraphController.cacheState === "fresh" ? theme.success : theme.warning
                    background: Rectangle { color: theme.surfaceSoft; radius: 7 }
                    padding: 5
                }
                Label {
                    visible: Number(knowledgeGraphController.qualitySummary.evidence_coverage || 0) > 0
                    text: "证据覆盖 " + Math.round(Number(knowledgeGraphController.qualitySummary.evidence_coverage || 0) * 100) + "%"
                    color: theme.textMuted
                    background: Rectangle { color: theme.surfaceSoft; radius: 7 }
                    padding: 5
                }
                BusyIndicator {
                    running: knowledgeGraphController.loading
                    visible: running
                    Layout.preferredWidth: 28
                    Layout.preferredHeight: 28
                }
                PillButton {
                    text: knowledgeGraphController.loading ? "生成中..." : "重新生成"
                    enabled: !knowledgeGraphController.loading
                    onClicked: {
                        if (root.comparisonMode)
                            knowledgeGraphController.regenerateComparisonGraph(root.comparisonRecords)
                        else
                            knowledgeGraphController.regenerateGraph(root.recordId, root.record, root.pdfPath)
                    }
                }
                PillButton {
                    text: "导出 JSON"
                    enabled: root.nodes.length > 0
                    onClicked: knowledgeGraphController.exportGraphJson(root.recordId)
                }
                PillButton {
                    text: "导出 Markdown"
                    enabled: root.nodes.length > 0
                    onClicked: knowledgeGraphController.exportGraphMarkdown(root.recordId)
                }
                PillButton {
                    text: "导出 Mermaid"
                    enabled: root.nodes.length > 0
                    onClicked: knowledgeGraphController.exportGraph(root.recordId, "mermaid")
                }
                PillButton {
                    text: "打开导出目录"
                    enabled: root.nodes.length > 0
                    onClicked: knowledgeGraphController.openGraphDirectory(root.recordId)
                }
            }
        }

        GraphFilterBar {
            Layout.fillWidth: true
            comparisonMode: root.comparisonMode
            filterCounts: knowledgeGraphController.filterCounts
            onFilterRequested: function(mode) { knowledgeGraphController.setFilterMode(mode) }
            onSearchRequested: function(text) { root.searchQuery = text; knowledgeGraphController.search(text) }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 10

            KnowledgeGraphView {
                Layout.fillWidth: true
                Layout.fillHeight: true
                nodes: root.nodes
                edges: root.edges
                searchQuery: root.searchQuery
                displayStyle: root.graphDisplayStyle
                onNodeRequested: function(nodeId) { knowledgeGraphController.selectNode(nodeId) }
                onEdgeRequested: function(edgeId) { knowledgeGraphController.selectEdge(edgeId) }
                onDisplayStyleRequested: function(displayStyle) { root.graphDisplayStyle = displayStyle }
                onFullscreenRequested: fullscreenGraph.open()
            }

            KnowledgeGraphPanel {
                Layout.preferredWidth: 300
                Layout.fillHeight: true
                selectedNode: knowledgeGraphController.selectedNode
                selectedEdge: knowledgeGraphController.selectedEdge
                onEvidenceRequested: function(itemId, index) { knowledgeGraphController.focusEvidence(itemId, index) }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 42
            radius: theme.radiusMedium
            color: theme.surface
            border.color: theme.border
            RowLayout {
                anchors.fill: parent
                anchors.margins: 8
                spacing: 14
                Text { text: "质量摘要"; color: theme.text; font.bold: true }
                Text { text: "节点证据 " + Math.round(Number(knowledgeGraphController.qualitySummary.evidence_coverage || 0) * 100) + "%"; color: theme.textMuted }
                Text { text: "关系证据 " + Math.round(Number(knowledgeGraphController.qualitySummary.edge_evidence_coverage || 0) * 100) + "%"; color: theme.textMuted }
                Text { text: "平均置信度 " + Math.round(Number(knowledgeGraphController.qualitySummary.average_confidence || 0) * 100) + "%"; color: theme.textMuted }
                Text { text: "待审核 " + Number(knowledgeGraphController.qualitySummary.needs_review_count || 0); color: Number(knowledgeGraphController.qualitySummary.needs_review_count || 0) > 0 ? theme.warning : theme.success }
                Text { text: "关系待审核 " + Number(knowledgeGraphController.qualitySummary.relation_needs_review_count || 0); color: Number(knowledgeGraphController.qualitySummary.relation_needs_review_count || 0) > 0 ? theme.warning : theme.success }
                Item { Layout.fillWidth: true }
                Text { text: "校验问题 " + Number(knowledgeGraphController.qualitySummary.validation_issue_count || 0); color: Number(knowledgeGraphController.qualitySummary.validation_issue_count || 0) > 0 ? theme.error : theme.success }
            }
        }

        Text {
            Layout.fillWidth: true
            text: knowledgeGraphController.statusText
            color: theme.textMuted
            elide: Text.ElideRight
        }
    }

    Popup {
        id: fullscreenGraph
        parent: Overlay.overlay
        x: 0
        y: 0
        width: parent ? parent.width : root.width
        height: parent ? parent.height : root.height
        modal: true
        focus: true
        closePolicy: Popup.CloseOnEscape
        padding: 12
        background: Rectangle { color: theme.canvas; border.color: theme.border }

        contentItem: ColumnLayout {
            spacing: 10
            RowLayout {
                Layout.fillWidth: true
                Text {
                    Layout.fillWidth: true
                    text: "全屏图谱 · " + (root.title || "当前文献")
                    color: theme.text
                    font.bold: true
                    font.pixelSize: 19
                    elide: Text.ElideRight
                }
                PillButton { text: "关闭"; onClicked: fullscreenGraph.close() }
            }
            RowLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 10
                KnowledgeGraphView {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    nodes: root.nodes
                    edges: root.edges
                    searchQuery: root.searchQuery
                    showFullscreenAction: false
                    displayStyle: root.graphDisplayStyle
                    onNodeRequested: function(nodeId) { knowledgeGraphController.selectNode(nodeId) }
                    onEdgeRequested: function(edgeId) { knowledgeGraphController.selectEdge(edgeId) }
                    onDisplayStyleRequested: function(displayStyle) { root.graphDisplayStyle = displayStyle }
                }
                KnowledgeGraphPanel {
                    Layout.preferredWidth: Math.min(380, fullscreenGraph.width * 0.30)
                    Layout.fillHeight: true
                    selectedNode: knowledgeGraphController.selectedNode
                    selectedEdge: knowledgeGraphController.selectedEdge
                    onEvidenceRequested: function(itemId, index) { knowledgeGraphController.focusEvidence(itemId, index) }
                }
            }
            Text {
                Layout.fillWidth: true
                text: "节点证据 " + Math.round(Number(knowledgeGraphController.qualitySummary.evidence_coverage || 0) * 100) + "%  ·  关系证据 " + Math.round(Number(knowledgeGraphController.qualitySummary.edge_evidence_coverage || 0) * 100) + "%  ·  待审核 " + Number(knowledgeGraphController.qualitySummary.needs_review_count || 0)
                color: theme.textMuted
            }
        }
    }
}
