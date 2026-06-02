import QtQuick
import QtQuick.Controls

Item {
    id: root
    property Item target: parent
    property string text: ""
    property bool shown: false
    property string placement: "right"
    property int gap: 10
    Theme { id: theme }

    width: 0
    height: 0

    Popup {
        id: bubble
        parent: root.target
        modal: false
        focus: false
        padding: 0
        margins: 8
        closePolicy: Popup.NoAutoClose
        visible: root.shown && !!root.target && root.text.length > 0
        x: !root.target ? 0 : root.placement === "bottom" ? (root.target.width - width) / 2 : root.target.width + root.gap
        y: !root.target ? 0 : root.placement === "bottom" ? root.target.height + root.gap : (root.target.height - height) / 2
        width: label.implicitWidth + 28
        height: 36

        enter: Transition {
            NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 120; easing.type: Easing.OutCubic }
            NumberAnimation { property: "scale"; from: 0.96; to: 1; duration: 120; easing.type: Easing.OutCubic }
        }
        exit: Transition {
            NumberAnimation { property: "opacity"; from: 1; to: 0; duration: 90; easing.type: Easing.InCubic }
        }
        background: Rectangle {
            radius: 10
            antialiasing: true
            color: theme.tooltipSurface
            border.color: theme.tooltipBorder
        }
        contentItem: Item {
            Rectangle {
                anchors.left: parent.left
                anchors.leftMargin: 12
                anchors.verticalCenter: parent.verticalCenter
                width: 5
                height: 5
                radius: 3
                color: theme.accent
            }
            Text {
                id: label
                anchors.left: parent.left
                anchors.leftMargin: 23
                anchors.verticalCenter: parent.verticalCenter
                text: root.text
                color: theme.tooltipText
                font.pixelSize: 12
                font.weight: Font.DemiBold
            }
        }
    }
}
