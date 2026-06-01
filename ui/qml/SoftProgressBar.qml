import QtQuick
import QtQuick.Controls

ProgressBar {
    id: control
    implicitHeight: 8
    Theme { id: theme }

    background: Rectangle {
        implicitHeight: 8
        radius: 4
        color: theme.accentSoft
    }

    contentItem: Item {
        implicitHeight: 8
        clip: true
        Rectangle {
            width: control.visualPosition * parent.width
            height: parent.height
            radius: 4
            color: theme.accent
            Behavior on width { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }
        }
    }
}
