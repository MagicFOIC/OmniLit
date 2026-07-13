import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts

Item {
    id: root

    property string recordId: ""
    property string pdfPath: ""
    property string title: ""
    property var record: ({})
    property bool comparisonMode: false
    property var comparisonRecords: []
    property string searchQuery: ""
    property string graphDisplayStyle: "overview"
    readonly property var nodes: knowledgeGraphController.renderNodes || []
    readonly property var edges: knowledgeGraphController.renderEdges || []
    property bool replayRunning: false
    property int replayInterval: 1500
    property string selectedSavedViewId: ""
    property bool literatureListOpen: true
    readonly property bool topicGraphMode: !!((knowledgeGraphController.graph.metadata || {}).topic_graph)
                                           || !!((knowledgeGraphController.graph.metadata || {}).evolution_graph)
                                           || !!((knowledgeGraphController.graph.metadata || {}).network_analysis_graph)
                                           || !!((knowledgeGraphController.graph.metadata || {}).research_network_graph)
    readonly property bool compactLayout: width < 1380
    readonly property bool narrowLayout: width < 980

    signal backRequested()
    signal evidenceRequested(string recordId, int page, var bbox, string elementId)

    Theme { id: theme }
    LayoutMetrics { id: metrics; viewportWidth: root.width; viewportHeight: root.height }

    Timer {
        id: replayTimer
        interval: root.replayInterval
        repeat: true
        running: root.replayRunning
        onTriggered: {
            if (!knowledgeGraphController.advanceReplay())
                root.replayRunning = false
        }
    }

    Shortcut {
        sequence: StandardKey.Undo
        enabled: root.visible && knowledgeGraphController.canUndo
        onActivated: knowledgeGraphController.undo(graphView.captureViewState())
    }
    Shortcut {
        sequence: StandardKey.Redo
        enabled: root.visible && knowledgeGraphController.canRedo
        onActivated: knowledgeGraphController.redo(graphView.captureViewState())
    }

    Connections {
        target: knowledgeGraphController
        enabled: root.visible
        function onEvidenceFocusRequested(recordId, page, bbox, elementId) {
            root.evidenceRequested(recordId, page, bbox, elementId)
        }
        function onViewRestored(viewport) {
            root.searchQuery = knowledgeGraphController.searchText
            root.graphDisplayStyle = String(viewport.displayStyle || "overview")
            graphView.applyViewState(viewport)
        }
        function onHistoryRestored() {
            root.searchQuery = knowledgeGraphController.searchText
        }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 10

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 64
            radius: theme.radiusMedium
            color: theme.surface
            border.color: theme.border

            RowLayout {
                anchors.fill: parent
                anchors.margins: 10
                spacing: 8

                PillButton { text: "返回"; onClicked: root.backRequested() }
                Text {
                    Layout.fillWidth: true
                    text: "知识图谱 · " + (root.title || "当前文献")
                    color: theme.text
                    font.weight: Font.Bold
                    font.pixelSize: 18
                    elide: Text.ElideRight
                }
                Label {
                    visible: !root.compactLayout
                    text: knowledgeGraphController.cacheState === "fresh" ? "缓存最新" : knowledgeGraphController.cacheState === "refreshing" ? "后台更新" : "构建中"
                    color: knowledgeGraphController.cacheState === "fresh" ? theme.success : theme.warning
                    background: Rectangle { color: theme.surfaceSoft; radius: 7 }
                    padding: 5
                }
                Label {
                    visible: knowledgeGraphController.explorationActive && !root.compactLayout
                    text: "探索 " + Number(knowledgeGraphController.explorationStats.visibleNodes || 0)
                          + " / " + Number(knowledgeGraphController.explorationStats.totalNodes || 0) + " 节点"
                    color: theme.accent
                    background: Rectangle { color: theme.accentSofter; radius: 7 }
                    padding: 5
                }
                Label {
                    visible: !root.compactLayout && Number(knowledgeGraphController.qualitySummary.evidence_coverage || 0) > 0
                    text: "证据覆盖 " + Math.round(Number(knowledgeGraphController.qualitySummary.evidence_coverage || 0) * 100) + "%"
                    color: theme.textMuted
                    background: Rectangle { color: theme.surfaceSoft; radius: 7 }
                    padding: 5
                }
                BusyIndicator {
                    running: knowledgeGraphController.loading
                    visible: running
                    Layout.preferredWidth: 28
                    Layout.preferredHeight: 28
                }
                PillButton {
                    text: root.replayRunning ? "暂停构建" : (knowledgeGraphController.replayComplete ? "重新演示" : (knowledgeGraphController.replayActive ? "继续构建" : "演示构建"))
                    visible: !root.topicGraphMode
                    enabled: !knowledgeGraphController.loading && root.nodes.length > 0
                    onClicked: {
                        if (!knowledgeGraphController.replayActive || knowledgeGraphController.replayComplete)
                            knowledgeGraphController.startReplay()
                        root.replayRunning = !root.replayRunning
                    }
                }
                PillButton {
                    text: "下一步"
                    visible: !root.topicGraphMode
                    enabled: knowledgeGraphController.replayActive && !knowledgeGraphController.replayComplete && !root.replayRunning
                    onClicked: knowledgeGraphController.advanceReplay()
                }
                PillButton {
                    text: "撤销"
                    enabled: knowledgeGraphController.canUndo
                    onClicked: knowledgeGraphController.undo(graphView.captureViewState())
                    ToolTip.visible: hovered
                    ToolTip.text: knowledgeGraphController.historyState.undoAction || "没有可撤销操作"
                }
                PillButton {
                    text: "重做"
                    enabled: knowledgeGraphController.canRedo
                    onClicked: knowledgeGraphController.redo(graphView.captureViewState())
                    ToolTip.visible: hovered
                    ToolTip.text: knowledgeGraphController.historyState.redoAction || "没有可重做操作"
                }
                Label {
                    visible: !root.compactLayout && (knowledgeGraphController.canUndo || knowledgeGraphController.canRedo)
                    text: "历史 " + Number(knowledgeGraphController.historyState.undoDepth || 0)
                          + " / " + Number(knowledgeGraphController.historyState.redoDepth || 0)
                    color: theme.textMuted
                    background: Rectangle { color: theme.surfaceSoft; radius: 7 }
                    padding: 4
                }
                PillButton {
                    text: "恢复默认"
                    visible: knowledgeGraphController.explorationActive && !root.narrowLayout
                    enabled: !root.replayRunning
                    onClicked: knowledgeGraphController.resetExploration(graphView.captureViewState())
                }
                PillButton {
                    text: root.literatureListOpen ? "收起列表" : "文献列表"
                    onClicked: root.literatureListOpen = !root.literatureListOpen
                }
                PillButton {
                    text: "保存视图"
                    visible: !root.narrowLayout
                    enabled: root.nodes.length > 0
                    onClicked: {
                        viewNameField.text = "研究视图 " + (knowledgeGraphController.savedViews.length + 1)
                        saveViewPopup.open()
                        viewNameField.forceActiveFocus()
                    }
                }
                StyledComboBox {
                    visible: !root.compactLayout && knowledgeGraphController.savedViews.length > 0
                    Layout.preferredWidth: visible ? 156 : 0
                    model: ["恢复视图…"].concat(knowledgeGraphController.savedViews.map(function(item) { return item.name }))
                    currentIndex: 0
                    onActivated: function(index) {
                        if (index <= 0) return
                        var item = knowledgeGraphController.savedViews[index - 1]
                        root.selectedSavedViewId = String(item.id || "")
                        knowledgeGraphController.restoreView(root.selectedSavedViewId)
                        currentIndex = 0
                    }
                }
                PillButton {
                    text: "删除视图"
                    visible: !root.compactLayout && !!root.selectedSavedViewId
                    onClicked: {
                        if (knowledgeGraphController.deleteView(root.selectedSavedViewId))
                            root.selectedSavedViewId = ""
                    }
                }
                PillButton {
                    text: knowledgeGraphController.loading ? "生成中..." : "重新生成"
                    visible: !root.narrowLayout && !root.topicGraphMode
                    enabled: !knowledgeGraphController.loading
                    onClicked: {
                        if (root.comparisonMode)
                            knowledgeGraphController.regenerateComparisonGraph(root.comparisonRecords)
                        else
                            knowledgeGraphController.regenerateGraph(root.recordId, root.record, root.pdfPath)
                    }
                }
                PillButton {
                    text: "导出 JSON"
                    visible: !root.compactLayout
                    enabled: root.nodes.length > 0
                    onClicked: knowledgeGraphController.exportGraphJson(root.recordId)
                }
                PillButton {
                    text: "导出 Markdown"
                    visible: !root.compactLayout
                    enabled: root.nodes.length > 0
                    onClicked: knowledgeGraphController.exportGraphMarkdown(root.recordId)
                }
                PillButton {
                    text: "导出图片"
                    visible: !root.compactLayout
                    enabled: root.nodes.length > 0 && !root.replayRunning
                             && (!knowledgeGraphController.replayActive || knowledgeGraphController.replayComplete)
                    onClicked: imageExportDialog.openForExport()
                }
                PillButton {
                    text: "导出 Mermaid"
                    visible: !root.compactLayout
                    enabled: root.nodes.length > 0
                    onClicked: knowledgeGraphController.exportGraph(root.recordId, "mermaid")
                }
                PillButton {
                    text: "生成分享包"
                    visible: !root.compactLayout
                    enabled: root.nodes.length > 0 && !root.replayRunning
                    onClicked: knowledgeGraphController.exportSharePackage(
                                   root.title ? root.title + " · 研究视图" : "研究视图",
                                   graphView.captureViewState())
                    ToolTip.visible: hovered
                    ToolTip.text: "导出包含图谱、筛选、探索范围和视口的可恢复文件"
                }
                PillButton {
                    text: "导入分享包"
                    visible: !root.compactLayout
                    onClicked: shareImportDialog.open()
                }
                PillButton {
                    text: "打开导出目录"
                    visible: !root.compactLayout
                    enabled: root.nodes.length > 0
                    onClicked: knowledgeGraphController.openGraphDirectory(root.recordId)
                }
            }
        }

        GraphFilterBar {
            Layout.fillWidth: true
            Layout.minimumHeight: implicitHeight
            comparisonMode: root.comparisonMode
            filterCounts: knowledgeGraphController.filterCounts
            searchText: root.searchQuery
            facetOptions: knowledgeGraphController.facetOptions
            facetFilters: knowledgeGraphController.facetFilters
            onFilterRequested: function(mode) { knowledgeGraphController.setFilterMode(mode) }
            onSearchRequested: function(text) { root.searchQuery = text; knowledgeGraphController.search(text) }
            onFacetRequested: function(facet, value) { knowledgeGraphController.setFacetFilter(facet, value) }
            onFacetsCleared: knowledgeGraphController.clearFacetFilters()
        }

        GraphPathPanel {
            Layout.fillWidth: true
            Layout.preferredHeight: implicitHeight
            Layout.minimumHeight: implicitHeight
            selectedNode: knowledgeGraphController.selectedNode
            pathState: knowledgeGraphController.pathState
            relationTypes: knowledgeGraphController.pathRelationTypes
            onStartRequested: function(nodeId) { knowledgeGraphController.setPathStart(nodeId) }
            onEndRequested: function(nodeId) { knowledgeGraphController.setPathEnd(nodeId) }
            onDirectedRequested: function(directed) { knowledgeGraphController.setPathDirected(directed) }
            onRelationFilterRequested: function(relationType) { knowledgeGraphController.setPathRelationFilter(relationType) }
            onComputeRequested: knowledgeGraphController.computeShortestPath()
            onClearRequested: knowledgeGraphController.clearPath()
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 10

            GraphLiteratureList {
                id: literatureList
                visible: root.literatureListOpen
                compactMode: true
                Layout.preferredWidth: visible ? Math.min(370, Math.max(280, root.width * 0.24)) : 0
                Layout.minimumWidth: visible ? 270 : 0
                Layout.maximumWidth: visible ? 390 : 0
                Layout.fillHeight: true
                rows: knowledgeGraphController.literatureRows
                selectedNodeId: String(knowledgeGraphController.selectedNode.id || "")
                hoveredNodeId: knowledgeGraphController.hoveredNodeId
                sortKey: knowledgeGraphController.literatureSortKey
                sortDescending: knowledgeGraphController.literatureSortDescending
                onNodeRequested: function(nodeId) {
                    if (knowledgeGraphController.selectLiteratureNode(nodeId))
                        graphView.focusNode(nodeId)
                }
                onNodeHovered: function(nodeId) { knowledgeGraphController.setHoveredNode(nodeId) }
                onSortRequested: function(sortKey, descending) { knowledgeGraphController.setLiteratureSort(sortKey, descending) }
            }

            GraphReplayDocument {
                id: graphDocument
                visible: !root.comparisonMode && knowledgeGraphController.replayActive
                Layout.preferredWidth: visible ? Math.max(root.narrowLayout ? 285 : 330, root.width * (root.narrowLayout ? 0.38 : 0.43)) : 0
                Layout.minimumWidth: visible ? (root.narrowLayout ? 270 : 310) : 0
                Layout.fillHeight: true
                recordId: root.recordId
                pdfPath: root.pdfPath
                replayEvent: knowledgeGraphController.replayEvent
                replayIndex: knowledgeGraphController.replayIndex
            }

            HybridKnowledgeGraphView {
                id: graphView
                Layout.fillWidth: true
                Layout.fillHeight: true
                recordId: root.recordId
                reactEnabled: !fullscreenGraph.visible
                nodes: root.nodes
                edges: root.edges
                graphLayout: knowledgeGraphController.renderLayout
                renderStatus: knowledgeGraphController.renderStatus
                fullExportNodes: knowledgeGraphController.imageExportNodes
                fullExportEdges: knowledgeGraphController.imageExportEdges
                fullExportLayout: knowledgeGraphController.layout
                searchQuery: root.searchQuery
                displayStyle: root.graphDisplayStyle
                settingsOpen: false
                pathNodeIds: knowledgeGraphController.pathState.nodeIds || []
                pathEdgeIds: knowledgeGraphController.pathState.edgeIds || []
                pathStartId: knowledgeGraphController.pathState.startId || ""
                pathEndId: knowledgeGraphController.pathState.endId || ""
                onNodeRequested: function(nodeId) { knowledgeGraphController.selectNode(nodeId) }
                onEdgeRequested: function(edgeId) { knowledgeGraphController.selectEdge(edgeId) }
                onExpandRequested: function(nodeId, relationMode) { knowledgeGraphController.expandNeighbors(nodeId, relationMode, 12) }
                onDisplayStyleRequested: function(displayStyle) { root.graphDisplayStyle = displayStyle }
                onRenderViewportRequested: function(width, height, scale, panX, panY, displayStyle) { knowledgeGraphController.setRenderViewport(width, height, scale, panX, panY, displayStyle) }
                onFullscreenRequested: fullscreenGraph.open()
            }

            KnowledgeGraphPanel {
                visible: !root.compactLayout
                Layout.preferredWidth: visible ? 300 : 0
                Layout.minimumWidth: 0
                Layout.fillHeight: true
                selectedNode: knowledgeGraphController.selectedNode
                selectedEdge: knowledgeGraphController.selectedEdge
                explorationActive: knowledgeGraphController.explorationActive
                explorationSummary: knowledgeGraphController.explorationSummary
                explorationStatus: knowledgeGraphController.explorationStatus
                onEvidenceRequested: function(itemId, index) { knowledgeGraphController.focusEvidence(itemId, index) }
                onExpandRequested: function(nodeId, relationMode) { knowledgeGraphController.expandNeighbors(nodeId, relationMode, 12) }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 42
            radius: theme.radiusMedium
            color: theme.surface
            border.color: theme.border
            RowLayout {
                anchors.fill: parent
                anchors.margins: 8
                spacing: 14
                Text { text: "质量摘要"; color: theme.text; font.bold: true }
                Text { text: "节点证据 " + Math.round(Number(knowledgeGraphController.qualitySummary.evidence_coverage || 0) * 100) + "%"; color: theme.textMuted }
                Text { visible: !root.narrowLayout; text: "关系证据 " + Math.round(Number(knowledgeGraphController.qualitySummary.edge_evidence_coverage || 0) * 100) + "%"; color: theme.textMuted }
                Text { visible: !root.compactLayout; text: "平均置信度 " + Math.round(Number(knowledgeGraphController.qualitySummary.average_confidence || 0) * 100) + "%"; color: theme.textMuted }
                Text { text: "待审核 " + Number(knowledgeGraphController.qualitySummary.needs_review_count || 0); color: Number(knowledgeGraphController.qualitySummary.needs_review_count || 0) > 0 ? theme.warning : theme.success }
                Text { visible: !root.compactLayout; text: "关系待审核 " + Number(knowledgeGraphController.qualitySummary.relation_needs_review_count || 0); color: Number(knowledgeGraphController.qualitySummary.relation_needs_review_count || 0) > 0 ? theme.warning : theme.success }
                Item { Layout.fillWidth: true }
                Text { visible: !root.narrowLayout; text: "校验问题 " + Number(knowledgeGraphController.qualitySummary.validation_issue_count || 0); color: Number(knowledgeGraphController.qualitySummary.validation_issue_count || 0) > 0 ? theme.error : theme.success }
            }
        }

        Text {
            Layout.fillWidth: true
            text: knowledgeGraphController.statusText
            color: theme.textMuted
            elide: Text.ElideRight
        }
    }

    GraphImageExportDialog {
        id: imageExportDialog
        targetView: graphView
        defaultName: root.title ? root.title + "-knowledge-graph" : "knowledge-graph"
    }

    FileDialog {
        id: shareImportDialog
        title: "导入 OmniLit 知识图谱分享包"
        nameFilters: ["OmniLit 图谱分享包 (*.omnilit-graph.json)", "JSON 文件 (*.json)"]
        fileMode: FileDialog.OpenFile
        onAccepted: knowledgeGraphController.importSharePackage(selectedFile)
    }

    Item {
        id: extractionFlightLayer
        anchors.fill: parent
        z: 200
        visible: knowledgeGraphController.replayActive && flightAnimation.running
        property real progress: 0
        property var nodeIds: []
        property point sourcePoint: Qt.point(0, 0)

        Canvas {
            id: flightCanvas
            anchors.fill: parent
            onPaint: {
                var ctx = getContext("2d")
                ctx.reset()
                if (!extractionFlightLayer.nodeIds.length) return
                for (var i = 0; i < extractionFlightLayer.nodeIds.length; ++i) {
                    var localT = Math.max(0, Math.min(1, extractionFlightLayer.progress * 1.25 - i * 0.12))
                    var source = extractionFlightLayer.sourcePoint
                    var target = graphView.nodePointIn(extractionFlightLayer.nodeIds[i], extractionFlightLayer)
                    var bend = Math.max(80, Math.abs(target.x - source.x) * 0.34)
                    var c1 = Qt.point(source.x + bend, source.y - 90 - i * 18)
                    var c2 = Qt.point(target.x - bend * 0.55, target.y - 55 + i * 12)
                    ctx.globalAlpha = 0.24
                    ctx.strokeStyle = theme.accent
                    ctx.lineWidth = 1.5
                    ctx.beginPath()
                    ctx.moveTo(source.x, source.y)
                    ctx.bezierCurveTo(c1.x, c1.y, c2.x, c2.y, target.x, target.y)
                    ctx.stroke()
                    var u = 1 - localT
                    var x = u*u*u*source.x + 3*u*u*localT*c1.x + 3*u*localT*localT*c2.x + localT*localT*localT*target.x
                    var y = u*u*u*source.y + 3*u*u*localT*c1.y + 3*u*localT*localT*c2.y + localT*localT*localT*target.y
                    var glow = ctx.createRadialGradient(x, y, 1, x, y, 13)
                    glow.addColorStop(0, "rgba(255,255,255,1)")
                    glow.addColorStop(0.25, theme.accent)
                    glow.addColorStop(1, "rgba(37,99,235,0)")
                    ctx.globalAlpha = localT >= 1 ? 0 : 1
                    ctx.fillStyle = glow
                    ctx.beginPath()
                    ctx.arc(x, y, 13, 0, Math.PI * 2)
                    ctx.fill()
                }
                ctx.globalAlpha = 1
            }
        }

        NumberAnimation {
            id: flightAnimation
            target: extractionFlightLayer
            property: "progress"
            from: 0; to: 1
            duration: 1050
            easing.type: Easing.InOutCubic
            onStarted: flightCanvas.requestPaint()
            onStopped: flightCanvas.requestPaint()
        }
        onProgressChanged: flightCanvas.requestPaint()
    }

    Connections {
        target: knowledgeGraphController
        property int observedReplayIndex: -2
        function onChanged() {
            if (observedReplayIndex === knowledgeGraphController.replayIndex) return
            observedReplayIndex = knowledgeGraphController.replayIndex
            if (!knowledgeGraphController.replayActive || !graphDocument.visible) return
            Qt.callLater(function() {
                extractionFlightLayer.nodeIds = (knowledgeGraphController.replayEvent.nodeIds || []).slice(0)
                extractionFlightLayer.sourcePoint = graphDocument.evidencePointIn(extractionFlightLayer)
                extractionFlightLayer.progress = 0
                flightAnimation.restart()
            })
        }
    }

    Popup {
        id: saveViewPopup
        parent: Overlay.overlay
        anchors.centerIn: parent
        modal: true
        focus: true
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        padding: 16
        background: Rectangle { color: theme.surfaceElevated; border.color: theme.border; radius: theme.radiusMedium }

        contentItem: ColumnLayout {
            spacing: 12
            Text { text: "保存研究视图"; color: theme.text; font.bold: true; font.pixelSize: 17 }
            Text { text: "同名视图会被当前状态覆盖。"; color: theme.textMuted }
            StyledTextField {
                id: viewNameField
                Layout.preferredWidth: 320
                placeholderText: "视图名称"
                selectByMouse: true
                onAccepted: saveViewButton.clicked()
            }
            RowLayout {
                Layout.alignment: Qt.AlignRight
                PillButton { text: "取消"; onClicked: saveViewPopup.close() }
                PillButton {
                    id: saveViewButton
                    text: "保存"
                    primary: true
                    enabled: viewNameField.text.trim().length > 0
                    onClicked: {
                        var viewId = knowledgeGraphController.saveView(viewNameField.text, graphView.captureViewState())
                        if (viewId) {
                            root.selectedSavedViewId = viewId
                            saveViewPopup.close()
                        }
                    }
                }
            }
        }
    }

    Popup {
        id: fullscreenGraph
        parent: Overlay.overlay
        x: 0
        y: 0
        width: parent ? parent.width : root.width
        height: parent ? parent.height : root.height
        modal: true
        focus: true
        closePolicy: Popup.CloseOnEscape
        padding: 12
        background: Rectangle { color: theme.canvas; border.color: theme.border }
        onOpened: fullscreenGraphView.syncRenderViewport()
        onClosed: graphView.syncRenderViewport()

        contentItem: ColumnLayout {
            spacing: 10
            RowLayout {
                Layout.fillWidth: true
                Text {
                    Layout.fillWidth: true
                    text: "全屏图谱 · " + (root.title || "当前文献")
                    color: theme.text
                    font.bold: true
                    font.pixelSize: 19
                    elide: Text.ElideRight
                }
                PillButton { text: "关闭"; onClicked: fullscreenGraph.close() }
            }
            RowLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 10
                HybridKnowledgeGraphView {
                    id: fullscreenGraphView
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    recordId: root.recordId
                    reactEnabled: fullscreenGraph.visible
                    nodes: root.nodes
                    edges: root.edges
                    graphLayout: knowledgeGraphController.renderLayout
                    renderStatus: knowledgeGraphController.renderStatus
                    fullExportNodes: knowledgeGraphController.imageExportNodes
                    fullExportEdges: knowledgeGraphController.imageExportEdges
                    fullExportLayout: knowledgeGraphController.layout
                    searchQuery: root.searchQuery
                    showFullscreenAction: false
                    displayStyle: root.graphDisplayStyle
                    pathNodeIds: knowledgeGraphController.pathState.nodeIds || []
                    pathEdgeIds: knowledgeGraphController.pathState.edgeIds || []
                    pathStartId: knowledgeGraphController.pathState.startId || ""
                    pathEndId: knowledgeGraphController.pathState.endId || ""
                    onNodeRequested: function(nodeId) { knowledgeGraphController.selectNode(nodeId) }
                    onEdgeRequested: function(edgeId) { knowledgeGraphController.selectEdge(edgeId) }
                    onExpandRequested: function(nodeId, relationMode) { knowledgeGraphController.expandNeighbors(nodeId, relationMode, 12) }
                    onDisplayStyleRequested: function(displayStyle) { root.graphDisplayStyle = displayStyle }
                    onRenderViewportRequested: function(width, height, scale, panX, panY, displayStyle) { knowledgeGraphController.setRenderViewport(width, height, scale, panX, panY, displayStyle) }
                }
                KnowledgeGraphPanel {
                    Layout.preferredWidth: Math.min(380, fullscreenGraph.width * 0.30)
                    Layout.fillHeight: true
                    selectedNode: knowledgeGraphController.selectedNode
                    selectedEdge: knowledgeGraphController.selectedEdge
                    explorationActive: knowledgeGraphController.explorationActive
                    explorationSummary: knowledgeGraphController.explorationSummary
                    explorationStatus: knowledgeGraphController.explorationStatus
                    onEvidenceRequested: function(itemId, index) { knowledgeGraphController.focusEvidence(itemId, index) }
                    onExpandRequested: function(nodeId, relationMode) { knowledgeGraphController.expandNeighbors(nodeId, relationMode, 12) }
                }
            }
            Text {
                Layout.fillWidth: true
                text: "节点证据 " + Math.round(Number(knowledgeGraphController.qualitySummary.evidence_coverage || 0) * 100) + "%  ·  关系证据 " + Math.round(Number(knowledgeGraphController.qualitySummary.edge_evidence_coverage || 0) * 100) + "%  ·  待审核 " + Number(knowledgeGraphController.qualitySummary.needs_review_count || 0)
                color: theme.textMuted
            }
        }
    }
}
