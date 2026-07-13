pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: root

    property var selectedNode: ({})
    property var pathState: ({})
    property var relationTypes: []
    property bool expanded: false
    property bool detailsOpen: false
    readonly property var steps: root.pathState.steps || []
    readonly property real wrappedControlHeight: Math.max(36, controlsFlow.childrenRect.height)

    signal startRequested(string nodeId)
    signal endRequested(string nodeId)
    signal directedRequested(bool directed)
    signal relationFilterRequested(string relationType)
    signal computeRequested()
    signal clearRequested()

    Theme { id: theme }
    color: theme.surface
    border.color: root.pathState.status === "ready" ? theme.warning : theme.border
    radius: theme.radiusMedium
    implicitHeight: !root.expanded ? 44
                    : root.detailsOpen && root.steps.length
                      ? Math.min(280, 80 + root.wrappedControlHeight + root.steps.length * 34)
                      : 66 + root.wrappedControlHeight
    clip: true

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 6
        spacing: 5

        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: 32
            spacing: 7

            Text { text: "最短路径"; color: theme.text; font.bold: true }
            Label {
                Layout.maximumWidth: 180
                text: "起点 " + (root.pathState.startLabel || "未设置")
                color: root.pathState.startId ? theme.success : theme.textMuted
                background: Rectangle { color: theme.surfaceSoft; border.color: theme.border; radius: 6 }
                padding: 4
                elide: Text.ElideRight
            }
            Label {
                Layout.maximumWidth: 180
                text: "终点 " + (root.pathState.endLabel || "未设置")
                color: root.pathState.endId ? theme.error : theme.textMuted
                background: Rectangle { color: theme.surfaceSoft; border.color: theme.border; radius: 6 }
                padding: 4
                elide: Text.ElideRight
            }
            Text {
                Layout.fillWidth: true
                visible: !root.expanded
                text: root.pathState.status === "ready"
                      ? Number(root.pathState.length || 0) + " 跳 · 已计算"
                      : (root.pathState.message || "按需展开路径工具")
                color: root.pathState.status === "ready" ? theme.warning : theme.textMuted
                elide: Text.ElideRight
                font.pixelSize: 11
            }
            PillButton {
                text: root.expanded ? "收起路径" : "路径工具"
                primary: root.expanded || root.pathState.status === "ready"
                onClicked: root.expanded = !root.expanded
            }
        }

        Flow {
            id: controlsFlow
            visible: root.expanded
            Layout.fillWidth: true
            Layout.preferredHeight: root.wrappedControlHeight
            spacing: 7

            PillButton {
                text: "所选为起点"
                enabled: !!root.selectedNode.id
                onClicked: root.startRequested(String(root.selectedNode.id || ""))
            }
            PillButton {
                text: "所选为终点"
                enabled: !!root.selectedNode.id
                onClicked: root.endRequested(String(root.selectedNode.id || ""))
            }
            StyledComboBox {
                width: 112
                model: ["无向路径", "有向路径"]
                currentIndex: root.pathState.directed ? 1 : 0
                onActivated: function(index) { root.directedRequested(index === 1) }
            }
            StyledComboBox {
                width: 148
                model: ["全部关系"].concat(root.relationTypes)
                currentIndex: root.relationIndex()
                onActivated: function(index) {
                    root.relationFilterRequested(index <= 0 ? "all" : String(root.relationTypes[index - 1]))
                }
            }
            PillButton {
                text: "计算路径"
                primary: root.pathState.status === "ready"
                enabled: !!root.pathState.startId && !!root.pathState.endId
                onClicked: root.computeRequested()
            }
            PillButton {
                visible: root.steps.length > 0
                text: root.detailsOpen ? "收起步骤" : "查看步骤"
                onClicked: root.detailsOpen = !root.detailsOpen
            }
            PillButton {
                text: "清除"
                enabled: !!root.pathState.startId || !!root.pathState.endId
                onClicked: root.clearRequested()
            }
            Text {
                height: 34
                verticalAlignment: Text.AlignVCenter
                visible: root.pathState.status === "ready"
                text: Number(root.pathState.length || 0) + " 跳 · 访问 " + Number(root.pathState.visited || 0) + " 节点"
                color: theme.warning
                font.bold: true
            }
        }

        Text {
            visible: root.expanded
            Layout.fillWidth: true
            text: root.pathState.message || "请选择路径起点和终点。"
            color: ["invalid", "no_path", "too_large", "error"].indexOf(String(root.pathState.status || "")) >= 0
                   ? theme.error : theme.textMuted
            elide: Text.ElideRight
            font.pixelSize: 11
        }

        ScrollView {
            visible: root.expanded && root.detailsOpen && root.steps.length > 0
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            ScrollBar.vertical: StyledScrollBar { policy: ScrollBar.AsNeeded }
            ColumnLayout {
                width: parent.width
                spacing: 3
                Repeater {
                    model: root.steps
                    delegate: Rectangle {
                        id: stepDelegate
                        required property var modelData
                        required property int index
                        Layout.fillWidth: true
                        Layout.preferredHeight: stepText.implicitHeight + 10
                        color: index % 2 ? theme.surfaceSoft : theme.surfaceElevated
                        radius: 5
                        Text {
                            id: stepText
                            anchors.fill: parent
                            anchors.margins: 5
                            text: (stepDelegate.index + 1) + ". " + stepDelegate.modelData.explanation
                                  + " · 置信度 " + Math.round(Number(stepDelegate.modelData.confidence || 0) * 100) + "%"
                            color: theme.text
                            wrapMode: Text.Wrap
                            font.pixelSize: 11
                        }
                    }
                }
            }
        }
    }

    function relationIndex() {
        var filter = String(root.pathState.relationFilter || "all").toUpperCase()
        if (filter === "ALL") return 0
        var index = root.relationTypes.indexOf(filter)
        return index >= 0 ? index + 1 : 0
    }
}
