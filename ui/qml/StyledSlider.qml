import QtQuick
import QtQuick.Controls

Slider {
    id: control
    Theme { id: theme }
    Motion { id: motion }
    implicitHeight: 30
    hoverEnabled: true
    background: Rectangle {
        x: control.leftPadding
        y: control.topPadding + control.availableHeight / 2 - height / 2
        implicitWidth: 180; implicitHeight: 6
        width: control.availableWidth; height: 6; radius: 3
        color: theme.border
        Rectangle { width: control.visualPosition * parent.width; height: parent.height; radius: parent.radius; color: theme.accent }
    }
    handle: Rectangle {
        x: control.leftPadding + control.visualPosition * (control.availableWidth - width)
        y: control.topPadding + control.availableHeight / 2 - height / 2
        implicitWidth: control.pressed || control.hovered ? 20 : 18
        implicitHeight: implicitWidth
        radius: width / 2
        color: theme.surface
        border.width: 2; border.color: theme.accent
        Behavior on implicitWidth { NumberAnimation { duration: motion.fast } }
    }
}
