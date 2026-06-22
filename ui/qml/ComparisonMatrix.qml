import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: root
    property var records: []
    property var nodes: []
    signal nodeRequested(string nodeId)
    Theme { id: theme }
    radius: theme.radiusMedium
    color: theme.surface
    border.color: theme.border
    readonly property var dimensions: [
        { key: "problem", label: "研究问题" }, { key: "method", label: "方法" },
        { key: "dataset", label: "数据集" }, { key: "metric", label: "指标" },
        { key: "baseline", label: "Baseline" }, { key: "result", label: "结果" },
        { key: "contribution", label: "贡献" }, { key: "limitation", label: "局限" },
        { key: "futurework", label: "未来工作" }
    ]

    ScrollView {
        anchors.fill: parent
        anchors.margins: 8
        contentWidth: matrixColumn.implicitWidth
        contentHeight: matrixColumn.implicitHeight
        Column {
            id: matrixColumn
            spacing: 4
            Row {
                spacing: 4
                Rectangle { width: 120; height: 36; color: theme.surfaceSoft; Text { anchors.centerIn: parent; text: "对比维度"; color: theme.text; font.bold: true } }
                Repeater {
                    model: root.records
                    Rectangle {
                        required property var modelData
                        width: 220; height: 36; color: theme.surfaceSoft
                        Text { anchors.fill: parent; anchors.margins: 6; text: modelData.title || modelData.recordId || "文献"; color: theme.text; font.bold: true; elide: Text.ElideRight; verticalAlignment: Text.AlignVCenter }
                    }
                }
            }
            Repeater {
                model: root.dimensions
                Row {
                    id: dimensionRow
                    required property var modelData
                    property string dimensionKey: String(modelData.key || "")
                    spacing: 4
                    Rectangle { width: 120; height: 54; color: theme.surfaceSoft; Text { anchors.centerIn: parent; text: modelData.label; color: theme.textMuted } }
                    Repeater {
                        model: root.records
                        Rectangle {
                            required property var modelData
                            property var matchingNode: root.nodeFor(String(modelData.recordId || ""), dimensionRow.dimensionKey)
                            width: 220; height: 54; radius: 5
                            color: matchingNode && matchingNode.type !== "missinginfo" ? theme.navHover : theme.surfaceSoft
                            border.color: theme.border
                            Text { anchors.fill: parent; anchors.margins: 6; text: parent.matchingNode ? parent.matchingNode.label : "未识别"; color: parent.matchingNode && parent.matchingNode.type !== "missinginfo" ? theme.text : theme.textMuted; wrapMode: Text.WrapAnywhere; maximumLineCount: 2; elide: Text.ElideRight; verticalAlignment: Text.AlignVCenter }
                            MouseArea { anchors.fill: parent; enabled: !!parent.matchingNode; cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor; onClicked: root.nodeRequested(String(parent.matchingNode.id || "")) }
                        }
                    }
                }
            }
        }
    }

    function nodeFor(recordId, dimension) {
        var missing = null
        for (var i = 0; i < root.nodes.length; ++i) {
            var node = root.nodes[i]
            var kind = String(node.type || "").toLowerCase().replace("_", "")
            var details = node.details || {}
            var paperIds = details.paper_ids || []
            if (paperIds.indexOf(recordId) < 0 && String(details.only_in || "") !== recordId)
                continue
            if (kind === dimension)
                return node
            if (kind === "missinginfo" && String(details.dimension || "") === dimension)
                missing = node
        }
        return missing
    }
}
