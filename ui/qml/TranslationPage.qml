import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: root
    property var tourHost: null
    property var selectedGlossaries: []
    property bool restoringSettings: true
    property bool advancedTranslationSettingsOpen: false
    readonly property int resultPaneMinimumHeight: metrics.compact ? 135 : 170
    readonly property int progressPaneHeight: metrics.compact ? 58 : 66
    readonly property real translationFormPaneHeight: Math.max(metrics.compact ? 390 : 450, form.implicitHeight + metrics.cardPadding * 2)
    readonly property real resultPanePreferredHeight: Math.max(
        resultPaneMinimumHeight,
        root.height - metrics.pageMargin * 2 - heading.implicitHeight - translationFormPaneHeight - progressPaneHeight - metrics.sectionSpacing * 3
    )

    Motion { id: motion }
    PageMotion { target: root }
    I18n { id: i18n }
    Theme { id: theme }
    LayoutMetrics { id: metrics; viewportWidth: root.width; viewportHeight: root.height }

    Timer { id: saveSettingsTimer; interval: 350; onTriggered: translationController.saveConfig(config()) }
    Component.onCompleted: { restoreSavedConfig(); restoringSettings = false; root.registerTourTargets() }
    Component.onDestruction: root.unregisterTourTargets()
    onSelectedGlossariesChanged: scheduleSave()

    Dialog {
        id: glossaryDialog
        title: i18n.text("select_glossary")
        modal: true
        width: Math.min(760, root.width - 32)
        height: Math.min(620, root.height - 32)
        anchors.centerIn: Overlay.overlay
        standardButtons: Dialog.Ok
        enter: Transition { NumberAnimation { property: "opacity"; from: 0; to: 1; duration: motion.fast } NumberAnimation { property: "scale"; from: 0.98; to: 1; duration: motion.fast } }
        exit: Transition { NumberAnimation { property: "opacity"; from: 1; to: 0; duration: motion.fast } NumberAnimation { property: "scale"; from: 1; to: 0.98; duration: motion.fast } }

        ColumnLayout {
            anchors.fill: parent
            spacing: 10

            ScrollView {
                id: glossaryScroll
                Layout.fillWidth: true
                Layout.fillHeight: true
                contentWidth: availableWidth
                clip: true
                ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

                ColumnLayout {
                    width: glossaryScroll.availableWidth
                    spacing: 10

                    Repeater {
                        model: translationController.glossaryCatalog
                        delegate: Rectangle {
                            Layout.fillWidth: true
                            implicitHeight: glossaryCardContent.implicitHeight + 22
                            radius: 8
                            color: selectedGlossaries.indexOf(modelData.path) >= 0 ? theme.accentSofter : theme.surfaceSoft
                            border.color: selectedGlossaries.indexOf(modelData.path) >= 0 ? theme.accent : theme.border

                            ColumnLayout {
                                id: glossaryCardContent
                                anchors.fill: parent
                                anchors.margins: 11
                                spacing: 6

                                RowLayout {
                                    Layout.fillWidth: true
                                    ModernCheckBox {
                                        checked: selectedGlossaries.indexOf(modelData.path) >= 0
                                        onToggled: toggleGlossary(modelData.path, checked)
                                    }
                                    ColumnLayout {
                                        Layout.fillWidth: true
                                        spacing: 2
                                        Text { Layout.fillWidth: true; text: modelData.titleZh; color: theme.text; font.weight: Font.Bold; elide: Text.ElideRight }
                                        Text { Layout.fillWidth: true; text: modelData.titleEn; color: theme.textMuted; elide: Text.ElideRight }
                                    }
                                    Text { text: i18n.formatText("terms_count", { count: modelData.terms }); color: theme.textMuted }
                                }

                                Text {
                                    Layout.fillWidth: true
                                    text: modelData.descriptionZh
                                    color: theme.text
                                    wrapMode: Text.WordWrap
                                }
                                Text {
                                    Layout.fillWidth: true
                                    text: modelData.descriptionEn
                                    color: theme.textMuted
                                    wrapMode: Text.WordWrap
                                }

                                Flow {
                                    Layout.fillWidth: true
                                    spacing: 6
                                    Repeater {
                                        model: modelData.preview || []
                                        delegate: Label {
                                            text: modelData.source + " => " + modelData.target
                                            color: theme.text
                                            padding: 6
                                            background: Rectangle { radius: 6; color: theme.surface; border.color: theme.border }
                                        }
                                    }
                                }
                            }

                            MouseArea {
                                anchors.fill: parent
                                acceptedButtons: Qt.LeftButton
                                onClicked: toggleGlossary(modelData.path, selectedGlossaries.indexOf(modelData.path) < 0)
                            }
                        }
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                PillButton { text: i18n.text("all"); onClicked: selectAll() }
                PillButton { text: i18n.text("clear"); onClicked: selectedGlossaries = [] }
                PillButton { text: i18n.text("default"); onClicked: restoreDefaults() }
                PillButton { text: i18n.text("refresh"); onClicked: translationController.refreshGlossaries() }
                Item { Layout.fillWidth: true }
                PillButton { text: i18n.text("open"); onClicked: translationController.openGlossaryDirectory() }
            }
        }
    }

    Dialog {
        id: rememberDialog
        title: i18n.text("remember_key")
        modal: true
        width: Math.min(420, root.width - 32)
        anchors.centerIn: Overlay.overlay
        standardButtons: Dialog.NoButton
        enter: Transition { NumberAnimation { property: "opacity"; from: 0; to: 1; duration: motion.fast } NumberAnimation { property: "scale"; from: 0.98; to: 1; duration: motion.fast } }
        exit: Transition { NumberAnimation { property: "opacity"; from: 1; to: 0; duration: motion.fast } NumberAnimation { property: "scale"; from: 1; to: 0.98; duration: motion.fast } }
        ColumnLayout {
            anchors.fill: parent
            spacing: 10
            TextField { id: rememberPassword; Layout.fillWidth: true; placeholderText: i18n.text("password"); echoMode: TextInput.Password }
            TextField { id: rememberConfirm; Layout.fillWidth: true; placeholderText: i18n.text("confirm_password"); echoMode: TextInput.Password }
            RowLayout {
                Item { Layout.fillWidth: true }
                PillButton { text: i18n.text("clear"); onClicked: rememberDialog.close() }
                PillButton { text: i18n.text("save"); primary: true; onClicked: if(translationController.rememberUserKey(apiKey.text, rememberPassword.text, rememberConfirm.text)) rememberDialog.close() }
            }
        }
    }

    Dialog {
        id: unlockDialog
        title: i18n.text("unlock")
        modal: true
        width: Math.min(420, root.width - 32)
        anchors.centerIn: Overlay.overlay
        standardButtons: Dialog.NoButton
        enter: Transition { NumberAnimation { property: "opacity"; from: 0; to: 1; duration: motion.fast } NumberAnimation { property: "scale"; from: 0.98; to: 1; duration: motion.fast } }
        exit: Transition { NumberAnimation { property: "opacity"; from: 1; to: 0; duration: motion.fast } NumberAnimation { property: "scale"; from: 1; to: 0.98; duration: motion.fast } }
        ColumnLayout {
            anchors.fill: parent
            spacing: 10
            TextField { id: unlockPassword; Layout.fillWidth: true; placeholderText: i18n.text("password"); echoMode: TextInput.Password }
            RowLayout {
                Item { Layout.fillWidth: true }
                PillButton { text: i18n.text("clear"); onClicked: unlockDialog.close() }
                PillButton { text: i18n.text("unlock"); primary: true; onClicked: if(translationController.unlockRememberedKey(unlockPassword.text)) unlockDialog.close() }
            }
        }
    }

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
                title: i18n.text("translate_title")
                subtitle: i18n.text("translate_desc")
                titleSize: metrics.headingSize
            }

            Card {
                id: functionCard
                Layout.fillWidth: true
                Layout.preferredHeight: root.translationFormPaneHeight
                Layout.minimumHeight: metrics.compact ? 390 : 450

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
                        spacing: metrics.compact ? 8 : 10

                        GridLayout {
                            Layout.fillWidth: true
                            columns: 2
                            columnSpacing: 10
                            rowSpacing: 8

                            Text { text: i18n.text("translation_dir"); color: theme.textMuted }
                            RowLayout {
                                Layout.fillWidth: true
                                TextField {
                                    id: translationDir
                                    Layout.fillWidth: true
                                    text: translationController.defaultInputDir
                                    onTextChanged: root.scheduleSave()
                                    onEditingFinished: translationController.refreshPendingDocuments(text)
                                }
                                PillButton { text: i18n.text("open"); onClicked: translationController.openDirectory(translationDir.text) }
                            }

                        }

                        Rectangle {
                            id: pendingDocumentsPanel
                            Layout.fillWidth: true
                            implicitHeight: pendingDocumentsContent.implicitHeight + 20
                            radius: 8
                            color: theme.surfaceSoft
                            border.color: theme.border

                            ColumnLayout {
                                id: pendingDocumentsContent
                                anchors.fill: parent
                                anchors.margins: 10
                                spacing: 7

                                RowLayout {
                                    Layout.fillWidth: true
                                    Text { text: i18n.text("pending_literature"); color: theme.text; font.weight: Font.Bold }
                                    Item { Layout.fillWidth: true }
                                    PillButton { text: i18n.text("refresh"); onClicked: translationController.refreshPendingDocuments(translationDir.text) }
                                }

                                Text {
                                    visible: translationController.pendingDocumentCount === 0
                                    text: i18n.text("empty_translation_dir")
                                    color: theme.textMuted
                                }

                                ScrollView {
                                    id: pendingDocumentsScroll
                                    visible: translationController.pendingDocumentCount > 0
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: Math.min(pendingDocumentsList.implicitHeight, metrics.compact ? 82 : 110)
                                    contentWidth: availableWidth
                                    clip: true
                                    ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

                                    ColumnLayout {
                                        id: pendingDocumentsList
                                        width: pendingDocumentsScroll.availableWidth
                                        Repeater {
                                            model: translationController.pendingDocuments
                                            delegate: RowLayout {
                                                Layout.fillWidth: true
                                                Text {
                                                    Layout.fillWidth: true
                                                    text: modelData.name
                                                    color: theme.text
                                                    elide: Text.ElideRight
                                                    MouseArea { id: titleMouse; anchors.fill: parent; hoverEnabled: true }
                                                    ModernToolTip {
                                                        placement: "bottom"
                                                        delay: 350
                                                        timeout: 5000
                                                        shown: parent.truncated && titleMouse.containsMouse
                                                        text: modelData.fileName ? modelData.name + "\n" + modelData.fileName : modelData.name
                                                    }
                                                }
                                                Text { text: modelData.sizeText; color: theme.textMuted }
                                                Text { text: modelData.modifiedText; color: theme.textMuted }
                                            }
                                        }
                                    }
                                }
                            }
                        }

                        GridLayout {
                            Layout.fillWidth: true
                            columns: 2
                            columnSpacing: 10
                            rowSpacing: 8

                            Text { text: i18n.text("translation_direction"); color: theme.textMuted }
                            ComboBox {
                                id: direction
                                Layout.fillWidth: true
                                textRole: "label"
                                valueRole: "value"
                                model: [
                                    { value: "zh", label: i18n.text("translate_en_to_zh") },
                                    { value: "en", label: i18n.text("translate_zh_to_en") }
                                ]
                                onActivated: root.scheduleSave()
                            }

                            Text { text: i18n.text("translation_range"); color: theme.textMuted }
                            RowLayout {
                                Layout.fillWidth: true
                                ComboBox {
                                    id: rangeMode
                                    Layout.fillWidth: true
                                    textRole: "label"
                                    model: [
                                        { label: i18n.text("range_full") },
                                        { label: i18n.text("range_quick") },
                                        { label: i18n.text("range_custom") }
                                    ]
                                    onActivated: root.scheduleSave()
                                }
                                Text { visible: rangeMode.currentIndex === 2; text: i18n.text("first_n_pages"); color: theme.textMuted }
                                SpinBox {
                                    id: customMaxPages
                                    visible: rangeMode.currentIndex === 2
                                    from: 1
                                    to: 999
                                    value: 10
                                    editable: true
                                    onValueChanged: root.scheduleSave()
                                }
                            }

                            Text { text: i18n.text("glossary"); color: theme.textMuted }
                            RowLayout {
                                Layout.fillWidth: true
                                Text {
                                    Layout.fillWidth: true
                                    text: i18n.formatText("selected_count", { count: selectedGlossaries.length })
                                    color: theme.text
                                    elide: Text.ElideRight
                                }
                                PillButton { text: i18n.text("select_glossary"); onClicked: glossaryDialog.open() }
                            }
                        }

                        Rectangle {
                            Layout.fillWidth: true
                            implicitHeight: serviceContent.implicitHeight + 18
                            radius: 8
                            color: theme.surfaceSoft
                            border.color: theme.border

                            ColumnLayout {
                                id: serviceContent
                                anchors.fill: parent
                                anchors.margins: 9
                                spacing: 8

                                GridLayout {
                                    Layout.fillWidth: true
                                    columns: 2
                                    columnSpacing: 10
                                    rowSpacing: 6

                                    Text { text: i18n.text("translation_service"); color: theme.textMuted }
                                    Text { Layout.fillWidth: true; text: i18n.text("omnilit_default_service"); color: theme.text; elide: Text.ElideRight }
                                    Text { text: i18n.text("model_label"); color: theme.textMuted }
                                    Text { Layout.fillWidth: true; text: i18n.text("recommended_model"); color: theme.text; elide: Text.ElideRight }
                                }

                                Text {
                                    Layout.fillWidth: true
                                    text: translationController.defaultKeyLoaded ? i18n.text("default_service_ready") : i18n.text("default_service_unavailable_short")
                                    color: translationController.defaultKeyLoaded ? theme.success : theme.warning
                                    wrapMode: Text.WordWrap
                                }

                                ModernCheckBox {
                                    id: customService
                                    text: i18n.text("custom_service")
                                    onToggled: root.scheduleSave()
                                }
                                Text {
                                    Layout.fillWidth: true
                                    visible: !customService.checked
                                    text: i18n.text("custom_service_hint")
                                    color: theme.textMuted
                                    wrapMode: Text.WordWrap
                                }

                                GridLayout {
                                    Layout.fillWidth: true
                                    visible: customService.checked
                                    columns: 2
                                    columnSpacing: 10
                                    rowSpacing: 8

                                    Text { text: i18n.text("model_profile"); color: theme.textMuted }
                                    ComboBox {
                                        id: profile
                                        Layout.fillWidth: true
                                        model: translationController.modelProfiles
                                        textRole: "label"
                                        onActivated: { applyProfile(); root.scheduleSave() }
                                        Component.onCompleted: applyProfile()
                                        function applyProfile() {
                                            let item = model[currentIndex]
                                            if(item) {
                                                modelId.text = item.model || ""
                                                baseUrl.text = item.base_url || ""
                                            }
                                        }
                                    }

                                    Text { text: i18n.text("model_id"); color: theme.textMuted }
                                    TextField { id: modelId; Layout.fillWidth: true; placeholderText: i18n.text("model_id"); onTextChanged: root.scheduleSave() }

                                    Text { text: i18n.text("api_url"); color: theme.textMuted }
                                    TextField { id: baseUrl; Layout.fillWidth: true; placeholderText: i18n.text("api_url"); onTextChanged: root.scheduleSave() }

                                    Text { text: "API Key"; color: theme.textMuted }
                                    RowLayout {
                                        Layout.fillWidth: true
                                        TextField { id: apiKey; Layout.fillWidth: true; echoMode: showKey.checked ? TextInput.Normal : TextInput.Password }
                                        ModernCheckBox { id: showKey; text: i18n.text("show") }
                                    }
                                }

                                RowLayout {
                                    visible: customService.checked
                                    Layout.fillWidth: true
                                    Item { Layout.fillWidth: true }
                                    PillButton { text: i18n.text("remember_key"); enabled: !!apiKey.text; onClicked: rememberDialog.open() }
                                    PillButton { text: i18n.text("unlock"); enabled: translationController.rememberedKeyExists; onClicked: unlockDialog.open() }
                                    PillButton { text: i18n.text("clear_key"); enabled: translationController.rememberedKeyExists; onClicked: translationController.clearRememberedKey() }
                                }
                            }
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            Text { text: i18n.text("more_options"); color: theme.text; font.weight: Font.Bold }
                            Item { Layout.fillWidth: true }
                            PillButton { text: root.advancedTranslationSettingsOpen ? i18n.text("collapse_advanced") : i18n.text("advanced"); onClicked: root.advancedTranslationSettingsOpen = !root.advancedTranslationSettingsOpen }
                        }

                        Flow {
                            Layout.fillWidth: true
                            visible: root.advancedTranslationSettingsOpen
                            spacing: 8
                            width: parent.width
                            ModernCheckBox { id: layoutOnly; text: i18n.text("layout_only"); onToggled: root.scheduleSave() }
                            ModernCheckBox { id: useCache; text: i18n.text("use_cache"); checked: true; onToggled: root.scheduleSave() }
                            ModernCheckBox { id: summary; text: i18n.text("summary_page"); checked: true; onToggled: root.scheduleSave() }
                            ModernCheckBox { id: references; text: i18n.text("translate_refs"); onToggled: root.scheduleSave() }
                            ModernCheckBox { id: headerFooter; text: i18n.text("translate_headers"); onToggled: root.scheduleSave() }
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            Item { Layout.fillWidth: true }
                            PillButton {
                                text: translationController.running ? i18n.text("running") : i18n.text("start_translate")
                                primary: true
                                busy: translationController.running
                                onClicked: translationController.start(config())
                            }
                            PillButton {
                                text: i18n.text("stop")
                                visible: translationController.running
                                enabled: translationController.running
                                onClicked: translationController.stop()
                            }
                        }

                        StatusBanner { Layout.fillWidth: true; text: translationController.statusText; busy: translationController.running }
                    }
                }
            }

            Card {
                id: progressCard
                Layout.fillWidth: true
                Layout.preferredHeight: root.progressPaneHeight
                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 10
                    Text { text: translationController.currentDocument || i18n.text("waiting_job"); color: theme.text; font.weight: Font.Bold }
                    SoftProgressBar {
                        Layout.fillWidth: true
                        value: translationController.progressValue
                    }
                }
            }

            GridLayout {
                Layout.fillWidth: true
                Layout.preferredHeight: root.resultPanePreferredHeight
                Layout.minimumHeight: root.resultPaneMinimumHeight
                columns: metrics.narrow ? 1 : 2
                rowSpacing: metrics.sectionSpacing
                columnSpacing: metrics.sectionSpacing

                Card {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 12
                        Text {
                            text: i18n.text("live_preview")
                            color: theme.text
                            font.weight: Font.Bold
                        }
                        AutoScrollPanel {
                            id: previewPanel
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            unreadText: i18n.text("new_translation_output")
                            contentRevision: String(translationController.previewEntries.length) + ":" + translationController.previewText.length

                            Repeater {
                                model: translationController.previewEntries
                                delegate: Rectangle {
                                    width: previewPanel.width
                                    implicitHeight: previewTextBlock.implicitHeight + 18
                                    radius: 8
                                    color: theme.accentSofter
                                    border.color: theme.border
                                    Text {
                                        id: previewTextBlock
                                        anchors.left: parent.left
                                        anchors.right: parent.right
                                        anchors.top: parent.top
                                        anchors.margins: 9
                                        text: modelData.text
                                        color: theme.text
                                        wrapMode: Text.WrapAnywhere
                                        lineHeight: theme.translationLineHeight
                                    }
                                }
                            }
                        }
                    }
                }

                Card {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 12
                        LogPanel {
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            title: i18n.text("task_log")
                            entries: translationController.logEntries
                            controller: translationController
                            unreadText: i18n.text("new_log_output")
                        }
                    }
                }
            }
        }
    }

    function toggleGlossary(path, enabled) {
        let result = selectedGlossaries.slice()
        let index = result.indexOf(path)
        if(enabled && index < 0) result.push(path)
        if(!enabled && index >= 0) result.splice(index, 1)
        selectedGlossaries = result
    }

    function restoreDefaults() {
        let result = []
        for(let item of translationController.glossaryCatalog)
            if(item.selected) result.push(item.path)
        selectedGlossaries = result
    }

    function selectAll() {
        let result = []
        for(let item of translationController.glossaryCatalog)
            result.push(item.path)
        selectedGlossaries = result
    }

    function savedValue(settings, key, fallback) {
        return settings[key] !== undefined && settings[key] !== null ? settings[key] : fallback
    }

    function scheduleSave() {
        if(!root.restoringSettings) saveSettingsTimer.restart()
    }

    function restoreSavedConfig() {
        let settings = translationController.savedConfig || {}
        translationDir.text = settings.translationDir || settings.inputDir || translationController.defaultInputDir
        translationController.refreshPendingDocuments(translationDir.text)
        profile.currentIndex = savedValue(settings, "profileIndex", profile.currentIndex)
        direction.currentIndex = targetLangIndex(savedValue(settings, "targetLang", "zh"))
        profile.applyProfile()
        modelId.text = savedValue(settings, "model", modelId.text)
        baseUrl.text = savedValue(settings, "baseUrl", baseUrl.text)
        customService.checked = savedValue(settings, "customService", settings.model !== undefined || settings.baseUrl !== undefined)
        if(settings.glossaryPaths !== undefined && settings.glossaryPaths !== null) selectedGlossaries = settings.glossaryPaths
        else restoreDefaults()
        customMaxPages.value = Number(savedValue(settings, "customMaxPages", savedValue(settings, "maxPages", 10))) || 10
        rangeMode.currentIndex = rangeIndexFromSettings(settings)
        layoutOnly.checked = savedValue(settings, "layoutOnly", false)
        useCache.checked = savedValue(settings, "useCache", true)
        summary.checked = savedValue(settings, "summaryPage", true)
        references.checked = savedValue(settings, "translateReferences", false)
        headerFooter.checked = savedValue(settings, "translateHeaderFooter", false)
    }

    function targetLangIndex(value) {
        return value === "en" ? 1 : 0
    }

    function rangeIndexFromSettings(settings) {
        if(settings.rangeMode !== undefined && settings.rangeMode !== null)
            return Math.max(0, Math.min(2, Number(settings.rangeMode) || 0))
        let pages = String(savedValue(settings, "maxPages", "") || "").trim()
        if(!pages) return 0
        return Number(pages) === 3 ? 1 : 2
    }

    function maxPagesValue() {
        if(rangeMode.currentIndex === 0) return ""
        if(rangeMode.currentIndex === 1) return 3
        return customMaxPages.value
    }

    function apiConfigured() {
        return translationController.defaultKeyLoaded || translationController.rememberedKeyExists || apiKey.text.length > 0
    }

    function config() {
        return {
            translationDir: translationDir.text,
            customService: customService.checked,
            model: customService.checked ? modelId.text : "deepseek-v4-flash",
            baseUrl: customService.checked ? baseUrl.text : "https://api.deepseek.com",
            apiKey: customService.checked ? apiKey.text : "",
            profileIndex: profile.currentIndex,
            targetLang: direction.currentValue || "zh",
            glossaryPaths: selectedGlossaries,
            maxPages: maxPagesValue(),
            rangeMode: rangeMode.currentIndex,
            customMaxPages: customMaxPages.value,
            layoutOnly: layoutOnly.checked,
            useCache: useCache.checked,
            summaryPage: summary.checked,
            translateReferences: references.checked,
            translateHeaderFooter: headerFooter.checked
        }
    }

    function registerTourTargets() {
        if(root.tourHost)
            root.tourHost.registerTourTarget("nav.translate", functionCard)
    }

    function unregisterTourTargets() {
        if(root.tourHost)
            root.tourHost.unregisterTourTarget("nav.translate", functionCard)
    }
}
