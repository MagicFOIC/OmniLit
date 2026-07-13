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
    property bool explorationActive: false
    property var explorationSummary: ({})
    property var explorationStatus: ({})
    signal evidenceRequested(string itemId, int index)
    signal expandRequested(string nodeId, string relationMode)

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
            onExpandRequested: function(nodeId, relationMode) { root.expandRequested(nodeId, relationMode) }
        }

        Rectangle {
            Layout.fillWidth: true
            visible: root.explorationActive && Object.keys(root.selectedNode || {}).length > 0
            Layout.preferredHeight: visible ? expansionColumn.implicitHeight + 18 : 0
            radius: theme.radiusSmall
            color: theme.surfaceSoft
            border.color: theme.border

            ColumnLayout {
                id: expansionColumn
                anchors.fill: parent
                anchors.margins: 9
                spacing: 7

                Text {
                    Layout.fillWidth: true
                    text: "按需展开邻居"
                    color: theme.text
                    font.bold: true
                }
                Flow {
                    Layout.fillWidth: true
                    Layout.preferredHeight: childrenRect.height
                    spacing: 5
                    Repeater {
                        model: [
                            { mode: "all", label: "全部" },
                            { mode: "references", label: "引用" },
                            { mode: "cited_by", label: "被引" },
                            { mode: "authors", label: "作者" },
                            { mode: "institutions", label: "机构" },
                            { mode: "topics", label: "主题" },
                            { mode: "venues", label: "期刊" }
                        ]
                        delegate: PillButton {
                            required property var modelData
                            property int neighborCount: Number(root.explorationSummary[modelData.mode] || 0)
                            text: modelData.label + " " + neighborCount
                            enabled: neighborCount > 0 && root.explorationStatus.status !== "loading"
                            onClicked: root.expandRequested(String(root.selectedNode.id || ""), modelData.mode)
                        }
                    }
                }
                Text {
                    Layout.fillWidth: true
                    visible: !!root.explorationStatus.message
                    text: root.explorationStatus.message || ""
                    color: root.explorationStatus.status === "error" ? theme.error : theme.textMuted
                    wrapMode: Text.Wrap
                    font.pixelSize: 11
                }
            }
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
