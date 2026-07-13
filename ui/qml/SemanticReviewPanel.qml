pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: root

    property var cell: ({})
    signal reviewRequested(string recordId, string dimension, string action, string label, string note)
    signal clearRequested(string recordId, string dimension)
    signal nodeRequested(string nodeId)

    Theme { id: theme }
    radius: theme.radiusMedium
    color: theme.surface
    border.color: theme.border

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 9
        spacing: 6

        RowLayout {
            Layout.fillWidth: true
            Text { Layout.fillWidth: true; text: root.cell.dimension ? "语义核验 · " + root.cell.dimension : "选择矩阵单元格进行核验"; color: theme.text; font.bold: true; elide: Text.ElideRight }
            Label {
                visible: !!(root.cell.review || {}).action
                text: "已人工审阅"
                color: theme.success
                background: Rectangle { color: theme.successSoft; radius: 6 }
                padding: 4
            }
        }
        Text { Layout.fillWidth: true; text: root.cell.explanation || "人工修正会作为覆盖层保存，原始自动抽取不会被删除。"; color: theme.textMuted; wrapMode: Text.Wrap; maximumLineCount: 3; elide: Text.ElideRight }

        ScrollView {
            Layout.fillWidth: true
            Layout.preferredHeight: 84
            contentWidth: availableWidth
            ScrollBar.vertical: StyledScrollBar { policy: ScrollBar.AsNeeded }
            ColumnLayout {
                width: parent.width
                Repeater {
                    model: root.cell.automaticItems || []
                    delegate: Rectangle {
                        id: automaticRow
                        required property var modelData
                        Layout.fillWidth: true
                        Layout.preferredHeight: 38
                        color: "transparent"
                        RowLayout {
                            anchors.fill: parent
                            spacing: 5
                            Text { Layout.fillWidth: true; text: automaticRow.modelData.label || "未命名自动抽取项"; color: theme.text; elide: Text.ElideRight }
                            Text { text: Math.round(Number(automaticRow.modelData.confidence || 0) * 100) + "% · " + Number(automaticRow.modelData.evidenceCount || 0) + "证据"; color: automaticRow.modelData.needsReview ? theme.warning : theme.textMuted; font.pixelSize: 9 }
                            PillButton { text: "图中定位"; enabled: !!automaticRow.modelData.nodeId; onClicked: root.nodeRequested(String(automaticRow.modelData.nodeId || "")) }
                        }
                    }
                }
                Text { visible: (root.cell.automaticItems || []).length === 0; text: "自动抽取未识别到该维度。可以补充人工结论，或确认缺失。"; color: theme.warning; wrapMode: Text.Wrap }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Text { text: "审阅动作"; color: theme.textMuted }
            StyledComboBox {
                id: actionBox
                Layout.preferredWidth: 145
                model: ["确认自动结果", "修正为", "补充一项", "排除自动结果"]
            }
            StyledTextField {
                id: correctionLabel
                Layout.fillWidth: true
                visible: actionBox.currentIndex === 1 || actionBox.currentIndex === 2
                placeholderText: actionBox.currentIndex === 1 ? "修正后的语义内容" : "补充的语义内容"
            }
        }
        TextArea {
            id: reviewNote
            Layout.fillWidth: true
            Layout.preferredHeight: 58
            placeholderText: "审阅备注（可选，例如证据页码或判断依据）"
            wrapMode: TextArea.Wrap
            color: theme.text
            placeholderTextColor: theme.textMuted
            background: Rectangle { color: theme.surfaceSoft; radius: 6; border.color: theme.border }
        }
        RowLayout {
            Layout.fillWidth: true
            PillButton {
                text: "保存人工审阅"
                primary: true
                enabled: !!root.cell.recordId && ((actionBox.currentIndex !== 1 && actionBox.currentIndex !== 2) || correctionLabel.text.trim().length > 0)
                onClicked: {
                    var actions = ["confirm", "replace", "add", "reject"]
                    root.reviewRequested(String(root.cell.recordId || ""), String(root.cell.dimension || ""), actions[actionBox.currentIndex], correctionLabel.text, reviewNote.text)
                    correctionLabel.text = ""
                    reviewNote.text = ""
                }
            }
            PillButton {
                text: "撤销人工审阅"
                visible: !!(root.cell.review || {}).action
                onClicked: root.clearRequested(String(root.cell.recordId || ""), String(root.cell.dimension || ""))
            }
            Item { Layout.fillWidth: true }
            Text { text: "自动抽取始终保留"; color: theme.textMuted; font.pixelSize: 9 }
        }
    }
}
