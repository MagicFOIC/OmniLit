import QtQuick
import QtQuick.Controls

Item {
    id: root
    // WebEngine can retain a texture at its previous size while a Qt Quick
    // layout is being resized. Keep that transient frame inside the graph
    // cell so it cannot cover the panel, footer, or newly exposed window area.
    clip: true
    property string recordId: ""
    property var nodes: []
    property var edges: []
    property var graphLayout: ({})
    property var renderStatus: ({})
    property var fullExportNodes: []
    property var fullExportEdges: []
    property var fullExportLayout: ({})
    property string searchQuery: ""
    property string displayStyle: "overview"
    property bool settingsOpen: false
    property var pathNodeIds: []
    property var pathEdgeIds: []
    property string pathStartId: ""
    property string pathEndId: ""
    property bool showFullscreenAction: true
    property bool reactEnabled: true
    readonly property bool reactActive: root.reactEnabled && desktopWebController.enabled && root.recordId !== ""

    signal nodeRequested(string nodeId)
    signal edgeRequested(string edgeId)
    signal expandRequested(string nodeId, string relationMode)
    signal displayStyleRequested(string displayStyle)
    signal renderViewportRequested(real width, real height, real scale, real panX, real panY, string displayStyle)
    signal fullscreenRequested()
    signal imageExportFinished(string path, bool success, string message)

    Theme { id: theme }

    Rectangle {
        anchors.fill: parent
        color: theme.canvas
    }

    function captureViewState() { return qmlView.captureViewState() }
    function applyViewState(viewport) { qmlView.applyViewState(viewport) }
    function focusNode(nodeId) { qmlView.focusNode(nodeId) }
    function syncRenderViewport() { qmlView.syncRenderViewport() }
    function nodePointIn(nodeId, targetItem) { return qmlView.nodePointIn(nodeId, targetItem) }
    function exportPng(path, scale, fullGraph, transparent) { return qmlView.exportPng(path, scale, fullGraph, transparent) }

    KnowledgeGraphView {
        id: qmlView
        anchors.fill: parent
        opacity: root.reactActive ? 0 : 1
        nodes: root.nodes
        edges: root.edges
        graphLayout: root.graphLayout
        renderStatus: root.renderStatus
        fullExportNodes: root.fullExportNodes
        fullExportEdges: root.fullExportEdges
        fullExportLayout: root.fullExportLayout
        searchQuery: root.searchQuery
        displayStyle: root.displayStyle
        settingsOpen: root.settingsOpen
        pathNodeIds: root.pathNodeIds
        pathEdgeIds: root.pathEdgeIds
        pathStartId: root.pathStartId
        pathEndId: root.pathEndId
        showFullscreenAction: root.showFullscreenAction
        onNodeRequested: function(nodeId) { root.nodeRequested(nodeId) }
        onEdgeRequested: function(edgeId) { root.edgeRequested(edgeId) }
        onExpandRequested: function(nodeId, relationMode) { root.expandRequested(nodeId, relationMode) }
        onDisplayStyleRequested: function(style) { root.displayStyleRequested(style) }
        onRenderViewportRequested: function(width, height, scale, panX, panY, style) { root.renderViewportRequested(width, height, scale, panX, panY, style) }
        onFullscreenRequested: root.fullscreenRequested()
        onImageExportFinished: function(path, success, message) { root.imageExportFinished(path, success, message) }
    }

    Loader {
        id: webCanvasLoader
        anchors.fill: parent
        clip: true
        active: root.reactActive
        asynchronous: true
        source: active ? "SharedKnowledgeGraphCanvasWebPage.qml" : ""
        onLoaded: item.recordId = Qt.binding(function() { return root.recordId })
        onStatusChanged: {
            if (status === Loader.Error)
                desktopWebController.fallbackToQml()
        }
    }

    Connections {
        target: webCanvasLoader.item
        enabled: target !== null
        ignoreUnknownSignals: true
        function onFallbackRequested() { desktopWebController.fallbackToQml() }
    }

    Button {
        visible: root.reactActive && root.showFullscreenAction
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.margins: 12
        text: "全屏"
        onClicked: root.fullscreenRequested()
    }
}
