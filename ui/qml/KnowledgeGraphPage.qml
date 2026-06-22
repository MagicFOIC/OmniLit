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
            onSearchRequested: function(text) { knowledgeGraphController.search(text) }
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
                onNodeRequested: function(nodeId) { knowledgeGraphController.selectNode(nodeId) }
                onEdgeRequested: function(edgeId) { knowledgeGraphController.selectEdge(edgeId) }
            }

            KnowledgeGraphPanel {
                Layout.preferredWidth: 300
                Layout.fillHeight: true
                selectedNode: knowledgeGraphController.selectedNode
                selectedEdge: knowledgeGraphController.selectedEdge
                onEvidenceRequested: function(itemId, index) { knowledgeGraphController.focusEvidence(itemId, index) }
            }
        }

        Text {
            Layout.fillWidth: true
            text: knowledgeGraphController.statusText
            color: theme.textMuted
            elide: Text.ElideRight
        }
    }

}
