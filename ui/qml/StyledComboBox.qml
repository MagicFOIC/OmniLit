pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls

ComboBox {
    id: control
    Theme { id: theme }
    Motion { id: motion }

    implicitWidth: Math.max(150, implicitContentWidth + leftPadding + rightPadding)
    implicitHeight: theme.controlHeight
    leftPadding: theme.controlPadding
    rightPadding: 40
    topPadding: 8
    bottomPadding: 8
    font.pixelSize: theme.baseFontSize
    hoverEnabled: true

    contentItem: Text {
        text: control.displayText
        font: control.font
        color: control.enabled ? theme.text : theme.disabledText
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }

    indicator: Item {
        width: 34
        height: control.height
        x: control.width - width - 3
        Rectangle { anchors.left: parent.left; anchors.verticalCenter: parent.verticalCenter; width: 1; height: 20; color: theme.divider }
        VectorIcon {
            anchors.centerIn: parent
            width: 16; height: 16
            name: "chevron-down"
            color: control.enabled ? (control.hovered || control.popup.visible ? theme.accent : theme.textMuted) : theme.disabledText
            rotation: control.popup.visible ? 180 : 0
            Behavior on rotation { NumberAnimation { duration: motion.fast; easing.type: Easing.OutCubic } }
            Behavior on color { ColorAnimation { duration: motion.fast } }
        }
    }

    background: Rectangle {
        radius: theme.radiusMedium
        color: !control.enabled ? theme.surfaceSoft : control.popup.visible ? theme.surface : control.hovered ? theme.accentSofter : theme.surface
        border.width: control.popup.visible ? 2 : 1
        border.color: !control.enabled ? theme.border : control.popup.visible ? theme.accent : control.hovered ? theme.borderStrong : theme.border
        antialiasing: true
        Behavior on color { ColorAnimation { duration: motion.fast } }
        Behavior on border.color { ColorAnimation { duration: motion.fast } }
    }

    delegate: ItemDelegate {
        id: option
        required property int index
        width: control.popup.width - 12
        height: 38
        leftPadding: 12; rightPadding: 12
        highlighted: control.highlightedIndex === index
        hoverEnabled: true
        contentItem: Text {
            text: control.textAt(option.index)
            color: option.highlighted ? theme.accentStrong : theme.text
            font: control.font
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
        }
        background: Rectangle { radius: theme.radiusSmall; color: option.highlighted ? theme.navSelected : option.hovered ? theme.navHover : "transparent" }
    }

    popup: Popup {
        y: control.height + 6
        width: Math.max(control.width, 180)
        implicitHeight: Math.min(contentItem.implicitHeight + 12, 320)
        padding: 6
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutsideParent
        contentItem: ListView {
            clip: true
            implicitHeight: contentHeight
            model: control.popup.visible ? control.delegateModel : null
            currentIndex: control.highlightedIndex
            ScrollIndicator.vertical: ScrollIndicator {}
        }
        background: Rectangle { radius: theme.radiusMedium; color: theme.surfaceElevated; border.color: theme.borderStrong }
        enter: Transition {
            NumberAnimation { property: "opacity"; from: 0; to: 1; duration: motion.fast }
            NumberAnimation { property: "scale"; from: 0.98; to: 1; duration: motion.fast; easing.type: Easing.OutCubic }
        }
        exit: Transition { NumberAnimation { property: "opacity"; from: 1; to: 0; duration: motion.fast } }
    }
}
