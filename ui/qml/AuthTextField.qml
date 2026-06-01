import QtQuick
import QtQuick.Controls

TextField {
    id: control
    property string iconName: ""
    Theme { id: theme; dynamic: false }

    implicitHeight: 46
    leftPadding: 42
    rightPadding: 14
    topPadding: 12
    bottomPadding: 12
    selectByMouse: true
    color: theme.text
    placeholderTextColor: theme.disabledText
    selectionColor: theme.navSelected
    selectedTextColor: theme.text
    font.pixelSize: 14

    background: Rectangle {
        radius: 11
        color: control.activeFocus ? theme.surface : theme.surfaceSoft
        border.width: control.activeFocus ? 2 : 1
        border.color: control.activeFocus ? theme.accent : theme.border
        antialiasing: true

        Behavior on color { ColorAnimation { duration: 160; easing.type: Easing.OutCubic } }
        Behavior on border.color { ColorAnimation { duration: 160; easing.type: Easing.OutCubic } }

        VectorIcon {
            width: 18
            height: 18
            anchors.left: parent.left
            anchors.leftMargin: 14
            anchors.verticalCenter: parent.verticalCenter
            name: control.iconName
            color: control.activeFocus ? theme.accent : theme.textMuted
            strokeWidth: 1.8

            Behavior on color { ColorAnimation { duration: 160; easing.type: Easing.OutCubic } }
        }
    }
}
