import QtQuick
import QtQuick.Controls

Rectangle {
    id: root
    property var terms: []
    property string selectedNormalized: ""
    signal termRequested(string normalized, string nodeId)

    Theme { id: theme }
    radius: theme.radiusMedium
    color: theme.surface
    border.color: theme.border
    clip: true

    Repeater {
        model: root.terms
        delegate: Item {
            id: termDelegate
            required property var modelData
            x: Number(modelData.x) * root.width - width / 2
            y: Number(modelData.y) * root.height - height / 2
            width: termLabel.implicitWidth
            height: termLabel.implicitHeight + 7
            opacity: root.selectedNormalized && root.selectedNormalized !== modelData.normalized ? 0.24 : 0.98
            scale: root.selectedNormalized === modelData.normalized ? 1.12 : termMouse.containsMouse ? 1.05 : 1.0

            Behavior on scale { NumberAnimation { duration: theme.reduceMotion ? 0 : 150; easing.type: Easing.OutCubic } }
            Behavior on opacity { NumberAnimation { duration: theme.reduceMotion ? 0 : 120 } }

            Text {
                id: termLabel
                text: modelData.text
                font.pixelSize: Math.max(11, Number(modelData.fontSize) * Math.min(root.width / 1000, root.height / 650))
                font.weight: (modelData.sourceKinds || []).indexOf("graph_node") >= 0 ? Font.DemiBold : Font.Normal
                color: root.termColor(modelData.category || modelData.colorGroup)
            }

            Rectangle {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                height: root.selectedNormalized === modelData.normalized ? 3 : 2
                radius: 1
                color: root.termColor(modelData.category || modelData.colorGroup)
                opacity: (modelData.nodeIds || []).length > 0 ? 0.72 : 0.0
            }

            Rectangle {
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.rightMargin: -7
                anchors.topMargin: -4
                width: 7; height: 7; radius: 4
                color: root.termColor(modelData.category || modelData.colorGroup)
                visible: (modelData.nodeIds || []).length > 0
            }

            MouseArea {
                id: termMouse
                anchors.fill: parent
                anchors.margins: -5
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: root.termRequested(String(modelData.normalized || ""), String(modelData.primaryNodeId || ""))
                ToolTip.visible: containsMouse
                ToolTip.text: modelData.text + " · " + (modelData.category || "Concept") + " · " + (modelData.nodeIds || []).length + " 个图谱节点"
            }
        }
    }

    Text {
        anchors.centerIn: parent
        visible: root.terms.length === 0 && !wordCloudController.loading
        text: "没有足够的核心概念生成词云"
        color: theme.textMuted
    }
    BusyIndicator { anchors.centerIn: parent; running: wordCloudController.loading; visible: running }

    function termColor(category) {
        var value = String(category || "Concept").toLowerCase()
        if (value === "method") return theme.accent
        if (value === "dataset") return theme.info
        if (value === "metric") return theme.warning
        if (value === "result") return theme.success
        return theme.textMuted
    }
}
