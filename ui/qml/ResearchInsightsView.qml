pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: root

    property var analysis: ({})
    property string viewMode: "authors"
    property var selectedEntity: ({})
    signal graphRequested(string mode)
    signal paperRequested(string recordId)

    Theme { id: theme }
    onViewModeChanged: root.selectedEntity = ({})

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
                spacing: 7
                PillButton { text: "作者合作"; primary: root.viewMode === "authors"; onClicked: root.viewMode = "authors" }
                PillButton { text: "机构合作"; primary: root.viewMode === "institutions"; onClicked: root.viewMode = "institutions" }
                PillButton { text: "推荐阅读"; primary: root.viewMode === "reading"; onClicked: root.viewMode = "reading" }
                Item { Layout.fillWidth: true }
                PillButton {
                    text: root.viewMode === "reading" ? "查看阅读路径图" : "进入合作网络"
                    primary: true
                    enabled: root.viewMode === "reading" ? (root.analysis.readingPaths || []).length > 0 : root.displayEntities().length > 0
                    onClicked: root.graphRequested(root.viewMode)
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
                Text { text: "作者覆盖 " + Math.round(Number((root.analysis.coverage || {}).authorCoverage || 0) * 100) + "%"; color: theme.text }
                Text { text: "机构覆盖 " + Math.round(Number((root.analysis.coverage || {}).institutionCoverage || 0) * 100) + "%"; color: theme.text }
                Text { text: "显式任职 " + Number((root.analysis.coverage || {}).explicitAffiliationCount || 0) + " 条"; color: theme.textMuted }
                Text { visible: root.viewMode === "reading"; text: "排除已读 " + Number((root.analysis.recommendationContext || {}).archivedExcluded || 0) + " 篇"; color: theme.success }
                Item { Layout.fillWidth: true }
                Text {
                    Layout.maximumWidth: 560
                    text: ((root.analysis.coverage || {}).warnings || []).join("；") || "合作关系均来自真实署名和机构元数据。"
                    color: ((root.analysis.coverage || {}).warnings || []).length ? theme.warning : theme.success
                    elide: Text.ElideRight
                }
            }
        }

        SplitView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: root.viewMode !== "reading"
            orientation: Qt.Horizontal

            Rectangle {
                SplitView.fillWidth: true
                SplitView.minimumWidth: 520
                radius: 8
                color: theme.canvas
                border.color: theme.border

                Canvas {
                    id: collaborationCanvas
                    anchors.fill: parent
                    anchors.margins: 12
                    property var nodes: root.displayEntities().slice(0, 60)
                    property var links: root.displayLinks()
                    onNodesChanged: requestPaint()
                    onLinksChanged: requestPaint()
                    onWidthChanged: requestPaint()
                    onHeightChanged: requestPaint()
                    onPaint: {
                        var context = getContext("2d")
                        context.clearRect(0, 0, width, height)
                        var byId = ({})
                        for (var i = 0; i < nodes.length; ++i) byId[String(nodes[i].id || "")] = nodes[i]
                        context.strokeStyle = theme.dark ? "#52677f" : "#cbd5e1"
                        for (var j = 0; j < links.length; ++j) {
                            var source = byId[String(links[j].source || "")]
                            var target = byId[String(links[j].target || "")]
                            if (!source || !target) continue
                            context.globalAlpha = Math.min(0.72, 0.18 + Number(links[j].paperCount || 1) * 0.12)
                            context.lineWidth = Math.min(5, 0.7 + Number(links[j].paperCount || 1) * 0.5)
                            context.beginPath()
                            context.moveTo(Number(source.x || 0.5) * width, Number(source.y || 0.5) * height)
                            context.lineTo(Number(target.x || 0.5) * width, Number(target.y || 0.5) * height)
                            context.stroke()
                        }
                        context.globalAlpha = 1
                    }
                }

                Repeater {
                    model: root.displayEntities().slice(0, 60)
                    delegate: Rectangle {
                        id: entityNode
                        required property var modelData
                        property real nodeSize: 15 + Math.sqrt(Number(modelData.paperCount || 1)) * 6
                        x: 12 + Number(modelData.x || 0.5) * Math.max(1, parent.width - 24) - width / 2
                        y: 12 + Number(modelData.y || 0.5) * Math.max(1, parent.height - 24) - height / 2
                        width: nodeSize; height: nodeSize; radius: width / 2
                        color: Qt.rgba(theme.accent.r, theme.accent.g, theme.accent.b, 0.24 + Number(modelData.importanceScore || 0) * 0.62)
                        border.color: theme.accent
                        border.width: String((root.selectedEntity || {}).id || "") === String(modelData.id || "") ? 3 : 1
                        Accessible.name: String(modelData.label || "") + "，重要性 " + Number(modelData.importanceScore || 0).toFixed(2)
                        Text {
                            anchors.left: parent.right; anchors.leftMargin: 3; anchors.verticalCenter: parent.verticalCenter
                            visible: Number(entityNode.modelData.importanceScore || 0) >= 0.28
                            text: entityNode.modelData.label || ""
                            color: theme.text; font.pixelSize: 10; style: Text.Outline; styleColor: theme.canvas
                        }
                        MouseArea {
                            anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                            onClicked: root.selectedEntity = entityNode.modelData
                            ToolTip.visible: containsMouse
                            ToolTip.text: (entityNode.modelData.reasons || []).join("；")
                        }
                    }
                }

                Rectangle {
                    anchors.left: parent.left; anchors.bottom: parent.bottom; anchors.margins: 14
                    width: collaborationLegend.implicitWidth + 18; height: 30; radius: 8
                    color: theme.surfaceElevated; border.color: theme.border
                    Row {
                        id: collaborationLegend; anchors.centerIn: parent; spacing: 10
                        Text { text: "节点大小 = 论文产出"; color: theme.textMuted; font.pixelSize: 10 }
                        Text { text: "边宽 = 共同论文"; color: theme.accent; font.pixelSize: 10 }
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
                    anchors.fill: parent; anchors.margins: 10; contentWidth: availableWidth
                    ScrollBar.vertical: StyledScrollBar { policy: ScrollBar.AsNeeded }
                    ColumnLayout {
                        width: parent.width; spacing: 7
                        Text { text: root.viewMode === "authors" ? "重要作者" : "重要机构"; color: theme.text; font.bold: true; font.pixelSize: 18 }
                        Text { Layout.fillWidth: true; text: (root.analysis.methods || {}).importance || ""; color: theme.textMuted; wrapMode: Text.Wrap }
                        Repeater {
                            model: root.displayEntities().slice(0, 35)
                            delegate: Rectangle {
                                id: entityRow
                                required property var modelData
                                Layout.fillWidth: true
                                Layout.preferredHeight: entityColumn.implicitHeight + 14
                                radius: 7
                                color: String((root.selectedEntity || {}).id || "") === String(modelData.id || "") ? theme.accentSoft : theme.surfaceSoft
                                border.color: theme.border
                                ColumnLayout {
                                    id: entityColumn; anchors.fill: parent; anchors.margins: 7; spacing: 3
                                    Text { Layout.fillWidth: true; text: entityRow.modelData.label || ""; color: theme.text; font.bold: true; elide: Text.ElideRight }
                                    Text { Layout.fillWidth: true; text: "重要性 " + Number(entityRow.modelData.importanceScore || 0).toFixed(2) + " · 桥接 " + Number(entityRow.modelData.bridgeScore || 0).toFixed(2) + " · " + Number(entityRow.modelData.paperCount || 0) + " 篇"; color: theme.accent; font.pixelSize: 10 }
                                    Text { Layout.fillWidth: true; text: (entityRow.modelData.reasons || []).join("；"); color: theme.textMuted; wrapMode: Text.Wrap }
                                }
                                MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: root.selectedEntity = entityRow.modelData }
                            }
                        }
                        Text { visible: root.displayEntities().length === 0; text: "当前集合缺少该类元数据，未生成合作网络。"; color: theme.warning; wrapMode: Text.Wrap }
                    }
                }
            }
        }

        SplitView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: root.viewMode === "reading"
            orientation: Qt.Horizontal

            Rectangle {
                SplitView.fillWidth: true
                SplitView.minimumWidth: 520
                radius: 8; color: theme.surface; border.color: theme.border
                ScrollView {
                    anchors.fill: parent; anchors.margins: 10; contentWidth: availableWidth
                    ScrollBar.vertical: StyledScrollBar { policy: ScrollBar.AsNeeded }
                    ColumnLayout {
                        width: parent.width; spacing: 7
                        Text { text: "下一步最值得阅读"; color: theme.text; font.bold: true; font.pixelSize: 18 }
                        Text { Layout.fillWidth: true; text: (root.analysis.methods || {}).recommendation || ""; color: theme.textMuted; wrapMode: Text.Wrap }
                        Repeater {
                            model: root.analysis.recommendations || []
                            delegate: Rectangle {
                                id: recommendationRow
                                required property var modelData
                                required property int index
                                Layout.fillWidth: true
                                Layout.preferredHeight: recommendationColumn.implicitHeight + 16
                                radius: 8; color: theme.surfaceSoft; border.color: theme.border
                                RowLayout {
                                    anchors.fill: parent; anchors.margins: 8; spacing: 8
                                    Label {
                                        text: String(recommendationRow.index + 1)
                                        color: theme.accent
                                        padding: 6
                                        background: Rectangle { color: theme.accentSofter; radius: 12 }
                                    }
                                    ColumnLayout {
                                        id: recommendationColumn; Layout.fillWidth: true; spacing: 3
                                        Text { Layout.fillWidth: true; text: recommendationRow.modelData.title || recommendationRow.modelData.recordId; color: theme.text; font.bold: true; wrapMode: Text.Wrap }
                                        Text { Layout.fillWidth: true; text: root.stageLabel(recommendationRow.modelData.stage) + " · 推荐分 " + Number(recommendationRow.modelData.score || 0).toFixed(2) + " · " + String(recommendationRow.modelData.year || "年份未知"); color: theme.accent; font.pixelSize: 10 }
                                        Text { Layout.fillWidth: true; text: (recommendationRow.modelData.reasons || []).join("；"); color: theme.textMuted; wrapMode: Text.Wrap }
                                    }
                                    PillButton { text: recommendationRow.modelData.downloaded ? "开始阅读" : "回到文献库"; onClicked: root.paperRequested(String(recommendationRow.modelData.recordId || "")) }
                                }
                            }
                        }
                    }
                }
            }

            Rectangle {
                SplitView.preferredWidth: 440
                SplitView.minimumWidth: 360
                radius: 8; color: theme.surface; border.color: theme.border
                ScrollView {
                    anchors.fill: parent; anchors.margins: 10; contentWidth: availableWidth
                    ScrollBar.vertical: StyledScrollBar { policy: ScrollBar.AsNeeded }
                    ColumnLayout {
                        width: parent.width; spacing: 8
                        Text { text: "推荐阅读路径"; color: theme.text; font.bold: true; font.pixelSize: 18 }
                        Text { Layout.fillWidth: true; text: ((root.analysis.readingPaths || [])[0] || {}).explanation || "当前证据不足，尚未形成阅读路径。"; color: theme.textMuted; wrapMode: Text.Wrap }
                        Repeater {
                            model: (((root.analysis.readingPaths || [])[0] || {}).steps || [])
                            delegate: Rectangle {
                                id: pathStep
                                required property var modelData
                                Layout.fillWidth: true
                                Layout.preferredHeight: pathColumn.implicitHeight + 14
                                radius: 7; color: theme.surfaceSoft; border.color: theme.border
                                ColumnLayout {
                                    id: pathColumn; anchors.fill: parent; anchors.margins: 7; spacing: 3
                                    Text { Layout.fillWidth: true; text: "第 " + Number(pathStep.modelData.step || 0) + " 步 · " + root.stageLabel(pathStep.modelData.stage); color: theme.accent; font.bold: true }
                                    Text { Layout.fillWidth: true; text: pathStep.modelData.title || pathStep.modelData.recordId; color: theme.text; font.bold: true; wrapMode: Text.Wrap }
                                    Text { Layout.fillWidth: true; text: (pathStep.modelData.transition || {}).explanation || ""; color: theme.textMuted; wrapMode: Text.Wrap }
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    function displayEntities() {
        return viewMode === "institutions" ? (analysis.institutions || []) : (analysis.authors || [])
    }

    function displayLinks() {
        return viewMode === "institutions" ? (analysis.institutionLinks || []) : (analysis.authorLinks || [])
    }

    function stageLabel(stage) {
        return ({ foundation: "基础论文", bridge: "跨主题桥梁", frontier: "前沿研究" })[String(stage || "")] || "补充阅读"
    }
}
