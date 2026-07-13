import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtWebChannel
import QtWebEngine

Item {
    id: root
    property string route: "workspace"
    property bool channelReady: false
    signal fallbackRequested()

    function fallbackToQml(code) {
        desktopWebController.recordDiagnostic("webengine", code || "business_page_fallback")
        root.fallbackRequested()
    }

    function loadRoute() {
        if (!root.channelReady || !root.route)
            return
        var targetUrl = desktopWebController.routeUrl(root.route)
        if (!desktopWebController.available || !targetUrl.toString()) {
            root.fallbackToQml("business_page_unavailable")
            return
        }
        webView.url = targetUrl
    }

    onRouteChanged: loadRoute()

    Component.onCompleted: {
        nativeChannel.registerObject("omnilitDesktopBridge", desktopWebController)
        root.channelReady = true
        root.loadRoute()
    }

    WebChannel {
        id: nativeChannel
    }

    WebEngineView {
        id: webView
        anchors.fill: parent
        url: ""
        webChannel: nativeChannel
        settings.javascriptCanOpenWindows: false
        settings.localContentCanAccessFileUrls: false
        settings.localContentCanAccessRemoteUrls: false
        onNavigationRequested: function(request) {
            var target = request.url.toString()
            if (!desktopWebController.isAllowedNavigation(target)) {
                request.action = WebEngineNavigationRequest.IgnoreRequest
                desktopWebController.openExternalUrl(target)
            }
        }
        onLoadingChanged: function(loadRequest) {
            if (loadRequest.status === WebEngineView.LoadFailedStatus)
                root.fallbackToQml("business_page_load_failed")
        }
        onRenderProcessTerminated: function() { root.fallbackToQml("business_page_render_process_terminated") }
    }
}
