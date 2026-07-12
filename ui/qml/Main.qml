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
    property bool windowTransitioning: false
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
            // Suppress the native backing store while changing from the compact
            // login geometry to the workspace geometry. On Windows the old
            // login frame can otherwise remain visible in the center of the
            // resized window until the first Workspace frame is presented.
            window.windowTransitioning = true
            window.opacity = 0
            window.lastLoggedIn = true
            window.applyWindowMode()
            Qt.callLater(function() {
                window.workspaceActive = true
                workspacePage.forceActiveFocus()
                // Give StackLayout one complete event turn to polish and paint
                // Workspace before making the native window visible again.
                Qt.callLater(function() {
                    window.opacity = 1
                    window.windowTransitioning = false
                })
            })
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
