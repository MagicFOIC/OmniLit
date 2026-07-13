pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls

FocusScope {
    id: root

    property var topics: []
    property var topicLinks: []
    property string selectedTopicId: ""
    property int currentIndex: 0
    signal topicRequested(string topicId)

    Theme { id: theme }

    function colorFor(index) {
        var colors = [theme.accent, theme.info, theme.success, theme.warning,
                      theme.error, theme.textMuted, theme.accentStrong, theme.success]
        return colors[Math.abs(Number(index || 0)) % colors.length]
    }

    function selectIndex(index) {
        if (!root.topics.length)
            return
        root.currentIndex = (index + root.topics.length) % root.topics.length
        root.topicRequested(String(root.topics[root.currentIndex].id || ""))
    }

    Keys.onPressed: function(event) {
        if (event.key === Qt.Key_Right || event.key === Qt.Key_Down) {
            root.selectIndex(root.currentIndex + 1)
            event.accepted = true
        } else if (event.key === Qt.Key_Left || event.key === Qt.Key_Up) {
            root.selectIndex(root.currentIndex - 1)
            event.accepted = true
        } else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter || event.key === Qt.Key_Space) {
            root.selectIndex(root.currentIndex)
            event.accepted = true
        }
    }

    Rectangle {
        anchors.fill: parent
        radius: theme.radiusMedium
        color: theme.canvas
        border.color: theme.border
    }

    Canvas {
        anchors.fill: parent
        opacity: 0.55
        onPaint: {
            var ctx = getContext("2d")
            ctx.reset()
            ctx.clearRect(0, 0, width, height)
            var glow = ctx.createRadialGradient(width * 0.5, height * 0.46, 0, width * 0.5, height * 0.46, Math.max(width, height) * 0.58)
            glow.addColorStop(0, theme.dark ? "rgba(96,165,250,0.13)" : "rgba(37,99,235,0.09)")
            glow.addColorStop(1, "rgba(0,0,0,0)")
            ctx.fillStyle = glow
            ctx.fillRect(0, 0, width, height)
        }
    }

    Canvas {
        id: similarityCanvas
        anchors.fill: parent
        opacity: 0.72
        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()
        onPaint: {
            var ctx = getContext("2d")
            ctx.reset()
            ctx.clearRect(0, 0, width, height)
            var positions = ({})
            for (var i = 0; i < root.topics.length; ++i) {
                var topic = root.topics[i]
                positions[String(topic.id || "")] = { x: Number(topic.x || 0.5) * width, y: Number(topic.y || 0.5) * height }
            }
            for (var j = 0; j < root.topicLinks.length; ++j) {
                var link = root.topicLinks[j]
                var source = positions[String(link.sourceTopicId || "")]
                var target = positions[String(link.targetTopicId || "")]
                if (!source || !target) continue
                var score = Number(link.similarity || 0)
                ctx.strokeStyle = theme.dark ? "rgba(147,197,253,0.58)" : "rgba(37,99,235,0.42)"
                ctx.lineWidth = 1 + score * 4
                ctx.beginPath()
                ctx.moveTo(source.x, source.y)
                ctx.lineTo(target.x, target.y)
                ctx.stroke()
                if (score >= 0.18) {
                    ctx.fillStyle = theme.textMuted
                    ctx.font = "10px sans-serif"
                    ctx.fillText(Math.round(score * 100) + "%", (source.x + target.x) / 2 + 4, (source.y + target.y) / 2 - 4)
                }
            }
        }
    }

    onTopicsChanged: similarityCanvas.requestPaint()
    onTopicLinksChanged: similarityCanvas.requestPaint()

    Repeater {
        model: root.topics
        delegate: Rectangle {
            id: bubble
            required property var modelData
            required property int index

            readonly property real diameter: Math.max(64, Math.min(root.width, root.height) * Number(modelData.radius || 0.10) * 2)
            width: diameter
            height: diameter
            radius: width / 2
            x: Math.max(4, Math.min(root.width - width - 4, Number(modelData.x || 0.5) * root.width - width / 2))
            y: Math.max(4, Math.min(root.height - height - 4, Number(modelData.y || 0.5) * root.height - height / 2))
            color: theme.mix(root.colorFor(modelData.colorIndex), theme.surface, theme.dark ? 0.62 : 0.33)
            border.width: String(modelData.id || "") === root.selectedTopicId ? 3 : 1
            border.color: String(modelData.id || "") === root.selectedTopicId ? root.colorFor(modelData.colorIndex) : theme.borderStrong
            scale: mouse.containsMouse || String(modelData.id || "") === root.selectedTopicId ? 1.055 : 1.0
            opacity: modelData.lowConfidence ? 0.72 : 0.96

            Behavior on scale { NumberAnimation { duration: 130; easing.type: Easing.OutCubic } }

            Column {
                anchors.centerIn: parent
                width: parent.width * 0.76
                spacing: 4
                Text {
                    width: parent.width
                    text: modelData.name || "未命名主题"
                    color: theme.text
                    font.bold: true
                    font.pixelSize: Math.max(11, Math.min(17, bubble.width * 0.10))
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.Wrap
                    maximumLineCount: 3
                    elide: Text.ElideRight
                }
                Text {
                    width: parent.width
                    text: Number(modelData.size || 0) + " 篇 · " + String((modelData.growth || {}).label || "年份不足")
                    color: theme.textMuted
                    font.pixelSize: 10
                    horizontalAlignment: Text.AlignHCenter
                }
                Text {
                    width: parent.width
                    visible: !!modelData.lowConfidence
                    text: "低置信度"
                    color: theme.warning
                    font.pixelSize: 9
                    horizontalAlignment: Text.AlignHCenter
                }
            }

            MouseArea {
                id: mouse
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: {
                    root.currentIndex = bubble.index
                    root.topicRequested(String(bubble.modelData.id || ""))
                    root.forceActiveFocus()
                }
                ToolTip.visible: containsMouse
                ToolTip.text: (bubble.modelData.explanation || {}).method || "选择主题查看解释"
            }
        }
    }

    Text {
        anchors.centerIn: parent
        visible: root.topics.length === 0
        text: "没有可显示的主题"
        color: theme.textMuted
    }
}
