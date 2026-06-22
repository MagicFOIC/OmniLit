import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: root
    property var selectedNode: ({})
    property var selectedEdge: ({})
    property var records: []
    signal evidenceRequested(string itemId, int evidenceIndex)
    Theme { id: theme }
    radius: theme.radiusMedium
    color: theme.surface
    border.color: theme.border

    readonly property var selectedItem: Object.keys(root.selectedNode || {}).length > 0 ? root.selectedNode : root.selectedEdge

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 10
        spacing: 8
        Text {
            Layout.fillWidth: true
            text: root.selectedItem.label || root.selectedItem.type || "选择共同点、差异点或关系查看证据"
            color: theme.text
            font.bold: true
            font.pixelSize: 16
            wrapMode: Text.WrapAnywhere
        }
        Text {
            Layout.fillWidth: true
            text: root.selectedItem.summary || ""
            visible: text.length > 0
            color: theme.textMuted
            wrapMode: Text.WrapAnywhere
            maximumLineCount: 3
            elide: Text.ElideRight
        }
        ScrollView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            contentWidth: evidenceRow.implicitWidth
            RowLayout {
                id: evidenceRow
                height: parent.height
                spacing: 8
                Repeater {
                    model: root.records
                    delegate: Rectangle {
                        required property var modelData
                        Layout.preferredWidth: Math.max(260, (root.width - 30) / Math.min(2, Math.max(1, root.records.length)))
                        Layout.fillHeight: true
                        radius: 7
                        color: theme.surfaceSoft
                        border.color: theme.border
                        ColumnLayout {
                            anchors.fill: parent
                            anchors.margins: 8
                            Text { Layout.fillWidth: true; text: modelData.title || modelData.recordId || "文献"; color: theme.accent; font.bold: true; elide: Text.ElideRight }
                            ListView {
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                clip: true
                                model: root.evidenceFor(String(modelData.recordId || ""))
                                delegate: Rectangle {
                                    required property var modelData
                                    required property int index
                                    width: ListView.view.width
                                    height: evidenceText.implicitHeight + 48
                                    color: "transparent"
                                    Text {
                                        id: evidenceText
                                        anchors.left: parent.left
                                        anchors.right: parent.right
                                        anchors.top: parent.top
                                        text: (modelData.value.page >= 0 ? "第 " + (Number(modelData.value.page) + 1) + " 页\n" : "") + (modelData.value.excerpt || modelData.value.source || "无原文摘录")
                                        color: theme.text
                                        wrapMode: Text.WrapAnywhere
                                        maximumLineCount: 6
                                        elide: Text.ElideRight
                                    }
                                    PillButton {
                                        anchors.left: parent.left
                                        anchors.bottom: parent.bottom
                                        text: "定位原文"
                                        enabled: modelData.value.page >= 0 || !!modelData.value.element_id
                                        onClicked: root.evidenceRequested(String(root.selectedItem.id || ""), Number(modelData.originalIndex))
                                    }
                                }
                                Text { anchors.centerIn: parent; visible: parent.count === 0; text: "该文献暂无对应证据"; color: theme.textMuted }
                            }
                        }
                    }
                }
            }
        }
    }

    function evidenceFor(recordId) {
        var result = []
        var evidence = root.selectedItem.evidence || []
        for (var i = 0; i < evidence.length; ++i) {
            var evidenceRecord = String(evidence[i].record_id || evidence[i].recordId || "")
            if (evidenceRecord === recordId)
                result.push({ value: evidence[i], originalIndex: i })
        }
        return result
    }
}
