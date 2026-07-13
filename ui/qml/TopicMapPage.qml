pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: root

    property var records: []
    property string title: "领域主题地图"
    property string viewMode: "topics"
    property bool playbackRunning: false
    property bool applyTimeFilterToTopics: true
    property string selectedEvolutionPaperId: ""
    property int speedTopicAIndex: 0
    property int speedTopicBIndex: 1
    readonly property var canonicalSelectedTopic: topicMapController.selectedTopic || ({})
    readonly property var selectedTopic: root.displayTopic()
    readonly property var selectedEvolutionPaper: root.paperForId(root.selectedEvolutionPaperId)
    signal backRequested()
    signal graphRequested(string topicId, var paperIds)
    signal evolutionGraphRequested(int startYear, int endYear, string selectedPaperId)
    signal analysisGraphRequested(string mode)
    signal researchGraphRequested(string mode)
    signal recommendationRequested(string recordId)

    Theme { id: theme }
    onVisibleChanged: { if (!root.visible) root.playbackRunning = false }

    Timer {
        interval: 1200
        repeat: true
        running: root.playbackRunning
        onTriggered: {
            if (!topicMapController.advanceEvolutionPlayback())
                root.playbackRunning = false
        }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 9

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 64
            radius: theme.radiusMedium
            color: theme.surface
            border.color: theme.border
            RowLayout {
                anchors.fill: parent
                anchors.margins: 10
                spacing: 9
                PillButton { text: "返回文献库"; onClicked: root.backRequested() }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 1
                    Text { Layout.fillWidth: true; text: root.title; color: theme.text; font.bold: true; font.pixelSize: 19; elide: Text.ElideRight }
                    Text {
                        Layout.fillWidth: true
                        text: root.viewMode === "topics"
                              ? Number(topicMapController.topicMap.clusterCount || 0) + " 个主题 · "
                                + Number(topicMapController.topicMap.analyzedPaperCount || 0) + " 篇论文 · 基于关键词、语义实体和馆藏引文"
                              : root.viewMode === "timeline" ? Number((topicMapController.evolution.yearRange || {}).knownYearCount || 0) + " 篇有年份 · "
                                + Number((topicMapController.evolution.diagnostics || {}).validCitationCount || 0) + " 条有效引文 · "
                                + Number((topicMapController.evolution.diagnostics || {}).keyPathCount || 0) + " 条关键路径"
                              : root.viewMode === "analysis" ? Number((topicMapController.networkAnalysis.coverage || {}).citationLinkCount || 0) + " 条真实引文 · "
                                + Number(((topicMapController.networkAnalysis.keywordNetwork || {}).nodes || []).length) + " 个关键词 · "
                                + Number((topicMapController.networkAnalysis.bursts || []).length) + " 个突现趋势"
                              : Number((topicMapController.researchNetwork.authors || []).length) + " 位作者 · "
                                + Number((topicMapController.researchNetwork.institutions || []).length) + " 个机构 · "
                                + Number((topicMapController.researchNetwork.recommendations || []).length) + " 篇阅读建议"
                        color: theme.textMuted
                        font.pixelSize: 11
                        elide: Text.ElideRight
                    }
                }
                PillButton { text: "主题地图"; primary: root.viewMode === "topics"; onClicked: { root.playbackRunning = false; root.viewMode = "topics" } }
                PillButton { text: "时间演化"; primary: root.viewMode === "timeline"; onClicked: root.viewMode = "timeline" }
                PillButton { text: "结构分析"; primary: root.viewMode === "analysis"; onClicked: { root.playbackRunning = false; root.viewMode = "analysis" } }
                PillButton { text: "研究者与阅读"; primary: root.viewMode === "research"; onClicked: { root.playbackRunning = false; root.viewMode = "research" } }
                PillButton {
                    visible: root.viewMode === "topics" && root.timeWindowActive()
                    text: root.applyTimeFilterToTopics ? "主题图：时间窗口" : "主题图：全部论文"
                    primary: root.applyTimeFilterToTopics
                    onClicked: root.applyTimeFilterToTopics = !root.applyTimeFilterToTopics
                }
                BusyIndicator { running: topicMapController.loading; visible: running; Layout.preferredWidth: 28; Layout.preferredHeight: 28 }
                PillButton {
                    text: topicMapController.loading ? "取消分析" : "重新分析"
                    enabled: root.records.length > 0
                    onClicked: {
                        root.playbackRunning = false
                        if (topicMapController.loading)
                            topicMapController.cancel()
                        else
                            topicMapController.regenerateForRecords(root.records)
                    }
                }
            }
        }

        SplitView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: root.viewMode === "topics"
            orientation: Qt.Horizontal

            Rectangle {
                SplitView.fillWidth: true
                SplitView.minimumWidth: 520
                radius: theme.radiusMedium
                color: theme.canvas
                border.color: theme.border

                TopicBubbleMap {
                    anchors.fill: parent
                    anchors.margins: 8
                    topics: root.useFilteredTopics() ? topicMapController.windowTopics : topicMapController.topics
                    topicLinks: (topicMapController.topicMap || {}).topicLinks || []
                    selectedTopicId: String(root.selectedTopic.id || "")
                    onTopicRequested: function(topicId) { topicMapController.selectTopic(topicId) }
                }

                Rectangle {
                    anchors.left: parent.left
                    anchors.bottom: parent.bottom
                    anchors.margins: 15
                    width: legendRow.implicitWidth + 18
                    height: 30
                    radius: 8
                    color: theme.surfaceElevated
                    border.color: theme.border
                    Row {
                        id: legendRow
                        anchors.centerIn: parent
                        spacing: 10
                        Text { text: "气泡大小 = 论文数"; color: theme.textMuted; font.pixelSize: 10 }
                        Text { text: "颜色 = 不同主题"; color: theme.accent; font.pixelSize: 10 }
                        Text { text: "连线/百分比 = 主题相似度"; color: theme.info; font.pixelSize: 10 }
                        Text { text: "透明 = 低置信度"; color: theme.warning; font.pixelSize: 10 }
                    }
                }
            }

            Rectangle {
                SplitView.preferredWidth: 410
                SplitView.minimumWidth: 340
                radius: theme.radiusMedium
                color: theme.surface
                border.color: theme.border

                ScrollView {
                    anchors.fill: parent
                    anchors.margins: 12
                    contentWidth: availableWidth
                    ScrollBar.vertical: StyledScrollBar { policy: ScrollBar.AsNeeded }
                    ColumnLayout {
                        width: parent.width
                        spacing: 10

                        Text {
                            Layout.fillWidth: true
                            text: root.selectedTopic.name || "选择气泡查看主题"
                            color: theme.text
                            font.bold: true
                            font.pixelSize: 20
                            wrapMode: Text.Wrap
                        }
                        RowLayout {
                            visible: !!root.selectedTopic.id
                            Label {
                                text: Number(root.selectedTopic.size || 0) + " 篇"
                                color: theme.accent
                                background: Rectangle { color: theme.accentSofter; radius: 7 }
                                padding: 5
                            }
                            Text { text: "占比 " + Math.round(Number(root.selectedTopic.share || 0) * 100) + "%"; color: theme.textMuted }
                            Text { text: "内聚度 " + Number(root.selectedTopic.cohesion || 0).toFixed(2); color: theme.textMuted }
                            Text { text: String((root.selectedTopic.growth || {}).label || "年份不足"); color: root.growthColor((root.selectedTopic.growth || {}).trend) }
                        }
                        Text {
                            Layout.fillWidth: true
                            visible: !!root.selectedTopic.id
                            text: root.selectedTopic.yearStart
                                  ? "时间范围 " + root.selectedTopic.yearStart + "–" + root.selectedTopic.yearEnd
                                    + " · 最近窗口 " + Number((root.selectedTopic.growth || {}).recentCount || 0)
                                    + " 篇 / 前一窗口 " + Number((root.selectedTopic.growth || {}).previousCount || 0) + " 篇"
                                  : "时间范围：年份数据不足"
                            color: theme.textMuted
                            wrapMode: Text.Wrap
                        }
                        PillButton {
                            Layout.fillWidth: true
                            visible: !!root.selectedTopic.id
                            text: "进入该主题的局部图谱"
                            primary: true
                            enabled: (root.selectedTopic.paperIds || []).length > 0
                            onClicked: root.graphRequested(String(root.selectedTopic.id || ""), root.selectedTopic.paperIds || [])
                        }

                        Text { visible: !!root.selectedTopic.id; text: "为什么形成该主题"; color: theme.text; font.bold: true }
                        Text {
                            Layout.fillWidth: true
                            visible: !!root.selectedTopic.id
                            text: (root.selectedTopic.explanation || {}).method || ""
                            color: theme.textMuted
                            wrapMode: Text.Wrap
                        }
                        Repeater {
                            model: (root.selectedTopic.explanation || {}).reasons || []
                            delegate: Text {
                                required property var modelData
                                Layout.fillWidth: true
                                text: "• " + String(modelData)
                                color: theme.textMuted
                                wrapMode: Text.Wrap
                            }
                        }

                        Text { visible: (root.selectedTopic.topTerms || []).length > 0; text: "核心主题词"; color: theme.text; font.bold: true }
                        Repeater {
                            model: root.selectedTopic.topTerms || []
                            delegate: Rectangle {
                                required property var modelData
                                Layout.fillWidth: true
                                Layout.preferredHeight: 34
                                radius: 7
                                color: theme.surfaceSoft
                                border.color: theme.border
                                RowLayout {
                                    anchors.fill: parent
                                    anchors.margins: 7
                                    Text { Layout.fillWidth: true; text: modelData.label || modelData.term; color: theme.text; elide: Text.ElideRight }
                                    Text { text: Number(modelData.paperCount || 0) + " 篇"; color: theme.textMuted }
                                    Text { text: Number(modelData.weight || 0).toFixed(2); color: theme.accent }
                                }
                            }
                        }

                        Text { visible: (root.selectedTopic.subtopics || []).length > 0; text: "子主题"; color: theme.text; font.bold: true }
                        Repeater {
                            model: root.selectedTopic.subtopics || []
                            delegate: Text {
                                required property var modelData
                                Layout.fillWidth: true
                                text: "↳ " + String(modelData.name || "") + " · " + Number(modelData.count || 0) + " 篇"
                                color: theme.textMuted
                                wrapMode: Text.Wrap
                            }
                        }

                        Text { visible: (root.selectedTopic.representativeAuthors || []).length > 0; text: "代表作者"; color: theme.text; font.bold: true }
                        Repeater {
                            model: root.selectedTopic.representativeAuthors || []
                            delegate: Text {
                                required property var modelData
                                Layout.fillWidth: true
                                text: String(modelData.name || "") + " · " + Number(modelData.paperCount || 0) + " 篇\n" + String(modelData.reason || "")
                                color: theme.textMuted
                                wrapMode: Text.Wrap
                            }
                        }

                        Text { visible: (root.selectedTopic.yearlyCounts || []).length > 0; text: "年度分布"; color: theme.text; font.bold: true }
                        RowLayout {
                            Layout.fillWidth: true
                            visible: (root.selectedTopic.yearlyCounts || []).length > 0
                            spacing: 3
                            Repeater {
                                model: root.selectedTopic.yearlyCounts || []
                                delegate: ColumnLayout {
                                    required property var modelData
                                    Layout.fillWidth: true
                                    spacing: 2
                                    Item { Layout.fillHeight: true }
                                    Rectangle {
                                        Layout.alignment: Qt.AlignHCenter
                                        Layout.preferredWidth: Math.max(5, parent.width - 4)
                                        Layout.preferredHeight: Math.max(5, Math.min(56, Number(modelData.count || 0) * 11))
                                        color: theme.accent
                                        radius: 3
                                    }
                                    Text { Layout.alignment: Qt.AlignHCenter; text: String(modelData.year || "").slice(-2); color: theme.textMuted; font.pixelSize: 8 }
                                }
                            }
                        }

                        Text { visible: (root.selectedTopic.representativePapers || []).length > 0; text: "代表论文"; color: theme.text; font.bold: true }
                        Repeater {
                            model: root.selectedTopic.representativePapers || []
                            delegate: Rectangle {
                                required property var modelData
                                Layout.fillWidth: true
                                Layout.preferredHeight: representativeColumn.implicitHeight + 14
                                radius: 7
                                color: theme.surfaceSoft
                                border.color: theme.border
                                ColumnLayout {
                                    id: representativeColumn
                                    anchors.fill: parent
                                    anchors.margins: 7
                                    Text { Layout.fillWidth: true; text: modelData.title || modelData.recordId; color: theme.text; font.bold: true; wrapMode: Text.Wrap; maximumLineCount: 2; elide: Text.ElideRight }
                                    Text { Layout.fillWidth: true; text: (modelData.year ? modelData.year + " · " : "") + (modelData.reason || ""); color: theme.textMuted; wrapMode: Text.Wrap }
                                }
                            }
                        }

                        Text { visible: root.assignmentsForTopic().length > 0; text: "论文归类依据"; color: theme.text; font.bold: true }
                        Repeater {
                            model: root.assignmentsForTopic().slice(0, 20)
                            delegate: Text {
                                required property var modelData
                                Layout.fillWidth: true
                                text: root.recordTitle(modelData.recordId) + "\n" + (modelData.reasons || []).join("；")
                                color: theme.textMuted
                                wrapMode: Text.Wrap
                            }
                        }
                    }
                }
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: root.viewMode === "timeline"
            spacing: 8

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 52
                radius: theme.radiusMedium
                color: theme.surface
                border.color: theme.border
                RowLayout {
                    anchors.fill: parent
                    anchors.margins: 8
                    spacing: 8
                    Text { text: "时间范围"; color: theme.text; font.bold: true }
                    StyledComboBox {
                        id: startYearBox
                        Layout.preferredWidth: 105
                        model: topicMapController.evolutionYears
                        currentIndex: Math.max(0, model.indexOf(Number(topicMapController.evolutionRange.start || 0)))
                        onActivated: topicMapController.setEvolutionRange(Number(currentText), Number(endYearBox.currentText))
                    }
                    Text { text: "至"; color: theme.textMuted }
                    StyledComboBox {
                        id: endYearBox
                        Layout.preferredWidth: 105
                        model: topicMapController.evolutionYears
                        currentIndex: Math.max(0, model.indexOf(Number(topicMapController.evolutionRange.end || 0)))
                        onActivated: topicMapController.setEvolutionRange(Number(startYearBox.currentText), Number(currentText))
                    }
                    PillButton { text: "全部年份"; onClicked: topicMapController.resetEvolutionRange() }
                    Rectangle { Layout.preferredWidth: 1; Layout.fillHeight: true; color: theme.divider }
                    PillButton {
                        text: root.playbackRunning ? "暂停" : "播放演化"
                        enabled: topicMapController.evolutionYears.length > 0
                        primary: root.playbackRunning
                        onClicked: {
                            if (root.playbackRunning) {
                                root.playbackRunning = false
                            } else {
                                if (Number(topicMapController.evolutionRange.playbackYear || 0) >= Number(topicMapController.evolutionRange.end || 0))
                                    topicMapController.startEvolutionPlayback()
                                root.playbackRunning = true
                            }
                        }
                    }
                    PillButton { text: "从头"; enabled: topicMapController.evolutionYears.length > 0; onClicked: { root.playbackRunning = false; topicMapController.startEvolutionPlayback() } }
                    Label {
                        text: "当前 " + Number(topicMapController.evolutionRange.playbackYear || 0) + " 年"
                        color: theme.accent
                        background: Rectangle { color: theme.accentSofter; radius: 7 }
                        padding: 5
                    }
                    Item { Layout.fillWidth: true }
                    PillButton {
                        text: "查看当前时间窗口图谱"
                        primary: true
                        enabled: topicMapController.visibleEvolutionEvents.length > 0
                        onClicked: root.evolutionGraphRequested(Number(topicMapController.evolutionRange.start || 0), root.effectiveEvolutionEnd(), root.selectedEvolutionPaperId)
                    }
                }
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 38
                radius: 8
                color: theme.surfaceSoft
                border.color: theme.border
                RowLayout {
                    anchors.fill: parent
                    anchors.margins: 6
                    spacing: 7
                    Text { text: "窗口主题"; color: theme.text; font.bold: true; font.pixelSize: 10 }
                    Repeater {
                        model: topicMapController.windowTopicStats.slice(0, 8)
                        delegate: Label {
                            required property var modelData
                            text: String(modelData.name || "待归类") + " " + Number(modelData.count || 0)
                            color: theme.textMuted
                            background: Rectangle { color: theme.surface; radius: 6; border.color: theme.border }
                            padding: 4
                        }
                    }
                    Item { Layout.fillWidth: true }
                    Text { text: "◆ 转折 · + 年度新增 · 代表 = 年度关键分最高"; color: theme.textMuted; font.pixelSize: 10 }
                    Text {
                        text: "缺失年份 " + Number((topicMapController.evolution.yearRange || {}).missingYearCount || 0)
                              + " · 时间冲突引文 " + Number((topicMapController.evolution.diagnostics || {}).chronologyConflictCount || 0)
                              + " · 同年循环降级 " + Number((topicMapController.evolution.diagnostics || {}).sameYearCycleBreakCount || 0)
                              + " · 分裂/合并/衰退信号 "
                              + (Number((topicMapController.evolution.diagnostics || {}).splitSignalCount || 0)
                                 + Number((topicMapController.evolution.diagnostics || {}).mergeSignalCount || 0)
                                 + Number((topicMapController.evolution.diagnostics || {}).declineSignalCount || 0))
                        color: Number((topicMapController.evolution.diagnostics || {}).chronologyConflictCount || 0) > 0 ? theme.warning : theme.textMuted
                        font.pixelSize: 10
                    }
                }
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 48
                radius: 8
                color: theme.surface
                border.color: theme.border
                RowLayout {
                    anchors.fill: parent
                    anchors.margins: 6
                    Text { text: "比较两个主题的发展速度"; color: theme.text; font.bold: true }
                    StyledComboBox {
                        Layout.preferredWidth: 210
                        model: topicMapController.evolution.topicSeries || []
                        textRole: "name"
                        currentIndex: Math.min(root.speedTopicAIndex, Math.max(0, count - 1))
                        onActivated: function(index) { root.speedTopicAIndex = index }
                    }
                    Text { text: "与"; color: theme.textMuted }
                    StyledComboBox {
                        Layout.preferredWidth: 210
                        model: topicMapController.evolution.topicSeries || []
                        textRole: "name"
                        currentIndex: Math.min(root.speedTopicBIndex, Math.max(0, count - 1))
                        onActivated: function(index) { root.speedTopicBIndex = index }
                    }
                    Text {
                        Layout.fillWidth: true
                        text: root.speedComparisonExplanation()
                        color: theme.accent
                        elide: Text.ElideRight
                        ToolTip.visible: speedCompareMouse.containsMouse
                        ToolTip.text: text
                        MouseArea { id: speedCompareMouse; anchors.fill: parent; hoverEnabled: true }
                    }
                }
            }

            EvolutionTimeline {
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.minimumHeight: 260
                events: topicMapController.visibleEvolutionEvents
                playbackYear: Number(topicMapController.evolutionRange.playbackYear || 0)
                selectedPaperId: root.selectedEvolutionPaperId
                onYearRequested: function(year) { root.playbackRunning = false; topicMapController.setEvolutionPlaybackYear(year) }
                onPaperRequested: function(recordId) { root.selectedEvolutionPaperId = recordId }
            }

            SplitView {
                Layout.fillWidth: true
                Layout.preferredHeight: 220
                orientation: Qt.Horizontal

                Rectangle {
                    SplitView.fillWidth: true
                    SplitView.minimumWidth: 360
                    radius: 8
                    color: theme.surface
                    border.color: theme.border
                    RowLayout {
                        anchors.fill: parent
                        anchors.margins: 8
                        spacing: 8
                        ScrollView {
                            Layout.preferredWidth: 260
                            Layout.fillHeight: true
                            contentWidth: availableWidth
                            ScrollBar.vertical: StyledScrollBar { policy: ScrollBar.AsNeeded }
                            ColumnLayout {
                                width: parent.width
                                Text { text: "关键引文路径"; color: theme.text; font.bold: true }
                                Repeater {
                                    model: topicMapController.evolution.keyPaths || []
                                    delegate: PillButton {
                                        required property var modelData
                                        Layout.fillWidth: true
                                        text: Number(modelData.length || 0) + " 篇 · " + Number(modelData.yearSpan || 0) + " 年跨度"
                                        primary: String(modelData.id || "") === String(topicMapController.selectedEvolutionPath.id || "")
                                        onClicked: topicMapController.selectEvolutionPath(String(modelData.id || ""))
                                        ToolTip.visible: hovered
                                        ToolTip.text: modelData.label || ""
                                    }
                                }
                                Text { visible: (topicMapController.evolution.keyPaths || []).length === 0; text: "没有足够的真实有向引文形成路径"; color: theme.textMuted; wrapMode: Text.Wrap }
                            }
                        }
                        Rectangle { Layout.preferredWidth: 1; Layout.fillHeight: true; color: theme.divider }
                        ColumnLayout {
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            Text { Layout.fillWidth: true; text: topicMapController.selectedEvolutionPath.label || "选择路径查看解释"; color: theme.text; font.bold: true; wrapMode: Text.Wrap }
                            Text { Layout.fillWidth: true; text: topicMapController.selectedEvolutionPath.explanation || ""; color: theme.textMuted; wrapMode: Text.Wrap }
                            Text {
                                Layout.fillWidth: true
                                visible: (topicMapController.selectedEvolutionPath.paperIds || []).length > 0
                                text: (topicMapController.selectedEvolutionPath.displayPaperIds || topicMapController.selectedEvolutionPath.paperIds || []).map(function(id) { return root.recordTitle(id) }).join("  →  ")
                                      + (topicMapController.selectedEvolutionPath.displayTruncated ? "  …（完整路径见分析数据）" : "")
                                color: theme.accent
                                wrapMode: Text.Wrap
                            }
                            Item { Layout.fillHeight: true }
                        }
                    }
                }

                Rectangle {
                    SplitView.preferredWidth: 390
                    SplitView.minimumWidth: 320
                    radius: 8
                    color: theme.surface
                    border.color: theme.border
                    ScrollView {
                        anchors.fill: parent
                        anchors.margins: 8
                        contentWidth: availableWidth
                        ScrollBar.vertical: StyledScrollBar { policy: ScrollBar.AsNeeded }
                        ColumnLayout {
                            width: parent.width
                            spacing: 6
                            Text { text: root.selectedEvolutionPaper.recordId ? "论文演化角色" : "关键转折点"; color: theme.text; font.bold: true }
                            Text { Layout.fillWidth: true; visible: !!root.selectedEvolutionPaper.recordId; text: root.selectedEvolutionPaper.title || root.selectedEvolutionPaper.recordId; color: theme.text; font.bold: true; wrapMode: Text.Wrap }
                            Text { Layout.fillWidth: true; visible: !!root.selectedEvolutionPaper.recordId; text: (root.selectedEvolutionPaper.reasons || []).join("；"); color: theme.textMuted; wrapMode: Text.Wrap }
                            PillButton { visible: !!root.selectedEvolutionPaper.recordId; text: "清除论文选择"; onClicked: root.selectedEvolutionPaperId = "" }
                            Repeater {
                                model: root.selectedEvolutionPaper.recordId ? [] : root.visibleTurningPoints().slice(0, 12)
                                delegate: Text {
                                    required property var modelData
                                    Layout.fillWidth: true
                                    text: String(modelData.year || "") + " · " + String(modelData.title || "") + "\n" + String(modelData.explanation || "")
                                    color: theme.textMuted
                                    wrapMode: Text.Wrap
                                }
                            }
                        }
                    }
                }
            }
        }

        NetworkAnalysisView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: root.viewMode === "analysis"
            analysis: topicMapController.networkAnalysis
            onGraphRequested: function(mode) { root.analysisGraphRequested(mode) }
        }

        ResearchInsightsView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: root.viewMode === "research"
            analysis: topicMapController.researchNetwork
            onGraphRequested: function(mode) { root.researchGraphRequested(mode) }
            onPaperRequested: function(recordId) { root.recommendationRequested(recordId) }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 36
            radius: 8
            color: topicMapController.state === "error" ? theme.errorSoft : theme.surface
            border.color: theme.border
            Text { anchors.fill: parent; anchors.margins: 8; text: topicMapController.statusText; color: topicMapController.state === "error" ? theme.error : theme.textMuted; elide: Text.ElideRight; verticalAlignment: Text.AlignVCenter }
        }
    }

    Rectangle {
        anchors.fill: parent
        visible: topicMapController.loading
        z: 20
        color: theme.dark ? "#99000000" : "#99ffffff"
        Column {
            anchors.centerIn: parent
            spacing: 10
            BusyIndicator { anchors.horizontalCenter: parent.horizontalCenter; running: parent.parent.visible }
            Text { text: topicMapController.statusText; color: theme.text; font.bold: true }
        }
    }

    function assignmentsForTopic() {
        var assignments = topicMapController.topicMap.assignments || []
        var topicId = String(root.selectedTopic.id || "")
        return assignments.filter(function(item) { return String(item.topicId || "") === topicId })
    }

    function effectiveEvolutionEnd() {
        return Math.min(Number(topicMapController.evolutionRange.end || 0), Number(topicMapController.evolutionRange.playbackYear || 0))
    }

    function timeWindowActive() {
        var range = topicMapController.evolutionRange || ({})
        return Number(range.start || 0) > Number(range.minimum || 0)
               || Number(range.end || 0) < Number(range.maximum || 0)
               || Number(range.playbackYear || 0) < Number(range.end || 0)
    }

    function useFilteredTopics() {
        return root.applyTimeFilterToTopics && root.timeWindowActive()
    }

    function displayTopic() {
        var selected = root.canonicalSelectedTopic || ({})
        if (!root.useFilteredTopics())
            return selected
        var topics = topicMapController.windowTopics || []
        for (var i = 0; i < topics.length; ++i)
            if (String(topics[i].id || "") === String(selected.id || ""))
                return topics[i]
        return selected
    }

    function visibleTurningPoints() {
        var start = Number(topicMapController.evolutionRange.start || 0)
        var end = root.effectiveEvolutionEnd()
        return (topicMapController.evolution.turningPoints || []).filter(function(item) {
            var year = Number(item.year || 0)
            return year >= start && year <= end
        })
    }

    function speedComparisonExplanation() {
        var series = topicMapController.evolution.topicSeries || []
        if (series.length < 2) return "至少需要两个有年份数据的主题"
        var left = series[Math.min(root.speedTopicAIndex, series.length - 1)]
        var right = series[Math.min(root.speedTopicBIndex, series.length - 1)]
        if (String(left.topicId || "") === String(right.topicId || "")) return "请选择两个不同主题"
        var comparisons = topicMapController.evolution.topicSpeedComparisons || []
        for (var i = 0; i < comparisons.length; ++i) {
            var item = comparisons[i]
            if ((String(item.leftTopicId) === String(left.topicId) && String(item.rightTopicId) === String(right.topicId))
                    || (String(item.leftTopicId) === String(right.topicId) && String(item.rightTopicId) === String(left.topicId)))
                return String(item.explanation || "")
        }
        return "没有可比较的速度数据"
    }

    function paperForId(recordId) {
        var papers = topicMapController.evolution.papers || []
        for (var i = 0; i < papers.length; ++i)
            if (String(papers[i].recordId || "") === String(recordId || ""))
                return papers[i]
        return ({})
    }

    function recordTitle(recordId) {
        for (var i = 0; i < root.records.length; ++i)
            if (String(root.records[i].recordId || root.records[i].id || "") === String(recordId || ""))
                return String(root.records[i].title || recordId)
        return String(recordId || "论文")
    }

    function growthColor(trend) {
        var value = String(trend || "unknown")
        if (value === "growing") return theme.success
        if (value === "declining") return theme.warning
        return theme.textMuted
    }
}
