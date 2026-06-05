import QtQuick
import QtQuick.Controls

CheckBox {
    id: control
    property bool activePulse: false
    Theme { id: theme }
    Motion { id: motion }

    hoverEnabled: true
    spacing: 7
    implicitHeight: Math.max(24, indicator.implicitHeight)
    HoverHandler { cursorShape: Qt.PointingHandCursor }

    indicator: Rectangle {
        id: indicator
        implicitWidth: 19
        implicitHeight: 19
        x: control.leftPadding
        y: (control.height - height) / 2
        radius: 6
        antialiasing: true
        scale: control.activePulse ? 1.08 : 1
        color: control.activePulse ? theme.accentStrong : control.checked ? theme.accent : control.hovered ? theme.accentSofter : theme.surface
        border.width: control.activePulse || control.activeFocus ? 2 : 1
        border.color: control.activePulse ? theme.accentText : control.checked ? theme.accentStrong : control.activeFocus ? theme.accent : control.hovered ? theme.borderStrong : theme.border
        SequentialAnimation on opacity {
            running: control.activePulse
            loops: Animation.Infinite
            NumberAnimation { from: 1; to: 0.45; duration: 420; easing.type: Easing.InOutQuad }
            NumberAnimation { from: 0.45; to: 1; duration: 420; easing.type: Easing.InOutQuad }
        }
        onVisibleChanged: if (!visible) opacity = 1
        onScaleChanged: if (!control.activePulse) opacity = 1
        Behavior on color { ColorAnimation { duration: motion.fast } }
        Behavior on border.color { ColorAnimation { duration: motion.fast } }
        Behavior on scale { NumberAnimation { duration: motion.fast; easing.type: Easing.OutCubic } }

        Canvas {
            anchors.fill: parent
            visible: control.checked
            onPaint: {
                const context = getContext("2d")
                context.reset()
                context.strokeStyle = theme.accentText
                context.lineWidth = 2
                context.lineCap = "round"
                context.lineJoin = "round"
                context.beginPath()
                context.moveTo(5, 10)
                context.lineTo(8, 13)
                context.lineTo(14, 6)
                context.stroke()
            }
        }
    }

    contentItem: Text {
        leftPadding: control.indicator.width + control.spacing
        text: control.text
        color: control.enabled ? theme.text : theme.disabledText
        font: control.font
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }
}
