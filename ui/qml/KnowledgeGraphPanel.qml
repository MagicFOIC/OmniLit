import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: root
    property var selectedNode: ({})
    property var selectedEdge: ({})
    property bool showGraph: false
    property var nodes: []
    property var edges: []
    signal evidenceRequested(string itemId, int index)

    Theme { id: theme }
    radius: theme.radiusMedium
    color: theme.surface
    border.color: theme.border

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 10
        spacing: 8

        RowLayout {
            Layout.fillWidth: true
            Text { Layout.fillWidth: true; text: "节点详情"; color: theme.text; font.bold: true; font.pixelSize: 15 }
            Label {
                visible: Object.keys(root.selectedEdge || {}).length > 0
                text: "关系"
                color: theme.accent
                background: Rectangle { color: theme.accentSofter; radius: 7 }
                padding: 4
            }
        }

        KnowledgeGraphView {
            visible: root.showGraph
            showFullscreenAction: false
            Layout.fillWidth: true
            Layout.preferredHeight: root.showGraph ? Math.max(230, root.height * 0.46) : 0
            nodes: root.nodes
            edges: root.edges
            onNodeRequested: function(nodeId) { knowledgeGraphController.selectNode(nodeId) }
            onEdgeRequested: function(edgeId) { knowledgeGraphController.selectEdge(edgeId) }
        }

        ScrollView {
            ScrollBar.vertical: StyledScrollBar { policy: ScrollBar.AsNeeded }
            ScrollBar.horizontal: StyledScrollBar { policy: ScrollBar.AsNeeded }
            Layout.fillWidth: true
            Layout.fillHeight: true
            contentWidth: availableWidth
            clip: true
            GraphNodeCard {
                width: parent.width
                node: Object.keys(root.selectedNode || {}).length > 0 ? root.selectedNode : root.selectedEdge
                onEvidenceRequested: function(index) {
                    var item = Object.keys(root.selectedNode || {}).length > 0 ? root.selectedNode : root.selectedEdge
                    root.evidenceRequested(String(item.id || ""), index)
                }
            }
        }
    }
}
