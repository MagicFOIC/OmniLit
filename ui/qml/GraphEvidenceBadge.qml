import QtQuick

Rectangle {
    id: root

    property int count: 0
    property real confidence: 1.0
    property bool needsReview: false

    Theme { id: theme }

    width: Math.max(16, label.implicitWidth + 8)
    height: 16
    radius: 8
    color: root.needsReview ? theme.warningSoft : theme.surfaceElevated
    border.color: root.needsReview ? theme.warning : theme.border
    opacity: root.count > 0 || root.needsReview ? 1 : 0

    Text {
        id: label
        anchors.centerIn: parent
        text: root.count > 0 ? String(root.count) : "!"
        color: root.needsReview ? theme.warning : theme.textMuted
        font.pixelSize: 9
        font.bold: true
    }
}
