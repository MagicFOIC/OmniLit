import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

RowLayout {
    id: root
    property string title: ""
    property string detail: ""
    signal back()
    Theme { id: theme }

    Layout.fillWidth: true
    Layout.leftMargin: 12
    Layout.rightMargin: 12
    Layout.topMargin: 12
    spacing: 10

    Button {
        implicitWidth: 42
        implicitHeight: 42
        onClicked: root.back()
        HoverHandler { cursorShape: Qt.PointingHandCursor }
        background: Rectangle {
            radius: theme.radiusMedium
            color: parent.hovered ? theme.navHover : "transparent"
            border.color: parent.hovered ? theme.border : "transparent"
        }
        contentItem: VectorIcon { name: "back"; color: theme.text }
    }
    ColumnLayout {
        Layout.fillWidth: true
        spacing: 1
        Text { text: root.title; color: theme.text; font.pixelSize: theme.baseFontSize + 6; font.weight: Font.Bold }
        Text { visible: !!root.detail; text: root.detail; color: theme.textMuted; font.pixelSize: theme.baseFontSize - 2; wrapMode: Text.WordWrap; Layout.fillWidth: true }
    }
}
