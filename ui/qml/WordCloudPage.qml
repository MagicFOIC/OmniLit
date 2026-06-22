import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: root
    property string recordId: ""
    property var record: ({})
    property var records: []
    property string title: "词云"
    property string scope: "record"
    signal backRequested()
    signal evidenceRequested(string recordId, int page, var bbox, string elementId)
    signal graphRequested(string recordId, string keyword)
    Theme { id: theme }

    readonly property var selected: wordCloudController.selectedTerm || ({})

    ColumnLayout {
        anchors.fill: parent
        spacing: 9
        Rectangle {
            Layout.fillWidth: true; Layout.preferredHeight: 62
            radius: theme.radiusMedium; color: theme.surface; border.color: theme.border
            RowLayout {
                anchors.fill: parent; anchors.margins: 10; spacing: 8
                PillButton { text: "返回"; onClicked: root.backRequested() }
                Text { Layout.fillWidth: true; text: "词云 · " + root.title; color: theme.text; font.bold: true; font.pixelSize: 18; elide: Text.ElideRight }
                BusyIndicator { running: wordCloudController.loading; visible: running; Layout.preferredWidth: 26; Layout.preferredHeight: 26 }
                PillButton {
                    text: wordCloudController.loading ? "生成中..." : "重新生成"
                    enabled: !wordCloudController.loading
                    onClicked: root.scope === "record" ? wordCloudController.generateForRecord(root.recordId, root.record, String(root.record.localPdfPath || "")) : wordCloudController.generateForRecords(root.records)
                }
            }
        }
        SplitView {
            Layout.fillWidth: true; Layout.fillHeight: true; orientation: Qt.Horizontal
            WordCloudView {
                SplitView.fillWidth: true; SplitView.minimumWidth: 480
                terms: wordCloudController.cloud.terms || []
                selectedNormalized: String(root.selected.normalized || "")
                onTermRequested: function(normalized) { wordCloudController.selectTerm(normalized) }
            }
            Rectangle {
                SplitView.preferredWidth: 360; SplitView.minimumWidth: 300
                radius: theme.radiusMedium; color: theme.surface; border.color: theme.border
                ScrollView {
                    anchors.fill: parent; anchors.margins: 12; contentWidth: availableWidth
                    ColumnLayout {
                        width: parent.width; spacing: 9
                        Text { Layout.fillWidth: true; text: root.selected.text || "选择词语查看来源"; color: theme.text; font.bold: true; font.pixelSize: 18; wrapMode: Text.WrapAnywhere }
                        Text { Layout.fillWidth: true; visible: !!root.selected.text; text: "权重 " + Number(root.selected.weight || 0).toFixed(2) + " · 出现 " + Number(root.selected.count || 0) + " 次 · " + (root.selected.paperIds || []).length + " 篇"; color: theme.textMuted }
                        PillButton { visible: root.scope === "record" && !!root.selected.text; text: "在知识图谱中查看"; onClicked: root.graphRequested(root.recordId, String(root.selected.normalized || "")) }
                        Text { visible: (root.selected.evidence || []).length > 0; text: "原文证据"; color: theme.text; font.bold: true }
                        Repeater {
                            model: root.selected.evidence || []
                            Rectangle {
                                required property var modelData
                                required property int index
                                Layout.fillWidth: true; Layout.preferredHeight: evidenceColumn.implicitHeight + 16
                                radius: 7; color: theme.surfaceSoft; border.color: theme.border
                                ColumnLayout {
                                    id: evidenceColumn; anchors.fill: parent; anchors.margins: 8
                                    Text { Layout.fillWidth: true; text: modelData.page >= 0 ? "第 " + (Number(modelData.page) + 1) + " 页" : modelData.source || "元数据"; color: theme.accent; font.bold: true }
                                    Text { Layout.fillWidth: true; text: modelData.excerpt || ""; color: theme.textMuted; wrapMode: Text.WrapAnywhere; maximumLineCount: 5; elide: Text.ElideRight }
                                    PillButton { enabled: modelData.page >= 0 || !!modelData.element_id; text: "定位原文"; onClicked: root.evidenceRequested(String(modelData.record_id || root.recordId), Number(modelData.page || 0), modelData.bbox || [], String(modelData.element_id || "")) }
                                }
                            }
                        }
                        Text { visible: root.scope === "library" && (root.selected.paperIds || []).length > 0; text: "相关文献"; color: theme.text; font.bold: true }
                        Repeater {
                            model: root.scope === "library" ? root.relatedRecords() : []
                            PillButton { required property var modelData; Layout.fillWidth: true; text: modelData.title || modelData.recordId || "文献"; onClicked: root.graphRequested(String(modelData.recordId || ""), String(root.selected.normalized || "")) }
                        }
                    }
                }
            }
        }
        Text { Layout.fillWidth: true; text: wordCloudController.statusText; color: theme.textMuted; elide: Text.ElideRight }
    }

    function relatedRecords() {
        var ids = root.selected.paperIds || []
        var result = []
        for (var i = 0; i < root.records.length; ++i)
            if (ids.indexOf(String(root.records[i].recordId || "")) >= 0) result.push(root.records[i])
        return result
    }
}
