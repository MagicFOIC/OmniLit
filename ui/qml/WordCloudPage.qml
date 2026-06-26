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
    property string categoryFilter: "All"
    signal backRequested()
    signal evidenceRequested(string recordId, int page, var bbox, string elementId)
    signal graphRequested(string recordId, string nodeId, string keyword)

    Theme { id: theme }
    readonly property var selected: wordCloudController.selectedTerm || ({})
    readonly property var visibleTerms: root.filteredTerms()

    ColumnLayout {
        anchors.fill: parent
        spacing: 9

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 62
            radius: theme.radiusMedium
            color: theme.surface
            border.color: theme.border
            RowLayout {
                anchors.fill: parent
                anchors.margins: 10
                spacing: 8
                PillButton { text: "返回"; onClicked: root.backRequested() }
                Text { Layout.fillWidth: true; text: "核心概念 · " + root.title; color: theme.text; font.bold: true; font.pixelSize: 18; elide: Text.ElideRight }
                ComboBox {
                    Layout.preferredWidth: 126
                    model: ["All", "Method", "Dataset", "Metric", "Result", "Concept"]
                    onActivated: root.categoryFilter = String(currentText)
                }
                BusyIndicator { running: wordCloudController.loading; visible: running; Layout.preferredWidth: 26; Layout.preferredHeight: 26 }
                PillButton {
                    text: wordCloudController.loading ? "生成中..." : "重新生成"
                    enabled: !wordCloudController.loading
                    onClicked: root.scope === "record"
                        ? wordCloudController.generateForRecord(root.recordId, root.record, String(root.record.localPdfPath || ""))
                        : wordCloudController.generateForRecords(root.records)
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 12
            Repeater {
                model: ["Method", "Dataset", "Metric", "Result", "Concept"]
                delegate: Row {
                    required property var modelData
                    spacing: 5
                    Rectangle { width: 9; height: 9; radius: 5; color: root.categoryColor(modelData) }
                    Text { text: String(modelData); color: theme.textMuted; font.pixelSize: 11 }
                }
            }
            Item { Layout.fillWidth: true }
            Text { text: root.visibleTerms.length + " 个核心概念"; color: theme.textMuted }
        }

        SplitView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            orientation: Qt.Horizontal

            WordCloudView {
                SplitView.fillWidth: true
                SplitView.minimumWidth: 480
                terms: root.visibleTerms
                selectedNormalized: String(root.selected.normalized || "")
                onTermRequested: function(normalized, nodeId) {
                    wordCloudController.selectTerm(normalized)
                    wordCloudController.selectGraphNodeForTerm(normalized, root.recordId)
                }
            }

            Rectangle {
                SplitView.preferredWidth: 370
                SplitView.minimumWidth: 310
                radius: theme.radiusMedium
                color: theme.surface
                border.color: theme.border
                ScrollView {
                    anchors.fill: parent
                    anchors.margins: 12
                    contentWidth: availableWidth
                    ColumnLayout {
                        width: parent.width
                        spacing: 9
                        Text { Layout.fillWidth: true; text: root.selected.text || "选择概念查看图谱来源"; color: theme.text; font.bold: true; font.pixelSize: 18; wrapMode: Text.WrapAnywhere }
                        RowLayout {
                            visible: !!root.selected.text
                            Label {
                                text: root.selected.category || "Concept"
                                color: root.categoryColor(root.selected.category)
                                background: Rectangle { color: theme.surfaceSoft; radius: 8; border.color: theme.border }
                                padding: 5
                            }
                            Text { text: "权重 " + Number(root.selected.weight || 0).toFixed(2); color: theme.textMuted }
                            Text { text: "绑定 " + (root.selected.nodeIds || []).length + " 个节点"; color: theme.textMuted }
                        }
                        Text {
                            Layout.fillWidth: true
                            visible: !!root.selected.text
                            text: "出现于 " + (root.selected.paperIds || []).length + " 篇论文 · 来源 " + (root.selected.sourceKinds || []).join(" / ")
                            color: theme.textMuted
                            wrapMode: Text.Wrap
                        }
                        RowLayout {
                            visible: !!root.selected.text
                            PillButton {
                                text: "高亮图谱节点"
                                enabled: (root.selected.nodeIds || []).length > 0
                                onClicked: wordCloudController.selectGraphNodeForTerm(String(root.selected.normalized || ""), root.recordId)
                            }
                            PillButton {
                                text: "在知识图谱中查看"
                                enabled: (root.selected.nodeIds || []).length > 0
                                onClicked: root.graphRequested(root.recordId, String(root.selected.primaryNodeId || ""), String(root.selected.normalized || ""))
                            }
                        }

                        Text { visible: (root.selected.evidence || []).length > 0; text: "原文证据"; color: theme.text; font.bold: true }
                        Repeater {
                            model: root.selected.evidence || []
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
                                    Text { Layout.fillWidth: true; text: modelData.page >= 0 ? "第 " + (Number(modelData.page) + 1) + " 页" : modelData.source || "元数据"; color: theme.accent; font.bold: true }
                                    Text { Layout.fillWidth: true; text: modelData.excerpt || ""; color: theme.textMuted; wrapMode: Text.WrapAnywhere; maximumLineCount: 5; elide: Text.ElideRight }
                                    PillButton {
                                        enabled: modelData.page >= 0 || !!modelData.element_id
                                        text: "定位原文"
                                        onClicked: root.evidenceRequested(String(modelData.record_id || root.recordId), Number(modelData.page || 0), modelData.bbox || [], String(modelData.element_id || ""))
                                    }
                                }
                            }
                        }

                        Text { visible: root.scope === "library" && (root.selected.paperIds || []).length > 0; text: "相关论文"; color: theme.text; font.bold: true }
                        Repeater {
                            model: root.scope === "library" ? root.relatedRecords() : []
                            delegate: PillButton {
                                required property var modelData
                                Layout.fillWidth: true
                                text: modelData.title || modelData.recordId || "论文"
                                onClicked: root.graphRequested(String(modelData.recordId || ""), root.nodeIdForRecord(String(modelData.recordId || "")), String(root.selected.normalized || ""))
                            }
                        }
                    }
                }
            }
        }

        Text { Layout.fillWidth: true; text: wordCloudController.statusText; color: theme.textMuted; elide: Text.ElideRight }
    }

    function filteredTerms() {
        var terms = wordCloudController.cloud.terms || []
        if (root.categoryFilter === "All") return terms
        return terms.filter(function(term) { return String(term.category || "Concept") === root.categoryFilter })
    }

    function relatedRecords() {
        var ids = root.selected.paperIds || []
        var result = []
        for (var i = 0; i < root.records.length; ++i)
            if (ids.indexOf(String(root.records[i].recordId || "")) >= 0) result.push(root.records[i])
        return result
    }

    function nodeIdForRecord(recordId) {
        var refs = root.selected.nodeRefs || []
        for (var i = 0; i < refs.length; ++i)
            if (String(refs[i].recordId || "") === String(recordId || "")) return String(refs[i].nodeId || "")
        return String(root.selected.primaryNodeId || "")
    }

    function categoryColor(category) {
        var value = String(category || "Concept").toLowerCase()
        if (value === "method") return theme.accent
        if (value === "dataset") return theme.info
        if (value === "metric") return theme.warning
        if (value === "result") return theme.success
        return theme.textMuted
    }
}
