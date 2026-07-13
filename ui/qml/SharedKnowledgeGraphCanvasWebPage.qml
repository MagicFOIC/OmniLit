import QtQuick
import QtQuick.Controls
import QtWebChannel
import QtWebEngine

Item {
    id: root
    // QQuickWebEngineView may briefly keep its pre-resize texture. This
    // component is also clipped independently because it is loaded
    // asynchronously and can receive geometry one frame after its Loader.
    clip: true
    property string recordId: ""
    property bool channelReady: false
    signal fallbackRequested()

    Theme { id: theme }

    Rectangle {
        anchors.fill: parent
        color: theme.canvas
    }

    function fallback(code) {
        desktopWebController.recordDiagnostic("webengine", code || "canvas_fallback")
        root.fallbackRequested()
    }

    function loadCanvas() {
        if (!root.channelReady || !root.recordId)
            return
        var targetUrl = desktopWebController.canvasUrl(root.recordId)
        if (!desktopWebController.available || !targetUrl.toString()) {
            root.fallback("canvas_unavailable")
            return
        }
        webView.url = targetUrl
    }

    onRecordIdChanged: loadCanvas()

    WebChannel {
        id: nativeChannel
    }

    WebEngineView {
        id: webView
        anchors.fill: parent
        backgroundColor: theme.canvas
        url: ""
        webChannel: nativeChannel
        settings.javascriptCanOpenWindows: false
        settings.localContentCanAccessFileUrls: false
        settings.localContentCanAccessRemoteUrls: false
        onNavigationRequested: function(request) {
            if (!desktopWebController.isAllowedNavigation(request.url.toString()))
                request.action = WebEngineNavigationRequest.IgnoreRequest
        }
        onLoadingChanged: function(request) {
            if (request.status === WebEngineView.LoadFailedStatus)
                root.fallback("canvas_load_failed")
        }
        onRenderProcessTerminated: function() { root.fallback("canvas_render_process_terminated") }
    }

    Component.onCompleted: {
        nativeChannel.registerObject("omnilitDesktopBridge", desktopWebController)
        nativeChannel.registerObject("knowledgeGraphController", knowledgeGraphController)
        root.channelReady = true
        root.loadCanvas()
    }
}
