import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: root

    property string contentRevision: ""
    property string unreadText: "New output available"
    property real stickThreshold: 28
    property real spacing: 8
    property bool followTail: true
    property bool hasUnread: false
    property real lastY: 0
    property real lastMaxY: 0
    default property alias content: contentColumn.data

    clip: true

    ScrollView {
        id: scroll
        anchors.fill: parent
        contentWidth: availableWidth
        clip: true
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

        Column {
            id: contentColumn
            width: scroll.availableWidth
            spacing: root.spacing
        }
    }

    PillButton {
        id: unreadButton
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 10
        visible: root.hasUnread && !root.followTail
        text: root.unreadText
        iconName: "download"
        primary: true
        onClicked: root.scrollToBottom()
    }

    Connections {
        target: scroll.contentItem
        function onContentYChanged() { root.captureScrollState() }
        function onHeightChanged() { root.preserveOrFollow() }
        function onContentHeightChanged() { root.preserveOrFollow() }
    }

    onContentRevisionChanged: root.preserveOrFollow()

    Component.onCompleted: Qt.callLater(root.scrollToBottom)

    function maxY() {
        let flick = scroll.contentItem
        return flick ? Math.max(0, flick.contentHeight - flick.height) : 0
    }

    function isNearBottom() {
        return root.lastY >= root.lastMaxY - root.stickThreshold
    }

    function captureScrollState() {
        let flick = scroll.contentItem
        if (!flick)
            return
        root.lastY = flick.contentY
        root.lastMaxY = root.maxY()
        if (root.isNearBottom()) {
            root.followTail = true
            root.hasUnread = false
        } else {
            root.followTail = false
        }
    }

    function preserveOrFollow() {
        let flick = scroll.contentItem
        if (!flick)
            return
        let oldY = root.lastY
        let wasAtBottom = root.followTail || root.isNearBottom()
        Qt.callLater(function() {
            let newMaxY = root.maxY()
            if (wasAtBottom) {
                flick.contentY = newMaxY
                root.followTail = true
                root.hasUnread = false
            } else {
                flick.contentY = Math.min(oldY, newMaxY)
                root.followTail = false
                root.hasUnread = newMaxY > oldY + root.stickThreshold
            }
            root.captureScrollState()
        })
    }

    function scrollToBottom() {
        let flick = scroll.contentItem
        if (!flick)
            return
        Qt.callLater(function() {
            flick.contentY = root.maxY()
            root.followTail = true
            root.hasUnread = false
            root.captureScrollState()
        })
    }
}
