import QtQuick
import QtQuick.Controls

Item {
    id: root
    property Item target: parent
    property string text: ""
    property bool shown: false
    property string placement: "right"
    property int gap: 10
    property int delay: 0
    property int timeout: 0
    property int maxWidth: 320
    readonly property int horizontalPadding: 42
    property bool active: false
    Theme { id: theme }

    width: 0
    height: 0

    onShownChanged: updateVisibilityRequest()
    onTextChanged: updateVisibilityRequest()

    Timer {
        id: delayTimer
        interval: root.delay
        repeat: false
        onTriggered: root.showBubble()
    }

    Timer {
        id: timeoutTimer
        interval: root.timeout
        repeat: false
        onTriggered: root.active = false
    }

    TextMetrics {
        id: labelMetrics
        text: root.text
        font.pixelSize: 12
        font.weight: Font.Medium
    }

    Popup {
        id: bubble
        parent: root.target
        modal: false
        focus: false
        padding: 0
        margins: 8
        closePolicy: Popup.NoAutoClose
        visible: root.active && !!root.target && root.text.length > 0
        x: !root.target ? 0 : root.placement === "bottom" ? (root.target.width - width) / 2 : root.target.width + root.gap
        y: !root.target ? 0 : root.placement === "bottom" ? root.target.height + root.gap : (root.target.height - height) / 2
        width: Math.min(root.maxWidth, Math.ceil(labelMetrics.advanceWidth) + root.horizontalPadding)
        height: Math.max(34, label.paintedHeight + 18)

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
                opacity: 0.72
            }
            Text {
                id: label
                anchors.left: parent.left
                anchors.leftMargin: 23
                anchors.right: parent.right
                anchors.rightMargin: 12
                anchors.verticalCenter: parent.verticalCenter
                text: root.text
                color: theme.tooltipText
                font.pixelSize: 12
                font.weight: Font.Medium
                wrapMode: Text.Wrap
                lineHeight: 1.18
            }
        }
    }

    function updateVisibilityRequest() {
        delayTimer.stop()
        timeoutTimer.stop()
        if(!shown || text.length === 0) {
            active = false
            return
        }
        if(delay > 0)
            delayTimer.restart()
        else
            showBubble()
    }

    function showBubble() {
        if(!shown || text.length === 0)
            return
        active = true
        if(timeout > 0)
            timeoutTimer.restart()
    }
}
