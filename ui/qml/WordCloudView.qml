import QtQuick
import QtQuick.Controls

Rectangle {
    id: root
    property var terms: []
    property string selectedNormalized: ""
    signal termRequested(string normalized)
    Theme { id: theme }
    radius: theme.radiusMedium
    color: theme.surface
    border.color: theme.border
    clip: true

    Repeater {
        model: root.terms
        delegate: Text {
            required property var modelData
            x: Number(modelData.x) * root.width - width / 2
            y: Number(modelData.y) * root.height - height / 2
            text: modelData.text
            font.pixelSize: Math.max(11, Number(modelData.fontSize) * Math.min(root.width / 1000, root.height / 650))
            font.weight: Number(modelData.weight) > 4 ? Font.DemiBold : Font.Normal
            color: root.termColor(modelData.colorGroup)
            opacity: root.selectedNormalized && root.selectedNormalized !== modelData.normalized ? 0.28 : 0.96
            scale: root.selectedNormalized === modelData.normalized ? 1.12 : 1.0
            Behavior on scale { NumberAnimation { duration: 150; easing.type: Easing.OutCubic } }
            Behavior on opacity { NumberAnimation { duration: 120 } }
            MouseArea {
                anchors.fill: parent
                anchors.margins: -4
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: root.termRequested(String(modelData.normalized || ""))
                ToolTip.visible: containsMouse
                ToolTip.text: modelData.text + " · " + modelData.count + " 次 · " + (modelData.paperIds || []).length + " 篇"
            }
        }
    }
    Text { anchors.centerIn: parent; visible: root.terms.length === 0 && !wordCloudController.loading; text: "没有足够的有效术语生成词云"; color: theme.textMuted }
    BusyIndicator { anchors.centerIn: parent; running: wordCloudController.loading; visible: running }

    function termColor(kind) {
        var value = String(kind || "concept").toLowerCase()
        if (value === "method" || value === "model" || value === "algorithm") return theme.accent
        if (value === "result" || value === "metric") return theme.success
        if (value === "limitation" || value === "researchgap") return theme.warning
        if (value === "dataset" || value === "experiment") return theme.textMuted
        return theme.text
    }
}
