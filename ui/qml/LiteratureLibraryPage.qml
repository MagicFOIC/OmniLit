import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: root

    property int selectedIndex: literatureList.currentIndex
    property string selectedRecordId: ""
    property var selectedRecord: ({})
    property var selectedDetails: ({})
    property string thumbnailUrl: ""
    property string thumbnailState: "missing_pdf"
    property string previewUrl: ""
    property string previewState: "missing_pdf"
    property real previewZoom: 1.0

    readonly property var relevanceValues: ["all", "keyword_only", "loose", "balanced", "strict", "very_strict"]
    readonly property var statusValues: ["all", "downloaded", "no_candidate", "failed", "not_open_access", "not_pdf", "request_error"]
    readonly property var relevanceLabels: ["全部相关性", "关键词提及即可", "宽松及以上", "均衡及以上", "严格及以上", "极严格"]
    readonly property var statusLabels: ["全部 PDF 状态", "已下载", "无候选", "下载失败", "非开放获取", "非 PDF", "请求失败"]

    Motion { id: motion }
    I18n { id: i18n }
    Theme { id: theme }
    LayoutMetrics { id: metrics; viewportWidth: root.width; viewportHeight: root.height }

    onVisibleChanged: {
        if(visible && !literatureLibraryController.hasLoaded && !literatureLibraryController.loading)
            literatureLibraryController.refresh()
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

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: metrics.pageMargin
        spacing: metrics.sectionSpacing

        PageHeading {
            Layout.fillWidth: true
            title: "文献库"
            subtitle: "查看、筛选、预览和按相关性整理已下载文献。相关性等级用于整理文献，不代表论文质量。"
            titleSize: metrics.headingSize
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 58
            radius: theme.radiusMedium
            color: theme.surface
            border.color: theme.border

            RowLayout {
                anchors.fill: parent
                anchors.margins: 10
                spacing: 10

                TextField {
                    id: query
                    Layout.fillWidth: true
                    placeholderText: "搜索标题、摘要、作者或 DOI"
                    onTextChanged: root.applyFilters()
                }
                ComboBox {
                    id: relevanceFilter
                    Layout.preferredWidth: 170
                    model: root.relevanceLabels
                    currentIndex: 0
                    enabled: !literatureLibraryController.loading
                    onCurrentIndexChanged: root.applyFilters()
                }
                ComboBox {
                    id: pdfStatusFilter
                    Layout.preferredWidth: 150
                    model: root.statusLabels
                    currentIndex: 0
                    enabled: !literatureLibraryController.loading
                    onCurrentIndexChanged: root.applyFilters()
                }
                PillButton {
                    text: literatureLibraryController.loading && literatureLibraryController.busyAction === "refresh" ? "刷新中..." : i18n.text("refresh")
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

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: metrics.sectionSpacing

            Rectangle {
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
                            width: literatureList.width
                            height: 112
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
                                    text: (modelData.authorsText || "Unknown authors") + "  ·  " + (modelData.year || "n.d.")
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
                                    Item { Layout.fillWidth: true }
                                    Text {
                                        text: modelData.source || ""
                                        color: theme.textMuted
                                        elide: Text.ElideRight
                                    }
                                }
                            }
                        }
                    }
                }
            }

            Rectangle {
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
                        text: root.selectedDetails.abstract || "暂无摘要。"
                        color: theme.text
                        wrapMode: Text.WordWrap
                    }
                    }
                }
            }
        }
    }

    function applyFilters() {
        literatureLibraryController.setFilters(root.relevanceValues[relevanceFilter.currentIndex],
                                               root.statusValues[pdfStatusFilter.currentIndex],
                                               query.text)
    }

    function selectRecord(index, record) {
        root.selectedRecord = record || ({})
        root.selectedRecordId = root.selectedRecord.recordId || ""
        root.selectedDetails = ({})
        root.thumbnailUrl = ""
        root.previewUrl = ""
        root.thumbnailState = "missing_pdf"
        root.previewState = "missing_pdf"
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
