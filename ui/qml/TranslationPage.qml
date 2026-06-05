import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: root
    property var selectedGlossaries: []
    property bool restoringSettings: true
    readonly property int resultPaneMinimumHeight: metrics.compact ? 135 : 170
    readonly property int progressPaneHeight: metrics.compact ? 58 : 66
    readonly property real translationFormPaneHeight: Math.max(metrics.compact ? 320 : 380, form.implicitHeight + metrics.cardPadding * 2)
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
    Component.onCompleted: { restoreSavedConfig(); syncPreview(); restoringSettings = false }
    onSelectedGlossariesChanged: scheduleSave()

    Dialog {
        id: glossaryDialog
        title: i18n.text("select_glossary")
        modal: true; width: Math.min(620, root.width - 32); height: Math.min(560, root.height - 32); anchors.centerIn: Overlay.overlay
        standardButtons: Dialog.Ok
        enter: Transition { NumberAnimation { property: "opacity"; from: 0; to: 1; duration: motion.fast } NumberAnimation { property: "scale"; from: 0.98; to: 1; duration: motion.fast } }
        exit: Transition { NumberAnimation { property: "opacity"; from: 1; to: 0; duration: motion.fast } NumberAnimation { property: "scale"; from: 1; to: 0.98; duration: motion.fast } }
        ColumnLayout {
            anchors.fill: parent; spacing: 8
            ScrollView {
                Layout.fillWidth: true; Layout.fillHeight: true
                ColumnLayout {
                    width: parent.width
                    Repeater {
                        model: translationController.glossaryCatalog
                        ModernCheckBox {
                            Layout.fillWidth: true
                            text: modelData.name + "  ·  " + modelData.terms
                            checked: selectedGlossaries.indexOf(modelData.path) >= 0
                            onToggled: toggleGlossary(modelData.path, checked)
                        }
                    }
                }
            }
            RowLayout {
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
        modal: true; width: Math.min(420, root.width - 32); anchors.centerIn: Overlay.overlay
        standardButtons: Dialog.NoButton
        enter: Transition { NumberAnimation { property: "opacity"; from: 0; to: 1; duration: motion.fast } NumberAnimation { property: "scale"; from: 0.98; to: 1; duration: motion.fast } }
        exit: Transition { NumberAnimation { property: "opacity"; from: 1; to: 0; duration: motion.fast } NumberAnimation { property: "scale"; from: 1; to: 0.98; duration: motion.fast } }
        ColumnLayout {
            anchors.fill: parent; spacing: 10
            TextField { id: rememberPassword; Layout.fillWidth: true; placeholderText: i18n.text("password"); echoMode: TextInput.Password }
            TextField { id: rememberConfirm; Layout.fillWidth: true; placeholderText: i18n.text("confirm_password"); echoMode: TextInput.Password }
            RowLayout {
                Item { Layout.fillWidth: true }
                PillButton { text: i18n.text("clear"); onClicked: rememberDialog.close() }
                PillButton { text: i18n.text("save"); primary: true; onClicked: if(translationController.rememberUserKey(apiKey.text,rememberPassword.text,rememberConfirm.text)) rememberDialog.close() }
            }
        }
    }

    Dialog {
        id: unlockDialog
        title: i18n.text("unlock")
        modal: true; width: Math.min(420, root.width - 32); anchors.centerIn: Overlay.overlay
        standardButtons: Dialog.NoButton
        enter: Transition { NumberAnimation { property: "opacity"; from: 0; to: 1; duration: motion.fast } NumberAnimation { property: "scale"; from: 0.98; to: 1; duration: motion.fast } }
        exit: Transition { NumberAnimation { property: "opacity"; from: 1; to: 0; duration: motion.fast } NumberAnimation { property: "scale"; from: 1; to: 0.98; duration: motion.fast } }
        ColumnLayout {
            anchors.fill: parent; spacing: 10
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
        width: pageScroll.availableWidth; spacing: metrics.sectionSpacing
        PageHeading { id: heading; Layout.fillWidth: true; title: i18n.text("translate_title"); subtitle: i18n.text("translate_desc"); titleSize: metrics.headingSize }
        Card {
            id: functionCard
            Layout.fillWidth: true
            Layout.preferredHeight: root.translationFormPaneHeight
            Layout.minimumHeight: metrics.compact ? 320 : 380
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
                    Layout.fillWidth: true; columns: 2; columnSpacing: 8; rowSpacing: 6
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
                        PillButton {
                            text: i18n.text("choose")
                            onClicked: {
                                let p=translationController.chooseDirectory(i18n.text("choose_translation_dir"), translationDir.text)
                                if(p) {
                                    translationDir.text=p
                                    translationController.refreshPendingDocuments(p)
                                }
                            }
                        }
                        PillButton { text: i18n.text("open"); onClicked: translationController.openDirectory(translationDir.text) }
                    }
                    Card {
                        Layout.columnSpan: 2
                        Layout.fillWidth: true
                        implicitHeight: pendingDocumentsContent.implicitHeight + 20
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
                                                ToolTip.delay: 350
                                                ToolTip.timeout: 5000
                                                ToolTip.visible: truncated && titleMouse.containsMouse
                                                ToolTip.text: modelData.fileName ? modelData.name + "\n" + modelData.fileName : modelData.name
                                                MouseArea { id: titleMouse; anchors.fill: parent; hoverEnabled: true }
                                            }
                                            Text { text: modelData.sizeText; color: theme.textMuted }
                                            Text { text: modelData.modifiedText; color: theme.textMuted }
                                        }
                                    }
                                }
                            }
                        }
                    }
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
                    Text { text: i18n.text("model_profile"); color: theme.textMuted }
                    ComboBox {
                        id: profile; Layout.fillWidth: true; model: translationController.modelProfiles; textRole: "label"
                        onActivated: { applyProfile(); root.scheduleSave() }
                        Component.onCompleted: applyProfile()
                        function applyProfile() { let item=model[currentIndex]; if(item) { modelId.text=item.model || ""; baseUrl.text=item.base_url || "" } }
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
                    Item { Layout.fillWidth: true }
                    PillButton { text: i18n.text("remember_key"); enabled: !!apiKey.text; onClicked: rememberDialog.open() }
                    PillButton { text: i18n.text("unlock"); enabled: translationController.rememberedKeyExists; onClicked: unlockDialog.open() }
                    PillButton { text: i18n.text("clear_key"); enabled: translationController.rememberedKeyExists; onClicked: translationController.clearRememberedKey() }
                    PillButton { text: translationController.defaultKeyLoaded ? i18n.text("unlocked") : "默认 API Key"; onClicked: translationController.unlockBundledDefaultKey() }
                }
                RowLayout {
                    Text { text: i18n.text("batch_size"); color: theme.textMuted }
                    SpinBox { id: batchSize; from: 1; to: 32; value: 3; editable: true; onValueChanged: root.scheduleSave() }
                    Text { text: i18n.text("batch_chars"); color: theme.textMuted }
                    SpinBox { id: batchChars; from: 1200; to: 20000; value: 3500; stepSize: 100; editable: true; onValueChanged: root.scheduleSave() }
                    Text { text: i18n.text("test_pages"); color: theme.textMuted }
                    TextField { id: maxPages; Layout.preferredWidth: 90; placeholderText: i18n.text("all_pages"); onTextChanged: root.scheduleSave() }
                    ModernCheckBox { id: layoutOnly; text: i18n.text("layout_only"); onToggled: root.scheduleSave() }
                    ModernCheckBox { id: useCache; text: i18n.text("use_cache"); checked: true; onToggled: root.scheduleSave() }
                    ModernCheckBox { id: summary; text: i18n.text("summary_page"); checked: true; onToggled: root.scheduleSave() }
                    ModernCheckBox { id: references; text: i18n.text("translate_refs"); onToggled: root.scheduleSave() }
                    ModernCheckBox { id: headerFooter; text: i18n.text("translate_headers"); onToggled: root.scheduleSave() }
                    Item { Layout.fillWidth: true }
                }
                RowLayout {
                    Text { text: i18n.text("glossary"); color: theme.textMuted }
                    Text { text: i18n.formatText("selected_count", { count: selectedGlossaries.length }); color: theme.text }
                    PillButton { text: i18n.text("select_glossary"); onClicked: glossaryDialog.open() }
                    Item { Layout.fillWidth: true }
                    PillButton { text: translationController.running ? i18n.text("running") : i18n.text("start_translate"); primary: true; busy: translationController.running; onClicked: translationController.start(config()) }
                    PillButton { text: i18n.text("stop"); enabled: translationController.running; onClicked: translationController.stop() }
                }
                StatusBanner { Layout.fillWidth: true; text: translationController.statusText; busy: translationController.running }
                }
            }
        }
        Card {
            id: progressCard
            Layout.fillWidth: true; Layout.preferredHeight: root.progressPaneHeight
            ColumnLayout {
                anchors.fill: parent; anchors.margins: 10
                Text { text: translationController.currentDocument || i18n.text("waiting_job"); color: theme.text; font.weight: Font.Bold }
                SoftProgressBar {
                    Layout.fillWidth: true
                    value: translationController.progressValue
                }
            }
        }
        GridLayout {
            Layout.fillWidth: true; Layout.preferredHeight: root.resultPanePreferredHeight; Layout.minimumHeight: root.resultPaneMinimumHeight; columns: metrics.narrow ? 1 : 2; rowSpacing: metrics.sectionSpacing; columnSpacing: metrics.sectionSpacing
            Card {
                Layout.fillWidth: true; Layout.fillHeight: true
                ColumnLayout {
                    anchors.fill: parent; anchors.margins: 12
                    Text { text: i18n.text("live_preview"); color: theme.text; font.weight: Font.Bold }
                    ScrollView {
                        id: previewScroll
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        SoftTextArea {
                            id: previewArea
                            width: previewScroll.availableWidth
                            readOnly: true
                            wrapMode: TextArea.Wrap
                        }
                    }
                }
            }
            Card {
                Layout.fillWidth: true; Layout.fillHeight: true
                ColumnLayout {
                    anchors.fill: parent; anchors.margins: 12
                    Text { text: i18n.text("task_log"); color: theme.text; font.weight: Font.Bold }
                    ScrollPreservingTextArea {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        text: translationController.logText
                        readOnly: true
                        wrapMode: TextArea.Wrap
                    }
                }
            }
        }
    }
    }

    Connections {
        target: translationController
        function onChanged() { root.syncPreview() }
    }

    // 勾选状态由路径而不是列表索引驱动，刷新自定义术语表后仍能稳定保留选择。
    function toggleGlossary(path, enabled) {
        let result=selectedGlossaries.slice(); let index=result.indexOf(path)
        if(enabled && index<0) result.push(path)
        if(!enabled && index>=0) result.splice(index,1)
        selectedGlossaries=result
    }
    function restoreDefaults() { let a=[]; for(let x of translationController.glossaryCatalog) if(x.selected) a.push(x.path); selectedGlossaries=a }
    function selectAll() { let a=[]; for(let x of translationController.glossaryCatalog) a.push(x.path); selectedGlossaries=a }
    function savedValue(settings, key, fallback) {
        return settings[key] !== undefined && settings[key] !== null ? settings[key] : fallback
    }
    function scheduleSave() {
        if(!root.restoringSettings) saveSettingsTimer.restart()
    }
    function restoreSavedConfig() {
        let settings=translationController.savedConfig || {}
        translationDir.text=settings.translationDir || settings.inputDir || translationController.defaultInputDir
        translationController.refreshPendingDocuments(translationDir.text)
        profile.currentIndex=savedValue(settings, "profileIndex", profile.currentIndex)
        direction.currentIndex=targetLangIndex(savedValue(settings, "targetLang", "zh"))
        profile.applyProfile()
        modelId.text=savedValue(settings, "model", modelId.text)
        baseUrl.text=savedValue(settings, "baseUrl", baseUrl.text)
        if(settings.glossaryPaths !== undefined && settings.glossaryPaths !== null) selectedGlossaries=settings.glossaryPaths
        else restoreDefaults()
        batchSize.value=savedValue(settings, "batchSize", 3)
        batchChars.value=savedValue(settings, "maxBatchChars", 3500)
        maxPages.text=savedValue(settings, "maxPages", "")
        layoutOnly.checked=savedValue(settings, "layoutOnly", false)
        useCache.checked=savedValue(settings, "useCache", true)
        summary.checked=savedValue(settings, "summaryPage", true)
        references.checked=savedValue(settings, "translateReferences", false)
        headerFooter.checked=savedValue(settings, "translateHeaderFooter", false)
    }
    function syncPreview() {
        let flick=previewScroll.contentItem
        if(!flick || previewArea.text === translationController.previewText) return
        let oldY=flick.contentY
        let maxY=Math.max(0, flick.contentHeight - flick.height)
        let wasAtBottom=oldY >= maxY - 12
        previewArea.text=translationController.previewText
        Qt.callLater(function() {
            let newMaxY=Math.max(0, flick.contentHeight - flick.height)
            flick.contentY=wasAtBottom ? newMaxY : Math.min(oldY, newMaxY)
        })
    }
    function targetLangIndex(value) {
        return value === "en" ? 1 : 0
    }
    function config() {
        return { translationDir:translationDir.text, model:modelId.text, baseUrl:baseUrl.text, apiKey:apiKey.text,
                 profileIndex:profile.currentIndex, targetLang:direction.currentValue || "zh", glossaryPaths:selectedGlossaries, batchSize:batchSize.value, maxBatchChars:batchChars.value, maxPages:maxPages.text,
                 layoutOnly:layoutOnly.checked, useCache:useCache.checked, summaryPage:summary.checked,
                 translateReferences:references.checked, translateHeaderFooter:headerFooter.checked }
    }
}
