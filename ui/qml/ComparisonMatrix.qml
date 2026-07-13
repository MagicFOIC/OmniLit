pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: root

    property var comparison: ({})
    property var selectedCell: ({})
    signal cellRequested(string recordId, string dimension)
    signal nodeRequested(string nodeId)

    Theme { id: theme }
    radius: theme.radiusMedium
    color: theme.surface
    border.color: theme.border
    readonly property var dimensions: root.comparison.dimensions || []
    readonly property var papers: root.comparison.papers || []

    ScrollView {
        ScrollBar.vertical: StyledScrollBar { policy: ScrollBar.AsNeeded }
        ScrollBar.horizontal: StyledScrollBar { policy: ScrollBar.AsNeeded }
        anchors.fill: parent
        anchors.margins: 8
        contentWidth: matrixColumn.implicitWidth
        contentHeight: matrixColumn.implicitHeight

        Column {
            id: matrixColumn
            spacing: 4

            Row {
                spacing: 4
                Rectangle {
                    width: 132; height: 48; color: theme.surfaceSoft
                    Text { anchors.centerIn: parent; text: "ORKG 对比维度"; color: theme.text; font.bold: true }
                }
                Repeater {
                    model: root.papers
                    delegate: Rectangle {
                        required property var modelData
                        width: 250; height: 48; color: theme.surfaceSoft
                        Text {
                            anchors.fill: parent; anchors.margins: 6
                            text: modelData.title || modelData.recordId || "文献"
                            color: theme.text; font.bold: true; elide: Text.ElideRight
                            verticalAlignment: Text.AlignVCenter
                        }
                    }
                }
            }

            Repeater {
                model: root.dimensions
                delegate: Row {
                    id: dimensionRow
                    required property var modelData
                    property string dimensionKey: String(modelData.key || "")
                    spacing: 4

                    Rectangle {
                        width: 132; height: 88; color: theme.surfaceSoft
                        Column {
                            anchors.centerIn: parent
                            width: parent.width - 12
                            spacing: 3
                            Text { width: parent.width; text: dimensionRow.modelData.label || dimensionRow.dimensionKey; color: theme.text; font.bold: true; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.Wrap }
                            Text { width: parent.width; text: root.coverageText(dimensionRow.dimensionKey); color: theme.textMuted; font.pixelSize: 9; horizontalAlignment: Text.AlignHCenter }
                        }
                    }

                    Repeater {
                        model: root.papers
                        delegate: Rectangle {
                            id: cellDelegate
                            required property var modelData
                            property var cell: root.cellFor(String(modelData.recordId || ""), dimensionRow.dimensionKey)
                            property bool selected: String((root.selectedCell || {}).recordId || "") === String(modelData.recordId || "")
                                                    && String((root.selectedCell || {}).dimension || "") === dimensionRow.dimensionKey
                            width: 250; height: 88; radius: 6
                            color: root.cellColor(cell)
                            border.color: selected ? theme.accent : theme.border
                            border.width: selected ? 2 : 1
                            Accessible.name: String(dimensionRow.modelData.label || dimensionRow.dimensionKey) + "，" + root.cellText(cell)
                            Accessible.description: cell.explanation || ""

                            ColumnLayout {
                                anchors.fill: parent
                                anchors.margins: 6
                                spacing: 3
                                Text {
                                    Layout.fillWidth: true
                                    text: root.cellText(cellDelegate.cell)
                                    color: (cellDelegate.cell.items || []).length ? theme.text : theme.textMuted
                                    font.bold: (cellDelegate.cell.review || {}).action !== undefined
                                    wrapMode: Text.WrapAnywhere; maximumLineCount: 2; elide: Text.ElideRight
                                }
                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: 5
                                    Text { text: root.statusLabel(cellDelegate.cell); color: root.statusColor(cellDelegate.cell); font.pixelSize: 9; font.bold: true }
                                    Text { text: "置信 " + Math.round(Number(cellDelegate.cell.confidence || 0) * 100) + "%"; color: theme.textMuted; font.pixelSize: 9; visible: (cellDelegate.cell.items || []).length > 0 }
                                    Text { text: "证据 " + Number(cellDelegate.cell.evidenceCount || 0); color: theme.textMuted; font.pixelSize: 9 }
                                    Item { Layout.fillWidth: true }
                                    Text { text: "共 " + Number(cellDelegate.cell.itemCount || 0) + " 项"; color: theme.textMuted; font.pixelSize: 9 }
                                }
                            }
                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                hoverEnabled: true
                                onClicked: {
                                    root.cellRequested(String(cellDelegate.modelData.recordId || ""), dimensionRow.dimensionKey)
                                    var items = cellDelegate.cell.items || []
                                    if (items.length && items[0].nodeId)
                                        root.nodeRequested(String(items[0].nodeId))
                                }
                                ToolTip.visible: containsMouse
                                ToolTip.text: cellDelegate.cell.explanation || ""
                            }
                        }
                    }
                }
            }
        }
    }

    function cellFor(recordId, dimension) {
        for (var i = 0; i < papers.length; ++i) {
            if (String(papers[i].recordId || "") !== recordId) continue
            var cells = papers[i].cells || []
            for (var j = 0; j < cells.length; ++j)
                if (String(cells[j].dimension || "") === dimension) return cells[j]
        }
        return ({ recordId: recordId, dimension: dimension, status: "missing", items: [], confidence: 0, evidenceCount: 0, explanation: "未生成该比较单元格。" })
    }

    function cellText(cell) {
        var items = cell.items || []
        if (!items.length) return cell.status === "reviewed_missing" ? "人工标记为不采用" : "未识别（不等于不存在）"
        return items.map(function(item) { return String(item.label || "") }).filter(function(value) { return value.length > 0 }).join("；")
    }

    function cellColor(cell) {
        if ((cell.review || {}).action) return theme.successSoft
        if (cell.needsReview) return theme.warningSoft
        return (cell.items || []).length ? theme.navHover : theme.surfaceSoft
    }

    function statusLabel(cell) {
        if ((cell.review || {}).action) return "人工审阅"
        if (cell.needsReview) return "待核验"
        return (cell.items || []).length ? "自动抽取" : "信息缺失"
    }

    function statusColor(cell) {
        if ((cell.review || {}).action) return theme.success
        if (cell.needsReview) return theme.warning
        return (cell.items || []).length ? theme.accent : theme.textMuted
    }

    function coverageText(dimension) {
        var coverage = comparison.coverage || []
        for (var i = 0; i < coverage.length; ++i)
            if (String(coverage[i].dimension || "") === dimension)
                return Number(coverage[i].paperCount || 0) + "/" + papers.length + " 篇 · " + Number(coverage[i].evidenceCount || 0) + " 证据"
        return "0/" + papers.length + " 篇"
    }
}
