import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: root
    property var sortValues: ["", "relevance_score:desc", "cited_by_count:desc", "publication_date:desc"]
    property var topicScoreValues: [0, 4, 6, 9, 12]
    property var topicScoreLabels: ["关键词提及即可 / 0", "宽松 / 4", "均衡 / 6", "严格 / 9", "极严格 / 12"]
    property var selectedSources: ["openalex"]
    property var selectedJournals: []
    property bool advancedVisible: false
    property bool restoringSettings: true
    property bool toDateAuto: true
    readonly property int logPaneMinimumHeight: metrics.compact ? (advancedVisible ? 78 : 105) : (advancedVisible ? 96 : 130)
    readonly property int statsPaneHeight: metrics.compact ? 64 : 72
    readonly property real downloadFormPaneHeight: Math.max(metrics.compact ? 320 : 380, form.implicitHeight + metrics.cardPadding * 2)
    readonly property real logPanePreferredHeight: Math.max(
        logPaneMinimumHeight,
        root.height - metrics.pageMargin * 2 - heading.implicitHeight - downloadFormPaneHeight - statsPaneHeight - metrics.sectionSpacing * 3
    )
    Motion { id: motion }
    PageMotion { target: root }
    I18n { id: i18n }
    Theme { id: theme }
    LayoutMetrics { id: metrics; viewportWidth: root.width; viewportHeight: root.height }
    Timer { id: saveSettingsTimer; interval: 350; onTriggered: downloadController.saveConfig(config()) }
    Component.onCompleted: { restoreSavedConfig(); restoringSettings = false }
    onSelectedSourcesChanged: scheduleSave()
    onSelectedJournalsChanged: scheduleSave()
    onAdvancedVisibleChanged: scheduleSave()

    ScrollView {
        id: pageScroll
        anchors.fill: parent
        anchors.margins: metrics.pageMargin
        contentWidth: availableWidth
        clip: true
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

    ColumnLayout {
        width: pageScroll.availableWidth; spacing: metrics.sectionSpacing
        PageHeading { id: heading; Layout.fillWidth: true; title: i18n.text("download_title"); subtitle: i18n.text("download_desc"); titleSize: metrics.headingSize }
        Card {
            id: functionCard
            Layout.fillWidth: true
            Layout.preferredHeight: root.downloadFormPaneHeight
            Layout.minimumHeight: metrics.compact ? (root.advancedVisible ? 360 : 320) : (root.advancedVisible ? 440 : 380)
            ScrollView {
                id: formScroll
                anchors.fill: parent
                anchors.margins: metrics.cardPadding
                contentWidth: availableWidth
                ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                clip: true
                ColumnLayout {
                    id: form
                    width: formScroll.availableWidth
                    spacing: metrics.compact ? 5 : 7
                GridLayout {
                    Layout.fillWidth: true; columns: metrics.narrow ? 2 : 4; columnSpacing: 12; rowSpacing: metrics.compact ? 6 : 8
                    Text { text: i18n.text("email"); color: theme.textMuted }
                    TextField { id: email; Layout.fillWidth: true; onTextChanged: root.scheduleSave() }
                    Text { text: i18n.text("output_dir"); color: theme.textMuted }
                    RowLayout {
                        Layout.fillWidth: true
                        TextField { id: outputDir; Layout.fillWidth: true; text: downloadController.defaultOutputDir; onTextChanged: root.scheduleSave() }
                        PillButton { text: i18n.text("choose"); onClicked: { let p=downloadController.chooseDirectory(outputDir.text); if(p) outputDir.text=p } }
                        PillButton { text: i18n.text("open"); onClicked: downloadController.openDirectory(outputDir.text) }
                    }
                    Text { text: i18n.text("from_date"); color: theme.textMuted }
                    DatePickerField { id: fromDate; text: downloadController.defaultFromDate; maxDateText: toDate.text; onTextChanged: root.scheduleSave() }
                    Text { text: i18n.text("to_date"); color: theme.textMuted }
                    DatePickerField {
                        id: toDate
                        text: downloadController.defaultToDate
                        minDateText: fromDate.text
                        maxDateText: downloadController.defaultToDate

                        onTextChanged: {
                            if(!root.restoringSettings)
                                root.toDateAuto = false
                            root.scheduleSave()
                        }
                    }
                    Text { text: i18n.text("sort"); color: theme.textMuted }
                    ComboBox {
                        id: sortMode; Layout.fillWidth: true
                        model: [i18n.text("sort_default"), i18n.text("sort_relevance") + " desc",
                                i18n.text("sort_citations") + " desc", i18n.text("sort_date") + " desc"]
                        currentIndex: 1
                        onCurrentIndexChanged: root.scheduleSave()
                    }
                    Text { text: i18n.text("max_records"); color: theme.textMuted }
                    TextField { id: maxRecords; Layout.fillWidth: true; placeholderText: i18n.text("optional"); onTextChanged: root.scheduleSave() }
                }
                Text { text: i18n.text("keywords"); color: theme.textMuted }
                SoftTextArea { id: keywords; Layout.fillWidth: true; Layout.preferredHeight: 54; text: downloadController.defaultKeywords; wrapMode: TextArea.Wrap; onTextChanged: root.scheduleSave() }
                RowLayout {
                    Text { text: i18n.text("literature_sources"); color: theme.textMuted }
                    Repeater {
                        model: downloadController.availableSources
                        ModernCheckBox {
                            text: modelData.label
                            checked: root.selectedSources.indexOf(modelData.key) >= 0
                            activePulse: downloadController.running && downloadController.activeSourceKey === modelData.key
                            ToolTip.delay: 250
                            ToolTip.timeout: 5000
                            ToolTip.visible: activePulse || hovered
                            ToolTip.text: activePulse ? downloadController.activeSourceText : modelData.label
                            onToggled: root.toggleSource(modelData.key, checked)
                        }
                    }
                    Item { Layout.fillWidth: true }
                }
                Rectangle {
                    Layout.fillWidth: true
                    implicitHeight: downloadController.activeSourceText.length > 0 ? activeSourceText.implicitHeight + 14 : 0
                    opacity: downloadController.activeSourceText.length > 0 ? 1 : 0
                    radius: 11
                    color: theme.accentSofter
                    border.color: theme.border
                    clip: true
                    Behavior on opacity { NumberAnimation { duration: motion.fast } }
                    Behavior on implicitHeight { NumberAnimation { duration: motion.fast; easing.type: Easing.OutCubic } }
                    Text {
                        id: activeSourceText
                        anchors.fill: parent
                        anchors.margins: 7
                        text: downloadController.activeSourceText
                        color: theme.text
                        font.weight: Font.DemiBold
                        verticalAlignment: Text.AlignVCenter
                        elide: Text.ElideRight
                    }
                }
                RowLayout {
                    ModernCheckBox { id: downloadPdfs; text: i18n.text("download_pdf"); checked: true; onToggled: root.scheduleSave() }
                    ModernCheckBox { id: resume; text: i18n.text("resume"); checked: true; onToggled: root.scheduleSave() }
                    ModernCheckBox {
                        id: oaOnly
                        text: i18n.text("oa_only")
                        ToolTip.delay: 250
                        ToolTip.timeout: 7000
                        ToolTip.visible: hovered
                        ToolTip.text: "只保留开放获取记录，用于排除非 OA 文献；PDF 仍只会下载合法开放获取链接。"
                        onToggled: root.scheduleSave()
                    }
                    Text { text: i18n.text("pages"); color: theme.textMuted }
                    SpinBox { id: pages; from: 1; to: 1000; value: 1; editable: true; onValueChanged: root.scheduleSave() }
                    Text { text: i18n.text("per_page"); color: theme.textMuted }
                    SpinBox { id: perPage; from: 1; to: 200; value: 20; editable: true; onValueChanged: root.scheduleSave() }
                    Item { Layout.fillWidth: true }
                    PillButton { text: root.advancedVisible ? i18n.text("collapse_advanced") : i18n.text("advanced"); onClicked: root.advancedVisible = !root.advancedVisible }
                }
                Item {
                    id: advancedPanel
                    Layout.fillWidth: true
                    Layout.preferredHeight: panelHeight
                    property real panelHeight: root.advancedVisible ? advancedContent.implicitHeight : 0
                    opacity: root.advancedVisible ? 1 : 0
                    clip: true
                    Behavior on panelHeight { NumberAnimation { duration: motion.expand; easing.type: Easing.OutCubic } }
                    Behavior on opacity { NumberAnimation { duration: motion.normal } }
                    ColumnLayout {
                        id: advancedContent
                        width: parent.width
                        GridLayout {
                            Layout.fillWidth: true; columns: metrics.narrow ? 2 : 4; columnSpacing: 12; rowSpacing: metrics.compact ? 6 : 8
                            Text { text: i18n.text("request_delay"); color: theme.textMuted }
                            TextField { id: requestDelay; Layout.fillWidth: true; text: "0.2"; onTextChanged: root.scheduleSave() }
                            Text { text: i18n.text("page_delay"); color: theme.textMuted }
                            TextField { id: pageDelay; Layout.fillWidth: true; text: "0.5"; onTextChanged: root.scheduleSave() }
                            Text { text: i18n.text("min_pdf_bytes"); color: theme.textMuted }
                            TextField { id: minPdfBytes; Layout.fillWidth: true; text: "1024"; onTextChanged: root.scheduleSave() }
                            Text { text: i18n.text("match_ratio"); color: theme.textMuted }
                            TextField { id: matchRatio; Layout.fillWidth: true; text: "0.75"; onTextChanged: root.scheduleSave() }
                            Text { text: "相关性过滤强度"; color: theme.textMuted }
                            ComboBox {
                                id: minTopicScore
                                Layout.fillWidth: true
                                model: root.topicScoreLabels
                                currentIndex: 0
                                hoverEnabled: true
                                ToolTip.delay: 350
                                ToolTip.timeout: 9000
                                ToolTip.visible: hovered
                                ToolTip.text: "关键词提及即可 / 0：召回最多。只要标题或摘要提到你的关键词就保留，适合建库、初筛和尽量多收文献。\n宽松 / 4：保留大多数相关文献，只过滤明显偏离主题的结果，适合希望减少少量噪声。\n均衡 / 6：在数量和准确性之间折中，适合日常检索和普通主题整理。\n严格 / 9：只保留主题信号更充分的文献，数量会减少，适合精读前筛选。\n极严格 / 12：只保留高度聚焦的文献，准确性更高，但可能漏掉综述、边缘相关或摘要较短的文献。"
                                onCurrentIndexChanged: root.scheduleSave()
                            }
                            Text { text: i18n.text("loop_sleep"); color: theme.textMuted }
                            TextField { id: loopSleep; Layout.fillWidth: true; text: "3600"; onTextChanged: root.scheduleSave() }
                            Text { text: i18n.text("runtime_hours"); color: theme.textMuted }
                            TextField { id: runtimeHours; Layout.fillWidth: true; placeholderText: i18n.text("optional"); onTextChanged: root.scheduleSave() }
                        }
                        GridLayout {
                            Layout.fillWidth: true
                            columns: metrics.narrow ? 2 : 3
                            ModernCheckBox { id: retryMissing; text: i18n.text("retry_missing"); checked: true; onToggled: root.scheduleSave() }
                            ModernCheckBox { id: writeRetry; text: i18n.text("write_retry"); onToggled: root.scheduleSave() }
                            ModernCheckBox { id: strictMatch; text: i18n.text("strict_match"); checked: true; onToggled: root.scheduleSave() }
                            ModernCheckBox {
                                id: preferredJournalOnly
                                text: "仅限推荐 OA 期刊"
                                ToolTip.delay: 350
                                ToolTip.timeout: 9000
                                ToolTip.visible: hovered
                                ToolTip.text: "默认关闭。关闭时推荐 OA 期刊只用于排序加权；开启后只保留推荐 OA 期刊内的论文。"
                                onToggled: root.scheduleSave()
                            }
                            ModernCheckBox { id: loopJob; text: i18n.text("loop_job"); onToggled: root.scheduleSave() }
                            ModernCheckBox { id: fastForward; text: i18n.text("fast_forward"); checked: true; onToggled: root.scheduleSave() }
                            ModernCheckBox {
                                id: discoveryMode
                                text: "宽松发现模式 / Discovery mode"
                                ToolTip.delay: 350
                                ToolTip.timeout: 9000
                                ToolTip.visible: hovered
                                ToolTip.text: "Disable strict keyword/topic/journal filters and resume fast-forward to diagnose source yield."
                                onToggled: {
                                    if(checked)
                                        root.applyDiscoveryMode()
                                    root.scheduleSave()
                                }
                            }
                        }
                    }
                }
                RowLayout {
                    Item { Layout.fillWidth: true }
                    PillButton { text: "补全已有文献 PDF"; enabled: !downloadController.running; onClicked: downloadController.backfillMissingPdfs(config()) }
                    PillButton { text: downloadController.running ? i18n.text("running") : i18n.text("start_download"); primary: true; busy: downloadController.running; onClicked: downloadController.start(config()) }
                    PillButton { text: i18n.text("stop"); enabled: downloadController.running; onClicked: downloadController.stop() }
                }
                    StatusBanner {
                        Layout.fillWidth: true
                        Layout.preferredHeight: implicitHeight
                        Layout.minimumHeight: implicitHeight
                        Layout.maximumHeight: implicitHeight

                        reserveSpace: true
                        maximumLines: 2
                        text: downloadController.statusText
                        busy: downloadController.running
                    }
                }
            }
        }
        RowLayout {
            id: statsRow
            Layout.fillWidth: true; Layout.preferredHeight: root.statsPaneHeight; spacing: 8
            StatCard { Layout.preferredHeight: root.statsPaneHeight; title: i18n.text("literature_records"); value: String(downloadController.stats.fetched_items || 0); detail: i18n.text("fetched") }
            StatCard { Layout.preferredHeight: root.statsPaneHeight; title: i18n.text("metadata"); value: String(downloadController.stats.added_records || 0); detail: i18n.text("saved") }
            StatCard { Layout.preferredHeight: root.statsPaneHeight; title: "PDF"; value: String((downloadController.stats.downloaded_pdfs || 0) + (downloadController.stats.backfill_downloaded_pdfs || 0)); detail: i18n.text("downloaded") }
        }
        Card {
            Layout.fillWidth: true
            Layout.preferredHeight: root.logPanePreferredHeight
            Layout.minimumHeight: root.logPaneMinimumHeight

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 12

                Text{
                    text: i18n.text("task_log")
                    color: theme.text
                    font.weight: Font.Bold
                }

                ScrollPreservingTextArea{
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    text: downloadController.logText
                    readOnly: true
                    wrapMode: TextArea.Wrap
                }
            }
        }
    }
    }

    // 灏嗙晫闈㈠瓧娈甸泦涓槧灏勫埌涓嬭浇鏍稿績锛岄伩鍏嶉珮绾ч€夐」鍦ㄨ縼绉诲悗闈欓粯涓㈠け銆?
    function config() {
        return { email: email.text, outputDir: outputDir.text, fromDate: fromDate.text,
                 toDate: normalizedToDate(toDate.text), toDateAuto: root.toDateAuto,
                 keywords: keywords.text, sort: root.sortValues[sortMode.currentIndex], maxPages: pages.value,
                 perPage: perPage.value, maxRecords: maxRecords.text, requestDelay: requestDelay.text,
                 pageDelay: pageDelay.text, minPdfBytes: minPdfBytes.text, downloadPdfs: downloadPdfs.checked,
                 retryMissingPdfs: retryMissing.checked, writeRetryRecords: writeRetry.checked,
                 strictKeywordMatch: strictMatch.checked, minKeywordMatchRatio: matchRatio.text,
                 topicPack: "auto", journalPack: "auto",
                 selectedJournals: root.selectedJournals, minTopicScore: root.topicScoreValues[minTopicScore.currentIndex],
                 journalWhitelistOnly: preferredJournalOnly.checked,
                 discoveryMode: discoveryMode.checked,
                 loop: loopJob.checked, loopSleep: loopSleep.text, maxRuntimeHours: runtimeHours.text,
                 resume: resume.checked, fastForwardExistingPages: fastForward.checked, oaOnly: oaOnly.checked,
                 sources: root.selectedSources, advancedVisible: root.advancedVisible }
    }
    function savedValue(settings, key, fallback) {
        return settings[key] !== undefined && settings[key] !== null ? settings[key] : fallback
    }
    function isIsoDate(value) {
        return /^\d{4}-\d{2}-\d{2}$/.test(String(value || ""))
    }

    function normalizedToDate(value) {
        let today = downloadController.defaultToDate
        let text = String(value || "").trim()

        if(!isIsoDate(text))
            return today

        if(text > today)
            return today

        return text
    }

    function restoredToDate(settings) {
        let today = downloadController.defaultToDate
        let savedAuto = savedValue(settings, "toDateAuto", true)
        let savedToDate = String(savedValue(settings, "toDate", "") || "").trim()

        // 旧配置没有 toDateAuto，默认走自动结束日期。
        // 这样可以修复“旧日期一直卡住”的问题。
        if(savedAuto || !isIsoDate(savedToDate) || savedToDate > today) {
            root.toDateAuto = true
            return today
        }

        root.toDateAuto = false
        return savedToDate
    }
    function topicScoreIndex(value) {
        let numericValue = Number(value)
        let bestIndex = 2
        let bestDistance = Math.abs(root.topicScoreValues[bestIndex] - numericValue)
        for(let i = 0; i < root.topicScoreValues.length; i++) {
            let distance = Math.abs(root.topicScoreValues[i] - numericValue)
            if(distance < bestDistance) {
                bestDistance = distance
                bestIndex = i
            }
        }
        return bestIndex
    }
    function scheduleSave() {
        if(!root.restoringSettings) saveSettingsTimer.restart()
    }
    function applyDiscoveryMode() {
        strictMatch.checked = false
        matchRatio.text = "0.3"
        minTopicScore.currentIndex = topicScoreIndex(0)
        preferredJournalOnly.checked = false
        resume.checked = false
        fastForward.checked = false
    }
    function restoreSavedConfig() {
        let settings=downloadController.savedConfig || {}
        email.text=savedValue(settings, "email", "")
        outputDir.text=savedValue(settings, "outputDir", downloadController.defaultOutputDir)
        fromDate.text=savedValue(settings, "fromDate", downloadController.defaultFromDate)
        toDate.text=restoredToDate(settings)
        keywords.text=savedValue(settings, "keywords", downloadController.defaultKeywords)
        let sortIndex=root.sortValues.indexOf(savedValue(settings, "sort", "relevance_score:desc"))
        sortMode.currentIndex=sortIndex >= 0 ? sortIndex : 1
        pages.value=savedValue(settings, "maxPages", 1)
        perPage.value=savedValue(settings, "perPage", 20)
        maxRecords.text=savedValue(settings, "maxRecords", "")
        requestDelay.text=savedValue(settings, "requestDelay", "0.2")
        pageDelay.text=savedValue(settings, "pageDelay", "0.5")
        minPdfBytes.text=savedValue(settings, "minPdfBytes", "1024")
        downloadPdfs.checked=savedValue(settings, "downloadPdfs", true)
        retryMissing.checked=savedValue(settings, "retryMissingPdfs", true)
        writeRetry.checked=savedValue(settings, "writeRetryRecords", false)
        strictMatch.checked=savedValue(settings, "strictKeywordMatch", true)
        matchRatio.text=savedValue(settings, "minKeywordMatchRatio", "0.75")
        root.selectedJournals=savedValue(settings, "selectedJournals", [])
        minTopicScore.currentIndex=topicScoreIndex(savedValue(settings, "minTopicScore", 0))
        preferredJournalOnly.checked=savedValue(settings, "journalWhitelistOnly", false)
        discoveryMode.checked=savedValue(settings, "discoveryMode", false)
        loopJob.checked=savedValue(settings, "loop", false)
        loopSleep.text=savedValue(settings, "loopSleep", "3600")
        runtimeHours.text=savedValue(settings, "maxRuntimeHours", "")
        resume.checked=savedValue(settings, "resume", true)
        fastForward.checked=savedValue(settings, "fastForwardExistingPages", true)
        if(discoveryMode.checked)
            root.applyDiscoveryMode()
        oaOnly.checked=savedValue(settings, "oaOnly", false)
        root.selectedSources=savedValue(settings, "sources", ["openalex"])
        root.advancedVisible=savedValue(settings, "advancedVisible", false)
    }
    function toggleSource(source, enabled) {
        let result=root.selectedSources.slice(); let index=result.indexOf(source)
        if(enabled && index<0) result.push(source)
        if(!enabled && index>=0) result.splice(index,1)
        root.selectedSources=result
    }
}
