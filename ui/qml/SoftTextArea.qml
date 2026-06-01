import QtQuick
import QtQuick.Controls

TextArea {
    id: control
    Theme { id: theme }
    Motion { id: motion }
    padding: 10
    selectByMouse: true
    color: theme.text
    selectionColor: theme.navSelected
    selectedTextColor: theme.text
    font.pixelSize: theme.baseFontSize

    background: Rectangle {
        radius: theme.radiusMedium
        color: control.readOnly ? theme.accentSofter : theme.surface
        border.color: control.activeFocus ? theme.accent : theme.border
        antialiasing: true
        Behavior on border.color { ColorAnimation { duration: motion.normal; easing.type: Easing.OutCubic } }
    }
}
