import QtQuick
import QtQuick.Controls

Rectangle {
    id: root

    property var nodes: []
    property var edges: []
    property var graphLayout: knowledgeGraphController.layout || ({})
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
    property int layoutRevision: 0

    property bool settingsOpen: true
    property bool showArrows: false
    property bool showLabels: false
    property bool dimUnrelated: true
    property real textFadeThreshold: 1.15
    property real nodeSizeScale: 1.0
    property real linkThickness: 1.0
    property bool animateLayout: false

    readonly property color graphBackground: theme.canvas
    readonly property color graphEdge: theme.mix(theme.borderStrong, theme.canvas, theme.dark ? 0.72 : 0.58)
    readonly property color graphEdgeActive: theme.accent
    readonly property color graphText: theme.text
    readonly property color graphTextMuted: theme.textMuted
    readonly property var styleValues: ["overview", "academic", "radial", "focus"]
    readonly property var displayNodes: root.visibleNodesForRevision(root.layoutRevision)
    readonly property var displayEdges: root.visibleEdgesForRevision(root.layoutRevision)
    readonly property var nodeMap: root.buildNodeMap(root.displayNodes)

    signal nodeRequested(string nodeId)
    signal edgeRequested(string edgeId)
    signal fullscreenRequested()
    signal displayStyleRequested(string displayStyle)

    Theme { id: theme }
    I18n { id: i18n }
    radius: theme.radiusMedium
    color: root.graphBackground
    border.color: theme.border
    clip: true

    Connections {
        target: knowledgeGraphController
        function onChanged() { root.refreshGraphLayout() }
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
                ctx.font = "10px sans-serif"
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
                    var selected = selectedEdgeId === String(edge.id || "")
                    var active = selected
                            || selectedNodeId === String(edge.source || "")
                            || selectedNodeId === String(edge.target || "")
                            || root.hoveredNodeId === String(edge.source || "")
                            || root.hoveredNodeId === String(edge.target || "")

                    ctx.globalAlpha = root.edgeOpacity(active)
                    ctx.lineWidth = root.linkThickness * (active ? 1.8 : 0.8)
                    ctx.strokeStyle = active ? root.graphEdgeActive : root.graphEdge
                    ctx.beginPath()
                    ctx.moveTo(sx, sy)
                    ctx.lineTo(tx, ty)
                    ctx.stroke()

                    if (root.showArrows) {
                        var angle = Math.atan2(ty - sy, tx - sx)
                        var arrowOffset = root.nodeRadius(root.displayNodes[targetIndex]) + 2
                        var arrowX = tx - Math.cos(angle) * arrowOffset
                        var arrowY = ty - Math.sin(angle) * arrowOffset
                        ctx.beginPath()
                        ctx.moveTo(arrowX, arrowY)
                        ctx.lineTo(arrowX - Math.cos(angle - 0.55) * 6, arrowY - Math.sin(angle - 0.55) * 6)
                        ctx.lineTo(arrowX - Math.cos(angle + 0.55) * 6, arrowY - Math.sin(angle + 0.55) * 6)
                        ctx.closePath()
                        ctx.fillStyle = active ? root.graphEdgeActive : root.graphEdge
                        ctx.fill()
                    }

                    if (active && root.graphScale >= 1.0) {
                        ctx.globalAlpha = 1.0
                        ctx.fillStyle = root.graphTextMuted
                        ctx.fillText(String(edge.label || edge.type || ""), (sx + tx) / 2 + 3, (sy + ty) / 2 - 3)
                    }
                }
                ctx.globalAlpha = 1.0
            }
        }

        Repeater {
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
                border.color: root.isSearchMatch(modelData) ? theme.warning : knowledgeGraphController.selectedNode.id === modelData.id ? root.graphEdgeActive : theme.borderStrong
                opacity: root.nodeOpacity(String(modelData.id || ""), Number(modelData.confidence))
                scale: knowledgeGraphController.selectedNode.id === modelData.id ? 1.25 : root.hoveredNodeId === String(modelData.id || "") ? 1.12 : 1.0

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
                             || root.hoveredNodeId === String(modelData.id || "")
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
                    onEntered: root.hoveredNodeId = String(modelData.id || "")
                    onExited: if (root.hoveredNodeId === String(modelData.id || "")) root.hoveredNodeId = ""
                    onClicked: root.nodeRequested(String(modelData.id || ""))
                    ToolTip.visible: containsMouse
                    ToolTip.text: (modelData.summary || modelData.label || "") + root.pageHint(modelData)
                }
            }
        }
    }

    MouseArea {
        anchors.fill: parent
        acceptedButtons: Qt.LeftButton
        property real lastX
        property real lastY
        onPressed: function(mouse) { lastX = mouse.x; lastY = mouse.y }
        onPositionChanged: function(mouse) {
            if (pressed) {
                root.panX += mouse.x - lastX
                root.panY += mouse.y - lastY
                lastX = mouse.x
                lastY = mouse.y
            }
        }
        onClicked: function(mouse) {
            var edge = root.edgeAt((mouse.x - root.panX - width / 2) / root.graphScale + width / 2, (mouse.y - root.panY - height / 2) / root.graphScale + height / 2)
            if (edge)
                root.edgeRequested(String(edge.id || ""))
        }
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

        ComboBox {
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
        ComboBox {
            width: 92
            model: [i18n.text("graph_density_compact"), i18n.text("graph_density_normal"), i18n.text("graph_density_detailed"), i18n.text("graph_density_all")]
            currentIndex: 1
            onActivated: knowledgeGraphController.setDensity(["compact", "normal", "detailed", "all"][currentIndex])
        }
        ComboBox {
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
        onClicked: {
            root.settingsOpen = !root.settingsOpen
            root.fitGraph()
        }
    }

    GraphSettingsPanel {
        id: settingsPanel
        z: 4
        visible: root.settingsOpen
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

    Text {
        anchors.centerIn: parent
        visible: root.displayNodes.length === 0
        text: root.reviewMode ? i18n.text("graph_empty_review") : i18n.text("graph_empty_filter")
        color: root.graphTextMuted
    }

    onNodesChanged: root.refreshGraphLayout()
    onEdgesChanged: root.refreshGraphLayout()
    onDisplayNodesChanged: edgeCanvas.requestPaint()
    onDisplayEdgesChanged: edgeCanvas.requestPaint()
    onDisplayStyleChanged: root.refreshGraphLayout()
    onFocusDepthChanged: root.refreshGraphLayout()
    onReviewModeChanged: root.refreshGraphLayout()
    onHoveredNodeIdChanged: edgeCanvas.requestPaint()
    onShowArrowsChanged: edgeCanvas.requestPaint()
    onDimUnrelatedChanged: edgeCanvas.requestPaint()
    onShowLabelsChanged: root.refreshGraphLayout()
    onTextFadeThresholdChanged: root.refreshGraphLayout()
    onNodeSizeScaleChanged: root.refreshGraphLayout()
    onLinkThicknessChanged: edgeCanvas.requestPaint()
    onAnimateLayoutChanged: root.refreshGraphLayout()
    onWidthChanged: root.refreshGraphLayout()
    onHeightChanged: root.refreshGraphLayout()

    function refreshGraphLayout() {
        root.layoutRevision += 1
        edgeCanvas.requestPaint()
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
        var depth = root.displayStyle === "focus" ? Math.max(1, root.focusDepth) : root.focusDepth
        var focusSet = depth > 0 && (selected || root.displayStyle === "focus") ? root.neighborhood(selected || center, depth) : null
        var result = []
        var queryActive = root.searchQuery.trim().length > 0
        for (var i = 0; i < root.nodes.length; ++i) {
            var node = root.nodes[i]
            var id = String(node.id || "")
            var isPaper = String(node.type || "").toLowerCase() === "paper"
            if (root.reviewMode && !isPaper && !node.needs_review && Number(node.confidence) >= 0.6)
                continue
            if (focusSet && !focusSet[id])
                continue
            if (root.displayStyle === "overview" && !queryActive && !root.reviewMode && !root.isOverviewNode(node, result.length))
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
        for (var j = 0; j < root.edges.length; ++j) {
            if (visible[String(root.edges[j].source || "")] && visible[String(root.edges[j].target || "")])
                result.push(root.edges[j])
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

    function styleIndex(value) {
        var index = root.styleValues.indexOf(String(value || "overview"))
        return index >= 0 ? index : 0
    }

    function nodeIndex(id) {
        var value = root.nodeMap[String(id || "")]
        return value === undefined ? -1 : Number(value)
    }

    function nodeRadius(node) {
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

    function normalizedPoint(index) {
        if (index < 0 || index >= root.displayNodes.length)
            return { x: 0.5, y: 0.5 }
        if (root.displayStyle === "radial")
            return root.radialPoint(index, root.centerNodeId(), 0.22)
        if (root.displayStyle === "focus")
            return root.radialPoint(index, root.centerNodeId(), 0.25)
        if (root.displayStyle === "overview")
            return root.overviewPoint(index)
        return root.academicPoint(index)
    }

    function academicPoint(index) {
        var node = root.displayNodes[index]
        var pos = root.graphLayout[String(node.id || "")]
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
        var pos = root.graphLayout[String(node.id || "")]
        if (pos && pos.layer !== undefined)
            return Number(pos.layer)
        var type = String(node.type || "").toLowerCase()
        if (type === "paper")
            return 0
        if (type === "problem" || type === "researchgap" || type === "section" || type === "concept")
            return 1
        if (type === "method" || type === "algorithm" || type === "model" || type === "contribution" || type === "comparison")
            return 2
        if (type === "dataset" || type === "metric" || type === "baseline" || type === "experiment")
            return 3
        if (type === "result" || type === "claim" || type === "limitation" || type === "futurework" || type === "conflict")
            return 4
        return 5
    }

    function centerNodeId() {
        var selected = String(knowledgeGraphController.selectedNode.id || "")
        if (selected)
            return selected
        for (var i = 0; i < root.nodes.length; ++i) {
            if (String(root.nodes[i].type || "").toLowerCase() === "paper")
                return String(root.nodes[i].id || "")
        }
        return root.nodes.length ? String(root.nodes[0].id || "") : ""
    }

    function isOverviewNode(node, acceptedCount) {
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
        if (type === "paper")
            return theme.mix(theme.accent, theme.surface, theme.dark ? 0.58 : 0.36)
        if (type === "method" || type === "algorithm" || type === "model")
            return theme.mix(theme.accent, theme.surface, theme.dark ? 0.72 : 0.44)
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
        var selected = String(knowledgeGraphController.selectedNode.id || "")
        if (!selected)
            return confidence < 0.6 ? 0.62 : 1.0
        if (!root.dimUnrelated)
            return 1.0
        if (selected === nodeId)
            return 1.0
        var neighbors = root.adjacency[selected] || []
        return neighbors.indexOf(nodeId) >= 0 ? 0.92 : 0.14
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
            if (s >= 0 && t >= 0 && root.distance(x, y, root.centerX(s), root.centerY(s), root.centerX(t), root.centerY(t)) < 7)
                return root.displayEdges[i]
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

        var panelReserve = root.settingsOpen ? Math.min(settingsPanel.width + 56, width * 0.38) : 0
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
}
