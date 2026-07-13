import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: root
    property string recordId: ""
    property var records: []
    property string graphDisplayStyle: "overview"
    property string searchQuery: ""
    property bool literatureListOpen: true
    signal backRequested()
    signal evidenceRequested(string recordId, int page, var bbox, string elementId)
    Theme { id: theme }

    Connections {
        target: knowledgeGraphController
        function onEvidenceFocusRequested(recordId, page, bbox, elementId) { root.evidenceRequested(recordId, page, bbox, elementId) }
        function onViewRestored(viewport) {
            root.searchQuery = knowledgeGraphController.searchText
            root.graphDisplayStyle = String(viewport.displayStyle || "overview")
            graphView.applyViewState(viewport)
        }
        function onHistoryRestored() { root.searchQuery = knowledgeGraphController.searchText }
    }

    Shortcut { sequence: StandardKey.Undo; enabled: root.visible && knowledgeGraphController.canUndo; onActivated: knowledgeGraphController.undo(graphView.captureViewState()) }
    Shortcut { sequence: StandardKey.Redo; enabled: root.visible && knowledgeGraphController.canRedo; onActivated: knowledgeGraphController.redo(graphView.captureViewState()) }

    ColumnLayout {
        anchors.fill: parent
        spacing: 8
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 62
            radius: theme.radiusMedium
            color: theme.surface
            border.color: theme.border
            RowLayout {
                anchors.fill: parent
                anchors.margins: 10
                spacing: 8
                PillButton { text: "返回对比"; onClicked: root.backRequested() }
                Text {
                    Layout.fillWidth: true
                    text: "文献对比知识图谱 · " + root.records.length + " 篇"
                    color: theme.text
                    font.bold: true
                    font.pixelSize: 18
                    elide: Text.ElideRight
                }
                BusyIndicator { running: knowledgeGraphController.loading; visible: running; Layout.preferredWidth: 26; Layout.preferredHeight: 26 }
                PillButton { text: "撤销"; enabled: knowledgeGraphController.canUndo; onClicked: knowledgeGraphController.undo(graphView.captureViewState()); ToolTip.visible: hovered; ToolTip.text: knowledgeGraphController.historyState.undoAction || "没有可撤销操作" }
                PillButton { text: "重做"; enabled: knowledgeGraphController.canRedo; onClicked: knowledgeGraphController.redo(graphView.captureViewState()); ToolTip.visible: hovered; ToolTip.text: knowledgeGraphController.historyState.redoAction || "没有可重做操作" }
                PillButton { text: "恢复默认"; onClicked: knowledgeGraphController.resetExploration(graphView.captureViewState()) }
                PillButton { text: knowledgeGraphController.loading ? "生成中..." : "重新生成"; enabled: !knowledgeGraphController.loading; onClicked: knowledgeGraphController.regenerateComparisonGraph(root.records) }
                PillButton { text: root.literatureListOpen ? "收起列表" : "文献列表"; onClicked: root.literatureListOpen = !root.literatureListOpen }
                PillButton { text: "对比报告"; onClicked: knowledgeGraphController.exportGraph(root.recordId, "markdown") }
                PillButton { text: "Mermaid"; onClicked: knowledgeGraphController.exportGraph(root.recordId, "mermaid") }
                PillButton { text: "导出图片"; enabled: knowledgeGraphController.nodes.length > 0 && !knowledgeGraphController.replayActive; onClicked: imageExportDialog.openForExport() }
                PillButton { text: "打开目录"; onClicked: knowledgeGraphController.openGraphDirectory(root.recordId) }
            }
        }
        GraphFilterBar {
            Layout.fillWidth: true
            comparisonMode: true
            filterCounts: knowledgeGraphController.filterCounts
            searchText: root.searchQuery
            onFilterRequested: function(mode) { knowledgeGraphController.setFilterMode(mode) }
            onSearchRequested: function(text) { root.searchQuery = text; knowledgeGraphController.search(text) }
        }
        GraphPathPanel {
            Layout.fillWidth: true
            Layout.preferredHeight: implicitHeight
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
        SplitView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            orientation: Qt.Horizontal
            KnowledgeGraphView {
                id: graphView
                SplitView.fillWidth: true
                SplitView.minimumWidth: 420
                nodes: knowledgeGraphController.renderNodes
                edges: knowledgeGraphController.renderEdges
                graphLayout: knowledgeGraphController.renderLayout
                renderStatus: knowledgeGraphController.renderStatus
                fullExportNodes: knowledgeGraphController.imageExportNodes
                fullExportEdges: knowledgeGraphController.imageExportEdges
                fullExportLayout: knowledgeGraphController.layout
                searchQuery: root.searchQuery
                displayStyle: root.graphDisplayStyle
                pathNodeIds: knowledgeGraphController.pathState.nodeIds || []
                pathEdgeIds: knowledgeGraphController.pathState.edgeIds || []
                pathStartId: knowledgeGraphController.pathState.startId || ""
                pathEndId: knowledgeGraphController.pathState.endId || ""
                onNodeRequested: function(nodeId) { knowledgeGraphController.selectNode(nodeId) }
                onEdgeRequested: function(edgeId) { knowledgeGraphController.selectEdge(edgeId) }
                onDisplayStyleRequested: function(displayStyle) { root.graphDisplayStyle = displayStyle }
                onRenderViewportRequested: function(width, height, scale, panX, panY, displayStyle) { knowledgeGraphController.setRenderViewport(width, height, scale, panX, panY, displayStyle) }
            }
            ColumnLayout {
                SplitView.preferredWidth: 560
                SplitView.minimumWidth: 360
                spacing: 8
                ComparisonEvidencePanel {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    records: root.records
                    selectedNode: knowledgeGraphController.selectedNode
                    selectedEdge: knowledgeGraphController.selectedEdge
                    onEvidenceRequested: function(itemId, index) { knowledgeGraphController.focusEvidence(itemId, index) }
                }
                SemanticReviewPanel {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 285
                    cell: knowledgeGraphController.selectedSemanticCell
                    onNodeRequested: function(nodeId) { knowledgeGraphController.selectNode(nodeId) }
                    onReviewRequested: function(recordId, dimension, action, label, note) { knowledgeGraphController.reviewSemanticCell(recordId, dimension, action, label, note) }
                    onClearRequested: function(recordId, dimension) { knowledgeGraphController.clearSemanticReview(recordId, dimension) }
                }
            }
        }
        GraphLiteratureList {
            id: compareLiteratureList
            visible: root.literatureListOpen
            Layout.fillWidth: true
            Layout.preferredHeight: visible ? 210 : 0
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
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 38
            radius: 7
            color: theme.surfaceSoft
            border.color: theme.border
            RowLayout {
                anchors.fill: parent
                anchors.margins: 6
                Text { text: "ORKG 语义比较"; color: theme.text; font.bold: true }
                Text { text: "单元格 " + Number((knowledgeGraphController.semanticComparison.diagnostics || {}).cellCount || 0); color: theme.textMuted }
                Text { text: "自动语义 " + Number((knowledgeGraphController.semanticComparison.diagnostics || {}).automaticItemCount || 0); color: theme.textMuted }
                Text { text: "人工审阅 " + Number((knowledgeGraphController.semanticComparison.diagnostics || {}).reviewedCellCount || 0); color: theme.success }
                Text { text: "待核验冲突 " + Number((knowledgeGraphController.semanticComparison.conflicts || []).length); color: (knowledgeGraphController.semanticComparison.conflicts || []).length ? theme.warning : theme.textMuted }
                Item { Layout.fillWidth: true }
                Text { text: "缺失表示未识别到，不表示论文明确没有"; color: theme.textMuted; font.pixelSize: 10 }
            }
        }
        ComparisonMatrix {
            Layout.fillWidth: true
            Layout.preferredHeight: 320
            comparison: knowledgeGraphController.semanticComparison
            selectedCell: knowledgeGraphController.selectedSemanticCell
            onCellRequested: function(recordId, dimension) { knowledgeGraphController.selectSemanticCell(recordId, dimension) }
            onNodeRequested: function(nodeId) { knowledgeGraphController.selectNode(nodeId) }
        }
        Text { Layout.fillWidth: true; text: knowledgeGraphController.statusText; color: theme.textMuted; elide: Text.ElideRight }
    }

    GraphImageExportDialog {
        id: imageExportDialog
        targetView: graphView
        defaultName: "literature-comparison-knowledge-graph"
    }
}
