import QtQuick
import QtQuick.Effects

Item {
    id: root
    Theme { id: theme }
    readonly property string mode: preferencesController.backgroundMode

    Rectangle {
        anchors.fill: parent
        color: theme.canvas
    }

    Rectangle {
        anchors.fill: parent
        visible: root.mode === "solid"
        color: theme.surface
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
        visible: root.mode === "paper" || root.mode === "grid" || root.mode === "dots" || root.mode === "focus"
        opacity: root.mode === "paper" ? 0.22 : root.mode === "focus" ? 0.18 : 0.38
        onVisibleChanged: requestPaint()
        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()
        onPaint: {
            const context = getContext("2d")
            context.reset()
            context.strokeStyle = root.mode === "focus" ? theme.accentSoft : theme.border
            context.fillStyle = theme.borderStrong
            context.lineWidth = 1
            const step = root.mode === "paper" || root.mode === "focus" ? 28 : 20
            if (root.mode === "dots") {
                for (let x = step / 2; x <= width; x += step)
                    for (let y = step / 2; y <= height; y += step) {
                        context.beginPath()
                        context.arc(x, y, 1.25, 0, Math.PI * 2)
                        context.fill()
                    }
                return
            }
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

    Rectangle {
        anchors.fill: parent
        visible: root.mode === "glow"
        gradient: Gradient {
            orientation: Gradient.Horizontal
            GradientStop { position: 0.0; color: theme.accentSofter }
            GradientStop { position: 0.55; color: theme.canvas }
            GradientStop { position: 1.0; color: theme.surfaceSoft }
        }
        opacity: 0.68
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
