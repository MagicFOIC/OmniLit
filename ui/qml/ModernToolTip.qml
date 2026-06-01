import QtQuick

Item {
    id: root
    property string text: ""
    property bool shown: false
    Theme { id: theme }

    implicitWidth: label.implicitWidth + 28
    implicitHeight: 36
    visible: opacity > 0.01
    opacity: shown ? 1 : 0
    scale: shown ? 1 : 0.96
    enabled: false
    z: 100

    Behavior on opacity { NumberAnimation { duration: 120; easing.type: Easing.OutCubic } }
    Behavior on scale { NumberAnimation { duration: 120; easing.type: Easing.OutCubic } }

    Rectangle {
        anchors.fill: parent
        radius: 10
        antialiasing: true
        color: theme.tooltipSurface
        border.color: theme.tooltipBorder
    }

    Rectangle {
        anchors.left: parent.left
        anchors.leftMargin: -4
        anchors.verticalCenter: parent.verticalCenter
        width: 9
        height: 9
        rotation: 45
        antialiasing: true
        color: theme.tooltipSurface
        border.color: theme.tooltipBorder
    }

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
