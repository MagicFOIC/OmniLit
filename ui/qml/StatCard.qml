import QtQuick
import QtQuick.Layouts

Card {
    id: root
    property string title: ""
    property string value: ""
    property string detail: ""
    Theme { id: theme }
    Layout.fillWidth: true
    Layout.preferredHeight: 84
    Rectangle {
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.rightMargin: 10
        anchors.topMargin: 10
        width: 30
        height: 4
        radius: 2
        color: theme.accentSoft
        Rectangle { width: 12; height: 4; radius: 2; color: theme.accent }
    }
    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 10
        spacing: 2
        RowLayout {
            spacing: 6
            Rectangle { Layout.preferredWidth: 6; Layout.preferredHeight: 6; radius: 3; color: theme.accent; opacity: 0.72 }
            Text { text: root.title; color: theme.textMuted; font.pixelSize: 12 }
        }
        Text { text: root.value; color: theme.text; font.pixelSize: 22; font.weight: Font.Bold }
        Text { text: root.detail; color: theme.textMuted; font.pixelSize: 12; wrapMode: Text.WordWrap; Layout.fillWidth: true }
    }
}
