pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

FocusScope {
    id: root

    property var events: []
    property int playbackYear: 0
    property string selectedPaperId: ""
    property int currentIndex: 0
    signal yearRequested(int year)
    signal paperRequested(string recordId)

    Theme { id: theme }

    function selectIndex(index) {
        if (!root.events.length)
            return
        root.currentIndex = Math.max(0, Math.min(root.events.length - 1, index))
        root.yearRequested(Number(root.events[root.currentIndex].year || 0))
    }

    onPlaybackYearChanged: {
        for (var i = 0; i < root.events.length; ++i) {
            if (Number(root.events[i].year || 0) === root.playbackYear) {
                root.currentIndex = i
                Qt.callLater(function() {
                    timelineFlick.contentX = Math.max(0, Math.min(timelineFlick.contentWidth - timelineFlick.width,
                                                                  root.currentIndex * 186 - timelineFlick.width + 196))
                })
                break
            }
        }
    }

    Keys.onPressed: function(event) {
        if (event.key === Qt.Key_Right) {
            root.selectIndex(root.currentIndex + 1); event.accepted = true
        } else if (event.key === Qt.Key_Left) {
            root.selectIndex(root.currentIndex - 1); event.accepted = true
        } else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter || event.key === Qt.Key_Space) {
            root.selectIndex(root.currentIndex); event.accepted = true
        }
    }

    Rectangle {
        anchors.fill: parent
        radius: theme.radiusMedium
        color: theme.canvas
        border.color: theme.border
    }

    Flickable {
        id: timelineFlick
        anchors.fill: parent
        anchors.margins: 8
        clip: true
        contentWidth: Math.max(width, yearRow.width)
        contentHeight: height
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.horizontal: StyledScrollBar { policy: ScrollBar.AsNeeded }

        Rectangle {
            x: 16
            y: 55
            width: Math.max(0, yearRow.width - 32)
            height: 3
            radius: 2
            color: theme.borderStrong
        }

        Row {
            id: yearRow
            height: timelineFlick.height - 10
            spacing: 10

            Repeater {
                model: root.events
                delegate: Rectangle {
                    id: yearCard
                    required property var modelData
                    required property int index
                    width: 176
                    height: yearRow.height - 12
                    radius: 10
                    color: Number(modelData.year || 0) === root.playbackYear ? theme.accentSofter : theme.surface
                    border.width: Number(modelData.year || 0) === root.playbackYear ? 2 : 1
                    border.color: Number(modelData.year || 0) === root.playbackYear ? theme.accent : theme.border

                    Rectangle {
                        anchors.horizontalCenter: parent.horizontalCenter
                        y: 46
                        width: 15
                        height: 15
                        radius: 8
                        color: Number(yearCard.modelData.year || 0) === root.playbackYear ? theme.accent : theme.surfaceElevated
                        border.color: theme.accent
                        border.width: 2
                    }

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 9
                        spacing: 6

                        Text {
                            Layout.fillWidth: true
                            text: String(yearCard.modelData.year || "")
                            color: theme.text
                            font.bold: true
                            font.pixelSize: 18
                            horizontalAlignment: Text.AlignHCenter
                        }
                        Item { Layout.preferredHeight: 12 }
                        Text {
                            Layout.fillWidth: true
                            text: (yearCard.modelData.papers || []).length + " 篇新论文 · "
                                  + (yearCard.modelData.citations || []).length + " 条引文"
                            color: theme.textMuted
                            font.pixelSize: 10
                            horizontalAlignment: Text.AlignHCenter
                        }
                        Repeater {
                            model: (yearCard.modelData.turningPoints || []).slice(0, 2)
                            delegate: Rectangle {
                                required property var modelData
                                Layout.fillWidth: true
                                Layout.preferredHeight: milestoneText.implicitHeight + 10
                                radius: 6
                                color: theme.warningSoft
                                border.color: theme.warning
                                Text {
                                    id: milestoneText
                                    anchors.fill: parent
                                    anchors.margins: 5
                                    text: "◆ " + String(modelData.title || "关键转折")
                                    color: theme.warning
                                    font.pixelSize: 9
                                    wrapMode: Text.Wrap
                                    maximumLineCount: 2
                                    elide: Text.ElideRight
                                }
                            }
                        }
                        Repeater {
                            model: (yearCard.modelData.topics || []).slice(0, 4)
                            delegate: Text {
                                required property var modelData
                                Layout.fillWidth: true
                                text: "+" + Number(modelData.newCount || 0) + " " + String(modelData.name || "待归类")
                                      + ((modelData.representativePaper || {}).title ? " · 代表 " + String(modelData.representativePaper.title) : "")
                                color: theme.accent
                                font.pixelSize: 10
                                elide: Text.ElideRight
                                ToolTip.visible: topicHover.containsMouse
                                ToolTip.text: ((modelData.representativePaper || {}).reason || "该主题该年度没有代表论文")
                                MouseArea { id: topicHover; anchors.fill: parent; hoverEnabled: true }
                            }
                        }
                        Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: theme.divider }
                        Text { text: "关键论文"; color: theme.text; font.bold: true; font.pixelSize: 10 }
                        Repeater {
                            model: (yearCard.modelData.papers || []).slice(0, 5)
                            delegate: Rectangle {
                                id: paperRow
                                required property var modelData
                                Layout.fillWidth: true
                                Layout.preferredHeight: 35
                                radius: 6
                                color: String(modelData.recordId || "") === root.selectedPaperId ? theme.navSelected : paperMouse.containsMouse ? theme.navHover : theme.surfaceSoft
                                border.color: theme.border
                                Text {
                                    anchors.fill: parent
                                    anchors.margins: 5
                                    text: String(paperRow.modelData.title || paperRow.modelData.recordId || "论文")
                                    color: theme.text
                                    font.pixelSize: 9
                                    verticalAlignment: Text.AlignVCenter
                                    elide: Text.ElideRight
                                }
                                MouseArea {
                                    id: paperMouse
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: {
                                        root.currentIndex = yearCard.index
                                        root.paperRequested(String(paperRow.modelData.recordId || ""))
                                        root.forceActiveFocus()
                                    }
                                    ToolTip.visible: containsMouse
                                    ToolTip.text: (paperRow.modelData.reasons || []).join("；")
                                }
                            }
                        }
                        Text {
                            Layout.fillWidth: true
                            visible: (yearCard.modelData.papers || []).length > 5
                            text: "另有 " + ((yearCard.modelData.papers || []).length - 5) + " 篇"
                            color: theme.textMuted
                            font.pixelSize: 9
                            horizontalAlignment: Text.AlignHCenter
                        }
                        Item { Layout.fillHeight: true }
                    }

                    MouseArea {
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.top: parent.top
                        height: 66
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            root.currentIndex = yearCard.index
                            root.yearRequested(Number(yearCard.modelData.year || 0))
                            root.forceActiveFocus()
                        }
                    }
                }
            }
        }
    }

    Text {
        anchors.centerIn: parent
        visible: root.events.length === 0
        text: "当前范围没有可显示的年份事件"
        color: theme.textMuted
    }
}
