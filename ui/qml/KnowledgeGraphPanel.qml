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
        anchors.margins: 8
        KnowledgeGraphView {
            visible: root.showGraph
            Layout.fillWidth: true
            Layout.preferredHeight: root.showGraph ? Math.max(220, root.height * 0.48) : 0
            nodes: root.nodes
            edges: root.edges
            onNodeRequested: function(nodeId) { knowledgeGraphController.selectNode(nodeId) }
            onEdgeRequested: function(edgeId) { knowledgeGraphController.selectEdge(edgeId) }
        }
        ScrollView {
        Layout.fillWidth: true
        Layout.fillHeight: true
        contentWidth: availableWidth
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
