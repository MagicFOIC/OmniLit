pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: root

    property var rows: []
    property string selectedNodeId: ""
    property string hoveredNodeId: ""
    property string sortKey: "relevance"
    property bool sortDescending: true
    property bool compactMode: false
    property int pageSize: 50
    property int currentPage: 0
    readonly property int pageCount: Math.max(1, Math.ceil(root.rows.length / root.pageSize))
    readonly property var pagedRows: root.rows.slice(root.currentPage * root.pageSize, (root.currentPage + 1) * root.pageSize)

    signal nodeRequested(string nodeId)
    signal nodeHovered(string nodeId)
    signal sortRequested(string sortKey, bool descending)

    Theme { id: theme }
    color: theme.surface
    border.color: theme.border
    radius: theme.radiusMedium
    clip: true

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 8
        spacing: 5

        RowLayout {
            Layout.fillWidth: true
            spacing: 8
            Text { text: "文献列表"; color: theme.text; font.bold: true; font.pixelSize: 14 }
            Label {
                text: root.rows.length + " 条"
                color: theme.textMuted
                background: Rectangle { color: theme.surfaceSoft; radius: 7 }
                padding: 4
            }
            Text {
                Layout.fillWidth: true
                visible: !root.compactMode
                text: "图中选中、悬停、搜索与筛选会同步到此列表"
                color: theme.textMuted
                elide: Text.ElideRight
                font.pixelSize: 11
            }
            Text {
                visible: root.pageCount > 1
                text: (root.currentPage + 1) + " / " + root.pageCount
                color: theme.textMuted
            }
            PillButton { visible: root.pageCount > 1; text: "上一页"; enabled: root.currentPage > 0; onClicked: root.currentPage -= 1 }
            PillButton { visible: root.pageCount > 1; text: "下一页"; enabled: root.currentPage + 1 < root.pageCount; onClicked: root.currentPage += 1 }
        }

        RowLayout {
            Layout.fillWidth: true
            visible: root.compactMode
            spacing: 6
            Text { text: "排序"; color: theme.textMuted; font.pixelSize: 10 }
            Repeater {
                model: [
                    { label: "相关性", key: "relevance" }, { label: "年份", key: "year" },
                    { label: "引用", key: "citations" }, { label: "重要性", key: "importance" }
                ]
                PillButton {
                    required property var modelData
                    text: modelData.label + (root.sortKey === modelData.key ? (root.sortDescending ? " ↓" : " ↑") : "")
                    primary: root.sortKey === modelData.key
                    onClicked: root.requestSort(modelData.key)
                }
            }
            Item { Layout.fillWidth: true }
        }

        Rectangle {
            visible: !root.compactMode
            Layout.fillWidth: true
            Layout.preferredHeight: visible ? 30 : 0
            color: theme.surfaceSoft
            radius: theme.radiusSmall

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 8
                anchors.rightMargin: 8
                spacing: 8
                Text { Layout.preferredWidth: 58; text: "类型"; color: theme.textMuted; font.bold: true; font.pixelSize: 11 }
                SortHeader { Layout.fillWidth: true; label: "标题"; keyName: "title" }
                SortHeader { Layout.preferredWidth: 62; label: "年份"; keyName: "year" }
                SortHeader { Layout.preferredWidth: 180; label: "作者"; keyName: "authors" }
                SortHeader { Layout.preferredWidth: 72; label: "引用"; keyName: "citations" }
                SortHeader { Layout.preferredWidth: 82; label: "重要性"; keyName: "importance" }
                SortHeader { Layout.preferredWidth: 82; label: "相关性"; keyName: "relevance" }
            }
        }

        ListView {
            id: listView
            Layout.fillWidth: true
            Layout.fillHeight: true
            model: root.pagedRows
            visible: root.rows.length > 0
            clip: true
            spacing: 2
            activeFocusOnTab: true
            keyNavigationEnabled: true
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: StyledScrollBar { policy: ScrollBar.AsNeeded }

            delegate: Rectangle {
                id: rowDelegate
                required property var modelData
                required property int index
                width: listView.width
                height: root.compactMode ? 78 : 40
                radius: 6
                color: root.selectedNodeId === String(modelData.nodeId || "") ? theme.accentSofter
                      : root.hoveredNodeId === String(modelData.nodeId || "") || listView.currentIndex === index ? theme.navHover
                      : (index % 2 ? theme.surfaceSoft : theme.surface)
                border.color: root.selectedNodeId === String(modelData.nodeId || "") ? theme.accent : "transparent"

                RowLayout {
                    visible: !root.compactMode
                    anchors.fill: parent
                    anchors.leftMargin: 8
                    anchors.rightMargin: 8
                    spacing: 8
                    Label {
                        Layout.preferredWidth: 58
                        text: rowDelegate.modelData.kind === "paper" ? "论文" : "引用"
                        color: rowDelegate.modelData.kind === "paper" ? theme.accent : theme.textMuted
                        background: Rectangle { color: theme.surfaceElevated; radius: 6; border.color: theme.border }
                        horizontalAlignment: Text.AlignHCenter
                        padding: 3
                    }
                    Text { Layout.fillWidth: true; text: rowDelegate.modelData.title || "Untitled"; color: theme.text; elide: Text.ElideRight; font.bold: root.selectedNodeId === String(rowDelegate.modelData.nodeId || "") }
                    Text { Layout.preferredWidth: 62; text: rowDelegate.modelData.year || "-"; color: theme.textMuted; horizontalAlignment: Text.AlignHCenter }
                    Text { Layout.preferredWidth: 180; text: rowDelegate.modelData.authors || "-"; color: theme.textMuted; elide: Text.ElideRight }
                    Text { Layout.preferredWidth: 72; text: Number(rowDelegate.modelData.citations || 0); color: theme.textMuted; horizontalAlignment: Text.AlignHCenter }
                    Text { Layout.preferredWidth: 82; text: Math.round(Number(rowDelegate.modelData.importance || 0) * 100) + "%"; color: theme.textMuted; horizontalAlignment: Text.AlignHCenter }
                    Text { Layout.preferredWidth: 82; text: Number(rowDelegate.modelData.relevance || 0).toFixed(2); color: theme.accent; horizontalAlignment: Text.AlignHCenter }
                }

                ColumnLayout {
                    visible: root.compactMode
                    anchors.fill: parent
                    anchors.margins: 7
                    spacing: 3
                    RowLayout {
                        Layout.fillWidth: true
                        Label {
                            text: rowDelegate.modelData.kind === "paper" ? "论文" : "引用"
                            color: rowDelegate.modelData.kind === "paper" ? theme.accent : theme.textMuted
                            background: Rectangle { color: theme.surfaceElevated; radius: 5; border.color: theme.border }
                            padding: 3
                        }
                        Text {
                            Layout.fillWidth: true
                            text: rowDelegate.modelData.title || "Untitled"
                            color: theme.text
                            font.bold: root.selectedNodeId === String(rowDelegate.modelData.nodeId || "")
                            elide: Text.ElideRight
                        }
                        Text { text: rowDelegate.modelData.year || "-"; color: theme.textMuted; font.pixelSize: 10 }
                    }
                    Text {
                        Layout.fillWidth: true
                        text: (rowDelegate.modelData.authors || "作者未知")
                              + " · 引用 " + Number(rowDelegate.modelData.citations || 0)
                              + " · 相关 " + Number(rowDelegate.modelData.relevance || 0).toFixed(2)
                        color: theme.textMuted
                        font.pixelSize: 10
                        elide: Text.ElideRight
                    }
                }

                MouseArea {
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onEntered: { listView.currentIndex = rowDelegate.index; root.nodeHovered(String(rowDelegate.modelData.nodeId || "")) }
                    onExited: if (root.hoveredNodeId === String(rowDelegate.modelData.nodeId || "")) root.nodeHovered("")
                    onClicked: { listView.currentIndex = rowDelegate.index; root.nodeRequested(String(rowDelegate.modelData.nodeId || "")); listView.forceActiveFocus() }
                }
            }

            Keys.onPressed: function(event) {
                if (!root.pagedRows.length) return
                if (event.key === Qt.Key_Down || event.key === Qt.Key_Up) {
                    var delta = event.key === Qt.Key_Down ? 1 : -1
                    currentIndex = Math.max(0, Math.min(root.pagedRows.length - 1, currentIndex + delta))
                    positionViewAtIndex(currentIndex, ListView.Contain)
                    root.nodeHovered(String(root.pagedRows[currentIndex].nodeId || ""))
                    event.accepted = true
                } else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter || event.key === Qt.Key_Space) {
                    if (currentIndex >= 0) root.nodeRequested(String(root.pagedRows[currentIndex].nodeId || ""))
                    event.accepted = true
                }
            }
        }

        Text {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: root.rows.length === 0
            text: "当前探索子图中没有文献节点。请展开引用关系或清除筛选。"
            color: theme.textMuted
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            wrapMode: Text.Wrap
        }
    }

    component SortHeader: Text {
        required property string label
        required property string keyName
        text: label + (root.sortKey === keyName ? (root.sortDescending ? " ↓" : " ↑") : "")
        color: root.sortKey === keyName ? theme.accent : theme.textMuted
        font.bold: true
        font.pixelSize: 11
        horizontalAlignment: Text.AlignHCenter
        MouseArea {
            anchors.fill: parent
            cursorShape: Qt.PointingHandCursor
            onClicked: root.requestSort(parent.keyName)
        }
    }

    onRowsChanged: {
        root.currentPage = Math.max(0, Math.min(root.currentPage, root.pageCount - 1))
        root.syncSelectedRow()
    }
    onSelectedNodeIdChanged: root.syncSelectedRow()

    function requestSort(keyName) {
        var descending = keyName === root.sortKey
                       ? !root.sortDescending
                       : ["year", "citations", "importance", "relevance"].indexOf(keyName) >= 0
        root.sortRequested(keyName, descending)
    }

    function syncSelectedRow() {
        if (!root.selectedNodeId) return
        for (var i = 0; i < root.rows.length; ++i) {
            if (String(root.rows[i].nodeId || "") !== root.selectedNodeId) continue
            root.currentPage = Math.floor(i / root.pageSize)
            listView.currentIndex = i % root.pageSize
            Qt.callLater(function() { listView.positionViewAtIndex(listView.currentIndex, ListView.Contain) })
            return
        }
    }
}
