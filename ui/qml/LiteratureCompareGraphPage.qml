import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: root
    property string recordId: ""
    property var records: []
    property string graphDisplayStyle: "overview"
    signal backRequested()
    signal evidenceRequested(string recordId, int page, var bbox, string elementId)
    Theme { id: theme }

    Connections {
        target: knowledgeGraphController
        function onEvidenceFocusRequested(recordId, page, bbox, elementId) { root.evidenceRequested(recordId, page, bbox, elementId) }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 8
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 62
            radius: theme.radiusMedium
            color: theme.surface
            border.color: theme.border
            RowLayout {
                anchors.fill: parent
                anchors.margins: 10
                spacing: 8
                PillButton { text: "返回对比"; onClicked: root.backRequested() }
                Text {
                    Layout.fillWidth: true
                    text: "文献对比知识图谱 · " + root.records.length + " 篇"
                    color: theme.text
                    font.bold: true
                    font.pixelSize: 18
                    elide: Text.ElideRight
                }
                BusyIndicator { running: knowledgeGraphController.loading; visible: running; Layout.preferredWidth: 26; Layout.preferredHeight: 26 }
                PillButton { text: knowledgeGraphController.loading ? "生成中..." : "重新生成"; enabled: !knowledgeGraphController.loading; onClicked: knowledgeGraphController.regenerateComparisonGraph(root.records) }
                PillButton { text: "对比报告"; onClicked: knowledgeGraphController.exportGraph(root.recordId, "markdown") }
                PillButton { text: "Mermaid"; onClicked: knowledgeGraphController.exportGraph(root.recordId, "mermaid") }
                PillButton { text: "打开目录"; onClicked: knowledgeGraphController.openGraphDirectory(root.recordId) }
            }
        }
        GraphFilterBar {
            Layout.fillWidth: true
            comparisonMode: true
            filterCounts: knowledgeGraphController.filterCounts
            onFilterRequested: function(mode) { knowledgeGraphController.setFilterMode(mode) }
            onSearchRequested: function(text) { knowledgeGraphController.search(text) }
        }
        SplitView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            orientation: Qt.Horizontal
            KnowledgeGraphView {
                SplitView.fillWidth: true
                SplitView.minimumWidth: 420
                nodes: knowledgeGraphController.nodes
                edges: knowledgeGraphController.edges
                displayStyle: root.graphDisplayStyle
                onNodeRequested: function(nodeId) { knowledgeGraphController.selectNode(nodeId) }
                onEdgeRequested: function(edgeId) { knowledgeGraphController.selectEdge(edgeId) }
                onDisplayStyleRequested: function(displayStyle) { root.graphDisplayStyle = displayStyle }
            }
            ComparisonEvidencePanel {
                SplitView.preferredWidth: 560
                SplitView.minimumWidth: 360
                records: root.records
                selectedNode: knowledgeGraphController.selectedNode
                selectedEdge: knowledgeGraphController.selectedEdge
                onEvidenceRequested: function(itemId, index) { knowledgeGraphController.focusEvidence(itemId, index) }
            }
        }
        ComparisonMatrix {
            Layout.fillWidth: true
            Layout.preferredHeight: 230
            records: root.records
            nodes: knowledgeGraphController.graph.nodes || []
            onNodeRequested: function(nodeId) { knowledgeGraphController.selectNode(nodeId) }
        }
        Text { Layout.fillWidth: true; text: knowledgeGraphController.statusText; color: theme.textMuted; elide: Text.ElideRight }
    }
}
