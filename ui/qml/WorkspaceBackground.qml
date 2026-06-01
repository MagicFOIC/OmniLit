import QtQuick
import QtQuick.Effects

Item {
    id: root
    Theme { id: theme }
    readonly property string mode: preferencesController.backgroundMode

    Rectangle {
        anchors.fill: parent
        color: root.mode === "none" ? "transparent" : theme.canvas
    }

    Rectangle {
        anchors.fill: parent
        visible: root.mode === "gradient"
        gradient: Gradient {
            GradientStop { position: 0.0; color: theme.canvasTop }
            GradientStop { position: 1.0; color: theme.canvasBottom }
        }
    }

    Canvas {
        id: pattern
        anchors.fill: parent
        visible: root.mode === "paper" || root.mode === "grid"
        opacity: root.mode === "paper" ? 0.28 : 0.42
        onVisibleChanged: requestPaint()
        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()
        onPaint: {
            const context = getContext("2d")
            context.reset()
            context.strokeStyle = theme.border
            context.lineWidth = 1
            const step = root.mode === "paper" ? 28 : 20
            for (let x = 0; x <= width; x += step) {
                context.beginPath()
                context.moveTo(x, 0)
                context.lineTo(x, height)
                context.stroke()
            }
            for (let y = 0; y <= height; y += step) {
                context.beginPath()
                context.moveTo(0, y)
                context.lineTo(width, y)
                context.stroke()
            }
        }
    }

    Connections {
        target: preferencesController
        function onChanged() {
            pattern.requestPaint()
        }
    }

    Image {
        id: imageSource
        anchors.fill: parent
        visible: false
        source: preferencesController.workspaceBackgroundUrl
        fillMode: Image.PreserveAspectCrop
        asynchronous: true
        cache: false
        smooth: true
        mipmap: true
    }

    MultiEffect {
        anchors.fill: parent
        visible: root.mode === "image" && imageSource.source.toString().length > 0
        source: imageSource
        opacity: preferencesController.backgroundOpacity
        blurEnabled: preferencesController.backgroundBlur > 0
        blur: preferencesController.backgroundBlur / 32.0
        blurMax: 32
    }

    Rectangle {
        anchors.fill: parent
        visible: root.mode === "image" && imageSource.source.toString().length > 0
        color: theme.workspaceOverlay
    }
}
