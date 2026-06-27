import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: root
    property var tourHost: null

    property int selectedIndex: literatureList.currentIndex
    property string selectedRecordId: ""
    property var selectedRecord: ({})
    property var selectedDetails: ({})
    property string thumbnailUrl: ""
    property string thumbnailState: "missing_pdf"
    property string previewUrl: ""
    property string previewState: "missing_pdf"
    property real previewZoom: 1.0
    property var selectedKeywordGroups: []
    property bool readerOpen: false
    property string readerRecordId: ""
    property string readerPdfPath: ""
    property string readerTitle: ""
    property real readerLastZoom: 1.0
    property string readerReturnTarget: ""
    property bool graphOpen: false
    property string graphRecordId: ""
    property string graphPdfPath: ""
    property string graphTitle: ""
    property var graphRecord: ({})
    property bool graphReturnToCompare: false
    property bool graphIsComparison: false
    property var graphComparisonRecords: []
    property bool wordCloudOpen: false
    property bool wordCloudReturnToReader: false
    property string wordCloudRecordId: ""
    property string wordCloudTitle: ""
    property string wordCloudScope: "record"
    property var wordCloudRecord: ({})
    property var wordCloudRecords: []
    property bool libraryFiltersOpen: false
    property bool libraryToolsOpen: false
    property string pendingGraphKeyword: ""
    property string pendingGraphNodeId: ""

    readonly property var relevanceValues: ["all", "keyword_only", "loose", "balanced", "strict", "very_strict"]
    readonly property var statusValues: ["all", "downloaded", "no_candidate", "failed", "not_open_access", "not_pdf", "request_error"]
    readonly property var sortValues: ["relevance_desc", "relevance_asc", "year_desc", "year_asc", "downloaded_first", "title_asc"]
    readonly property var sortLabels: ["相关性 高→低", "相关性 低→高", "年份 新→旧", "年份 旧→新", "已下载优先", "标题 A-Z"]
    readonly property var journalTypeValues: ["all", "flagship", "field_journal", "review_journal", "oa_journal", "preprint", "conference", "unknown"]
    readonly property var journalTypeLabels: ["全部期刊类型", "综合/高影响力", "专业领域", "综述类", "开放获取", "预印本", "会议/论文集", "未识别"]
    readonly property var relevanceLabels: ["全部相关性", "关键词提及即可", "宽松及以上", "均衡及以上", "严格及以上", "极严格"]
    readonly property var statusLabels: ["全部 PDF 状态", "已下载", "无候选", "下载失败", "非开放获取", "非 PDF", "请求失败"]

    Motion { id: motion }
    I18n { id: i18n }
    Theme { id: theme }
    LayoutMetrics { id: metrics; viewportWidth: root.width; viewportHeight: root.height }

    Component.onCompleted: root.registerTourTargets()
    Component.onDestruction: root.unregisterTourTargets()

    onVisibleChanged: {
        if(visible && !literatureLibraryController.hasLoaded && !literatureLibraryController.loading)
            literatureLibraryController.ensureLoaded()
    }

    Connections {
        target: literatureLibraryController
        function onChanged() {
            if(literatureLibraryController.records.length > 0 && literatureList.currentIndex < 0)
                literatureList.currentIndex = 0
            else if(literatureList.currentIndex >= literatureLibraryController.records.length)
                literatureList.currentIndex = literatureLibraryController.records.length > 0 ? 0 : -1
            root.syncSelectedRecordFromIndex()
            root.updateSelection()
        }
        function onThumbnailReady(recordId, url) {
            if(recordId === root.selectedRecordId) {
                root.thumbnailState = literatureLibraryController.thumbnailStateFor(recordId)
                root.thumbnailUrl = url || ""
            }
        }
        function onPreviewReady(recordId, url) {
            if(previewPopup.opened && recordId === root.selectedRecordId) {
                root.previewState = literatureLibraryController.previewStateFor(recordId)
                root.previewUrl = url || ""
            }
        }
    }

    Connections {
        target: knowledgeGraphController
        function onGraphReady(recordId) {
            if (recordId === root.graphRecordId) {
                var selected = false
                if (root.pendingGraphNodeId)
                    selected = knowledgeGraphController.selectNode(root.pendingGraphNodeId)
                if (!selected && root.pendingGraphKeyword)
                    knowledgeGraphController.search(root.pendingGraphKeyword)
                root.pendingGraphNodeId = ""
                root.pendingGraphKeyword = ""
            }
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: metrics.pageMargin
        spacing: metrics.sectionSpacing
        visible: !root.readerOpen && !root.graphOpen && !root.wordCloudOpen

        PageHeading {
            Layout.fillWidth: true
            title: "文献库"
            subtitle: "查看、筛选、预览和按相关性整理已下载文献。相关性等级用于整理文献，不代表论文质量。"
            titleSize: metrics.headingSize
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: libraryToolbarContent.implicitHeight + 20
            radius: theme.radiusMedium
            color: theme.surface
            border.color: theme.border
            clip: true

            ColumnLayout {
                id: libraryToolbarContent
                anchors.fill: parent
                anchors.margins: 10
                spacing: 8

                Flow {
                    Layout.fillWidth: true
                    spacing: 8
                    width: parent.width
                    TextField {
                        id: query
                        width: Math.min(360, Math.max(220, parent.width - 380))
                        placeholderText: "搜索标题、摘要、作者或 DOI"
                        selectByMouse: true
                        onTextChanged: root.applyFilters()
                    }
                    PillButton {
                        text: root.libraryFiltersOpen ? "收起筛选" : "筛选"
                        enabled: !literatureLibraryController.loading
                        onClicked: root.libraryFiltersOpen = !root.libraryFiltersOpen
                    }
                    Text {
                        text: "已筛选 " + literatureLibraryController.filteredCount + " / " + literatureLibraryController.totalCount
                        color: theme.textMuted
                        verticalAlignment: Text.AlignVCenter
                    }
                    PillButton {
                        text: literatureLibraryController.loading && literatureLibraryController.busyAction === "refresh" ? "刷新中..." : i18n.text("refresh")
                        enabled: !literatureLibraryController.loading
                        onClicked: literatureLibraryController.refresh()
                    }
                    PillButton {
                        text: root.libraryToolsOpen ? "收起更多" : "更多"
                        enabled: !literatureLibraryController.loading
                        onClicked: root.libraryToolsOpen = !root.libraryToolsOpen
                    }
                }

                GridLayout {
                    Layout.fillWidth: true
                    visible: root.libraryFiltersOpen
                    columns: metrics.narrow ? 1 : 3
                    columnSpacing: 8
                    rowSpacing: 8
                    ComboBox {
                        id: relevanceFilter
                        Layout.fillWidth: true
                        model: root.relevanceLabels
                        currentIndex: 0
                        enabled: !literatureLibraryController.loading
                        onCurrentIndexChanged: root.applyFilters()
                    }
                    ComboBox {
                        id: pdfStatusFilter
                        Layout.fillWidth: true
                        model: root.statusLabels
                        currentIndex: 0
                        enabled: !literatureLibraryController.loading
                        onCurrentIndexChanged: root.applyFilters()
                    }
                    ComboBox {
                        id: sortFilter
                        Layout.fillWidth: true
                        model: root.sortLabels
                        currentIndex: 0
                        enabled: !literatureLibraryController.loading
                        onCurrentIndexChanged: root.applyFilters()
                    }
                    ComboBox {
                        id: journalTypeFilter
                        Layout.fillWidth: true
                        model: root.journalTypeLabels
                        currentIndex: 0
                        enabled: !literatureLibraryController.loading
                        onCurrentIndexChanged: root.applyFilters()
                    }
                    ComboBox {
                        id: projectFilter
                        Layout.fillWidth: true
                        model: root.favoriteProjectFilterLabels()
                        currentIndex: 0
                        enabled: !literatureLibraryController.loading
                        onCurrentIndexChanged: root.applyFilters()
                    }
                    PillButton {
                        id: keywordGroupButton
                        text: root.selectedKeywordGroupsText()
                        enabled: !literatureLibraryController.loading && literatureLibraryController.keywordGroupOptions.length > 0
                        onClicked: keywordGroupPopup.open()
                        ModernToolTip {
                            placement: "bottom"
                            delay: 350
                            shown: parent.hovered && literatureLibraryController.keywordGroupOptions.length === 0
                            text: i18n.text("no_keyword_groups")
                        }
                    }
                }

                Flow {
                    Layout.fillWidth: true
                    visible: root.libraryToolsOpen
                    spacing: 8
                    width: parent.width
                    PillButton {
                        text: "新建收藏分类"
                        enabled: !literatureLibraryController.loading
                        onClicked: createProjectPopup.open()
                    }
                    PillButton {
                        text: literatureLibraryController.loading && literatureLibraryController.busyAction === "refresh" ? "刷新中..." : i18n.text("refresh")
                        visible: false
                        enabled: !literatureLibraryController.loading
                        onClicked: literatureLibraryController.refresh()
                    }
                    PillButton {
                        text: literatureLibraryController.loading && literatureLibraryController.busyAction === "recompute" ? "重算中..." : "重算相关性"
                        enabled: !literatureLibraryController.loading
                        onClicked: literatureLibraryController.recomputeRelevance()
                    }
                    PillButton {
                        text: literatureLibraryController.loading && literatureLibraryController.busyAction === "organize" ? "归档中..." : "按相关性归档"
                        enabled: !literatureLibraryController.loading
                        primary: true
                        onClicked: literatureLibraryController.organizeByRelevance()
                    }
                    PillButton {
                        text: knowledgeGraphController.loading && knowledgeGraphController.currentRecordId === "__batch__" ? "批量生成中..." : "批量生成图谱"
                        enabled: !knowledgeGraphController.loading && literatureLibraryController.records.length > 0
                        onClicked: knowledgeGraphController.generateGraphs(literatureLibraryController.records)
                    }
                    PillButton {
                        text: wordCloudController.loading && wordCloudController.currentScope === "library" ? "词云生成中..." : "筛选词云"
                        enabled: !wordCloudController.loading && literatureLibraryController.records.length > 0
                        onClicked: root.openLibraryWordCloud()
                    }
                    PillButton {
                        text: literatureLibraryController.loading && literatureLibraryController.busyAction === "preview_cleanup" ? "扫描中..." :
                              literatureLibraryController.loading && literatureLibraryController.busyAction === "confirm_cleanup" ? "删除中..." : "清理旧 PDF"
                        enabled: !literatureLibraryController.loading
                        onClicked: {
                            cleanupPopup.open()
                            literatureLibraryController.previewCleanup()
                        }
                    }
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: metrics.sectionSpacing

            Rectangle {
                id: libraryListPanel
                Layout.preferredWidth: Math.min(620, Math.max(460, root.width * 0.46))
                Layout.fillHeight: true
                radius: theme.radiusMedium
                color: theme.surface
                border.color: theme.border
                clip: true

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 10
                    spacing: 8

                    RowLayout {
                        Layout.fillWidth: true
                        Text {
                            Layout.fillWidth: true
                            text: "筛选结果 " + literatureLibraryController.filteredCount + " / " + literatureLibraryController.totalCount
                            color: theme.text
                            font.weight: Font.DemiBold
                        }
                        BusyIndicator {
                            Layout.preferredWidth: 24
                            Layout.preferredHeight: 24
                            running: literatureLibraryController.loading
                            visible: literatureLibraryController.loading
                        }
                        Text {
                            text: literatureLibraryController.loading && literatureLibraryController.progressText ? literatureLibraryController.progressText : literatureLibraryController.statusText
                            color: theme.textMuted
                            elide: Text.ElideRight
                            Layout.maximumWidth: 320
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        visible: literatureLibraryController.compareCount > 0
                        spacing: 8
                        Label {
                            text: "对比组 " + literatureLibraryController.compareCount + "/4"
                            color: theme.accent
                            background: Rectangle { color: theme.accentSofter; radius: 5 }
                            padding: 5
                        }
                        PillButton {
                            text: "查看对比"
                            onClicked: comparePopup.open()
                        }
                        PillButton {
                            text: "清空"
                            onClicked: literatureLibraryController.clearCompare()
                        }
                        Item { Layout.fillWidth: true }
                    }

                    ListView {
                        id: literatureList
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        model: literatureLibraryController.records
                        ScrollBar.vertical: ScrollBar {
                            policy: ScrollBar.AsNeeded
                        }
                        Component.onCompleted: {
                            if(count > 0) {
                                currentIndex = 0
                                root.syncSelectedRecordFromIndex()
                                root.updateSelection()
                            }
                        }
                        onCurrentIndexChanged: {
                            root.syncSelectedRecordFromIndex()
                            root.updateSelection()
                        }
                        delegate: Rectangle {
                            id: recordDelegate
                            property var record: modelData
                            width: literatureList.width
                            height: 148
                            radius: 8
                            color: ListView.isCurrentItem ? theme.navSelected : mouse.containsMouse ? theme.navHover : "transparent"
                            border.color: ListView.isCurrentItem ? theme.borderStrong : "transparent"

                            MouseArea {
                                id: mouse
                                anchors.fill: parent
                                hoverEnabled: true
                                onClicked: root.selectRecord(index, modelData)
                            }

                            ColumnLayout {
                                anchors.fill: parent
                                anchors.margins: 10
                                spacing: 5

                                Text {
                                    Layout.fillWidth: true
                                    text: modelData.title || "Untitled"
                                    color: theme.text
                                    font.weight: Font.DemiBold
                                    elide: Text.ElideRight
                                    maximumLineCount: 1
                                }
                                Text {
                                    Layout.fillWidth: true
                                    text: (modelData.authorsText || "Unknown authors") + "  ·  " + (modelData.publicationDate || modelData.year || "n.d.")
                                    color: theme.textMuted
                                    elide: Text.ElideRight
                                }
                                Text {
                                    Layout.fillWidth: true
                                    text: (modelData.journalTitle || "Unknown journal") + "  ·  " + (modelData.impactFactorText || "未知")
                                    color: theme.textMuted
                                    elide: Text.ElideRight
                                }
                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: 6
                                    Label {
                                        text: modelData.relevanceLabel || "未知"
                                        color: theme.accent
                                        background: Rectangle { color: theme.accentSofter; radius: 5 }
                                        padding: 5
                                    }
                                    Label {
                                        text: "分数 " + String(modelData.relevance_score || 0)
                                        visible: false
                                        color: theme.textSecondary
                                        background: Rectangle { color: theme.surfaceSoft; radius: 5 }
                                        padding: 5
                                    }
                                    Label {
                                        text: modelData.localPdfPath ? "已下载" : (modelData.pdfStatus || "unknown")
                                        color: modelData.localPdfPath ? theme.success : theme.warning
                                        background: Rectangle { color: theme.surfaceSoft; radius: 5 }
                                        padding: 5
                                    }
                                    Label {
                                        text: modelData.journalTypeLabel || "未识别"
                                        visible: false
                                        color: theme.textSecondary
                                        background: Rectangle { color: theme.surfaceSoft; radius: 5 }
                                        padding: 5
                                    }
                                    Label {
                                        property bool generated: {
                                            knowledgeGraphController.statusText
                                            return knowledgeGraphController.hasGraph(String(modelData.recordId || ""))
                                        }
                                        text: "图谱"
                                        visible: generated
                                        color: theme.success
                                        background: Rectangle { color: theme.surfaceSoft; radius: 5 }
                                        padding: 5
                                    }
                                    Label {
                                        property bool generated: {
                                            wordCloudController.statusText
                                            return wordCloudController.hasCloud(String(modelData.recordId || ""))
                                        }
                                        text: "词云"
                                        visible: generated
                                        color: theme.success
                                        background: Rectangle { color: theme.surfaceSoft; radius: 5 }
                                        padding: 5
                                    }
                                    Item { Layout.fillWidth: true }
                                    Text {
                                        text: modelData.source || ""
                                        visible: false
                                        color: theme.textMuted
                                        elide: Text.ElideRight
                                    }
                                }
                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: 6
                                    PillButton {
                                        id: favoriteButton
                                        text: modelData.isFavorite ? "已收藏" : "收藏"
                                        onClicked: favoriteMenu.open()
                                    }
                                    PillButton {
                                        text: modelData.inCompare ? "移出对比" : "加入对比"
                                        visible: false
                                        onClicked: literatureLibraryController.toggleCompare(modelData.recordId)
                                    }
                                    PillButton {
                                        text: "解析阅读"
                                        visible: !!modelData.localPdfPath
                                        enabled: !!modelData.localPdfPath
                                        onClicked: root.openReader(index,modelData)
                                    }
                                    PillButton {
                                        property bool generated: {
                                            knowledgeGraphController.statusText
                                            return knowledgeGraphController.hasGraph(String(modelData.recordId || ""))
                                        }
                                        text: knowledgeGraphController.loading
                                              && knowledgeGraphController.currentRecordId === String(modelData.recordId || "")
                                              ? "生成中..." : generated ? "知识图谱 ✓" : "知识图谱"
                                        visible: false
                                        enabled: !!modelData.localPdfPath && !knowledgeGraphController.loading
                                        success: generated
                                        onClicked: root.openKnowledgeGraph(index, modelData)
                                    }
                                    PillButton {
                                        property bool generated: {
                                            wordCloudController.statusText
                                            return wordCloudController.hasCloud(String(modelData.recordId || ""))
                                        }
                                        text: wordCloudController.loading && wordCloudController.currentScope === "record" && wordCloudController.currentKey === String(modelData.recordId || "") ? "生成中..." : generated ? "词云 ✓" : "词云"
                                        visible: false
                                        enabled: !!modelData.localPdfPath && !wordCloudController.loading
                                        success: generated
                                        onClicked: root.openWordCloud(index, modelData, false)
                                    }
                                    PillButton {
                                        text: "更多"
                                        onClicked: recordMoreMenu.open()
                                    }
                                    Text {
                                        Layout.fillWidth: true
                                        text: (modelData.favoriteProjectNamesText ? modelData.favoriteProjectNamesText + "  路  " : "") + (modelData.journalName || modelData.source || "")
                                        color: theme.textMuted
                                        elide: Text.ElideRight
                                        font.pixelSize: 11
                                    }
                                    Menu {
                                        id: favoriteMenu
                                        Repeater {
                                            model: literatureLibraryController.favoriteProjects
                                            MenuItem {
                                                text: modelData.name || ""
                                                checkable: true
                                                checked: root.containsValue(recordDelegate.record.favoriteProjectIds, modelData.id)
                                                onTriggered: literatureLibraryController.toggleFavorite(recordDelegate.record.recordId, modelData.id)
                                            }
                                        }
                                    }
                                    Menu {
                                        id: recordMoreMenu
                                        MenuItem {
                                            text: recordDelegate.record.inCompare ? "移出对比" : "加入对比"
                                            onTriggered: literatureLibraryController.toggleCompare(recordDelegate.record.recordId)
                                        }
                                        MenuItem {
                                            text: knowledgeGraphController.hasGraph(String(recordDelegate.record.recordId || "")) ? "打开知识图谱" : "生成知识图谱"
                                            enabled: !!recordDelegate.record.localPdfPath && !knowledgeGraphController.loading
                                            onTriggered: root.openKnowledgeGraph(index, recordDelegate.record)
                                        }
                                        MenuItem {
                                            text: wordCloudController.hasCloud(String(recordDelegate.record.recordId || "")) ? "打开词云" : "生成词云"
                                            enabled: !!recordDelegate.record.localPdfPath && !wordCloudController.loading
                                            onTriggered: root.openWordCloud(index, recordDelegate.record, false)
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }

            Rectangle {
                id: detailPanel
                Layout.fillWidth: true
                Layout.fillHeight: true
                radius: theme.radiusMedium
                color: theme.surface
                border.color: theme.border
                clip: true

                ScrollView {
                    id: detailScroll
                    anchors.fill: parent
                    anchors.margins: 14
                    clip: true
                    ScrollBar.vertical.policy: ScrollBar.AsNeeded
                    ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

                    ColumnLayout {
                    width: detailScroll.availableWidth
                    spacing: 10

                    Text {
                        Layout.fillWidth: true
                        text: root.selectedRecord.title || "选择一篇文献查看详情"
                        color: theme.text
                        font.pixelSize: theme.baseFontSize + 4
                        font.weight: Font.Bold
                        wrapMode: Text.WordWrap
                        maximumLineCount: 3
                    }
                    Text {
                        Layout.fillWidth: true
                        text: root.selectedRecord.authorsText || ""
                        color: theme.textMuted
                        wrapMode: Text.WordWrap
                        maximumLineCount: 2
                    }

                    GridLayout {
                        Layout.fillWidth: true
                        columns: 4
                        columnSpacing: 8
                        rowSpacing: 6
                        Text { text: "相关性"; color: theme.textMuted }
                        Text { text: root.selectedRecord.relevanceLabel || "-"; color: theme.accent; font.weight: Font.DemiBold }
                        Text { text: "PDF"; color: theme.textMuted }
                        Text { text: root.selectedRecord.localPdfPath ? "已下载" : (root.selectedRecord.pdfStatus || "-"); color: root.selectedRecord.localPdfPath ? theme.success : theme.warning }
                        Text { text: "发表时间"; color: theme.textMuted }
                        Text { text: root.selectedDetails.publicationDate || root.selectedRecord.publicationDate || root.selectedRecord.year || "-"; color: theme.text }
                        Text { text: "发表期刊"; color: theme.textMuted }
                        Text { Layout.fillWidth: true; text: root.selectedDetails.journalTitle || root.selectedRecord.journalTitle || "-"; color: theme.text; elide: Text.ElideRight }
                        Text { text: "影响因子"; color: theme.textMuted }
                        Text { text: root.selectedDetails.impactFactorText || root.selectedRecord.impactFactorText || "未知"; color: theme.text }
                        Text { text: "命中词"; color: theme.textMuted }
                        Text { Layout.fillWidth: true; text: root.selectedDetails.matchedKeywordsText || root.selectedRecord.matchedKeywordsText || "-"; color: theme.text; elide: Text.ElideRight }
                        Text { text: "命中位置"; color: theme.textMuted }
                        Text { text: root.selectedDetails.matchedFieldsText || root.selectedRecord.matchedFieldsText || "-"; color: theme.text }
                    }

                    Text {
                        Layout.fillWidth: true
                        text: root.selectedDetails.relevanceReasonsText || ""
                        color: theme.textSecondary
                        wrapMode: Text.WordWrap
                    }

                    Rectangle {
                        id: thumbnailFrame
                        Layout.fillWidth: true
                        Layout.preferredHeight: Math.min(360, root.height * 0.38)
                        radius: 8
                        color: theme.surfaceSoft
                        border.color: thumbnailMouse.containsMouse && root.thumbnailUrl !== "" ? theme.accent : theme.border
                        clip: true
                        Image {
                            anchors.fill: parent
                            anchors.margins: 8
                            source: root.thumbnailUrl
                            fillMode: Image.PreserveAspectFit
                            asynchronous: true
                            visible: source != ""
                        }
                        Text {
                            anchors.centerIn: parent
                            width: parent.width - 32
                            text: root.thumbnailStatusText()
                            color: theme.textMuted
                            horizontalAlignment: Text.AlignHCenter
                            wrapMode: Text.WordWrap
                            visible: root.thumbnailUrl === ""
                        }
                        BusyIndicator {
                            anchors.horizontalCenter: parent.horizontalCenter
                            anchors.bottom: parent.verticalCenter
                            anchors.bottomMargin: 12
                            width: 26
                            height: 26
                            running: root.thumbnailState === "generating"
                            visible: running && root.thumbnailUrl === ""
                        }
                        Rectangle {
                            anchors.right: parent.right
                            anchors.bottom: parent.bottom
                            anchors.margins: 10
                            visible: root.thumbnailUrl !== ""
                            radius: 6
                            color: theme.surface
                            border.color: theme.border
                            opacity: thumbnailMouse.containsMouse ? 1 : 0.86
                            Text {
                                anchors.centerIn: parent
                                anchors.margins: 8
                                text: "点击放大"
                                color: theme.textSecondary
                                font.pixelSize: 12
                            }
                            width: 78
                            height: 28
                        }
                        MouseArea {
                            id: thumbnailMouse
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: root.thumbnailUrl !== "" ? Qt.PointingHandCursor : Qt.ArrowCursor
                            onClicked: root.openPreview()
                        }
                    }

                    Text {
                        Layout.fillWidth: true
                        text: root.selectedDetails.keywordsText ? ("关键词：" + root.selectedDetails.keywordsText) : ""
                        color: theme.textSecondary
                        wrapMode: Text.WordWrap
                        visible: text.length > 0
                    }

                    Text {
                        Layout.fillWidth: true
                        text: root.selectedDetails.contentSummary ? ("主要内容：" + root.selectedDetails.contentSummary) : ""
                        color: theme.textSecondary
                        wrapMode: Text.WordWrap
                        visible: text.length > 0
                    }

                    Text {
                        Layout.fillWidth: true
                        text: root.selectedDetails.abstract || "暂无摘要。"
                        color: theme.text
                        wrapMode: Text.WordWrap
                    }
                    }
                }
            }
        }
    }

    LiteratureReaderPage {
        id: readerPage
        anchors.fill: parent
        anchors.margins: metrics.pageMargin
        visible: root.readerOpen
        recordId: root.readerRecordId
        pdfPath: root.readerPdfPath
        title: root.readerTitle
        initialZoom: root.readerLastZoom

        onBackRequested: root.closeReader()

        onZoomPersistRequested: function(value) {
            root.readerLastZoom = value
        }
        onKnowledgeGraphRequested: function(recordId, pdfPath, title) {
            root.readerOpen = false
            root.openKnowledgeGraph(root.selectedIndex, root.selectedRecord)
        }
        onWordCloudRequested: function(recordId, pdfPath, title) {
            root.openWordCloud(root.selectedIndex, root.selectedRecord, true)
        }
    }

    KnowledgeGraphPage {
        anchors.fill: parent
        anchors.margins: metrics.pageMargin
        visible: root.graphOpen && !root.graphIsComparison
        recordId: root.graphRecordId
        pdfPath: root.graphPdfPath
        title: root.graphTitle
        record: root.graphRecord
        comparisonMode: root.graphIsComparison
        comparisonRecords: root.graphComparisonRecords
        onBackRequested: {
            root.graphOpen = false
            if (root.graphReturnToCompare) {
                root.graphReturnToCompare = false
                comparePopup.open()
            }
        }
        onEvidenceRequested: function(recordId, page, bbox, elementId) {
            root.openEvidenceInReader(recordId, page, bbox, elementId)
        }
    }

    LiteratureCompareGraphPage {
        anchors.fill: parent
        anchors.margins: metrics.pageMargin
        visible: root.graphOpen && root.graphIsComparison
        recordId: root.graphRecordId
        records: root.graphComparisonRecords
        onBackRequested: {
            root.graphOpen = false
            root.graphReturnToCompare = false
            comparePopup.open()
        }
        onEvidenceRequested: function(recordId, page, bbox, elementId) {
            root.openEvidenceInReader(recordId, page, bbox, elementId)
        }
    }

    WordCloudPage {
        anchors.fill: parent
        anchors.margins: metrics.pageMargin
        visible: root.wordCloudOpen
        recordId: root.wordCloudRecordId
        record: root.wordCloudRecord
        records: root.wordCloudRecords
        title: root.wordCloudTitle
        scope: root.wordCloudScope
        onBackRequested: {
            root.wordCloudOpen = false
            if (root.wordCloudReturnToReader) {
                root.wordCloudReturnToReader = false
                root.readerOpen = true
            }
        }
        onEvidenceRequested: function(recordId, page, bbox, elementId) { root.openEvidenceInReader(recordId, page, bbox, elementId) }
        onGraphRequested: function(recordId, nodeId, keyword) { root.openGraphFromWordCloud(recordId, nodeId, keyword) }
    }

    function applyFilters() {
        literatureLibraryController.setLibraryFilters({
            "relevance": root.relevanceValues[relevanceFilter.currentIndex],
            "pdf_status": root.statusValues[pdfStatusFilter.currentIndex],
            "query": query.text,
            "sort": root.sortValues[sortFilter.currentIndex],
            "journal_type": root.journalTypeValues[journalTypeFilter.currentIndex],
            "project_id": root.favoriteProjectFilterId(),
            "keyword_groups": root.selectedKeywordGroups
        })
    }

    function containsValue(values, value) {
        if(!values)
            return false
        for(let i = 0; i < values.length; i++) {
            if(String(values[i]) === String(value))
                return true
        }
        return false
    }

    function favoriteProjectFilterLabels() {
        let labels = ["全部文献"]
        for(let i = 0; i < literatureLibraryController.favoriteProjects.length; i++)
            labels.push("收藏：" + literatureLibraryController.favoriteProjects[i].name)
        return labels
    }

    function favoriteProjectFilterId() {
        if(projectFilter.currentIndex <= 0)
            return "all"
        let index = projectFilter.currentIndex - 1
        if(index >= 0 && index < literatureLibraryController.favoriteProjects.length)
            return literatureLibraryController.favoriteProjects[index].id
        return "all"
    }

    function selectedKeywordGroupsText() {
        if(literatureLibraryController.keywordGroupOptions.length === 0)
            return i18n.text("no_keyword_groups")
        if(root.selectedKeywordGroups.length === 0)
            return i18n.text("keyword_groups")
        return i18n.formatText("keyword_groups_selected", {"count": root.selectedKeywordGroups.length})
    }

    function selectAllKeywordGroups() {
        let result = []
        for(let i = 0; i < literatureLibraryController.keywordGroupOptions.length; i++)
            result.push(literatureLibraryController.keywordGroupOptions[i].key)
        root.selectedKeywordGroups = result
        root.applyFilters()
    }

    function toggleKeywordGroup(key, enabled) {
        let result = root.selectedKeywordGroups.slice()
        let index = result.indexOf(key)
        if(enabled && index < 0)
            result.push(key)
        if(!enabled && index >= 0)
            result.splice(index, 1)
        root.selectedKeywordGroups = result
        root.applyFilters()
    }

    function selectRecord(index, record) {
        root.selectedRecord = record || ({})
        root.selectedRecordId = root.selectedRecord.recordId || ""
        root.selectedDetails = ({})
        root.thumbnailUrl = ""
        root.previewUrl = ""
        root.thumbnailState = "missing_pdf"
        root.previewState = "missing_pdf"
        if (root.selectedRecordId)
            knowledgeGraphController.prefetchGraph(String(root.selectedRecordId))
        if(literatureList.currentIndex !== index)
            literatureList.currentIndex = index
        else
            root.updateSelection()
    }

    function syncSelectedRecordFromIndex() {
        if(literatureList.currentIndex >= 0 && literatureList.currentIndex < literatureLibraryController.records.length) {
            root.selectedRecord = literatureLibraryController.records[literatureList.currentIndex]
            root.selectedRecordId = root.selectedRecord.recordId || ""
        } else {
            root.selectedRecord = ({})
            root.selectedRecordId = ""
        }
    }

    function updateSelection() {
        if(root.selectedRecordId !== "") {
            var recordId = root.selectedRecordId
            root.selectedDetails = literatureLibraryController.detailsFor(recordId)
            root.thumbnailUrl = literatureLibraryController.thumbnailFor(recordId)
            root.thumbnailState = literatureLibraryController.thumbnailStateFor(recordId)
            if(previewPopup.opened)
                root.requestPreview()
        } else {
            root.selectedDetails = ({})
            root.thumbnailUrl = ""
            root.previewUrl = ""
            root.thumbnailState = "missing_pdf"
            root.previewState = "missing_pdf"
        }
    }

    function openPreview() {
        if(root.thumbnailUrl === "" || root.selectedRecordId === "")
            return
        root.previewZoom = 1.0
        root.previewUrl = root.thumbnailUrl
        root.previewState = "ready"
        previewPopup.open()
        root.requestPreview()
    }

    function requestPreview() {
        if(root.selectedRecordId === "")
            return
        var recordId = root.selectedRecordId
        var url = literatureLibraryController.previewFor(recordId)
        root.previewState = literatureLibraryController.previewStateFor(recordId)
        if(url !== "")
            root.previewUrl = url
    }

    function thumbnailStatusText() {
        if(root.thumbnailState === "generating")
            return "PDF首页预览正在生成"
        if(root.thumbnailState === "failed")
            return "PDF首页预览生成失败"
        return root.selectedRecord.localPdfPath ? "PDF首页预览正在生成" : "这条记录没有可预览的本地 PDF。"
    }

    function previewStatusText() {
        if(root.previewState === "generating")
            return "PDF首页预览正在生成"
        if(root.previewState === "failed")
            return "PDF首页预览生成失败"
        return root.selectedRecord.localPdfPath ? "PDF首页预览正在生成" : "这条记录没有可预览的本地 PDF。"
    }

    function adjustPreviewZoom(delta) {
        root.previewZoom = Math.max(0.5, Math.min(4.0, root.previewZoom + delta))
    }

    function openReader(index, record) {
        if(!record || !record.localPdfPath)
            return

        // 先同步左侧列表与详情状态，避免“按钮所在文献”和“当前选中文献”脱节
        root.selectRecord(index, record)

        var recordId = String(record.recordId || "")
        var pdfPath = String(record.localPdfPath || "")

        root.readerRecordId = recordId
        root.readerPdfPath = pdfPath
        root.readerTitle = String(record.title || "解析阅读")
        root.readerReturnTarget = ""
        readerPage.clearEvidenceFocus()
        root.readerOpen = true
    }

    function closeReader() {
        root.readerOpen = false
        var target = root.readerReturnTarget
        root.readerReturnTarget = ""
        if (target === "wordcloud")
            root.wordCloudOpen = true
        else if (target === "graph" || target === "comparison")
            root.graphOpen = true
    }
    function openKnowledgeGraph(index, record) {
        if (!record || !record.localPdfPath)
            return
        root.selectRecord(index, record)
        root.graphRecordId = String(record.recordId || "")
        root.graphPdfPath = String(record.localPdfPath || "")
        root.graphTitle = String(record.title || "知识图谱")
        root.graphRecord = record
        root.graphReturnToCompare = false
        root.graphIsComparison = false
        root.graphComparisonRecords = []
        root.graphOpen = true
        knowledgeGraphController.generateGraph(root.graphRecordId, record, root.graphPdfPath)
    }
    function openWordCloud(index, record, returnToReader) {
        if (!record || !record.localPdfPath)
            return
        root.selectRecord(index, record)
        root.readerOpen = false
        root.graphOpen = false
        root.wordCloudRecordId = String(record.recordId || "")
        root.wordCloudTitle = String(record.title || "文献词云")
        root.wordCloudScope = "record"
        root.wordCloudRecord = record
        root.wordCloudRecords = [record]
        root.wordCloudReturnToReader = !!returnToReader
        root.wordCloudOpen = true
        wordCloudController.generateForRecord(root.wordCloudRecordId, record, String(record.localPdfPath || ""))
    }
    function openLibraryWordCloud() {
        var records = literatureLibraryController.records || []
        if (records.length === 0)
            return
        root.wordCloudRecordId = ""
        root.wordCloudTitle = "当前筛选结果"
        root.wordCloudScope = "library"
        root.wordCloudRecord = ({})
        root.wordCloudRecords = records
        root.wordCloudReturnToReader = false
        root.wordCloudOpen = true
        wordCloudController.generateForRecords(records)
    }
    function openGraphFromWordCloud(recordId, nodeId, keyword) {
        var records = literatureLibraryController.records || []
        var target = null
        for (var i = 0; i < records.length; ++i) {
            if (String(records[i].recordId || "") === String(recordId || "")) {
                target = records[i]
                break
            }
        }
        if (!target && String(root.wordCloudRecord.recordId || "") === String(recordId || ""))
            target = root.wordCloudRecord
        if (!target)
            return
        root.wordCloudOpen = false
        root.pendingGraphKeyword = String(keyword || "")
        root.pendingGraphNodeId = String(nodeId || "")
        root.graphRecordId = String(target.recordId || "")
        root.graphPdfPath = String(target.localPdfPath || "")
        root.graphTitle = String(target.title || "知识图谱")
        root.graphRecord = target
        root.graphIsComparison = false
        root.graphOpen = true
        knowledgeGraphController.generateGraph(root.graphRecordId, target, root.graphPdfPath)
        if (!knowledgeGraphController.loading) {
            var selected = root.pendingGraphNodeId && knowledgeGraphController.selectNode(root.pendingGraphNodeId)
            if (!selected)
                knowledgeGraphController.search(root.pendingGraphKeyword)
            root.pendingGraphNodeId = ""
            root.pendingGraphKeyword = ""
        }
    }
    function openComparisonKnowledgeGraph() {
        var records = literatureLibraryController.compareRecords || []
        if (records.length === 0)
            return
        comparePopup.close()
        if (!knowledgeGraphController.generateComparisonGraph(records))
            return
        root.graphRecordId = knowledgeGraphController.currentRecordId
        root.graphPdfPath = ""
        root.graphTitle = "对比知识图谱"
        root.graphRecord = ({})
        root.graphReturnToCompare = true
        root.graphIsComparison = true
        root.graphComparisonRecords = records
        root.readerOpen = false
        root.graphOpen = true
    }
    function openEvidenceInReader(recordId, page, bbox, elementId) {
        var target = null
        var records = literatureLibraryController.records || []
        for (var i = 0; i < records.length; ++i) {
            if (String(records[i].recordId || "") === String(recordId || "")) {
                target = records[i]
                break
            }
        }
        var candidates = root.graphComparisonRecords || []
        for (var j = 0; !target && j < candidates.length; ++j) {
            if (String(candidates[j].recordId || "") === String(recordId || ""))
                target = candidates[j]
        }
        candidates = root.wordCloudRecords || []
        for (var k = 0; !target && k < candidates.length; ++k) {
            if (String(candidates[k].recordId || "") === String(recordId || ""))
                target = candidates[k]
        }
        if (!target && String(root.graphRecord.recordId || "") === String(recordId || ""))
            target = root.graphRecord
        if (!target || !target.localPdfPath)
            return
        root.readerReturnTarget = root.wordCloudOpen ? "wordcloud" : (root.graphIsComparison ? "comparison" : "graph")
        root.graphOpen = false
        root.wordCloudOpen = false
        root.readerRecordId = String(target.recordId || "")
        root.readerPdfPath = String(target.localPdfPath || "")
        root.readerTitle = String(target.title || "解析阅读")
        root.readerOpen = true
        Qt.callLater(function() {
            pdfExtractionController.loadIndexForPdf(root.readerRecordId, root.readerPdfPath)
            readerPage.focusEvidence(page, bbox || [], elementId)
        })
    }
    function registerTourTargets() {
        if(root.tourHost) {
            root.tourHost.registerTourTarget("nav.library", libraryListPanel)
            root.tourHost.registerTourTarget("nav.extract", detailPanel)
        }
    }
    function unregisterTourTargets() {
        if(root.tourHost) {
            root.tourHost.unregisterTourTarget("nav.library", libraryListPanel)
            root.tourHost.unregisterTourTarget("nav.extract", detailPanel)
        }
    }

    Popup {
        id: keywordGroupPopup
        parent: Overlay.overlay
        modal: false
        focus: true
        width: 300
        height: Math.min(420, root.height - 80)
        x: Math.max(24, Math.min(root.width - width - 24, keywordGroupButton.mapToItem(root, 0, 0).x))
        y: keywordGroupButton.mapToItem(root, 0, 0).y + keywordGroupButton.height + 8
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        padding: 0

        background: Rectangle {
            color: theme.surface
            radius: theme.radiusMedium
            border.color: theme.border
        }

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 12
            spacing: 8

            RowLayout {
                Layout.fillWidth: true
                Text {
                    Layout.fillWidth: true
                    text: i18n.text("keyword_groups")
                    color: theme.text
                    font.weight: Font.Bold
                }
                Text {
                    text: i18n.formatText("keyword_groups_selected", {"count": root.selectedKeywordGroups.length})
                    color: theme.textMuted
                    font.pixelSize: Math.max(10, theme.baseFontSize - 2)
                }
            }

            RowLayout {
                Layout.fillWidth: true
                PillButton {
                    text: i18n.text("select_all")
                    enabled: literatureLibraryController.keywordGroupOptions.length > 0 && root.selectedKeywordGroups.length < literatureLibraryController.keywordGroupOptions.length
                    onClicked: root.selectAllKeywordGroups()
                }
                PillButton {
                    text: i18n.text("clear")
                    enabled: root.selectedKeywordGroups.length > 0
                    onClicked: {
                        root.selectedKeywordGroups = []
                        root.applyFilters()
                    }
                }
            }

            ListView {
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                model: literatureLibraryController.keywordGroupOptions
                visible: literatureLibraryController.keywordGroupOptions.length > 0
                ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
                delegate: ModernCheckBox {
                    width: ListView.view.width
                    text: modelData.label + " (" + modelData.count + ")"
                    checked: root.selectedKeywordGroups.indexOf(modelData.key) >= 0
                    onToggled: root.toggleKeywordGroup(modelData.key, checked)
                }
            }
            Text {
                Layout.fillWidth: true
                Layout.fillHeight: true
                visible: literatureLibraryController.keywordGroupOptions.length === 0
                text: i18n.text("no_keyword_groups")
                color: theme.textMuted
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
            }
        }
    }

    Popup {
        id: createProjectPopup
        parent: Overlay.overlay
        modal: true
        focus: true
        width: Math.min(360, root.width - 64)
        height: 160
        x: (root.width - width) / 2
        y: (root.height - height) / 2
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        padding: 0

        background: Rectangle {
            color: theme.surface
            radius: theme.radiusMedium
            border.color: theme.border
        }

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 16
            spacing: 10

            Text {
                Layout.fillWidth: true
                text: "新建收藏分类"
                color: theme.text
                font.weight: Font.Bold
            }
            TextField {
                id: newProjectName
                Layout.fillWidth: true
                placeholderText: "分类名称"
                selectByMouse: true
                onAccepted: {
                    literatureLibraryController.createFavoriteProject(text)
                    text = ""
                    createProjectPopup.close()
                }
            }
            RowLayout {
                Layout.fillWidth: true
                Item { Layout.fillWidth: true }
                PillButton {
                    text: "取消"
                    onClicked: createProjectPopup.close()
                }
                PillButton {
                    text: "创建"
                    primary: true
                    enabled: newProjectName.text.trim().length > 0
                    onClicked: {
                        literatureLibraryController.createFavoriteProject(newProjectName.text)
                        newProjectName.text = ""
                        createProjectPopup.close()
                    }
                }
            }
        }
    }

    Popup {
        id: comparePopup
        parent: Overlay.overlay
        modal: true
        focus: true
        width: Math.min(900, root.width - 64)
        height: Math.min(560, root.height - 64)
        x: (root.width - width) / 2
        y: (root.height - height) / 2
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        padding: 0

        background: Rectangle {
            color: theme.surface
            radius: theme.radiusMedium
            border.color: theme.border
        }

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 16
            spacing: 10

            RowLayout {
                Layout.fillWidth: true
                Text {
                    Layout.fillWidth: true
                    text: "文献对比 " + literatureLibraryController.compareCount + "/4"
                    color: theme.text
                    font.pixelSize: theme.baseFontSize + 5
                    font.weight: Font.Bold
                    elide: Text.ElideRight
                }
                PillButton {
                    text: "清空对比"
                    enabled: literatureLibraryController.compareCount > 0
                    onClicked: literatureLibraryController.clearCompare()
                }
                PillButton {
                    text: knowledgeGraphController.loading ? "生成中..." : "知识图谱"
                    enabled: literatureLibraryController.compareCount > 0 && !knowledgeGraphController.loading
                    onClicked: root.openComparisonKnowledgeGraph()
                }
                PillButton {
                    text: "关闭"
                    onClicked: comparePopup.close()
                }
            }

            ScrollView {
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                ColumnLayout {
                    width: comparePopup.width - 32
                    spacing: 8
                    Repeater {
                        model: literatureLibraryController.compareRecords
                        delegate: Rectangle {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 176
                            radius: 8
                            color: theme.surfaceSoft
                            border.color: theme.border
                            ColumnLayout {
                                anchors.fill: parent
                                anchors.margins: 10
                                spacing: 5
                                RowLayout {
                                    Layout.fillWidth: true
                                    Text {
                                        Layout.fillWidth: true
                                        text: modelData.title || "Untitled"
                                        color: theme.text
                                        font.weight: Font.DemiBold
                                        elide: Text.ElideRight
                                    }
                                    PillButton {
                                        text: "移出"
                                        onClicked: literatureLibraryController.removeCompare(modelData.recordId)
                                    }
                                }
                                Text {
                                    Layout.fillWidth: true
                                    text: (modelData.authorsText || "Unknown authors") + "  路  " + (modelData.year || "n.d.")
                                    color: theme.textMuted
                                    elide: Text.ElideRight
                                }
                                GridLayout {
                                    Layout.fillWidth: true
                                    columns: 4
                                    columnSpacing: 8
                                    rowSpacing: 4
                                    Text { text: "类型"; color: theme.textMuted }
                                    Text { text: modelData.journalTypeLabel || "-"; color: theme.text; elide: Text.ElideRight; Layout.fillWidth: true }
                                    Text { text: "期刊"; color: theme.textMuted }
                                    Text { text: modelData.journalName || modelData.source || "-"; color: theme.text; elide: Text.ElideRight; Layout.fillWidth: true }
                                    Text { text: "相关性"; color: theme.textMuted }
                                    Text { text: (modelData.relevanceLabel || "-") + " / " + String(modelData.relevance_score || 0); color: theme.accent; elide: Text.ElideRight; Layout.fillWidth: true }
                                    Text { text: "PDF"; color: theme.textMuted }
                                    Text { text: modelData.downloaded ? "已下载" : "未下载"; color: modelData.downloaded ? theme.success : theme.warning; elide: Text.ElideRight; Layout.fillWidth: true }
                                    Text { text: "关键词"; color: theme.textMuted }
                                    Text { text: modelData.matchedKeywordsText || "-"; color: theme.text; elide: Text.ElideRight; Layout.fillWidth: true }
                                    Text { text: "命中字段"; color: theme.textMuted }
                                    Text { text: modelData.matchedFieldsText || "-"; color: theme.text; elide: Text.ElideRight; Layout.fillWidth: true }
                                    Text { text: "DOI"; color: theme.textMuted }
                                    Text { text: modelData.doi || "-"; color: theme.text; elide: Text.ElideRight; Layout.fillWidth: true }
                                    Text { text: "本地 PDF"; color: theme.textMuted }
                                    Text { text: modelData.localPdfPath || "-"; color: theme.text; elide: Text.ElideRight; Layout.fillWidth: true }
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    Popup {
        id: previewPopup
        parent: Overlay.overlay
        modal: true
        focus: true
        width: Math.min(root.width * 0.9, root.width - 48)
        height: Math.min(root.height * 0.9, root.height - 48)
        x: (root.width - width) / 2
        y: (root.height - height) / 2
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        padding: 0
        onOpened: root.requestPreview()
        onClosed: root.previewZoom = 1.0

        background: Rectangle {
            color: theme.surface
            radius: theme.radiusMedium
            border.color: theme.border
        }

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 14
            spacing: 10

            RowLayout {
                Layout.fillWidth: true
                spacing: 8
                Text {
                    Layout.fillWidth: true
                    text: root.selectedRecord.title || "PDF 首页预览"
                    color: theme.text
                    font.pixelSize: theme.baseFontSize + 4
                    font.weight: Font.Bold
                    elide: Text.ElideRight
                }
                PillButton { text: "-"; onClicked: root.adjustPreviewZoom(-0.25) }
                PillButton { text: "+"; onClicked: root.adjustPreviewZoom(0.25) }
                PillButton { text: "重置"; onClicked: root.previewZoom = 1.0 }
                PillButton { text: "关闭"; onClicked: previewPopup.close() }
            }

            Rectangle {
                id: previewViewport
                Layout.fillWidth: true
                Layout.fillHeight: true
                radius: 8
                color: theme.surfaceSoft
                border.color: theme.border
                clip: true

                Flickable {
                    id: previewFlick
                    anchors.fill: parent
                    anchors.margins: 8
                    clip: true
                    interactive: root.previewZoom > 1.0
                    boundsBehavior: Flickable.StopAtBounds
                    contentWidth: Math.max(width, previewImage.width)
                    contentHeight: Math.max(height, previewImage.height)

                    Image {
                        id: previewImage
                        source: root.previewUrl
                        asynchronous: true
                        fillMode: Image.PreserveAspectFit
                        smooth: true
                        width: implicitWidth > 0 && implicitHeight > 0
                               ? implicitWidth * Math.min(previewFlick.width / implicitWidth, previewFlick.height / implicitHeight) * root.previewZoom
                               : previewFlick.width
                        height: implicitWidth > 0 && implicitHeight > 0
                                ? implicitHeight * Math.min(previewFlick.width / implicitWidth, previewFlick.height / implicitHeight) * root.previewZoom
                                : previewFlick.height
                        x: Math.max(0, (previewFlick.width - width) / 2)
                        y: Math.max(0, (previewFlick.height - height) / 2)
                        visible: source != ""
                    }

                    MouseArea {
                        anchors.fill: parent
                        acceptedButtons: Qt.NoButton
                        onWheel: function(wheel) {
                            root.adjustPreviewZoom(wheel.angleDelta.y > 0 ? 0.15 : -0.15)
                        }
                    }
                }

                Text {
                    anchors.centerIn: parent
                    width: parent.width - 32
                    text: root.previewStatusText()
                    color: theme.textMuted
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.WordWrap
                    visible: root.previewUrl === ""
                }
                BusyIndicator {
                    anchors.horizontalCenter: parent.horizontalCenter
                    anchors.bottom: parent.verticalCenter
                    anchors.bottomMargin: 12
                    width: 30
                    height: 30
                    running: root.previewState === "generating"
                    visible: running && root.previewUrl === ""
                }
            }
        }
    }

    Popup {
        id: cleanupPopup
        parent: Overlay.overlay
        modal: true
        focus: true
        width: Math.min(720, root.width - 80)
        height: Math.min(560, root.height - 80)
        x: (root.width - width) / 2
        y: (root.height - height) / 2
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        padding: 0

        background: Rectangle {
            color: theme.surface
            radius: theme.radiusMedium
            border.color: theme.border
        }

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 18
            spacing: 12

            RowLayout {
                Layout.fillWidth: true
                Text {
                    Layout.fillWidth: true
                    text: "清理旧 PDF"
                    color: theme.text
                    font.pixelSize: theme.baseFontSize + 6
                    font.weight: Font.Bold
                }
                BusyIndicator {
                    Layout.preferredWidth: 24
                    Layout.preferredHeight: 24
                    running: literatureLibraryController.loading && (literatureLibraryController.busyAction === "preview_cleanup" || literatureLibraryController.busyAction === "confirm_cleanup")
                    visible: running
                }
            }

            Text {
                Layout.fillWidth: true
                text: literatureLibraryController.loading && literatureLibraryController.progressText ? literatureLibraryController.progressText :
                      literatureLibraryController.cleanupSummary.count > 0 ?
                      "将直接删除 " + literatureLibraryController.cleanupSummary.count + " 个文件，预计释放 " + literatureLibraryController.cleanupSummary.totalSizeText + "。此操作不创建备份。" :
                      literatureLibraryController.statusText
                color: theme.textSecondary
                wrapMode: Text.WordWrap
            }

            GridLayout {
                Layout.fillWidth: true
                columns: 4
                columnSpacing: 8
                rowSpacing: 6
                Text { text: "metadata PDF"; color: theme.textMuted }
                Text { text: String(literatureLibraryController.cleanupSummary.metadataCount || 0); color: theme.text }
                Text { text: "孤儿 PDF"; color: theme.textMuted }
                Text { text: String(literatureLibraryController.cleanupSummary.orphanCount || 0); color: theme.text }
                Text { text: "归档副本"; color: theme.textMuted }
                Text { text: String(literatureLibraryController.cleanupSummary.libraryCount || 0); color: theme.text }
                Text { text: "缩略图"; color: theme.textMuted }
                Text { text: String(literatureLibraryController.cleanupSummary.thumbnailCount || 0); color: theme.text }
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.fillHeight: true
                radius: 8
                color: theme.surfaceSoft
                border.color: theme.border
                clip: true

                ListView {
                    anchors.fill: parent
                    anchors.margins: 8
                    clip: true
                    model: literatureLibraryController.cleanupCandidates
                    delegate: ColumnLayout {
                        width: ListView.view.width
                        spacing: 3
                        Text {
                            Layout.fillWidth: true
                            text: modelData.name || modelData.path
                            color: theme.text
                            font.weight: Font.DemiBold
                            elide: Text.ElideRight
                        }
                        Text {
                            Layout.fillWidth: true
                            text: (modelData.reasonText || modelData.reason || "") + " · " + (modelData.sizeText || "")
                            color: theme.textMuted
                            elide: Text.ElideRight
                        }
                        Rectangle {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 1
                            color: theme.border
                        }
                    }
                }

                Text {
                    anchors.centerIn: parent
                    width: parent.width - 32
                    text: literatureLibraryController.loading ? "正在扫描..." : "没有需要清理的旧 PDF。"
                    color: theme.textMuted
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.WordWrap
                    visible: literatureLibraryController.cleanupCandidates.length === 0
                }
            }

            RowLayout {
                Layout.fillWidth: true
                Item { Layout.fillWidth: true }
                PillButton {
                    text: "取消"
                    enabled: !literatureLibraryController.loading
                    onClicked: cleanupPopup.close()
                }
                PillButton {
                    text: literatureLibraryController.loading && literatureLibraryController.busyAction === "confirm_cleanup" ? "删除中..." : "确认直接删除"
                    primary: true
                    enabled: !literatureLibraryController.loading && literatureLibraryController.cleanupPending
                    onClicked: literatureLibraryController.confirmCleanup()
                }
            }
        }
    }
}
