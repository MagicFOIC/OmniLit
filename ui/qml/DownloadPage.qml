import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: root
    property var tourHost: null
    property var selectedSources: ["openalex", "europe_pmc", "arxiv", "crossref", "doaj"]
    property var keywordOptions: []
    property var keywordTerms: []
    property int editingKeywordIndex: -1
    property bool addingKeyword: false
    property bool apiSettingsExpanded: false
    property var qualityValues: ["keyword", "relaxed", "balanced", "strict", "very_strict"]
    property var qualityLabelKeys: ["quality_keyword", "quality_relaxed", "quality_balanced", "quality_strict", "quality_very_strict"]
    property var qualityTipKeys: ["quality_keyword_tip", "quality_relaxed_tip", "quality_balanced_tip", "quality_strict_tip", "quality_very_strict_tip"]
    property int selectedQualityIndex: 2
    property bool restoringSettings: true
    property bool toDateAuto: true
    readonly property int statsPaneHeight: metrics.compact ? 64 : 72
    readonly property real downloadFormPaneHeight: Math.max(metrics.compact ? 300 : 360, form.implicitHeight + metrics.cardPadding * 2)
    readonly property int logPaneMinimumHeight: metrics.compact ? 112 : 140
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

    Component.onCompleted: {
        restoreSavedConfig()
        restoreApiSettings()
        restoringSettings = false
        root.registerTourTargets()
    }
    Component.onDestruction: root.unregisterTourTargets()
    onSelectedSourcesChanged: scheduleSave()
    onSelectedQualityIndexChanged: scheduleSave()

    ScrollView {
        id: pageScroll
        anchors.fill: parent
        anchors.margins: metrics.pageMargin
        contentWidth: availableWidth
        clip: true
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

        ColumnLayout {
            width: pageScroll.availableWidth
            spacing: metrics.sectionSpacing

            PageHeading {
                id: heading
                Layout.fillWidth: true
                title: i18n.text("download_title")
                subtitle: i18n.text("download_desc")
                titleSize: metrics.headingSize
            }

            Card {
                id: functionCard
                Layout.fillWidth: true
                Layout.preferredHeight: root.downloadFormPaneHeight
                Layout.minimumHeight: metrics.compact ? 300 : 360

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
                        spacing: metrics.compact ? 7 : 10

                        GridLayout {
                            Layout.fillWidth: true
                            columns: metrics.narrow ? 2 : 4
                            columnSpacing: 12
                            rowSpacing: metrics.compact ? 6 : 8

                            Text { text: i18n.text("from_date"); color: theme.textMuted }
                            DatePickerField {
                                id: fromDate
                                text: downloadController.defaultFromDate
                                maxDateText: toDate.text
                                onTextChanged: root.scheduleSave()
                            }

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

                            Text { text: i18n.text("output_dir"); color: theme.textMuted }
                            RowLayout {
                                Layout.fillWidth: true
                                Layout.columnSpan: metrics.narrow ? 1 : 3
                                TextField {
                                    id: outputDir
                                    Layout.fillWidth: true
                                    text: downloadController.defaultOutputDir
                                    onTextChanged: root.scheduleSave()
                                }
                                PillButton {
                                    text: i18n.text("open")
                                    onClicked: downloadController.openDirectory(outputDir.text)
                                }
                            }
                        }

                        Text { text: i18n.text("keywords"); color: theme.textMuted }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 7

                            Flow {
                                id: keywordChipFlow
                                Layout.fillWidth: true
                                spacing: 7
                                Repeater {
                                    model: root.keywordTerms
                                    Rectangle {
                                        id: keywordChip
                                        property bool editing: root.editingKeywordIndex === index
                                        radius: 8
                                        color: theme.accentSofter
                                        border.color: theme.border
                                        implicitWidth: keywordChipRow.implicitWidth + 18
                                        implicitHeight: editing ? 36 : 32
                                        Row {
                                            id: keywordChipRow
                                            anchors.centerIn: parent
                                            spacing: 7
                                            Text {
                                                anchors.verticalCenter: parent.verticalCenter
                                                visible: !keywordChip.editing
                                                text: modelData
                                                color: theme.text
                                                font.pixelSize: Math.max(11, theme.baseFontSize - 1)
                                                elide: Text.ElideRight
                                                width: Math.min(260, implicitWidth)
                                                MouseArea {
                                                    anchors.fill: parent
                                                    cursorShape: Qt.IBeamCursor
                                                    onClicked: root.startEditKeyword(index)
                                                }
                                            }
                                            TextField {
                                                id: keywordEdit
                                                anchors.verticalCenter: parent.verticalCenter
                                                visible: keywordChip.editing
                                                text: modelData
                                                selectByMouse: true
                                                width: visible ? Math.min(300, Math.max(160, implicitWidth + 24)) : 0
                                                onVisibleChanged: if(visible) {
                                                    text = modelData
                                                    forceActiveFocus()
                                                    selectAll()
                                                }
                                                onAccepted: root.commitKeywordEdit(index, text)
                                                onActiveFocusChanged: if(keywordChip.editing && !activeFocus)
                                                    root.commitKeywordEdit(index, text)
                                            }
                                            Button {
                                                width: 20
                                                height: 20
                                                text: "x"
                                                hoverEnabled: true
                                                onClicked: root.removeKeyword(index)
                                                background: Rectangle {
                                                    radius: 8
                                                    color: parent.hovered ? theme.accentSoft : "transparent"
                                                }
                                                contentItem: Text {
                                                    text: parent.text
                                                    color: theme.textMuted
                                                    font.pixelSize: 12
                                                    font.weight: Font.Bold
                                                    horizontalAlignment: Text.AlignHCenter
                                                    verticalAlignment: Text.AlignVCenter
                                                }
                                            }
                                        }
                                    }
                                }

                                Rectangle {
                                    id: addKeywordChip
                                    property bool editing: root.addingKeyword
                                    radius: 8
                                    color: editing ? theme.surface : theme.accentSofter
                                    border.color: editing ? theme.accent : theme.border
                                    implicitWidth: editing ? addKeywordEdit.width + 18 : 36
                                    implicitHeight: editing ? 36 : 32

                                    MouseArea {
                                        anchors.fill: parent
                                        enabled: !addKeywordChip.editing
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: root.startAddKeyword()
                                    }

                                    Text {
                                        anchors.centerIn: parent
                                        visible: !addKeywordChip.editing
                                        text: "+"
                                        color: theme.accentStrong
                                        font.pixelSize: 18
                                        font.weight: Font.Bold
                                    }

                                    TextField {
                                        id: addKeywordEdit
                                        anchors.centerIn: parent
                                        visible: addKeywordChip.editing
                                        selectByMouse: true
                                        width: visible ? 240 : 0
                                        placeholderText: i18n.text("keyword_input_placeholder")
                                        onVisibleChanged: if(visible) {
                                            text = ""
                                            forceActiveFocus()
                                        }
                                        onAccepted: root.commitNewKeyword(text)
                                        onActiveFocusChanged: if(root.addingKeyword && !activeFocus)
                                            root.commitNewKeyword(text)
                                    }
                                }
                            }
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            Text { text: i18n.text("literature_sources"); color: theme.textMuted }
                            Repeater {
                                model: downloadController.availableSources
                                ModernCheckBox {
                                    text: modelData.label
                                    checked: root.selectedSources.indexOf(modelData.key) >= 0
                                    activePulse: downloadController.running && downloadController.activeSourceKey === modelData.key
                                    onToggled: root.toggleSource(modelData.key, checked)
                                    ModernToolTip {
                                        placement: "bottom"
                                        delay: 250
                                        timeout: 5000
                                        shown: parent.activePulse || parent.hovered
                                        text: parent.activePulse ? downloadController.activeSourceText : modelData.label
                                    }
                                }
                            }
                            Item { Layout.fillWidth: true }
                        }

                        Rectangle {
                            Layout.fillWidth: true
                            implicitHeight: downloadController.activeSourceText.length > 0 ? activeSourceText.implicitHeight + 14 : 0
                            opacity: downloadController.activeSourceText.length > 0 ? 1 : 0
                            radius: 8
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

                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 8

                            RowLayout {
                                Layout.fillWidth: true
                                Text {
                                    Layout.fillWidth: true
                                    text: i18n.text("source_api_settings")
                                    color: theme.text
                                    font.weight: Font.Bold
                                }
                                PillButton {
                                    text: root.apiSettingsExpanded ? i18n.text("source_api_collapse") : i18n.text("source_api_expand")
                                    onClicked: root.apiSettingsExpanded = !root.apiSettingsExpanded
                                    ModernToolTip {
                                        placement: "bottom"
                                        delay: 250
                                        timeout: 7000
                                        shown: parent.hovered
                                        text: i18n.text("source_api_settings_tip")
                                    }
                                }
                            }

                            Rectangle {
                                Layout.fillWidth: true
                                implicitHeight: root.apiSettingsExpanded ? apiSettingsColumn.implicitHeight + 16 : 0
                                opacity: root.apiSettingsExpanded ? 1 : 0
                                radius: 8
                                color: theme.surface
                                border.color: theme.border
                                clip: true
                                Behavior on opacity { NumberAnimation { duration: motion.fast } }
                                Behavior on implicitHeight { NumberAnimation { duration: motion.fast; easing.type: Easing.OutCubic } }

                                ColumnLayout {
                                    id: apiSettingsColumn
                                    anchors.left: parent.left
                                    anchors.right: parent.right
                                    anchors.top: parent.top
                                    anchors.margins: 8
                                    spacing: 8

                                    GridLayout {
                                        Layout.fillWidth: true
                                        columns: metrics.narrow ? 1 : 2
                                        columnSpacing: 10
                                        rowSpacing: 8

                                        TextField {
                                            id: openalexApiKey
                                            Layout.fillWidth: true
                                            echoMode: TextInput.Password
                                            placeholderText: sourceHasKey("openalex") ? i18n.text("api_key_saved_placeholder") : i18n.text("openalex_api_key")
                                        }
                                        TextField {
                                            id: crossrefMailto
                                            Layout.fillWidth: true
                                            placeholderText: i18n.text("crossref_mailto")
                                        }
                                        TextField {
                                            id: europePmcEmail
                                            Layout.fillWidth: true
                                            placeholderText: i18n.text("europe_pmc_email")
                                        }
                                        TextField {
                                            id: doajApiKey
                                            Layout.fillWidth: true
                                            echoMode: TextInput.Password
                                            placeholderText: sourceHasKey("doaj") ? i18n.text("api_key_saved_placeholder") : i18n.text("doaj_api_key")
                                        }
                                        TextField {
                                            id: semanticScholarApiKey
                                            Layout.fillWidth: true
                                            echoMode: TextInput.Password
                                            placeholderText: sourceHasKey("semantic_scholar") ? i18n.text("api_key_saved_placeholder") : i18n.text("semantic_scholar_api_key")
                                        }
                                    }

                                    Flow {
                                        Layout.fillWidth: true
                                        spacing: 8
                                        Repeater {
                                            model: downloadController.availableSourceApiStatuses
                                            Row {
                                                spacing: 6
                                                height: 30
                                                Text {
                                                    anchors.verticalCenter: parent.verticalCenter
                                                    text: modelData.label + ": " + root.sourceApiStatusText(modelData)
                                                    color: modelData.status === "test_failed" ? theme.danger : (modelData.configured ? theme.text : theme.textMuted)
                                                    font.pixelSize: Math.max(11, theme.baseFontSize - 1)
                                                }
                                                PillButton {
                                                    text: i18n.text("test_connection")
                                                    enabled: !downloadController.running
                                                    onClicked: downloadController.testSourceApi(modelData.source)
                                                }
                                                PillButton {
                                                    visible: modelData.hasKey
                                                    text: i18n.text("clear_key")
                                                    enabled: !downloadController.running
                                                    onClicked: downloadController.clearSourceApiKey(modelData.source)
                                                }
                                            }
                                        }
                                    }

                                    RowLayout {
                                        Layout.fillWidth: true
                                        Item { Layout.fillWidth: true }
                                        PillButton {
                                            text: i18n.text("save_api_settings")
                                            primary: true
                                            enabled: !downloadController.running
                                            onClicked: {
                                                downloadController.saveSourceApiSettings(root.apiSettings())
                                                openalexApiKey.text = ""
                                                doajApiKey.text = ""
                                                semanticScholarApiKey.text = ""
                                            }
                                        }
                                    }
                                }
                            }
                        }

                        Text {
                            Layout.fillWidth: true
                            text: i18n.text("settings_group_filter_quality")
                            color: theme.text
                            font.weight: Font.Bold
                        }

                        Flow {
                            Layout.fillWidth: true
                            spacing: 8
                            Repeater {
                                model: root.qualityValues.length
                                PillButton {
                                    text: i18n.text(root.qualityLabelKeys[index])
                                    primary: root.selectedQualityIndex === index
                                    onClicked: root.selectedQualityIndex = index
                                    ModernToolTip {
                                        placement: "bottom"
                                        delay: 250
                                        timeout: 9000
                                        shown: parent.hovered
                                        text: i18n.text(root.qualityTipKeys[index])
                                    }
                                }
                            }
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            Item { Layout.fillWidth: true }
                            PillButton {
                                text: downloadController.running ? i18n.text("running") : i18n.text("start_download")
                                primary: true
                                busy: downloadController.running
                                onClicked: downloadController.start(config())
                            }
                            PillButton {
                                text: i18n.text("pdf_backfill")
                                enabled: !downloadController.running
                                onClicked: downloadController.backfillMissingPdfs(config())
                                ModernToolTip {
                                    placement: "bottom"
                                    delay: 250
                                    timeout: 6000
                                    shown: parent.hovered
                                    text: i18n.text("pdf_backfill_tip")
                                }
                            }
                            PillButton {
                                text: i18n.text("stop")
                                enabled: downloadController.running
                                onClicked: downloadController.stop()
                            }
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
                Layout.fillWidth: true
                Layout.preferredHeight: root.statsPaneHeight
                spacing: 8
                StatCard { Layout.preferredHeight: root.statsPaneHeight; title: i18n.text("literature_records"); value: String(downloadController.stats.fetched_items_total || downloadController.stats.fetched_items || 0); detail: i18n.text("fetched") }
                StatCard { Layout.preferredHeight: root.statsPaneHeight; title: i18n.text("metadata"); value: String(downloadController.stats.added_records || 0); detail: i18n.text("saved") }
                StatCard { Layout.preferredHeight: root.statsPaneHeight; title: "PDF"; value: String(downloadController.stats.downloaded_pdfs || downloadController.stats.pdf_downloaded || 0); detail: i18n.text("downloaded") }
            }

            Card {
                Layout.fillWidth: true
                Layout.preferredHeight: root.logPanePreferredHeight
                Layout.minimumHeight: root.logPaneMinimumHeight

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 12

                    Text {
                        text: i18n.text("task_log")
                        color: theme.text
                        font.weight: Font.Bold
                    }

                    ScrollPreservingTextArea {
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

    function config() {
        return {
            email: downloadController.contactEmail,
            outputDir: outputDir.text,
            fromDate: fromDate.text,
            toDate: normalizedToDate(toDate.text),
            toDateAuto: root.toDateAuto,
            keywords: root.keywordTerms.join("\n"),
            sort: "relevance_score:desc",
            maxPages: 1000,
            perPage: 50,
            maxRecords: "",
            requestDelay: "0.2",
            pageDelay: "0.5",
            minPdfBytes: "1024",
            downloadPdfs: true,
            retryMissingPdfs: true,
            writeRetryRecords: false,
            qualityPreset: root.qualityValues[root.selectedQualityIndex],
            topicPack: "auto",
            journalPack: "auto",
            selectedJournals: [],
            minTopicScore: 0,
            journalWhitelistOnly: false,
            minImpactFactor: "",
            includeUnknownImpactFactor: true,
            journalMetricSource: "local_then_openalex",
            journalMetricCsv: "",
            loop: false,
            loopSleep: "3600",
            maxRuntimeHours: "",
            resume: true,
            fastForwardExistingPages: true,
            oaOnly: false,
            sources: root.selectedSources,
            advancedVisible: false
        }
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
        if(!isIsoDate(text) || text > today)
            return today
        return text
    }

    function restoredToDate(settings) {
        let today = downloadController.defaultToDate
        let savedAuto = savedValue(settings, "toDateAuto", true)
        let savedToDate = String(savedValue(settings, "toDate", "") || "").trim()
        if(savedAuto || !isIsoDate(savedToDate) || savedToDate > today) {
            root.toDateAuto = true
            return today
        }
        root.toDateAuto = false
        return savedToDate
    }

    function sourceHasKey(source) {
        let statuses = downloadController.availableSourceApiStatuses || []
        for(let i = 0; i < statuses.length; i++) {
            if(statuses[i].source === source)
                return !!statuses[i].hasKey
        }
        return false
    }

    function sourceApiStatusText(status) {
        if(status.status === "test_success")
            return i18n.text("source_api_test_success_short")
        if(status.status === "test_failed")
            return i18n.text("source_api_test_failed_short")
        return status.configured ? i18n.text("source_api_configured") : i18n.text("source_api_not_configured")
    }

    function apiSettings() {
        return {
            openalexApiKey: openalexApiKey.text,
            crossrefMailto: crossrefMailto.text,
            europePmcEmail: europePmcEmail.text,
            doajApiKey: doajApiKey.text,
            semanticScholarApiKey: semanticScholarApiKey.text
        }
    }

    function restoreApiSettings() {
        let settings = downloadController.sourceApiSettings || {}
        crossrefMailto.text = savedValue(settings, "crossrefMailto", downloadController.contactEmail)
        europePmcEmail.text = savedValue(settings, "europePmcEmail", downloadController.contactEmail)
        openalexApiKey.text = ""
        doajApiKey.text = ""
        semanticScholarApiKey.text = ""
    }

    function splitKeywords(value) {
        let text = String(value || "")
        return text.split(/[\r\n;,，；]+/).map(item => item.trim()).filter(item => item.length > 0)
    }

    function keywordOptionsFrom(value) {
        let result = []
        let seen = ({})
        let candidates = []
        for(let i = 0; i < downloadController.keywordSuggestions.length; i++)
            candidates.push(downloadController.keywordSuggestions[i])
        let saved = splitKeywords(value)
        for(let j = 0; j < saved.length; j++)
            candidates.push(saved[j])
        for(let k = 0; k < candidates.length; k++) {
            let item = String(candidates[k] || "").trim()
            let key = item.toLowerCase()
            if(item.length > 0 && !seen[key]) {
                result.push(item)
                seen[key] = true
            }
        }
        return result
    }

    function addKeywords(value) {
        let result = root.keywordTerms.slice()
        let seen = ({})
        for(let i = 0; i < result.length; i++)
            seen[String(result[i]).toLowerCase()] = true
        let incoming = splitKeywords(value)
        let changed = false
        for(let j = 0; j < incoming.length; j++) {
            let item = incoming[j]
            let key = item.toLowerCase()
            if(!seen[key]) {
                result.push(item)
                seen[key] = true
                changed = true
            }
        }
        if(!changed)
            return
        root.keywordTerms = result
        root.keywordOptions = keywordOptionsFrom(result.join("\n"))
        root.scheduleSave()
    }

    function startEditKeyword(index) {
        root.addingKeyword = false
        root.editingKeywordIndex = index
    }

    function startAddKeyword() {
        root.editingKeywordIndex = -1
        root.addingKeyword = true
    }

    function commitNewKeyword(value) {
        if(!root.addingKeyword)
            return
        root.addingKeyword = false
        addKeywords(value)
    }

    function commitKeywordEdit(index, value) {
        if(root.editingKeywordIndex !== index)
            return
        let edited = splitKeywords(value)
        let result = []
        let seen = ({})
        for(let i = 0; i < root.keywordTerms.length; i++) {
            let terms = i === index ? edited : [root.keywordTerms[i]]
            for(let j = 0; j < terms.length; j++) {
                let item = String(terms[j] || "").trim()
                let key = item.toLowerCase()
                if(item.length > 0 && !seen[key]) {
                    result.push(item)
                    seen[key] = true
                }
            }
        }
        root.editingKeywordIndex = -1
        root.keywordTerms = result
        root.keywordOptions = keywordOptionsFrom(result.join("\n"))
        root.scheduleSave()
    }

    function removeKeyword(index) {
        let result = root.keywordTerms.slice()
        if(index >= 0 && index < result.length)
            result.splice(index, 1)
        if(root.editingKeywordIndex === index)
            root.editingKeywordIndex = -1
        root.addingKeyword = false
        root.keywordTerms = result
        root.scheduleSave()
    }

    function qualityPresetIndex(value) {
        let index = root.qualityValues.indexOf(String(value || "balanced"))
        return index >= 0 ? index : 2
    }

    function legacyQualityPreset(settings) {
        if(savedValue(settings, "discoveryMode", false))
            return "keyword"
        let score = Number(savedValue(settings, "minTopicScore", 6))
        if(score <= 0)
            return "keyword"
        if(score <= 4)
            return "relaxed"
        if(score <= 6)
            return "balanced"
        if(score <= 9)
            return "strict"
        return "very_strict"
    }

    function scheduleSave() {
        if(!root.restoringSettings)
            saveSettingsTimer.restart()
    }

    function restoreSavedConfig() {
        let settings = downloadController.savedConfig || {}
        let savedKeywords = savedValue(settings, "keywords", downloadController.defaultKeywords)
        root.keywordOptions = keywordOptionsFrom(savedKeywords)
        outputDir.text = savedValue(settings, "outputDir", downloadController.defaultOutputDir)
        fromDate.text = savedValue(settings, "fromDate", downloadController.defaultFromDate)
        toDate.text = restoredToDate(settings)
        root.keywordTerms = splitKeywords(savedKeywords)
        root.selectedQualityIndex = qualityPresetIndex(savedValue(settings, "qualityPreset", legacyQualityPreset(settings)))
        root.selectedSources = savedValue(settings, "sources", ["openalex", "europe_pmc", "arxiv", "crossref", "doaj"])
    }

    function toggleSource(source, enabled) {
        let result = root.selectedSources.slice()
        let index = result.indexOf(source)
        if(enabled && index < 0)
            result.push(source)
        if(!enabled && index >= 0)
            result.splice(index, 1)
        root.selectedSources = result
    }

    function registerTourTargets() {
        if(root.tourHost)
            root.tourHost.registerTourTarget("nav.download", functionCard)
    }

    function unregisterTourTargets() {
        if(root.tourHost)
            root.tourHost.unregisterTourTarget("nav.download", functionCard)
    }
}
