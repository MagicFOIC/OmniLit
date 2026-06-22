import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: root
    property var node: ({})
    signal evidenceRequested(int index)
    spacing: 8
    Theme { id: theme }

    Text { text: root.node.label || "未选择节点"; color: theme.text; font.bold: true; font.pixelSize: 17; wrapMode: Text.WrapAnywhere; Layout.fillWidth: true }
    Text { text: "类型：" + (root.node.type || "-"); color: theme.textMuted; Layout.fillWidth: true }
    Text { text: "置信度：" + (root.node.confidence === undefined ? "-" : Math.round(Number(root.node.confidence) * 100) + "%"); color: Number(root.node.confidence) < 0.6 ? theme.warning : theme.textMuted; Layout.fillWidth: true }
    Text { text: root.node.summary || "点击节点查看摘要与证据"; color: theme.text; wrapMode: Text.WrapAnywhere; Layout.fillWidth: true }
    Text { text: "证据"; visible: (root.node.evidence || []).length > 0; color: theme.text; font.bold: true }
    Repeater {
        model: root.node.evidence || []
        delegate: Rectangle {
            required property var modelData
            required property int index
            Layout.fillWidth: true
            Layout.preferredHeight: evidenceColumn.implicitHeight + 16
            radius: 7
            color: theme.surfaceSoft
            border.color: theme.border
            ColumnLayout {
                id: evidenceColumn
                anchors.fill: parent
                anchors.margins: 8
                Text { text: modelData.page >= 0 ? "第 " + (Number(modelData.page) + 1) + " 页" : (modelData.source || "元数据"); color: theme.accent; font.bold: true }
                Text { Layout.fillWidth: true; text: modelData.excerpt || modelData.source || ""; color: theme.textMuted; wrapMode: Text.WrapAnywhere; maximumLineCount: 5; elide: Text.ElideRight }
                PillButton { text: "定位原文"; enabled: modelData.page >= 0 || !!modelData.element_id; onClicked: root.evidenceRequested(index) }
            }
        }
    }
}
