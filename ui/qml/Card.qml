import QtQuick

Rectangle {
    Theme { id: theme }
    radius: theme.radiusLarge
    color: theme.surface
    border.color: theme.border
    border.width: 1
    antialiasing: true

    Rectangle {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.leftMargin: 14
        anchors.rightMargin: 14
        height: 1
        color: theme.dark ? theme.borderStrong : theme.surface
        opacity: 0.9
    }
}
