import QtQuick
import QtQuick.Layouts

Rectangle {
    id: root
    property string status: ""
    property bool compact: false
    Theme { id: theme }

    visible: !!status
    implicitWidth: compact ? 16 : statusRow.implicitWidth + 16
    implicitHeight: compact ? 16 : 26
    width: implicitWidth
    height: implicitHeight
    radius: height / 2
    color: compact ? theme.surface : theme.successSoft
    border.color: compact ? theme.surface : theme.successBorder
    border.width: compact ? 2 : 1
    antialiasing: true

    RowLayout {
        id: statusRow
        visible: !root.compact
        anchors.centerIn: parent
        spacing: 6

        Rectangle {
            Layout.preferredWidth: 7
            Layout.preferredHeight: 7
            radius: 4
            color: theme.presence
        }
        Text {
            text: root.status
            color: theme.text
            font.pixelSize: 11
            font.weight: Font.DemiBold
        }
    }

    Rectangle {
        visible: root.compact
        anchors.centerIn: parent
        width: 8
        height: 8
        radius: 4
        color: theme.presence
    }
}
