import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: root
    property var sortValues: ["", "relevance_score:desc", "cited_by_count:desc", "publication_date:desc"]
    property var packValues: ["auto", "li_sulfur", "custom"]
    property var selectedSources: ["openalex"]
    property var selectedJournals: []
    property bool advancedVisible: false
    property bool restoringSettings: true
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

    ColumnLayout {
        anchors.fill: parent; anchors.margins: metrics.pageMargin; spacing: metrics.sectionSpacing
        PageHeading { Layout.fillWidth: true; title: i18n.text("download_title"); subtitle: i18n.text("download_desc"); titleSize: metrics.headingSize }
        Card {
            Layout.fillWidth: true
            Layout.preferredHeight: Math.min(form.implicitHeight + metrics.cardPadding * 2,
                                             Math.max(metrics.compact ? 270 : 360, root.height - (metrics.compact ? 230 : 260)))
            Layout.minimumHeight: metrics.compact ? 250 : Math.min(form.implicitHeight + metrics.cardPadding * 2, 360)
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
                    DatePickerField { id: fromDate; text: downloadController.defaultFromDate; onTextChanged: root.scheduleSave() }
                    Text { text: i18n.text("to_date"); color: theme.textMuted }
                    DatePickerField { id: toDate; text: downloadController.defaultToDate; onTextChanged: root.scheduleSave() }
                    Text { text: i18n.text("sort"); color: theme.textMuted }
                    ComboBox {
                        id: sortMode; Layout.fillWidth: true
                        model: [i18n.text("sort_default"), i18n.text("sort_relevance") + " ↓",
                                i18n.text("sort_citations") + " ↓", i18n.text("sort_date") + " ↓"]
                        currentIndex: 1
                        onCurrentIndexChanged: root.scheduleSave()
                    }
                    Text { text: i18n.text("max_records"); color: theme.textMuted }
                    TextField { id: maxRecords; Layout.fillWidth: true; placeholderText: i18n.text("optional"); onTextChanged: root.scheduleSave() }
                    Text { text: "Topic pack"; color: theme.textMuted }
                    ComboBox {
                        id: topicPack
                        Layout.fillWidth: true
                        model: ["自动根据关键词生成", "Li-S batteries 预设", "自定义"]
                        currentIndex: 0
                        onCurrentIndexChanged: root.scheduleSave()
                    }
                    Text { text: "OA journal pack"; color: theme.textMuted }
                    ComboBox {
                        id: journalPack
                        Layout.fillWidth: true
                        model: ["自动根据关键词生成", "Li-S batteries 预设", "自定义"]
                        currentIndex: 0
                        onCurrentIndexChanged: root.scheduleSave()
                    }
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
                            onToggled: root.toggleSource(modelData.key, checked)
                        }
                    }
                    Item { Layout.fillWidth: true }
                }
                RowLayout {
                    Text { text: i18n.text("pages"); color: theme.textMuted }
                    SpinBox { id: pages; from: 1; to: 1000; value: 1; editable: true; onValueChanged: root.scheduleSave() }
                    Text { text: i18n.text("per_page"); color: theme.textMuted }
                    SpinBox { id: perPage; from: 1; to: 200; value: 20; editable: true; onValueChanged: root.scheduleSave() }
                    Item { Layout.fillWidth: true }
                    PillButton { text: root.advancedVisible ? i18n.text("collapse_advanced") : i18n.text("advanced"); onClicked: root.advancedVisible = !root.advancedVisible }
                }
                RowLayout {
                    ModernCheckBox { id: downloadPdfs; text: i18n.text("download_pdf"); checked: true; onToggled: root.scheduleSave() }
                    ModernCheckBox { id: resume; text: i18n.text("resume"); checked: true; onToggled: root.scheduleSave() }
                    ModernCheckBox { id: oaOnly; text: i18n.text("oa_only"); onToggled: root.scheduleSave() }
                    ModernCheckBox { id: journalWhitelistOnly; text: "OA journal whitelist only"; onToggled: root.scheduleSave() }
                    Item { Layout.fillWidth: true }
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
                            Text { text: "Min topic score"; color: theme.textMuted }
                            TextField { id: minTopicScore; Layout.fillWidth: true; text: "6"; onTextChanged: root.scheduleSave() }
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
                            ModernCheckBox { id: loopJob; text: i18n.text("loop_job"); onToggled: root.scheduleSave() }
                            ModernCheckBox { id: fastForward; text: i18n.text("fast_forward"); checked: true; onToggled: root.scheduleSave() }
                        }
                    }
                }
                RowLayout {
                    Item { Layout.fillWidth: true }
                    PillButton { text: downloadController.running ? i18n.text("running") : i18n.text("start_download"); primary: true; busy: downloadController.running; onClicked: downloadController.start(config()) }
                    PillButton { text: i18n.text("stop"); enabled: downloadController.running; onClicked: downloadController.stop() }
                }
                StatusBanner { Layout.fillWidth: true; text: downloadController.statusText; busy: downloadController.running }
                }
            }
        }
        RowLayout {
            Layout.fillWidth: true; spacing: 8
            StatCard { title: i18n.text("literature_records"); value: String(downloadController.stats.fetched_items || 0); detail: i18n.text("fetched") }
            StatCard { title: i18n.text("metadata"); value: String(downloadController.stats.added_records || 0); detail: i18n.text("saved") }
            StatCard { title: "PDF"; value: String(downloadController.stats.downloaded_pdfs || 0); detail: i18n.text("downloaded") }
        }
        Card {
            Layout.fillWidth: true; Layout.fillHeight: true; Layout.minimumHeight: metrics.compact ? 64 : 80
            ScrollView { anchors.fill: parent; anchors.margins: 12; SoftTextArea { text: downloadController.logText; readOnly: true; wrapMode: TextArea.Wrap } }
        }
    }

    // 将界面字段集中映射到下载核心，避免高级选项在迁移后静默丢失。
    function config() {
        return { email: email.text, outputDir: outputDir.text, fromDate: fromDate.text, toDate: toDate.text,
                 keywords: keywords.text, sort: root.sortValues[sortMode.currentIndex], maxPages: pages.value,
                 perPage: perPage.value, maxRecords: maxRecords.text, requestDelay: requestDelay.text,
                 pageDelay: pageDelay.text, minPdfBytes: minPdfBytes.text, downloadPdfs: downloadPdfs.checked,
                 retryMissingPdfs: retryMissing.checked, writeRetryRecords: writeRetry.checked,
                 strictKeywordMatch: strictMatch.checked, minKeywordMatchRatio: matchRatio.text,
                 topicPack: root.packValues[topicPack.currentIndex], journalPack: root.packValues[journalPack.currentIndex],
                 selectedJournals: root.selectedJournals, minTopicScore: minTopicScore.text,
                 journalWhitelistOnly: journalWhitelistOnly.checked,
                 loop: loopJob.checked, loopSleep: loopSleep.text, maxRuntimeHours: runtimeHours.text,
                 resume: resume.checked, fastForwardExistingPages: fastForward.checked, oaOnly: oaOnly.checked,
                 sources: root.selectedSources, advancedVisible: root.advancedVisible }
    }
    function savedValue(settings, key, fallback) {
        return settings[key] !== undefined && settings[key] !== null ? settings[key] : fallback
    }
    function packIndex(value, fallback) {
        let index = root.packValues.indexOf(value)
        if(index >= 0) return index
        let fallbackIndex = root.packValues.indexOf(fallback)
        return fallbackIndex >= 0 ? fallbackIndex : 0
    }
    function scheduleSave() {
        if(!root.restoringSettings) saveSettingsTimer.restart()
    }
    function restoreSavedConfig() {
        let settings=downloadController.savedConfig || {}
        email.text=savedValue(settings, "email", "")
        outputDir.text=savedValue(settings, "outputDir", downloadController.defaultOutputDir)
        fromDate.text=savedValue(settings, "fromDate", downloadController.defaultFromDate)
        toDate.text=savedValue(settings, "toDate", downloadController.defaultToDate)
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
        topicPack.currentIndex=packIndex(savedValue(settings, "topicPack", "auto"), "auto")
        journalPack.currentIndex=packIndex(savedValue(settings, "journalPack", "auto"), "auto")
        root.selectedJournals=savedValue(settings, "selectedJournals", [])
        minTopicScore.text=savedValue(settings, "minTopicScore", "6")
        journalWhitelistOnly.checked=savedValue(settings, "journalWhitelistOnly", false)
        loopJob.checked=savedValue(settings, "loop", false)
        loopSleep.text=savedValue(settings, "loopSleep", "3600")
        runtimeHours.text=savedValue(settings, "maxRuntimeHours", "")
        resume.checked=savedValue(settings, "resume", true)
        fastForward.checked=savedValue(settings, "fastForwardExistingPages", true)
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
