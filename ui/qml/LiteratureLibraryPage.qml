import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: root
    property int selectedIndex: literatureList.currentIndex
    property var selectedRecord: selectedIndex >= 0 && selectedIndex < literatureLibraryController.records.length ? literatureLibraryController.records[selectedIndex] : ({})
    property string thumbnailUrl: ""
    readonly property var relevanceValues: ["all", "keyword_only", "loose", "balanced", "strict", "very_strict"]
    readonly property var statusValues: ["all", "downloaded", "no_candidate", "failed", "not_open_access", "not_pdf", "request_error"]
    readonly property var relevanceLabels: ["全部相关性", "关键词提及即可", "宽松及以上", "均衡及以上", "严格及以上", "极严格"]
    readonly property var statusLabels: ["全部 PDF 状态", "已下载", "无候选", "下载失败", "非开放获取", "非 PDF", "请求失败"]

    Motion { id: motion }
    I18n { id: i18n }
    Theme { id: theme }
    LayoutMetrics { id: metrics; viewportWidth: root.width; viewportHeight: root.height }

    Connections {
        target: literatureLibraryController
        function onChanged() {
            if(literatureLibraryController.records.length > 0 && literatureList.currentIndex < 0)
                literatureList.currentIndex = 0
            else if(literatureList.currentIndex >= literatureLibraryController.records.length)
                literatureList.currentIndex = literatureLibraryController.records.length > 0 ? 0 : -1
            root.updateThumbnail()
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
                    onCurrentIndexChanged: root.applyFilters()
                }
                ComboBox {
                    id: pdfStatusFilter
                    Layout.preferredWidth: 150
                    model: root.statusLabels
                    currentIndex: 0
                    onCurrentIndexChanged: root.applyFilters()
                }
                PillButton { text: i18n.text("refresh"); onClicked: literatureLibraryController.refresh() }
                PillButton { text: "重算相关性"; onClicked: literatureLibraryController.recomputeRelevance() }
                PillButton { text: "按相关性归档"; primary: true; onClicked: literatureLibraryController.organizeByRelevance() }
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
                        Text {
                            text: literatureLibraryController.statusText
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
                        Component.onCompleted: if(count > 0) currentIndex = 0
                        onCurrentIndexChanged: root.updateThumbnail()
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
                                onClicked: literatureList.currentIndex = index
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
                                        text: modelData.pdfStatus || "unknown"
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

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 14
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
                        Text { Layout.fillWidth: true; text: root.selectedRecord.matchedKeywordsText || "-"; color: theme.text; elide: Text.ElideRight }
                        Text { text: "命中位置"; color: theme.textMuted }
                        Text { text: root.selectedRecord.matchedFieldsText || "-"; color: theme.text }
                    }

                    Text {
                        Layout.fillWidth: true
                        text: root.selectedRecord.relevanceReasonsText || ""
                        color: theme.textSecondary
                        wrapMode: Text.WordWrap
                    }

                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: Math.min(360, root.height * 0.38)
                        radius: 8
                        color: theme.surfaceSoft
                        border.color: theme.border
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
                            text: root.selectedRecord.localPdfPath ? "PDF 首屏预览生成失败或正在生成。" : "这条记录没有可预览的本地 PDF。"
                            color: theme.textMuted
                            horizontalAlignment: Text.AlignHCenter
                            wrapMode: Text.WordWrap
                            visible: root.thumbnailUrl === ""
                        }
                    }

                    Text {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        text: root.selectedRecord.abstract || "暂无摘要。"
                        color: theme.text
                        wrapMode: Text.WordWrap
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

    function updateThumbnail() {
        if(root.selectedRecord && root.selectedRecord.recordId)
            root.thumbnailUrl = literatureLibraryController.thumbnailFor(root.selectedRecord.recordId)
        else
            root.thumbnailUrl = ""
    }
}
