import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
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
    property bool workspaceActive: false
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
        workspaceActive = lastLoggedIn
    }

    Connections {
        target: authController
        function onAuthenticated() {
            window.lastLoggedIn = true
            // Workspace is already instantiated while the login page is shown.
            // Switch to that prepared frame before resizing the native window,
            // avoiding both the stretched login frame and a compositor fade.
            window.workspaceActive = true
            workspacePage.forceActiveFocus()
            window.applyWindowMode()
        }
        function onLoggedOut() {
            window.rememberWorkspaceSize()
            window.lastLoggedIn = false
            window.workspaceActive = false
            window.applyWindowMode()
        }
    }

    StackLayout {
        id: pageHost
        anchors.fill: parent
        currentIndex: window.workspaceActive ? 1 : 0

        // Both roots stay instantiated, while StackLayout changes their
        // visibility as one mutually-exclusive state. This prevents a frame
        // where AuthPage is painted on top of the Workspace.
        AuthPage {
            id: authPage
        }

        Workspace {
            id: workspacePage
        }
    }

    function rememberWorkspaceSize() {
        savedWorkspaceWidth = Math.max(workspaceMinimumWidth, width)
        savedWorkspaceHeight = Math.max(workspaceMinimumHeight, height)
    }

    function applyWindowMode() {
        applyingWindowMode = true
        if (lastLoggedIn) {
            maximumWidth = 16777215
            maximumHeight = 16777215
            minimumWidth = Math.min(workspaceMinimumWidth, Screen.desktopAvailableWidth)
            minimumHeight = Math.min(workspaceMinimumHeight, Screen.desktopAvailableHeight)
            // Keep the workspace windowed at its compact usable size. Python
            // centers the native frame on this window's current screen after
            // the resize has reached the window manager.
            visibility = Window.Windowed
            width = Math.min(workspaceMinimumWidth, Screen.desktopAvailableWidth)
            height = Math.min(workspaceMinimumHeight, Screen.desktopAvailableHeight)
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
