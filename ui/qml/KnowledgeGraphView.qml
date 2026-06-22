import QtQuick
import QtQuick.Controls

Rectangle {
    id: root
    property var nodes: []
    property var edges: []
    property var graphLayout: knowledgeGraphController.layout || ({})
    property var adjacency: knowledgeGraphController.graph.adjacency || ({})
    readonly property var nodeMap: root.buildNodeMap(root.nodes)
    property real graphScale: 1.0
    property real panX: 0
    property real panY: 0
    signal nodeRequested(string nodeId)
    signal edgeRequested(string edgeId)
    Theme { id: theme }
    Connections { target: knowledgeGraphController; function onChanged() { edgeCanvas.requestPaint() } }
    radius: theme.radiusMedium
    color: theme.surface
    border.color: theme.border
    clip: true

    Item {
        id: viewport
        z: 1
        anchors.fill: parent
        transform: [Translate { x: root.panX; y: root.panY }, Scale { origin.x: viewport.width / 2; origin.y: viewport.height / 2; xScale: root.graphScale; yScale: root.graphScale }]

        Canvas {
            id: edgeCanvas
            anchors.fill: parent
            onPaint: {
                var ctx = getContext("2d")
                ctx.reset()
                ctx.lineWidth = 1
                ctx.strokeStyle = theme.borderStrong
                ctx.fillStyle = theme.textMuted
                ctx.font = "10px sans-serif"
                var selectedId = String(knowledgeGraphController.selectedNode.id || "")
                var selectedEdgeId = String(knowledgeGraphController.selectedEdge.id || "")
                for (var i = 0; i < root.edges.length; ++i) {
                    var edge = root.edges[i]
                    var sourceIndex = root.nodeIndex(edge.source)
                    var targetIndex = root.nodeIndex(edge.target)
                    if (sourceIndex < 0 || targetIndex < 0) continue
                    var sx = root.centerX(sourceIndex), sy = root.centerY(sourceIndex)
                    var tx = root.centerX(targetIndex), ty = root.centerY(targetIndex)
                    var active = selectedEdgeId === String(edge.id || "") || selectedId === String(edge.source || "") || selectedId === String(edge.target || "")
                    ctx.globalAlpha = selectedId && !active ? 0.12 : active ? 1.0 : 0.46
                    ctx.lineWidth = active ? 2.2 : 1.0
                    ctx.strokeStyle = active ? theme.accent : theme.borderStrong
                    ctx.beginPath(); ctx.moveTo(sx, sy); ctx.lineTo(tx, ty); ctx.stroke()
                    var angle = Math.atan2(ty - sy, tx - sx)
                    var arrowX = tx - Math.cos(angle) * 24
                    var arrowY = ty - Math.sin(angle) * 24
                    ctx.beginPath(); ctx.moveTo(arrowX, arrowY)
                    ctx.lineTo(arrowX - Math.cos(angle - 0.55) * 8, arrowY - Math.sin(angle - 0.55) * 8)
                    ctx.lineTo(arrowX - Math.cos(angle + 0.55) * 8, arrowY - Math.sin(angle + 0.55) * 8)
                    ctx.closePath(); ctx.fillStyle = active ? theme.accent : theme.borderStrong; ctx.fill()
                    if (active) {
                        ctx.globalAlpha = 1.0
                        ctx.fillStyle = theme.textMuted
                        ctx.fillText(String(edge.label || edge.type || ""), (sx + tx) / 2 + 3, (sy + ty) / 2 - 3)
                    }
                }
                ctx.globalAlpha = 1.0
            }
        }
        Repeater {
            model: root.nodes
            delegate: Rectangle {
                required property var modelData
                required property int index
                x: root.nodeX(index); y: root.nodeY(index)
                width: String(modelData.type).toLowerCase() === "paper" ? 140 : 112
                height: String(modelData.type).toLowerCase() === "paper" ? 54 : 44
                radius: height / 2
                color: root.nodeColor(modelData.type)
                border.width: knowledgeGraphController.selectedNode.id === modelData.id ? 3 : 1
                border.color: knowledgeGraphController.selectedNode.id === modelData.id ? theme.accent : theme.borderStrong
                scale: knowledgeGraphController.selectedNode.id === modelData.id ? 1.08 : 1.0
                Behavior on scale { NumberAnimation { duration: 140; easing.type: Easing.OutCubic } }
                opacity: root.nodeOpacity(String(modelData.id || ""), Number(modelData.confidence))
                Text { anchors.fill: parent; anchors.margins: 7; text: modelData.label || modelData.type; color: theme.text; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight; maximumLineCount: 2; wrapMode: Text.Wrap; font.pixelSize: 11 }
                Rectangle {
                    anchors.left: parent.left; anchors.top: parent.top; anchors.leftMargin: 5; anchors.topMargin: -7
                    width: typeLabel.implicitWidth + 10; height: 17; radius: 8
                    color: theme.surface; border.color: theme.border
                    Text { id: typeLabel; anchors.centerIn: parent; text: String(modelData.type || ""); color: theme.textMuted; font.pixelSize: 9 }
                }
                Rectangle {
                    visible: (modelData.evidence || []).length > 0
                    anchors.right: parent.right; anchors.bottom: parent.bottom; anchors.rightMargin: 4; anchors.bottomMargin: -6
                    width: 20; height: 16; radius: 8; color: theme.accentSofter
                    Text { anchors.centerIn: parent; text: String((modelData.evidence || []).length); color: theme.accent; font.pixelSize: 9; font.bold: true }
                }
                MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: root.nodeRequested(String(modelData.id || "")); hoverEnabled: true; ToolTip.visible: containsMouse; ToolTip.text: (modelData.summary || modelData.label || "") + root.pageHint(modelData) }
            }
        }
    }

    MouseArea {
        anchors.fill: parent
        acceptedButtons: Qt.LeftButton
        property real lastX
        property real lastY
        onPressed: function(mouse) { lastX = mouse.x; lastY = mouse.y }
        onPositionChanged: function(mouse) { if (pressed) { root.panX += mouse.x - lastX; root.panY += mouse.y - lastY; lastX = mouse.x; lastY = mouse.y } }
        onClicked: function(mouse) { var edge = root.edgeAt((mouse.x - root.panX - width / 2) / root.graphScale + width / 2, (mouse.y - root.panY - height / 2) / root.graphScale + height / 2); if (edge) root.edgeRequested(String(edge.id || "")) }
        onWheel: function(wheel) { root.graphScale = Math.max(0.45, Math.min(2.5, root.graphScale + (wheel.angleDelta.y > 0 ? 0.1 : -0.1))); wheel.accepted = true }
    }
    Row {
        z: 2; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 8; spacing: 6
        ComboBox { width: 108; model: ["精简", "标准", "详细", "全部"]; onActivated: knowledgeGraphController.setDensity(["compact", "normal", "detailed", "all"][currentIndex]) }
        PillButton { text: "适配全图"; onClicked: root.fitGraph() }
    }
    Text { anchors.centerIn: parent; visible: root.nodes.length === 0; text: "当前筛选下没有节点"; color: theme.textMuted }

    onNodesChanged: edgeCanvas.requestPaint()
    onEdgesChanged: edgeCanvas.requestPaint()
    onWidthChanged: edgeCanvas.requestPaint()
    onHeightChanged: edgeCanvas.requestPaint()
    function buildNodeMap(values) { var result={}; for(var i=0;i<values.length;++i) result[String(values[i].id||"")]=i; return result }
    function nodeIndex(id) { var value=root.nodeMap[String(id||"")]; return value === undefined ? -1 : Number(value) }
    function group(type) { type = String(type).toLowerCase(); if (type === "paper") return 0; if (type === "concept" || type === "keyword" || type === "comparison") return 1; if (["figure","table","equation"].indexOf(type) >= 0) return 3; return 2 }
    function groupInfo(index) { var g = group(nodes[index].type), pos = 0, count = 0; for (var i=0;i<nodes.length;++i) if(group(nodes[i].type)===g){if(i===index)pos=count;count++} return {group:g,position:pos,count:Math.max(1,count)} }
    function radiusFor(group) { return Math.min(width, height) * (group === 0 ? 0.10 : group === 1 ? 0.23 : group === 2 ? 0.34 : 0.44) }
    function nodeX(index) { var paper=group(nodes[index].type)===0, pos=root.graphLayout[String(nodes[index].id||"")]; if(pos)return 45+Number(pos.x)*Math.max(100,width-90)-(paper?70:56); var info=groupInfo(index),r=radiusFor(info.group),a=-Math.PI/2+2*Math.PI*info.position/info.count;return width/2+Math.cos(a)*r-(paper?70:56) }
    function nodeY(index) { var paper=group(nodes[index].type)===0, pos=root.graphLayout[String(nodes[index].id||"")]; if(pos)return 48+Number(pos.y)*Math.max(100,height-96)-(paper?27:22); var info=groupInfo(index),r=radiusFor(info.group),a=-Math.PI/2+2*Math.PI*info.position/info.count;return height/2+Math.sin(a)*r-(paper?27:22) }
    function centerX(index) { return nodeX(index)+(group(nodes[index].type)===0?70:56) }
    function centerY(index) { return nodeY(index)+(group(nodes[index].type)===0?27:22) }
    function nodeColor(type) { type=String(type).toLowerCase(); if(type==="paper")return theme.accentSofter;if(type==="concept"||type==="comparison")return theme.navSelected;if(["figure","table","equation"].indexOf(type)>=0)return theme.surfaceSoft;if(type==="conflict"||type==="missinginfo")return theme.surfaceSoft;return theme.navHover }
    function pageHint(node) { var ev=node.evidence||[]; return ev.length&&ev[0].page>=0 ? "\n第 "+(Number(ev[0].page)+1)+" 页" : "" }
    function distance(px,py,x1,y1,x2,y2){var dx=x2-x1,dy=y2-y1;if(dx===0&&dy===0)return Math.hypot(px-x1,py-y1);var t=Math.max(0,Math.min(1,((px-x1)*dx+(py-y1)*dy)/(dx*dx+dy*dy)));return Math.hypot(px-(x1+t*dx),py-(y1+t*dy))}
    function edgeAt(x,y){for(var i=edges.length-1;i>=0;--i){var s=nodeIndex(edges[i].source),t=nodeIndex(edges[i].target);if(s>=0&&t>=0&&distance(x,y,centerX(s),centerY(s),centerX(t),centerY(t))<7)return edges[i]}return null}
    function nodeOpacity(nodeId, confidence) { var selected=String(knowledgeGraphController.selectedNode.id||""); if(!selected)return confidence<0.6?0.70:1.0;if(selected===nodeId)return 1.0;var neighbors=root.adjacency[selected]||[];return neighbors.indexOf(nodeId)>=0?0.94:0.18 }
    function fitGraph() { root.graphScale=1.0; root.panX=0; root.panY=0 }
}
