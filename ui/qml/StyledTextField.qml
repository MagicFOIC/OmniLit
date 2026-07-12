import QtQuick
import QtQuick.Controls

TextField {
    id: control
    Theme { id: theme }
    Motion { id: motion }
    implicitHeight: theme.controlHeight
    leftPadding: theme.controlPadding; rightPadding: theme.controlPadding; topPadding: 8; bottomPadding: 8
    selectByMouse: true
    color: control.enabled ? theme.text : theme.disabledText
    placeholderTextColor: theme.disabledText
    selectionColor: theme.navSelected
    selectedTextColor: theme.text
    font.pixelSize: theme.baseFontSize
    hoverEnabled: true
    background: Rectangle {
        radius: theme.radiusMedium
        color: !control.enabled ? theme.surfaceSoft : control.activeFocus ? theme.surface : control.hovered ? theme.accentSofter : theme.surface
        border.width: control.activeFocus ? 2 : 1
        border.color: !control.enabled ? theme.border : control.activeFocus ? theme.accent : control.hovered ? theme.borderStrong : theme.border
        antialiasing: true
        Behavior on color { ColorAnimation { duration: motion.fast } }
        Behavior on border.color { ColorAnimation { duration: motion.fast } }
    }
}
