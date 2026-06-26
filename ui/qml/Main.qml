import QtQuick
import QtQuick.Controls
import QtQuick.Window

ApplicationWindow {
    id: window
    Theme { id: theme; dynamic: authController.loggedIn }
    readonly property int authWindowWidth: 472
    readonly property int authWindowHeight: 620
    readonly property int workspaceMinimumWidth: 1280
    readonly property int workspaceMinimumHeight: 860
    property int savedWorkspaceWidth: 0
    property int savedWorkspaceHeight: 0
    property bool applyingWindowMode: false
    property bool lastLoggedIn: false
    width: authWindowWidth
    height: authWindowHeight
    minimumWidth: authWindowWidth
    minimumHeight: authWindowHeight
    maximumWidth: 16777215
    maximumHeight: 16777215
    visible: true
    title: "OmniLit"
    color: theme.canvas
    palette.highlight: theme.accent
    palette.button: theme.surface
    palette.buttonText: theme.text
    palette.base: theme.surface
    palette.alternateBase: theme.surfaceSoft
    palette.text: theme.text
    palette.windowText: theme.text
    palette.placeholderText: theme.disabledText
    palette.highlightedText: theme.accentText
    palette.window: theme.canvas

    Rectangle {
        anchors.fill: parent
        gradient: Gradient {
            GradientStop { position: 0.0; color: theme.canvasTop }
            GradientStop { position: 1.0; color: theme.canvasBottom }
        }
    }

    onWidthChanged: {
        if (!applyingWindowMode && lastLoggedIn)
            savedWorkspaceWidth = width
    }
    onHeightChanged: {
        if (!applyingWindowMode && lastLoggedIn)
            savedWorkspaceHeight = height
    }

    Component.onCompleted: {
        lastLoggedIn = authController.loggedIn
        applyWindowMode()
    }

    Connections {
        target: authController
        function onChanged() {
            const loggedIn = authController.loggedIn
            if (loggedIn === lastLoggedIn)
                return
            if (!loggedIn)
                rememberWorkspaceSize()
            lastLoggedIn = loggedIn
            applyWindowMode()
        }
    }

    Loader {
        anchors.fill: parent
        sourceComponent: authController.loggedIn ? workspace : authPage
    }

    Component { id: authPage; AuthPage {} }
    Component { id: workspace; Workspace {} }

    function rememberWorkspaceSize() {
        savedWorkspaceWidth = Math.max(workspaceMinimumWidth, width)
        savedWorkspaceHeight = Math.max(workspaceMinimumHeight, height)
    }

    function applyWindowMode() {
        applyingWindowMode = true
        if (lastLoggedIn) {
            visibility = Window.Windowed
            maximumWidth = 16777215
            maximumHeight = 16777215
            minimumWidth = Math.min(workspaceMinimumWidth, Screen.desktopAvailableWidth)
            minimumHeight = Math.min(workspaceMinimumHeight, Screen.desktopAvailableHeight)
            x = Screen.desktopAvailableX
            y = Screen.desktopAvailableY
            width = Screen.desktopAvailableWidth
            height = Screen.desktopAvailableHeight
        } else {
            visibility = Window.Windowed
            minimumWidth = authWindowWidth
            minimumHeight = authWindowHeight
            maximumWidth = 16777215
            maximumHeight = 16777215
            width = authWindowWidth
            height = authWindowHeight
        }
        applyingWindowMode = false
    }
}
