import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Button {
    id: control
    property string iconName: ""
    property string label: ""
    property string detail: ""
    property bool attention: false
    Theme { id: theme }
    Motion { id: motion }

    implicitHeight: 64
    leftPadding: 12
    rightPadding: 12
    hoverEnabled: true
    HoverHandler { cursorShape: Qt.PointingHandCursor }

    background: Rectangle {
        radius: theme.radiusLarge
        color: control.hovered ? theme.navHover : theme.surface
        border.color: control.hovered ? theme.borderStrong : theme.border
        antialiasing: true
        Behavior on color { ColorAnimation { duration: motion.fast } }
        Behavior on border.color { ColorAnimation { duration: motion.fast } }
    }

    contentItem: RowLayout {
        spacing: 12

        Rectangle {
            Layout.preferredWidth: 38
            Layout.preferredHeight: 38
            radius: 12
            color: control.hovered ? theme.accentSoft : theme.accentSofter
            VectorIcon {
                anchors.centerIn: parent
                width: 20
                height: 20
                name: control.iconName
                color: theme.accent
            }
        }
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 1
            Text { text: control.label; color: theme.text; font.pixelSize: 14; font.weight: Font.DemiBold }
            Text { visible: !!control.detail; text: control.detail; color: theme.textMuted; font.pixelSize: 11 }
        }
        Rectangle { visible: control.attention; Layout.preferredWidth: 8; Layout.preferredHeight: 8; radius: 4; color: theme.error }
        VectorIcon { name: "chevron-right"; color: theme.textMuted; Layout.preferredWidth: 17; Layout.preferredHeight: 17; strokeWidth: 2.1 }
    }
}
