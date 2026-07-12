import QtQuick
import QtQuick.Controls

Switch {
    id: control
    Theme { id: theme }
    Motion { id: motion }
    implicitHeight: 32
    spacing: 9
    hoverEnabled: true
    indicator: Rectangle {
        implicitWidth: 42; implicitHeight: 24
        x: control.leftPadding; y: (control.height - height) / 2
        radius: height / 2
        color: control.checked ? theme.accent : control.hovered ? theme.borderStrong : theme.border
        opacity: control.enabled ? 1 : 0.55
        Behavior on color { ColorAnimation { duration: motion.fast } }
        Rectangle {
            width: 18; height: 18; radius: 9
            x: control.checked ? parent.width - width - 3 : 3
            anchors.verticalCenter: parent.verticalCenter
            color: theme.accentText
            Behavior on x { NumberAnimation { duration: motion.fast; easing.type: Easing.OutCubic } }
        }
    }
    contentItem: Text {
        leftPadding: control.indicator.width + control.spacing
        text: control.text
        font: control.font
        color: control.enabled ? theme.text : theme.disabledText
        verticalAlignment: Text.AlignVCenter
    }
}
