import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ScrollView {
    id: root

    property string text: ""
    property real stickThreshold: 12
    property bool followTail: true

    property alias readOnly: area.readOnly
    property alias wrapMode: area.wrapMode

    contentWidth: availableWidth
    clip: true
    ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

    SoftTextArea {
        id: area
        width: root.availableWidth
        readOnly: true
        wrapMode: TextArea.Wrap
    }

    Component.onCompleted: syncText()
    onTextChanged: syncText()

    function syncText() {
        let flick = root.contentItem
        if (!flick || area.text === root.text)
            return

        let oldY = flick.contentY
        let maxY = Math.max(0, flick.contentHeight - flick.height)
        let wasAtBottom = oldY >= maxY - root.stickThreshold

        area.text = root.text

        Qt.callLater(function() {
            let newMaxY = Math.max(0, flick.contentHeight - flick.height)
            flick.contentY = root.followTail && wasAtBottom
                ? newMaxY
                : Math.min(oldY, newMaxY)
        })
    }
}