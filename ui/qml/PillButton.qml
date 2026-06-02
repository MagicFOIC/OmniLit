import QtQuick
import QtQuick.Controls

Button {
    id: control
    property bool primary: false
    property bool busy: false
    property string iconName: ""
    Theme { id: theme }
    Motion { id: motion }
    implicitHeight: 42
    padding: 13
    font.pixelSize: theme.baseFontSize
    font.weight: Font.DemiBold
    enabled: !busy
    hoverEnabled: true
    scale: down ? 0.98 : 1
    Behavior on scale { NumberAnimation { duration: motion.fast; easing.type: Easing.OutCubic } }
    HoverHandler { cursorShape: control.enabled ? Qt.PointingHandCursor : Qt.ArrowCursor }
    background: Rectangle {
        radius: theme.radiusMedium
        antialiasing: true
        color: !control.enabled ? theme.surfaceSoft : control.primary ? (control.hovered ? theme.accentStrong : theme.accent) : control.hovered ? theme.accentSoft : theme.surface
        border.color: !control.enabled ? theme.border : control.primary ? (control.hovered ? theme.accentStrong : theme.accent) : control.hovered ? theme.borderStrong : theme.border
        Behavior on color { ColorAnimation { duration: motion.fast } }
        Behavior on border.color { ColorAnimation { duration: motion.fast } }
    }
    contentItem: Item {
        implicitWidth: contentRow.implicitWidth
        implicitHeight: contentRow.implicitHeight
        Row {
            id: contentRow
            spacing: 7
            anchors.centerIn: parent
            BusyIndicator {
                width: 18
                height: 18
                running: control.busy
                visible: running
                palette.dark: control.primary ? theme.accentText : theme.accent
            }
            VectorIcon {
                anchors.verticalCenter: parent.verticalCenter
                width: 18
                height: 18
                visible: !!control.iconName && !control.busy
                name: control.iconName
                color: !control.enabled ? theme.disabledText : control.primary ? theme.accentText : theme.text
                strokeWidth: 2
            }
            Text {
                anchors.verticalCenter: parent.verticalCenter
                visible: !!control.text
                text: control.text
                color: !control.enabled && !control.busy ? theme.disabledText : control.primary ? theme.accentText : theme.text
                font: control.font
                Behavior on color { ColorAnimation { duration: motion.fast } }
            }
        }
    }
}
