import QtQuick
import QtQuick.Controls

Rectangle {
    id: root

    property var nodes: []
    property var edges: []
    property var graphLayout: knowledgeGraphController.renderLayout || ({})
    property var fullExportLayout: knowledgeGraphController.layout || ({})
    property var renderStatus: knowledgeGraphController.renderStatus || ({})
    property var adjacency: knowledgeGraphController.graph.adjacency || ({})
    property string searchQuery: ""
    property string displayStyle: "overview"
    property int focusDepth: 0
    property bool reviewMode: false
    property bool showFullscreenAction: true
    property real graphScale: 1.0
    property real panX: 0
    property real panY: 0
    property string hoveredNodeId: ""
    readonly property string effectiveHoveredNodeId: root.hoveredNodeId || String(knowledgeGraphController.hoveredNodeId || "")
    property string hoveredEdgeId: ""
    property int layoutRevision: 0

    property bool settingsOpen: false
    property bool showArrows: false
    property bool showLabels: false
    property bool dimUnrelated: true
    property real textFadeThreshold: 1.15
    property real nodeSizeScale: 1.0
    property real linkThickness: 1.0
    property bool animateLayout: false
    property var fullExportNodes: []
    property var fullExportEdges: []
    property bool exportMode: false
    property bool exportUseFullGraph: false
    property bool exportTransparent: false
    readonly property var activeNodes: root.exportUseFullGraph ? root.fullExportNodes : root.nodes
    readonly property var activeEdges: root.exportUseFullGraph ? root.fullExportEdges : root.edges
    readonly property var activeGraphLayout: root.exportUseFullGraph ? root.fullExportLayout : root.graphLayout
    property var pathNodeIds: []
    property var pathEdgeIds: []
    property string pathStartId: ""
    property string pathEndId: ""
    readonly property var pathNodeSet: root.idSet(root.pathNodeIds)
    readonly property var pathEdgeSet: root.idSet(root.pathEdgeIds)

    readonly property color graphBackground: theme.canvas
    readonly property color graphEdge: theme.mix(theme.borderStrong, theme.canvas, theme.dark ? 0.72 : 0.58)
    readonly property color graphEdgeActive: theme.accent
    readonly property color graphText: theme.text
    readonly property color graphTextMuted: theme.textMuted
    readonly property real relationLabelThreshold: 1.35
    readonly property var styleValues: ["overview", "academic", "radial", "focus"]
    readonly property var displayNodes: root.visibleNodesForRevision(root.layoutRevision)
    readonly property var displayEdges: root.visibleEdgesForRevision(root.layoutRevision)
    readonly property var nodeMap: root.buildNodeMap(root.displayNodes)

    signal nodeRequested(string nodeId)
    signal edgeRequested(string edgeId)
    signal expandRequested(string nodeId, string relationMode)
    signal fullscreenRequested()
    signal displayStyleRequested(string displayStyle)
    signal imageExportFinished(string path, bool success, string message)
    signal renderViewportRequested(real width, real height, real scale, real panX, real panY, string displayStyle)

    Theme { id: theme }
    I18n { id: i18n }
    radius: theme.radiusMedium
    color: root.exportMode && root.exportTransparent ? "transparent" : root.graphBackground
    border.color: root.exportMode && root.exportTransparent ? "transparent" : theme.border
    clip: true

    Connections {
        target: knowledgeGraphController
        function onChanged() { root.refreshGraphLayout() }
    }

    Timer {
        id: renderViewportTimer
        interval: 80
        repeat: false
        onTriggered: {
            if (!root.exportMode && root.visible && root.width > 0 && root.height > 0)
                root.renderViewportRequested(root.width, root.height, root.graphScale, root.panX, root.panY, root.displayStyle)
        }
    }

    Canvas {
        id: backgroundCanvas
        z: 0
        anchors.fill: parent
        onPaint: {
            var ctx = getContext("2d")
            ctx.reset()
            ctx.clearRect(0, 0, width, height)
            if (root.exportMode && root.exportTransparent)
                return
            ctx.fillStyle = root.graphBackground
            ctx.fillRect(0, 0, width, height)

            var highlight = ctx.createRadialGradient(width * 0.45, height * 0.32, 0, width * 0.45, height * 0.32, Math.max(width, height) * 0.72)
            highlight.addColorStop(0, theme.dark ? "rgba(96, 165, 250, 0.13)" : "rgba(37, 99, 235, 0.08)")
            highlight.addColorStop(0.52, theme.dark ? "rgba(96, 165, 250, 0.035)" : "rgba(37, 99, 235, 0.025)")
            highlight.addColorStop(1, "rgba(0, 0, 0, 0)")
            ctx.fillStyle = highlight
            ctx.fillRect(0, 0, width, height)

            ctx.strokeStyle = theme.dark ? "rgba(148, 163, 184, 0.08)" : "rgba(71, 85, 105, 0.075)"
            ctx.lineWidth = 1
            var step = 28
            var offsetX = ((root.panX % step) + step) % step
            var offsetY = ((root.panY % step) + step) % step
            ctx.beginPath()
            for (var x = offsetX; x < width; x += step) {
                ctx.moveTo(x, 0)
                ctx.lineTo(x, height)
            }
            for (var y = offsetY; y < height; y += step) {
                ctx.moveTo(0, y)
                ctx.lineTo(width, y)
            }
            ctx.stroke()
        }
    }

    Item {
        id: viewport
        z: 1
        anchors.fill: parent
        transform: [
            Translate { x: root.panX; y: root.panY },
            Scale {
                origin.x: viewport.width / 2
                origin.y: viewport.height / 2
                xScale: root.graphScale
                yScale: root.graphScale
            }
        ]

        Canvas {
            id: edgeCanvas
            anchors.fill: parent
            onPaint: {
                var ctx = getContext("2d")
                ctx.reset()
                var selectedNodeId = String(knowledgeGraphController.selectedNode.id || "")
                var selectedEdgeId = String(knowledgeGraphController.selectedEdge.id || "")
                for (var i = 0; i < root.displayEdges.length; ++i) {
                    var edge = root.displayEdges[i]
                    var sourceIndex = root.nodeIndex(edge.source)
                    var targetIndex = root.nodeIndex(edge.target)
                    if (sourceIndex < 0 || targetIndex < 0)
                        continue

                    var sx = root.centerX(sourceIndex)
                    var sy = root.centerY(sourceIndex)
                    var tx = root.centerX(targetIndex)
                    var ty = root.centerY(targetIndex)
                    var control = root.edgeControlPoint(sx, sy, tx, ty, i)
                    var selected = selectedEdgeId === String(edge.id || "")
                    var hovered = root.hoveredEdgeId === String(edge.id || "")
                    var onPath = root.isPathEdge(String(edge.id || ""))
                    var active = onPath || selected || hovered
                            || selectedNodeId === String(edge.source || "")
                            || selectedNodeId === String(edge.target || "")
                            || root.effectiveHoveredNodeId === String(edge.source || "")
                            || root.effectiveHoveredNodeId === String(edge.target || "")

                    ctx.globalAlpha = onPath ? 0.98 : root.edgeOpacity(active)
                    ctx.lineWidth = root.linkThickness * (onPath ? 2.8 : active ? 1.9 : (edge.needs_review ? 0.65 : 0.85))
                    ctx.strokeStyle = onPath ? theme.warning : active ? root.graphEdgeActive : root.graphEdge
                    if (ctx.setLineDash && edge.needs_review && !active)
                        ctx.setLineDash([5, 5])
                    else if (ctx.setLineDash)
                        ctx.setLineDash([])
                    ctx.beginPath()
                    ctx.moveTo(sx, sy)
                    ctx.quadraticCurveTo(control.x, control.y, tx, ty)
                    ctx.stroke()
                    if (ctx.setLineDash)
                        ctx.setLineDash([])

                    if (root.showArrows) {
                        var angle = Math.atan2(ty - control.y, tx - control.x)
                        var arrowOffset = root.nodeRadius(root.displayNodes[targetIndex]) + 2
                        var arrowX = tx - Math.cos(angle) * arrowOffset
                        var arrowY = ty - Math.sin(angle) * arrowOffset
                        ctx.beginPath()
                        ctx.moveTo(arrowX, arrowY)
                        ctx.lineTo(arrowX - Math.cos(angle - 0.55) * 6, arrowY - Math.sin(angle - 0.55) * 6)
                        ctx.lineTo(arrowX - Math.cos(angle + 0.55) * 6, arrowY - Math.sin(angle + 0.55) * 6)
                        ctx.closePath()
                        ctx.fillStyle = onPath ? theme.warning : active ? root.graphEdgeActive : root.graphEdge
                        ctx.fill()
                    }

                }
                ctx.globalAlpha = 1.0
            }
        }

        Repeater {
            id: graphNodeRepeater
            model: root.displayNodes
            delegate: Rectangle {
                id: nodeDelegate
                required property var modelData
                required property int index
                property real r: root.layoutRevision, root.nodeRadius(modelData)

                width: r * 2
                height: r * 2
                radius: width / 2
                x: root.layoutRevision, root.centerX(index) - r
                y: root.layoutRevision, root.centerY(index) - r
                color: root.nodeColor(modelData.type)
                border.width: root.isSearchMatch(modelData) ? 2.8 : knowledgeGraphController.selectedNode.id === modelData.id ? 2.5 : 1
                border.color: String(modelData.id || "") === root.pathStartId ? theme.success
                            : String(modelData.id || "") === root.pathEndId ? theme.error
                            : root.isPathNode(String(modelData.id || "")) ? theme.warning
                            : root.isSearchMatch(modelData) ? theme.warning
                            : knowledgeGraphController.selectedNode.id === modelData.id ? root.graphEdgeActive : theme.borderStrong
                opacity: root.nodeOpacity(String(modelData.id || ""), Number(modelData.confidence))
                scale: knowledgeGraphController.selectedNode.id === modelData.id ? 1.25 : root.isPathNode(String(modelData.id || "")) ? 1.16 : root.effectiveHoveredNodeId === String(modelData.id || "") ? 1.12 : 1.0

                Behavior on scale {
                    NumberAnimation {
                        duration: theme.reduceMotion || !root.animateLayout ? 0 : 140
                        easing.type: Easing.OutCubic
                    }
                }
                Behavior on x {
                    NumberAnimation {
                        duration: theme.reduceMotion || !root.animateLayout ? 0 : 180
                        easing.type: Easing.OutCubic
                    }
                }
                Behavior on y {
                    NumberAnimation {
                        duration: theme.reduceMotion || !root.animateLayout ? 0 : 180
                        easing.type: Easing.OutCubic
                    }
                }

                Rectangle {
                    anchors.centerIn: parent
                    width: parent.width + 8
                    height: parent.height + 8
                    radius: width / 2
                    color: "transparent"
                    border.width: String(modelData.type || "").toLowerCase() === "paper" ? 2.6 : 1.8
                    border.color: root.confidenceColor(Number(modelData.confidence === undefined ? 1 : modelData.confidence), !!modelData.needs_review)
                    opacity: knowledgeGraphController.selectedNode.id === modelData.id || root.effectiveHoveredNodeId === String(modelData.id || "") ? 0.98 : 0.72
                }

                Text {
                    anchors.centerIn: parent
                    text: root.nodeGlyph(modelData.type)
                    color: String(modelData.type || "").toLowerCase() === "paper" ? theme.accentText : theme.text
                    opacity: theme.dark ? 0.92 : 0.78
                    font.pixelSize: Math.max(10, parent.width * 0.42)
                    font.bold: true
                }

                GraphEvidenceBadge {
                    visible: !modelData.aggregate
                    anchors.right: parent.right
                    anchors.bottom: parent.bottom
                    anchors.rightMargin: -8
                    anchors.bottomMargin: -7
                    count: (modelData.evidence || []).length
                    confidence: Number(modelData.confidence === undefined ? 1 : modelData.confidence)
                    needsReview: !!modelData.needs_review || Number(modelData.confidence) < 0.6
                }

                Text {
                    anchors.top: parent.bottom
                    anchors.horizontalCenter: parent.horizontalCenter
                    anchors.topMargin: 4
                    width: 120
                    text: modelData.label || modelData.type
                    color: knowledgeGraphController.selectedNode.id === modelData.id ? root.graphText : root.graphTextMuted
                    font.pixelSize: 10
                    horizontalAlignment: Text.AlignHCenter
                    elide: Text.ElideRight
                    visible: root.showLabels
                             || root.graphScale >= root.textFadeThreshold
                             || knowledgeGraphController.selectedNode.id === modelData.id
                             || root.effectiveHoveredNodeId === String(modelData.id || "")
                    opacity: visible ? 1 : 0
                }

                Rectangle {
                    visible: modelData.needs_review || Number(modelData.confidence) < 0.6
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.rightMargin: -2
                    anchors.topMargin: -2
                    width: 7
                    height: 7
                    radius: 4
                    color: theme.error
                }

                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    hoverEnabled: true
                    onEntered: {
                        root.hoveredNodeId = String(modelData.id || "")
                        if (!modelData.aggregate)
                            knowledgeGraphController.setHoveredNode(root.hoveredNodeId)
                    }
                    onExited: {
                        if (root.hoveredNodeId === String(modelData.id || "")) root.hoveredNodeId = ""
                        if (!modelData.aggregate && knowledgeGraphController.hoveredNodeId === String(modelData.id || "")) knowledgeGraphController.setHoveredNode("")
                    }
                    onClicked: {
                        if (modelData.aggregate)
                            root.focusCluster(modelData)
                        else
                            root.nodeRequested(String(modelData.id || ""))
                    }
                    onDoubleClicked: {
                        if (modelData.aggregate) {
                            root.focusCluster(modelData)
                            return
                        }
                        root.nodeRequested(String(modelData.id || ""))
                        root.expandRequested(String(modelData.id || ""), "all")
                        root.displayStyle = "focus"
                        root.focusDepth = Math.max(1, root.focusDepth)
                        root.displayStyleRequested(root.displayStyle)
                        root.refreshGraphLayout()
                        root.fitGraph()
                    }
                    ToolTip.visible: containsMouse
                    ToolTip.text: (modelData.summary || modelData.label || "") + root.pageHint(modelData)
                }
            }
        }
    }

    Repeater {
        id: edgeLabelOverlay
        z: 2
        model: root.displayEdges

        delegate: Rectangle {
            id: edgeLabelDelegate
            required property var modelData
            required property int index

            readonly property int sourceIndex: root.nodeIndex(modelData.source)
            readonly property int targetIndex: root.nodeIndex(modelData.target)
            readonly property bool selected: String(knowledgeGraphController.selectedEdge.id || "") === String(modelData.id || "")
            readonly property bool hovered: root.hoveredEdgeId === String(modelData.id || "")
            readonly property bool onPath: root.isPathEdge(String(modelData.id || ""))
            readonly property bool active: onPath || selected || hovered
                                           || String(knowledgeGraphController.selectedNode.id || "") === String(modelData.source || "")
                                           || String(knowledgeGraphController.selectedNode.id || "") === String(modelData.target || "")
                                           || root.effectiveHoveredNodeId === String(modelData.source || "")
                                           || root.effectiveHoveredNodeId === String(modelData.target || "")
            readonly property point graphMidpoint: {
                if (sourceIndex < 0 || targetIndex < 0)
                    return Qt.point(-10000, -10000)
                var sx = root.centerX(sourceIndex)
                var sy = root.centerY(sourceIndex)
                var tx = root.centerX(targetIndex)
                var ty = root.centerY(targetIndex)
                var control = root.edgeControlPoint(sx, sy, tx, ty, edgeLabelDelegate.index)
                return root.curvePoint(sx, sy, control.x, control.y, tx, ty, 0.5)
            }
            readonly property point screenMidpoint: Qt.point(
                (graphMidpoint.x - root.width / 2) * root.graphScale + root.width / 2 + root.panX,
                (graphMidpoint.y - root.height / 2) * root.graphScale + root.height / 2 + root.panY)

            visible: sourceIndex >= 0 && targetIndex >= 0
                     && (onPath || root.showLabels || selected || hovered
                         || (active && root.graphScale >= 0.95)
                         || root.graphScale >= root.relationLabelThreshold)
            width: Math.min(190, Math.max(28, relationText.implicitWidth + 10))
            height: 20
            x: Math.round(screenMidpoint.x - width / 2)
            y: Math.round(screenMidpoint.y - height / 2 - 4)
            radius: 4
            color: theme.mix(theme.surfaceElevated, theme.canvas, theme.dark ? 0.18 : 0.08)
            border.color: onPath ? theme.warning : active ? theme.borderStrong : theme.border
            opacity: visible ? 0.96 : 0

            Text {
                id: relationText
                anchors.fill: parent
                anchors.leftMargin: 5
                anchors.rightMargin: 5
                text: edgeLabelDelegate.modelData.label || edgeLabelDelegate.modelData.type || ""
                color: edgeLabelDelegate.onPath ? theme.warning
                       : edgeLabelDelegate.active ? root.graphText : root.graphTextMuted
                font.pixelSize: 11
                font.hintingPreference: Font.PreferFullHinting
                renderType: Text.NativeRendering
                verticalAlignment: Text.AlignVCenter
                horizontalAlignment: Text.AlignHCenter
                elide: Text.ElideRight
            }
        }
    }

    MouseArea {
        anchors.fill: parent
        acceptedButtons: Qt.LeftButton
        hoverEnabled: true
        property real lastX
        property real lastY
        onPressed: function(mouse) { lastX = mouse.x; lastY = mouse.y }
        onPositionChanged: function(mouse) {
            if (pressed) {
                root.panX += mouse.x - lastX
                root.panY += mouse.y - lastY
                lastX = mouse.x
                lastY = mouse.y
            } else {
                var hoverEdge = root.edgeAt((mouse.x - root.panX - width / 2) / root.graphScale + width / 2, (mouse.y - root.panY - height / 2) / root.graphScale + height / 2)
                root.hoveredEdgeId = hoverEdge ? String(hoverEdge.id || "") : ""
            }
        }
        onClicked: function(mouse) {
            var edge = root.edgeAt((mouse.x - root.panX - width / 2) / root.graphScale + width / 2, (mouse.y - root.panY - height / 2) / root.graphScale + height / 2)
            if (edge && !edge.aggregate)
                root.edgeRequested(String(edge.id || ""))
        }
        onExited: root.hoveredEdgeId = ""
        onWheel: function(wheel) {
            root.graphScale = Math.max(0.45, Math.min(2.5, root.graphScale + (wheel.angleDelta.y > 0 ? 0.1 : -0.1)))
            wheel.accepted = true
        }
    }

    Row {
        z: 4
        anchors.left: parent.left
        anchors.top: parent.top
        anchors.margins: 8
        spacing: 6
        visible: !root.exportMode

        StyledComboBox {
            width: 116
            model: [i18n.text("graph_style_overview"), i18n.text("graph_style_academic"), i18n.text("graph_style_radial"), i18n.text("graph_style_focus")]
            currentIndex: root.styleIndex(root.displayStyle)
            onActivated: function(index) {
                root.displayStyle = root.styleValues[index]
                if (root.displayStyle === "focus" && root.focusDepth === 0)
                    root.focusDepth = 1
                root.displayStyleRequested(root.displayStyle)
                root.refreshGraphLayout()
                root.fitGraph()
            }
        }
        StyledComboBox {
            width: 92
            model: [i18n.text("graph_density_compact"), i18n.text("graph_density_normal"), i18n.text("graph_density_detailed"), i18n.text("graph_density_all")]
            currentIndex: 1
            onActivated: knowledgeGraphController.setDensity(["compact", "normal", "detailed", "all"][currentIndex])
        }
        StyledComboBox {
            width: 86
            model: [i18n.text("graph_depth_full"), i18n.text("graph_depth_one_hop"), i18n.text("graph_depth_two_hop")]
            currentIndex: root.focusDepth
            onActivated: {
                root.focusDepth = currentIndex
                root.refreshGraphLayout()
                root.fitGraph()
            }
            ToolTip.visible: hovered
            ToolTip.text: i18n.text("graph_depth_tooltip")
        }
        PillButton {
            text: i18n.text("graph_review")
            primary: root.reviewMode
            onClicked: {
                root.reviewMode = !root.reviewMode
                root.refreshGraphLayout()
                root.fitGraph()
            }
        }
        PillButton { text: i18n.text("graph_fit"); onClicked: root.fitGraph() }
        PillButton { visible: root.showFullscreenAction; text: i18n.text("graph_fullscreen"); onClicked: root.fullscreenRequested() }
    }

    ToolButton {
        z: 5
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: 10
        text: root.settingsOpen ? "x" : i18n.text("graph_settings")
        visible: !root.exportMode
        onClicked: {
            root.settingsOpen = !root.settingsOpen
            root.fitGraph()
        }
    }

    GraphSettingsPanel {
        id: settingsPanel
        z: 4
        visible: root.settingsOpen && !root.exportMode
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        anchors.margins: 36

        showArrows: root.showArrows
        showLabels: root.showLabels
        dimUnrelated: root.dimUnrelated
        textFadeThreshold: root.textFadeThreshold
        nodeSizeScale: root.nodeSizeScale
        linkThickness: root.linkThickness
        animateLayout: root.animateLayout

        onShowArrowsChanged: {
            root.showArrows = showArrows
            edgeCanvas.requestPaint()
        }
        onShowLabelsChanged: {
            root.showLabels = showLabels
            root.refreshGraphLayout()
        }
        onDimUnrelatedChanged: {
            root.dimUnrelated = dimUnrelated
            edgeCanvas.requestPaint()
        }
        onTextFadeThresholdChanged: {
            root.textFadeThreshold = textFadeThreshold
            root.refreshGraphLayout()
        }
        onNodeSizeScaleChanged: {
            root.nodeSizeScale = nodeSizeScale
            root.refreshGraphLayout()
        }
        onLinkThicknessChanged: {
            root.linkThickness = linkThickness
            edgeCanvas.requestPaint()
        }
        onAnimateLayoutChanged: {
            root.animateLayout = animateLayout
            root.refreshGraphLayout()
        }
        onResetRequested: root.resetGraphSettings()
    }

    Rectangle {
        id: minimap
        z: 3
        anchors.left: parent.left
        anchors.bottom: parent.bottom
        anchors.margins: 10
        width: 118
        height: 76
        radius: 8
        color: theme.surfaceElevated
        border.color: theme.border
        opacity: 0.92
        visible: !root.exportMode
        Repeater {
            model: root.displayNodes
            delegate: Rectangle {
                required property var modelData
                required property int index
                property var point: root.normalizedPoint(index)
                x: 8 + Number(point.x) * (minimap.width - 20)
                y: 8 + Number(point.y) * (minimap.height - 20)
                width: String(modelData.type).toLowerCase() === "paper" ? 6 : 4
                height: width
                radius: width / 2
                color: root.nodeColor(modelData.type)
            }
        }
    }

    GraphLegend {
        z: 3
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.margins: 10
        anchors.rightMargin: root.settingsOpen && !root.exportMode ? Math.min(settingsPanel.width + 46, parent.width * 0.42) : 10
        nodes: root.displayNodes
        edges: root.displayEdges
    }

    Rectangle {
        z: 3
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.topMargin: 48
        anchors.rightMargin: root.settingsOpen && !root.exportMode ? Math.min(settingsPanel.width + 46, parent.width * 0.42) : 10
        width: renderStatusText.implicitWidth + 18
        height: 28
        radius: 7
        visible: !root.exportMode && !!root.renderStatus.degraded
        color: theme.surfaceElevated
        border.color: theme.border
        opacity: 0.94
        Text {
            id: renderStatusText
            anchors.centerIn: parent
            text: "层级 " + String(root.renderStatus.level || "normal") + " · "
                  + Number(root.renderStatus.renderedNodes || 0) + " / " + Number(root.renderStatus.totalSemanticNodes || 0)
                  + (Number(root.renderStatus.aggregatedNodes || 0) > 0 ? " · 聚合 " + Number(root.renderStatus.aggregatedNodes) : "")
            color: theme.textMuted
            font.pixelSize: 10
        }
    }

    Text {
        anchors.centerIn: parent
        visible: root.displayNodes.length === 0
        text: root.reviewMode ? i18n.text("graph_empty_review") : i18n.text("graph_empty_filter")
        color: root.graphTextMuted
    }

    onNodesChanged: root.refreshGraphLayout()
    onEdgesChanged: root.refreshGraphLayout()
    onSearchQueryChanged: {
        root.refreshGraphLayout()
        if (root.searchQuery.trim().length > 0)
            root.fitGraph()
    }
    onGraphScaleChanged: { edgeCanvas.requestPaint(); renderViewportTimer.restart() }
    onPanXChanged: { edgeCanvas.requestPaint(); backgroundCanvas.requestPaint(); renderViewportTimer.restart() }
    onPanYChanged: { edgeCanvas.requestPaint(); backgroundCanvas.requestPaint(); renderViewportTimer.restart() }
    onDisplayNodesChanged: edgeCanvas.requestPaint()
    onDisplayEdgesChanged: edgeCanvas.requestPaint()
    onDisplayStyleChanged: { root.refreshGraphLayout(); renderViewportTimer.restart() }
    onFocusDepthChanged: root.refreshGraphLayout()
    onReviewModeChanged: root.refreshGraphLayout()
    onHoveredNodeIdChanged: edgeCanvas.requestPaint()
    onEffectiveHoveredNodeIdChanged: edgeCanvas.requestPaint()
    onHoveredEdgeIdChanged: edgeCanvas.requestPaint()
    onShowArrowsChanged: edgeCanvas.requestPaint()
    onDimUnrelatedChanged: edgeCanvas.requestPaint()
    onShowLabelsChanged: root.refreshGraphLayout()
    onTextFadeThresholdChanged: root.refreshGraphLayout()
    onNodeSizeScaleChanged: root.refreshGraphLayout()
    onLinkThicknessChanged: edgeCanvas.requestPaint()
    onAnimateLayoutChanged: root.refreshGraphLayout()
    onFullExportNodesChanged: root.refreshGraphLayout()
    onFullExportEdgesChanged: root.refreshGraphLayout()
    onExportUseFullGraphChanged: root.refreshGraphLayout()
    onExportModeChanged: { if (!root.exportMode) renderViewportTimer.restart() }
    onExportTransparentChanged: backgroundCanvas.requestPaint()
    onPathNodeIdsChanged: { root.refreshGraphLayout(); edgeCanvas.requestPaint() }
    onPathEdgeIdsChanged: edgeCanvas.requestPaint()
    onWidthChanged: { root.refreshGraphLayout(); backgroundCanvas.requestPaint(); renderViewportTimer.restart() }
    onHeightChanged: { root.refreshGraphLayout(); backgroundCanvas.requestPaint(); renderViewportTimer.restart() }
    onVisibleChanged: { if (root.visible) renderViewportTimer.restart() }
    Component.onCompleted: renderViewportTimer.start()

    function refreshGraphLayout() {
        root.layoutRevision += 1
        edgeCanvas.requestPaint()
    }

    function syncRenderViewport() {
        renderViewportTimer.restart()
    }

    function visibleNodesForRevision(revision) {
        return root.filteredNodes()
    }

    function visibleEdgesForRevision(revision) {
        return root.filteredEdges()
    }

    function filteredNodes() {
        var selected = String(knowledgeGraphController.selectedNode.id || "")
        var center = root.centerNodeId()
        var activeStyle = root.exportMode && root.exportUseFullGraph ? "academic" : root.displayStyle
        var depth = activeStyle === "focus" ? Math.max(1, root.focusDepth) : root.focusDepth
        var focusSet = depth > 0 && (selected || activeStyle === "focus") ? root.neighborhood(selected || center, depth) : null
        var result = []
        var queryActive = root.searchQuery.trim().length > 0
        for (var i = 0; i < root.activeNodes.length; ++i) {
            var node = root.activeNodes[i]
            var id = String(node.id || "")
            var isPaper = String(node.type || "").toLowerCase() === "paper"
            if (root.reviewMode && !isPaper && !node.needs_review && Number(node.confidence) >= 0.6)
                continue
            if (focusSet && !focusSet[id])
                continue
            if (activeStyle === "overview" && !queryActive && !root.reviewMode && !root.isOverviewNode(node, result.length))
                continue
            result.push(node)
        }
        return result
    }

    function filteredEdges() {
        var visible = {}
        for (var i = 0; i < root.displayNodes.length; ++i)
            visible[String(root.displayNodes[i].id || "")] = true
        var result = []
        for (var j = 0; j < root.activeEdges.length; ++j) {
            if (visible[String(root.activeEdges[j].source || "")] && visible[String(root.activeEdges[j].target || "")])
                result.push(root.activeEdges[j])
        }
        return result
    }

    function neighborhood(startId, depth) {
        var visited = {}
        if (!startId)
            return visited
        visited[startId] = true
        var frontier = [startId]
        for (var level = 0; level < depth; ++level) {
            var next = []
            for (var i = 0; i < frontier.length; ++i) {
                var neighbors = root.adjacency[frontier[i]] || []
                for (var j = 0; j < neighbors.length; ++j) {
                    var id = String(neighbors[j])
                    if (!visited[id]) {
                        visited[id] = true
                        next.push(id)
                    }
                }
            }
            frontier = next
        }
        return visited
    }

    function buildNodeMap(values) {
        var result = {}
        for (var i = 0; i < values.length; ++i)
            result[String(values[i].id || "")] = i
        return result
    }

    function idSet(values) {
        var result = {}
        for (var i = 0; i < (values || []).length; ++i)
            result[String(values[i] || "")] = true
        return result
    }

    function isPathNode(nodeId) { return !!root.pathNodeSet[String(nodeId || "")] }
    function isPathEdge(edgeId) { return !!root.pathEdgeSet[String(edgeId || "")] }

    function styleIndex(value) {
        var index = root.styleValues.indexOf(String(value || "overview"))
        return index >= 0 ? index : 0
    }

    function nodeIndex(id) {
        var value = root.nodeMap[String(id || "")]
        return value === undefined ? -1 : Number(value)
    }

    function nodeRadius(node) {
        if (node.aggregate)
            return Math.max(13, Math.min(28, 9 + Math.sqrt(Math.max(1, Number(node.memberCount || 1))) * 1.5)) * root.nodeSizeScale
        var id = String(node.id || "")
        var degree = (root.adjacency[id] || []).length
        var evidenceCount = (node.evidence || []).length
        var base = 4 + Math.sqrt(Math.max(1, degree + evidenceCount)) * 2.2
        if (String(node.type || "").toLowerCase() === "paper")
            base += 5
        return Math.max(4, Math.min(18, base)) * root.nodeSizeScale
    }

    function centerX(index) {
        var point = root.normalizedPoint(index)
        return 36 + Number(point.x) * Math.max(120, width - 72)
    }

    function centerY(index) {
        var point = root.normalizedPoint(index)
        return 42 + Number(point.y) * Math.max(120, height - 92)
    }

    function nodePointIn(nodeId, targetItem) {
        var index = root.nodeIndex(String(nodeId || ""))
        if (index < 0 || !targetItem)
            return Qt.point(width / 2, height / 2)
        return viewport.mapToItem(targetItem, root.centerX(index), root.centerY(index))
    }

    function captureViewState() {
        return {
            displayStyle: root.displayStyle,
            focusDepth: root.focusDepth,
            reviewMode: root.reviewMode,
            graphScale: root.graphScale,
            panX: root.panX,
            panY: root.panY,
            showArrows: root.showArrows,
            showLabels: root.showLabels,
            dimUnrelated: root.dimUnrelated,
            textFadeThreshold: root.textFadeThreshold,
            nodeSizeScale: root.nodeSizeScale,
            linkThickness: root.linkThickness,
            animateLayout: root.animateLayout
        }
    }

    function applyViewState(state, preserveDisplayStyle) {
        var value = state || {}
        if (!preserveDisplayStyle)
            root.displayStyle = root.styleValues.indexOf(String(value.displayStyle || "overview")) >= 0 ? String(value.displayStyle) : "overview"
        root.focusDepth = Math.max(0, Math.min(2, Number(value.focusDepth || 0)))
        root.reviewMode = !!value.reviewMode
        root.graphScale = Math.max(0.45, Math.min(2.5, Number(value.graphScale || 1.0)))
        root.panX = Number(value.panX || 0)
        root.panY = Number(value.panY || 0)
        root.showArrows = !!value.showArrows
        root.showLabels = !!value.showLabels
        root.dimUnrelated = value.dimUnrelated === undefined ? true : !!value.dimUnrelated
        root.textFadeThreshold = Number(value.textFadeThreshold || 1.15)
        root.nodeSizeScale = Number(value.nodeSizeScale || 1.0)
        root.linkThickness = Number(value.linkThickness || 1.0)
        root.animateLayout = !!value.animateLayout
        if (!preserveDisplayStyle)
            root.displayStyleRequested(root.displayStyle)
        root.refreshGraphLayout()
    }

    function focusNode(nodeId) {
        if (!nodeId)
            return false
        root.displayStyle = "focus"
        root.focusDepth = Math.max(1, root.focusDepth)
        root.displayStyleRequested(root.displayStyle)
        root.refreshGraphLayout()
        Qt.callLater(function() { root.fitGraph() })
        return true
    }

    function normalizedPoint(index) {
        if (index < 0 || index >= root.displayNodes.length)
            return { x: 0.5, y: 0.5 }
        var activeStyle = root.exportMode && root.exportUseFullGraph ? "academic" : root.displayStyle
        if (activeStyle === "radial")
            return root.radialPoint(index, root.centerNodeId(), 0.22)
        if (activeStyle === "focus")
            return root.radialPoint(index, root.centerNodeId(), 0.25)
        if (activeStyle === "overview")
            return root.overviewPoint(index)
        return root.academicPoint(index)
    }

    function academicPoint(index) {
        var node = root.displayNodes[index]
        var pos = root.activeGraphLayout[String(node.id || "")]
        return pos ? { x: Number(pos.x), y: Number(pos.y) } : root.overviewPoint(index)
    }

    function overviewPoint(index) {
        var node = root.displayNodes[index]
        var layer = root.layerForNode(node)
        if (String(node.type || "").toLowerCase() === "paper")
            return { x: 0.08, y: 0.5 }
        var count = root.countLayer(layer)
        var order = root.indexInLayer(index, layer)
        var x = 0.14 + Math.min(5, Math.max(1, layer)) * 0.155
        var y = (order + 1) / (count + 1)
        return { x: Math.max(0.16, Math.min(0.92, x)), y: Math.max(0.08, Math.min(0.92, y)) }
    }

    function radialPoint(index, centerId, ringStep) {
        var node = root.displayNodes[index]
        var id = String(node.id || "")
        if (id === centerId)
            return { x: 0.5, y: 0.5 }
        var depth = root.radialDepth(id, centerId)
        if (depth < 0)
            depth = Math.min(3, Math.max(1, root.layerForNode(node)))
        var peers = root.countRadialDepth(depth, centerId)
        var order = root.indexInRadialDepth(index, depth, centerId)
        var depthValue = Math.max(1, depth)
        var ringJitter = (depthValue % 2) * 0.17
        var angleStep = Math.PI * 2 / Math.max(1, peers)
        var angle = -Math.PI / 2 + ringJitter + angleStep * order
        var radius = Math.min(0.48, 0.24 + (depthValue - 1) * ringStep)
        var crowdOffset = peers > 10 ? ((order % 2) * 0.035 - 0.0175) : 0
        radius = Math.max(0.18, Math.min(0.48, radius + crowdOffset))
        return { x: 0.5 + Math.cos(angle) * radius, y: 0.5 + Math.sin(angle) * radius }
    }

    function radialDepth(id, centerId) {
        if (!centerId)
            return -1
        if (id === centerId)
            return 0
        var visited = {}
        visited[centerId] = true
        var frontier = [centerId]
        for (var depth = 1; depth <= 4; ++depth) {
            var next = []
            for (var i = 0; i < frontier.length; ++i) {
                var neighbors = root.adjacency[frontier[i]] || []
                for (var j = 0; j < neighbors.length; ++j) {
                    var neighbor = String(neighbors[j])
                    if (neighbor === id)
                        return depth
                    if (!visited[neighbor]) {
                        visited[neighbor] = true
                        next.push(neighbor)
                    }
                }
            }
            frontier = next
        }
        return -1
    }

    function countLayer(layer) {
        var count = 0
        for (var i = 0; i < root.displayNodes.length; ++i) {
            if (root.layerForNode(root.displayNodes[i]) === layer)
                count += 1
        }
        return count
    }

    function indexInLayer(index, layer) {
        var order = 0
        for (var i = 0; i < index; ++i) {
            if (root.layerForNode(root.displayNodes[i]) === layer)
                order += 1
        }
        return order
    }

    function countRadialDepth(depth, centerId) {
        var count = 0
        for (var i = 0; i < root.displayNodes.length; ++i) {
            var itemDepth = root.radialDepth(String(root.displayNodes[i].id || ""), centerId)
            if (itemDepth < 0)
                itemDepth = Math.min(3, Math.max(1, root.layerForNode(root.displayNodes[i])))
            if (itemDepth === depth && String(root.displayNodes[i].id || "") !== centerId)
                count += 1
        }
        return Math.max(1, count)
    }

    function indexInRadialDepth(index, depth, centerId) {
        var order = 0
        for (var i = 0; i < index; ++i) {
            var itemDepth = root.radialDepth(String(root.displayNodes[i].id || ""), centerId)
            if (itemDepth < 0)
                itemDepth = Math.min(3, Math.max(1, root.layerForNode(root.displayNodes[i])))
            if (itemDepth === depth && String(root.displayNodes[i].id || "") !== centerId)
                order += 1
        }
        return order
    }

    function layerForNode(node) {
        var pos = root.activeGraphLayout[String(node.id || "")]
        if (pos && pos.layer !== undefined)
            return Number(pos.layer)
        var type = String(node.type || "").toLowerCase()
        if (type === "paper")
            return 0
        if (type === "problem" || type === "researchgap" || type === "researchquestion" || type === "section" || type === "concept")
            return 1
        if (type === "method" || type === "algorithm" || type === "model" || type === "contribution" || type === "comparison")
            return 2
        if (type === "dataset" || type === "metric" || type === "baseline" || type === "experiment")
            return 3
        if (type === "result" || type === "claim" || type === "conclusion" || type === "limitation" || type === "futurework" || type === "conflict")
            return 4
        return 5
    }

    function centerNodeId() {
        var selected = String(knowledgeGraphController.selectedNode.id || "")
        if (selected)
            return selected
        for (var i = 0; i < root.activeNodes.length; ++i) {
            if (String(root.activeNodes[i].type || "").toLowerCase() === "paper")
                return String(root.activeNodes[i].id || "")
        }
        return root.activeNodes.length ? String(root.activeNodes[0].id || "") : ""
    }

    function isOverviewNode(node, acceptedCount) {
        if (node.aggregate)
            return true
        var type = String(node.type || "").toLowerCase()
        if (type === "paper")
            return true
        if (acceptedCount >= 60)
            return false
        if (node.needs_review || Number(node.confidence) < 0.58)
            return false
        var importance = Number(node.importance === undefined ? node.weight || 0.5 : node.importance)
        return importance >= 0.42 || (node.evidence || []).length > 0
    }

    function nodeColor(type) {
        type = String(type || "").toLowerCase()
        if (type === "cluster")
            return theme.mix(theme.accent, theme.surface, theme.dark ? 0.52 : 0.24)
        if (type === "paper")
            return theme.mix(theme.accent, theme.surface, theme.dark ? 0.58 : 0.36)
        if (type === "method" || type === "algorithm" || type === "model")
            return theme.mix(theme.accent, theme.surface, theme.dark ? 0.72 : 0.44)
        if (type === "topic" || type === "concept")
            return theme.mix(theme.info, theme.surface, theme.dark ? 0.70 : 0.40)
        if (type === "author")
            return theme.mix(theme.success, theme.surface, theme.dark ? 0.64 : 0.36)
        if (type === "institution" || type === "venue")
            return theme.mix(theme.textMuted, theme.surface, theme.dark ? 0.58 : 0.30)
        if (type === "experiment" || type === "dataset" || type === "metric")
            return theme.mix(theme.warning, theme.surface, theme.dark ? 0.76 : 0.44)
        if (type === "result" || type === "claim" || type === "conclusion")
            return theme.mix(theme.success, theme.surface, theme.dark ? 0.76 : 0.46)
        if (type === "citation")
            return theme.mix(theme.textMuted, theme.surface, theme.dark ? 0.62 : 0.34)
        if (type === "limitation" || type === "conflict" || type === "futurework")
            return theme.mix(theme.error, theme.surface, theme.dark ? 0.78 : 0.48)
        if (type === "figure" || type === "table" || type === "equation")
            return theme.mix(theme.info, theme.surface, theme.dark ? 0.58 : 0.30)
        return theme.mix(theme.textMuted, theme.surface, theme.dark ? 0.42 : 0.22)
    }

    function pageHint(node) {
        var ev = node.evidence || []
        return ev.length && ev[0].page >= 0 ? "\n" + i18n.text("graph_page") + " " + (Number(ev[0].page) + 1) : ""
    }

    function isSearchMatch(node) {
        var query = root.searchQuery.trim().toLowerCase()
        if (!query)
            return false
        var text = String(node.label || "") + " " + String(node.summary || "") + " " + String(node.type || "") + " " + (node.tags || []).join(" ")
        return text.toLowerCase().indexOf(query) >= 0
    }

    function edgeIsActive(edge) {
        var selected = String(knowledgeGraphController.selectedNode.id || "")
        return selected && (selected === String(edge.source || "") || selected === String(edge.target || ""))
    }

    function edgeOpacity(active) {
        var selectedNodeId = String(knowledgeGraphController.selectedNode.id || "")
        if (selectedNodeId && root.dimUnrelated && !active)
            return 0.08
        return active ? 0.9 : 0.28
    }

    function nodeOpacity(nodeId, confidence) {
        if (String(nodeId || "").indexOf("cluster:") === 0)
            return 0.94
        var selected = String(knowledgeGraphController.selectedNode.id || "")
        if (root.pathNodeIds.length > 0)
            return root.isPathNode(nodeId) ? 1.0 : 0.16
        if (root.effectiveHoveredNodeId === nodeId)
            return 1.0
        if (!selected)
            return confidence < 0.6 ? 0.62 : 1.0
        if (!root.dimUnrelated)
            return 1.0
        if (selected === nodeId)
            return 1.0
        var neighbors = root.adjacency[selected] || []
        return neighbors.indexOf(nodeId) >= 0 ? 0.92 : 0.14
    }

    function edgeControlPoint(x1, y1, x2, y2, index) {
        var dx = x2 - x1
        var dy = y2 - y1
        var length = Math.max(1, Math.hypot(dx, dy))
        var normalX = -dy / length
        var normalY = dx / length
        var arc = Math.min(46, Math.max(14, length * 0.08))
        var direction = (index % 2 === 0) ? 1 : -1
        var stagger = ((index % 5) - 2) * 2.5
        return { x: (x1 + x2) / 2 + normalX * (arc + stagger) * direction, y: (y1 + y2) / 2 + normalY * (arc + stagger) * direction }
    }

    function curvePoint(x1, y1, cx, cy, x2, y2, t) {
        var inv = 1 - t
        return {
            x: inv * inv * x1 + 2 * inv * t * cx + t * t * x2,
            y: inv * inv * y1 + 2 * inv * t * cy + t * t * y2
        }
    }

    function distanceToCurve(px, py, x1, y1, cx, cy, x2, y2) {
        var best = Number.POSITIVE_INFINITY
        for (var i = 0; i <= 16; ++i) {
            var point = root.curvePoint(x1, y1, cx, cy, x2, y2, i / 16)
            best = Math.min(best, Math.hypot(px - point.x, py - point.y))
        }
        return best
    }

    function confidenceColor(confidence, needsReview) {
        if (needsReview)
            return theme.warning
        if (confidence >= 0.78)
            return theme.success
        if (confidence >= 0.6)
            return theme.accent
        return theme.error
    }

    function nodeGlyph(type) {
        type = String(type || "").toLowerCase()
        if (type === "cluster")
            return "#"
        if (type === "paper")
            return "P"
        if (type === "method" || type === "algorithm" || type === "model")
            return "M"
        if (type === "author")
            return "A"
        if (type === "institution")
            return "I"
        if (type === "venue")
            return "V"
        if (type === "topic" || type === "concept")
            return "K"
        if (type === "dataset")
            return "D"
        if (type === "metric")
            return "%"
        if (type === "result" || type === "claim" || type === "conclusion")
            return "R"
        if (type === "contribution")
            return "+"
        if (type === "limitation")
            return "!"
        if (type === "futurework")
            return "W"
        if (type === "citation")
            return "C"
        if (type === "figure")
            return "G"
        if (type === "table")
            return "T"
        if (type === "equation")
            return "="
        return String(type || "?").slice(0, 1).toUpperCase()
    }

    function distance(px, py, x1, y1, x2, y2) {
        var dx = x2 - x1
        var dy = y2 - y1
        if (dx === 0 && dy === 0)
            return Math.hypot(px - x1, py - y1)
        var t = Math.max(0, Math.min(1, ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)))
        return Math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))
    }

    function edgeAt(x, y) {
        for (var i = root.displayEdges.length - 1; i >= 0; --i) {
            var s = root.nodeIndex(root.displayEdges[i].source)
            var t = root.nodeIndex(root.displayEdges[i].target)
            if (s >= 0 && t >= 0) {
                var sx = root.centerX(s)
                var sy = root.centerY(s)
                var tx = root.centerX(t)
                var ty = root.centerY(t)
                var control = root.edgeControlPoint(sx, sy, tx, ty, i)
                if (root.distanceToCurve(x, y, sx, sy, control.x, control.y, tx, ty) < 8)
                    return root.displayEdges[i]
            }
        }
        return null
    }

    function resetGraphSettings() {
        root.showArrows = false
        root.showLabels = false
        root.dimUnrelated = true
        root.textFadeThreshold = 1.15
        root.nodeSizeScale = 1.0
        root.linkThickness = 1.0
        root.animateLayout = false
        settingsPanel.showArrows = root.showArrows
        settingsPanel.showLabels = root.showLabels
        settingsPanel.dimUnrelated = root.dimUnrelated
        settingsPanel.textFadeThreshold = root.textFadeThreshold
        settingsPanel.nodeSizeScale = root.nodeSizeScale
        settingsPanel.linkThickness = root.linkThickness
        settingsPanel.animateLayout = root.animateLayout
        root.fitGraph()
        root.refreshGraphLayout()
    }

    function resetView() {
        root.graphScale = 1.0
        root.panX = 0
        root.panY = 0
        root.focusDepth = 0
        root.reviewMode = false
        root.displayStyle = "overview"
        root.displayStyleRequested(root.displayStyle)
    }

    function fitGraph() {
        if (root.displayNodes.length === 0 || width <= 0 || height <= 0) {
            root.graphScale = 1.0
            root.panX = 0
            root.panY = 0
            root.refreshGraphLayout()
            return
        }

        var minX = Number.POSITIVE_INFINITY
        var minY = Number.POSITIVE_INFINITY
        var maxX = Number.NEGATIVE_INFINITY
        var maxY = Number.NEGATIVE_INFINITY

        for (var i = 0; i < root.displayNodes.length; ++i) {
            var radius = root.nodeRadius(root.displayNodes[i]) + 18
            var cx = root.centerX(i)
            var cy = root.centerY(i)
            minX = Math.min(minX, cx - radius)
            minY = Math.min(minY, cy - radius)
            maxX = Math.max(maxX, cx + radius)
            maxY = Math.max(maxY, cy + radius)
        }

        var panelReserve = root.settingsOpen && !root.exportMode ? Math.min(settingsPanel.width + 56, width * 0.38) : 0
        var padding = 28
        var availableWidth = Math.max(160, width - panelReserve - padding * 2)
        var availableHeight = Math.max(140, height - padding * 2)
        var boundsWidth = Math.max(1, maxX - minX)
        var boundsHeight = Math.max(1, maxY - minY)
        var targetScale = Math.min(availableWidth / boundsWidth, availableHeight / boundsHeight)
        root.graphScale = Math.max(0.45, Math.min(2.5, targetScale))

        var graphCenterX = (minX + maxX) / 2
        var graphCenterY = (minY + maxY) / 2
        var targetCenterX = padding + availableWidth / 2
        var targetCenterY = height / 2
        var scaledGraphCenterX = (graphCenterX - width / 2) * root.graphScale + width / 2
        var scaledGraphCenterY = (graphCenterY - height / 2) * root.graphScale + height / 2
        root.panX = targetCenterX - scaledGraphCenterX
        root.panY = targetCenterY - scaledGraphCenterY
        root.refreshGraphLayout()
    }

    function focusCluster(cluster) {
        var nodeId = String((cluster || {}).id || "")
        root.displayStyle = "academic"
        root.displayStyleRequested(root.displayStyle)
        root.refreshGraphLayout()
        var index = root.nodeIndex(nodeId)
        if (index < 0)
            return false
        var centerX = root.centerX(index)
        var centerY = root.centerY(index)
        var targetScale = Math.max(1.15, Math.min(2.5, root.graphScale * 1.65))
        root.graphScale = targetScale
        root.panX = -(centerX - width / 2) * targetScale
        root.panY = -(centerY - height / 2) * targetScale
        root.refreshGraphLayout()
        renderViewportTimer.restart()
        return true
    }

    function exportPng(path, scale, fullGraph, transparent) {
        var outputPath = String(path || "")
        var outputScale = Math.max(1, Math.min(4, Math.round(Number(scale || 1))))
        var targetWidth = Math.round(width * outputScale)
        var targetHeight = Math.round(height * outputScale)
        if (!outputPath) {
            root.imageExportFinished(outputPath, false, "导出路径为空")
            return false
        }
        if (root.exportMode) {
            root.imageExportFinished(outputPath, false, "已有图片导出任务正在进行")
            return false
        }
        if (width <= 0 || height <= 0 || targetWidth > 16384 || targetHeight > 16384
                || targetWidth * targetHeight > 100000000) {
            root.imageExportFinished(outputPath, false, "导出尺寸超出安全范围")
            return false
        }

        var savedView = root.captureViewState()
        root.exportMode = true
        root.exportUseFullGraph = !!fullGraph
        root.exportTransparent = !!transparent
        root.animateLayout = false

        if (fullGraph) {
            root.focusDepth = 0
            root.reviewMode = false
            root.showLabels = true
            root.graphScale = 1.0
            root.panX = 0
            root.panY = 0
        }
        root.refreshGraphLayout()
        backgroundCanvas.requestPaint()

        function restoreExportState() {
            root.exportUseFullGraph = false
            root.exportTransparent = false
            root.exportMode = false
            root.applyViewState(savedView, true)
            backgroundCanvas.requestPaint()
        }

        Qt.callLater(function() {
            if (fullGraph)
                root.fitGraph()
            Qt.callLater(function() {
                var accepted = root.grabToImage(function(result) {
                    var saved = false
                    var errorMessage = ""
                    try {
                        saved = result.saveToFile(outputPath)
                        if (!saved)
                            errorMessage = "无法写入 PNG 文件"
                    } catch (error) {
                        errorMessage = String(error)
                    }
                    restoreExportState()
                    root.imageExportFinished(outputPath, saved, errorMessage)
                }, Qt.size(targetWidth, targetHeight))
                if (!accepted) {
                    restoreExportState()
                    root.imageExportFinished(outputPath, false, "无法启动画布截图")
                }
            })
        })
        return true
    }
}
