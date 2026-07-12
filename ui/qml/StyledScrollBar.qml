import QtQuick
import QtQuick.Controls

ScrollBar {
    id: control
    Theme { id: theme }
    Motion { id: motion }

    readonly property bool expanded: control.hovered || control.pressed
    implicitWidth: control.orientation === Qt.Vertical ? (expanded ? 14 : 8) : 8
    implicitHeight: control.orientation === Qt.Horizontal ? (expanded ? 14 : 8) : 8
    minimumSize: 0.08
    interactive: true
    padding: expanded ? 2 : 1

    Behavior on implicitWidth { NumberAnimation { duration: motion.fast; easing.type: Easing.OutCubic } }
    Behavior on implicitHeight { NumberAnimation { duration: motion.fast; easing.type: Easing.OutCubic } }

    contentItem: Rectangle {
        implicitWidth: 6
        implicitHeight: 6
        radius: Math.min(width, height) / 2
        color: control.pressed ? theme.accentStrong : control.hovered ? theme.accent : theme.textMuted
        opacity: control.pressed ? 1 : control.hovered ? 0.9 : control.active ? 0.62 : 0.38
        Behavior on color { ColorAnimation { duration: motion.fast } }
        Behavior on opacity { NumberAnimation { duration: motion.fast } }
    }

    background: Rectangle {
        radius: Math.min(width, height) / 2
        color: control.expanded ? theme.accentSofter : "transparent"
        Behavior on color { ColorAnimation { duration: motion.fast } }
    }
}
