import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtWebChannel
import QtWebEngine

Item {
    id: root
    property string recordId: ""
    property string title: "知识图谱"
    property bool channelReady: false
    signal backRequested()
    signal fallbackRequested()

    function fallbackToQml(code) {
        desktopWebController.recordDiagnostic("webengine", code || "fallback_to_qml")
        root.fallbackRequested()
    }

    function loadGraph() {
        if (!root.channelReady || !root.recordId)
            return
        var targetUrl = desktopWebController.graphUrl(root.recordId)
        if (!desktopWebController.available || !targetUrl.toString()) {
            root.fallbackToQml()
            return
        }
        webView.url = targetUrl
    }

    onRecordIdChanged: loadGraph()

    Component.onCompleted: {
        nativeChannel.registerObject("omnilitDesktopBridge", desktopWebController)
        root.channelReady = true
        root.loadGraph()
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
                root.fallbackToQml("web_load_failed")
        }
        onRenderProcessTerminated: function() { root.fallbackToQml("render_process_terminated") }
    }

    Button {
        anchors.left: parent.left
        anchors.top: parent.top
        anchors.margins: 14
        z: 3
        text: "返回文献库"
        onClicked: root.backRequested()
    }

    Rectangle {
        id: failurePanel
        anchors.centerIn: parent
        width: Math.min(520, parent.width - 48)
        implicitHeight: failureLayout.implicitHeight + 40
        visible: !desktopWebController.available || !webView.url.toString()
        color: "#ffffff"
        border.color: "#cbd5e1"
        radius: 16
        z: 4
        ColumnLayout {
            id: failureLayout
            anchors.fill: parent
            anchors.margins: 20
            spacing: 10
            Label { text: "共享 Web 图谱暂不可用"; font.pixelSize: 18; font.bold: true }
            Label { Layout.fillWidth: true; text: desktopWebController.detail; wrapMode: Text.WordWrap }
            Button {
                text: "使用稳定 QML 图谱"
                onClicked: root.fallbackToQml()
            }
        }
    }
}
