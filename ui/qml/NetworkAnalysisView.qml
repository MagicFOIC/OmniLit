pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: root

    property var analysis: ({})
    property string analysisMode: "keywords"
    property var selectedItem: ({})
    signal graphRequested(string mode)

    Theme { id: theme }

    ColumnLayout {
        anchors.fill: parent
        spacing: 8

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 50
            radius: 8
            color: theme.surface
            border.color: theme.border
            RowLayout {
                anchors.fill: parent
                anchors.margins: 7
                spacing: 6
                PillButton { text: "关键词密度"; primary: root.analysisMode === "keywords"; onClicked: root.analysisMode = "keywords" }
                PillButton { text: "共被引"; primary: root.analysisMode === "cocitation"; onClicked: root.analysisMode = "cocitation" }
                PillButton { text: "文献耦合"; primary: root.analysisMode === "coupling"; onClicked: root.analysisMode = "coupling" }
                PillButton { text: "核心论文"; primary: root.analysisMode === "core"; onClicked: root.analysisMode = "core" }
                PillButton { text: "桥接论文"; primary: root.analysisMode === "bridge"; onClicked: root.analysisMode = "bridge" }
                PillButton { text: "突现趋势"; primary: root.analysisMode === "burst"; onClicked: root.analysisMode = "burst" }
                PillButton { text: "主题增长"; primary: root.analysisMode === "trend"; onClicked: root.analysisMode = "trend" }
                Item { Layout.fillWidth: true }
                PillButton {
                    text: "进入局部图谱"
                    primary: true
                    visible: root.analysisMode !== "keywords" && root.analysisMode !== "burst"
                    enabled: root.displayItems().length > 0
                    onClicked: root.graphRequested(root.analysisMode)
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 42
            radius: 8
            color: theme.surfaceSoft
            border.color: theme.border
            RowLayout {
                anchors.fill: parent
                anchors.margins: 7
                spacing: 12
                Text { text: "覆盖 " + Number((root.analysis.coverage || {}).paperCount || 0) + " 篇"; color: theme.text; font.bold: true }
                Text { text: "引文覆盖 " + Math.round(Number((root.analysis.coverage || {}).referenceCoverage || 0) * 100) + "%"; color: theme.textMuted }
                Text { text: "年份覆盖 " + Math.round(Number((root.analysis.coverage || {}).yearCoverage || 0) * 100) + "%"; color: theme.textMuted }
                Text { text: "真实引文 " + Number((root.analysis.coverage || {}).citationLinkCount || 0) + " 条"; color: theme.textMuted }
                Item { Layout.fillWidth: true }
                Text {
                    Layout.maximumWidth: 520
                    text: ((root.analysis.coverage || {}).warnings || []).join("；") || "所有指标均可追溯至当前馆藏元数据与语义特征。"
                    color: ((root.analysis.coverage || {}).warnings || []).length ? theme.warning : theme.success
                    elide: Text.ElideRight
                }
            }
        }

        SplitView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            orientation: Qt.Horizontal

            Rectangle {
                SplitView.fillWidth: true
                SplitView.minimumWidth: 520
                radius: 8
                color: theme.canvas
                border.color: theme.border

                Canvas {
                    id: densityCanvas
                    anchors.fill: parent
                    anchors.margins: 12
                    property var nodes: (root.analysis.keywordNetwork || {}).nodes || []
                    property var links: (root.analysis.keywordNetwork || {}).links || []
                    onNodesChanged: requestPaint()
                    onLinksChanged: requestPaint()
                    onWidthChanged: requestPaint()
                    onHeightChanged: requestPaint()
                    onPaint: {
                        var context = getContext("2d")
                        context.clearRect(0, 0, width, height)
                        var byId = ({})
                        for (var i = 0; i < nodes.length; ++i)
                            byId[String(nodes[i].id || "")] = nodes[i]
                        for (var h = 0; h < nodes.length; ++h) {
                            var heatNode = nodes[h]
                            var heatX = Number(heatNode.x || 0.5) * width
                            var heatY = Number(heatNode.y || 0.5) * height
                            var heatRadius = 22 + Number(heatNode.density || 0) * 46
                            var gradient = context.createRadialGradient(heatX, heatY, 0, heatX, heatY, heatRadius)
                            gradient.addColorStop(0, theme.dark ? "rgba(96,165,250,0.34)" : "rgba(37,99,235,0.28)")
                            gradient.addColorStop(1, "rgba(37,99,235,0)")
                            context.fillStyle = gradient
                            context.fillRect(heatX - heatRadius, heatY - heatRadius, heatRadius * 2, heatRadius * 2)
                        }
                        context.lineWidth = 1
                        context.strokeStyle = theme.dark ? "#35506f" : "#cbd5e1"
                        for (var j = 0; j < links.length; ++j) {
                            var source = byId[String(links[j].source || "")]
                            var target = byId[String(links[j].target || "")]
                            if (!source || !target) continue
                            context.globalAlpha = Math.min(0.44, 0.06 + Number(links[j].score || 0) * 0.8)
                            context.beginPath()
                            context.moveTo(Number(source.x || 0.5) * width, Number(source.y || 0.5) * height)
                            context.lineTo(Number(target.x || 0.5) * width, Number(target.y || 0.5) * height)
                            context.stroke()
                        }
                        context.globalAlpha = 1
                    }
                }

                Repeater {
                    model: ((root.analysis.keywordNetwork || {}).nodes || []).slice(0, 80)
                    delegate: Rectangle {
                        id: keywordNode
                        required property var modelData
                        property real nodeSize: 12 + Math.sqrt(Number(modelData.paperCount || 1)) * 5
                        x: 12 + Number(modelData.x || 0.5) * Math.max(1, parent.width - 24) - width / 2
                        y: 12 + Number(modelData.y || 0.5) * Math.max(1, parent.height - 24) - height / 2
                        width: nodeSize
                        height: nodeSize
                        radius: width / 2
                        color: Qt.rgba(theme.accent.r, theme.accent.g, theme.accent.b, 0.18 + Number(modelData.density || 0) * 0.66)
                        border.color: theme.accent
                        border.width: String((root.selectedItem || {}).term || "") === String(modelData.term || "") ? 3 : 1
                        Accessible.name: String(modelData.label || modelData.term || "") + "，覆盖 " + Number(modelData.paperCount || 0) + " 篇论文"
                        Text {
                            anchors.left: parent.right
                            anchors.leftMargin: 3
                            anchors.verticalCenter: parent.verticalCenter
                            visible: Number(keywordNode.modelData.density || 0) > 0.18 || Number(keywordNode.modelData.paperCount || 0) > 2
                            text: keywordNode.modelData.label || keywordNode.modelData.term
                            color: theme.text
                            font.pixelSize: 10
                            style: Text.Outline
                            styleColor: theme.canvas
                        }
                        MouseArea {
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: root.selectedItem = keywordNode.modelData
                            ToolTip.visible: containsMouse
                            ToolTip.text: keywordNode.modelData.explanation || ""
                        }
                    }
                }

                Rectangle {
                    anchors.left: parent.left
                    anchors.bottom: parent.bottom
                    anchors.margins: 14
                    width: densityLegend.implicitWidth + 18
                    height: 30
                    radius: 8
                    color: theme.surfaceElevated
                    border.color: theme.border
                    Row {
                        id: densityLegend
                        anchors.centerIn: parent
                        spacing: 10
                        Text { text: "圆大小 = 论文覆盖"; color: theme.textMuted; font.pixelSize: 10 }
                        Text { text: "颜色浓度 = 共现加权度"; color: theme.accent; font.pixelSize: 10 }
                    }
                }
            }

            Rectangle {
                SplitView.preferredWidth: 430
                SplitView.minimumWidth: 350
                radius: 8
                color: theme.surface
                border.color: theme.border
                ScrollView {
                    anchors.fill: parent
                    anchors.margins: 10
                    contentWidth: availableWidth
                    ScrollBar.vertical: StyledScrollBar { policy: ScrollBar.AsNeeded }
                    ColumnLayout {
                        width: parent.width
                        spacing: 8
                        Text { Layout.fillWidth: true; text: root.modeTitle(); color: theme.text; font.bold: true; font.pixelSize: 18; wrapMode: Text.Wrap }
                        Text { Layout.fillWidth: true; text: root.methodText(); color: theme.textMuted; wrapMode: Text.Wrap }
                        Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: theme.divider }
                        Repeater {
                            model: root.displayItems().slice(0, 40)
                            delegate: Rectangle {
                                id: resultRow
                                required property var modelData
                                Layout.fillWidth: true
                                Layout.preferredHeight: resultColumn.implicitHeight + 14
                                radius: 7
                                color: String((root.selectedItem || {}).recordId || (root.selectedItem || {}).term || "") === String(modelData.recordId || modelData.term || "") ? theme.accentSoft : theme.surfaceSoft
                                border.color: theme.border
                                ColumnLayout {
                                    id: resultColumn
                                    anchors.left: parent.left
                                    anchors.right: parent.right
                                    anchors.verticalCenter: parent.verticalCenter
                                    anchors.margins: 7
                                    spacing: 3
                                    Text { Layout.fillWidth: true; text: root.itemTitle(resultRow.modelData); color: theme.text; font.bold: true; wrapMode: Text.Wrap }
                                    Text { Layout.fillWidth: true; text: root.itemScore(resultRow.modelData); color: theme.accent; font.pixelSize: 11; wrapMode: Text.Wrap }
                                    Text { Layout.fillWidth: true; text: resultRow.modelData.explanation || (resultRow.modelData.reasons || []).join("；"); color: theme.textMuted; wrapMode: Text.Wrap }
                                }
                                MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: root.selectedItem = resultRow.modelData }
                            }
                        }
                        Text { visible: root.displayItems().length === 0; text: "当前馆藏证据不足，未生成该类关系。"; color: theme.warning; wrapMode: Text.Wrap }
                    }
                }
            }
        }
    }

    function displayItems() {
        if (analysisMode === "cocitation") return (analysis.coCitation || {}).links || []
        if (analysisMode === "coupling") return (analysis.coupling || {}).links || []
        if (analysisMode === "core") return analysis.corePapers || []
        if (analysisMode === "bridge") return analysis.bridgePapers || []
        if (analysisMode === "burst") return analysis.bursts || []
        if (analysisMode === "trend") return analysis.topicTrends || []
        return (analysis.keywordNetwork || {}).nodes || []
    }

    function modeTitle() {
        return ({ keywords: "关键词共现与密度", cocitation: "文献共被引", coupling: "文献耦合", core: "核心论文", bridge: "桥接论文", burst: "突现关键词", trend: "主题增长趋势" })[analysisMode] || "结构分析"
    }

    function methodText() {
        if (analysisMode === "cocitation") return (analysis.coCitation || {}).method || ""
        if (analysisMode === "coupling") return (analysis.coupling || {}).method || ""
        if (analysisMode === "keywords") return (analysis.keywordNetwork || {}).method || ""
        return (analysis.methods || {})[analysisMode === "burst" ? "burst" : analysisMode] || ""
    }

    function itemTitle(item) {
        if (item.recordId) return String(item.title || item.recordId)
        if (item.term) return String(item.label || item.term)
        if (item.topicId) return String(item.name || item.topicId)
        return String(item.source || "") + " ↔ " + String(item.target || "")
    }

    function itemScore(item) {
        if (analysisMode === "core") return "核心度 " + Number(item.coreScore || 0).toFixed(2) + " · 馆藏内被引 " + Number(item.citationIn || 0)
        if (analysisMode === "bridge") return "桥接度 " + Number(item.bridgeScore || 0).toFixed(2) + " · 跨主题连接 " + Number(item.crossTopicLinks || 0)
        if (analysisMode === "burst") return "突现强度 " + Number(item.burstScore || 0).toFixed(2) + " · 增长 " + Number(item.growthRate || 0).toFixed(2) + "×"
        if (analysisMode === "trend") return "主题规模 " + Number(item.size || 0) + " 篇 · 最近/前窗 " + Number(item.recentCount || 0) + "/" + Number(item.previousCount || 0) + " · " + String(item.label || item.trend || "未知")
        if (analysisMode === "keywords") return "覆盖 " + Number(item.paperCount || 0) + " 篇 · 密度 " + Number(item.density || 0).toFixed(2)
        return "共享证据 " + Number(item.sharedReferences || item.sharedCiters || 0) + " · 归一化强度 " + Number(item.score || 0).toFixed(2)
    }
}
