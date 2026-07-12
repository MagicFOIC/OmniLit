import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: root

    property string title: ""
    property string unreadText: "New logs available"
    property var entries: []
    property var controller: null
    property var filteredEntries: []
    property string revisionKey: ""
    property string actionStatus: ""

    Theme { id: theme }
    I18n { id: i18n }

    ColumnLayout {
        anchors.fill: parent
        spacing: 8

        RowLayout {
            Layout.fillWidth: true
            spacing: 8

            Text {
                Layout.fillWidth: true
                text: root.title
                color: theme.text
                font.weight: Font.Bold
                elide: Text.ElideRight
            }

            StyledComboBox {
                id: levelFilter
                Layout.preferredWidth: 128
                textRole: "label"
                valueRole: "value"
                model: [
                    { label: i18n.text("log_level_all"), value: "all" },
                    { label: i18n.text("log_level_info"), value: "info" },
                    { label: i18n.text("log_level_success"), value: "success" },
                    { label: i18n.text("log_level_warning"), value: "warning" },
                    { label: i18n.text("log_level_error"), value: "error" },
                    { label: i18n.text("log_level_debug"), value: "debug" }
                ]
                onActivated: root.refreshFilter()
            }

            StyledTextField {
                id: searchField
                Layout.preferredWidth: 180
                placeholderText: i18n.text("search_logs")
                onTextChanged: root.refreshFilter()
            }

            PillButton {
                text: ""
                iconName: "copy"
                Layout.preferredWidth: 42
                Layout.minimumWidth: 42
                enabled: root.filteredEntries.length > 0
                onClicked: root.copyVisible()
                ModernToolTip { shown: parent.hovered; text: i18n.text("copy_visible_logs"); placement: "bottom"; delay: 250 }
            }

            PillButton {
                text: ""
                iconName: "download"
                Layout.preferredWidth: 42
                Layout.minimumWidth: 42
                enabled: root.entries.length > 0 && root.controller !== null
                onClicked: root.exportLogs()
                ModernToolTip { shown: parent.hovered; text: i18n.text("export_logs"); placement: "bottom"; delay: 250 }
            }

            PillButton {
                text: ""
                iconName: "trash"
                Layout.preferredWidth: 42
                Layout.minimumWidth: 42
                enabled: root.entries.length > 0 && root.controller !== null
                onClicked: root.clearLogs()
                ModernToolTip { shown: parent.hovered; text: i18n.text("clear_logs"); placement: "bottom"; delay: 250 }
            }
        }

        AutoScrollPanel {
            id: autoPanel
            Layout.fillWidth: true
            Layout.fillHeight: true
            unreadText: root.unreadText
            contentRevision: root.revisionKey

            Repeater {
                model: root.filteredEntries
                delegate: Rectangle {
                    width: autoPanel.width
                    implicitHeight: entryColumn.implicitHeight + 14
                    radius: 8
                    color: root.levelSoftColor(modelData.level)
                    border.color: root.levelColor(modelData.level)

                    ColumnLayout {
                        id: entryColumn
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.top: parent.top
                        anchors.margins: 7
                        spacing: 5

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 6
                            Label {
                                text: String(modelData.level || "info").toUpperCase()
                                color: theme.accentText
                                padding: 5
                                background: Rectangle { radius: 6; color: root.levelColor(modelData.level) }
                            }
                            Text {
                                text: modelData.time || ""
                                color: theme.textMuted
                                font.pixelSize: Math.max(10, theme.baseFontSize - 3)
                            }
                            Text {
                                text: modelData.stage || "task"
                                color: theme.textMuted
                                font.pixelSize: Math.max(10, theme.baseFontSize - 3)
                                elide: Text.ElideRight
                            }
                            Text {
                                Layout.fillWidth: true
                                text: modelData.document || modelData.source || ""
                                color: theme.textMuted
                                font.pixelSize: Math.max(10, theme.baseFontSize - 3)
                                elide: Text.ElideRight
                            }
                        }

                        Text {
                            Layout.fillWidth: true
                            text: modelData.message || modelData.title || ""
                            color: theme.text
                            wrapMode: Text.WrapAnywhere
                        }

                        Button {
                            id: detailsButton
                            visible: !!modelData.details
                            checkable: true
                            text: checked ? i18n.text("hide_details") : i18n.text("show_details")
                            padding: 4
                            background: Rectangle { radius: 6; color: detailsButton.hovered ? theme.navHover : theme.surface }
                            contentItem: Text { text: detailsButton.text; color: theme.textMuted; font.pixelSize: Math.max(10, theme.baseFontSize - 3) }
                        }

                        Text {
                            Layout.fillWidth: true
                            visible: detailsButton.visible && detailsButton.checked
                            text: modelData.details || ""
                            color: theme.textMuted
                            wrapMode: Text.WrapAnywhere
                            font.family: "Consolas"
                            font.pixelSize: Math.max(10, theme.baseFontSize - 3)
                        }
                    }
                }
            }
        }
    }

    Rectangle {
        id: actionToast
        anchors.top: parent.top
        anchors.right: parent.right
        anchors.topMargin: 40
        anchors.rightMargin: 2
        z: 20
        visible: root.actionStatus.length > 0
        radius: 8
        color: theme.tooltipSurface
        border.color: theme.tooltipBorder
        width: Math.min(300, actionLabel.implicitWidth + 24)
        height: actionLabel.implicitHeight + 14

        Text {
            id: actionLabel
            anchors.centerIn: parent
            width: Math.min(276, implicitWidth)
            text: root.actionStatus
            color: theme.tooltipText
            font.pixelSize: 12
            font.weight: Font.Medium
            elide: Text.ElideRight
        }
    }

    Timer {
        id: actionStatusTimer
        interval: 2400
        repeat: false
        onTriggered: root.actionStatus = ""
    }

    TextArea {
        id: copyBuffer
        visible: false
    }

    onEntriesChanged: refreshFilter()
    Component.onCompleted: refreshFilter()

    function refreshFilter() {
        let result = []
        let selected = levelFilter.currentValue || "all"
        let query = String(searchField.text || "").toLowerCase()
        let source = root.entries || []
        let start = Math.max(0, source.length - 1000)
        for (let i = start; i < source.length; i++) {
            let item = source[i]
            let level = String(item.level || "info")
            let haystack = [item.time, item.level, item.stage, item.message, item.details, item.document, item.source].join(" ").toLowerCase()
            if (selected !== "all" && level !== selected)
                continue
            if (query.length > 0 && haystack.indexOf(query) < 0)
                continue
            result.push(item)
        }
        root.filteredEntries = result
        let last = result.length > 0 ? String(result[result.length - 1].id || result.length) : "empty"
        root.revisionKey = String(source.length) + ":" + last + ":" + selected + ":" + query
    }

    function copyVisible() {
        let lines = []
        for (let item of root.filteredEntries) {
            lines.push("[" + (item.time || "") + "] [" + String(item.level || "info").toUpperCase() + "] [" + (item.stage || "task") + "] " + (item.message || item.title || ""))
            if (item.details)
                lines.push(item.details)
        }
        let copied = false
        if (root.controller && root.controller.copyLogEntries)
            copied = root.controller.copyLogEntries(root.filteredEntries)
        copyBuffer.text = lines.join("\n")
        if (!copied) {
            copyBuffer.forceActiveFocus()
            copyBuffer.selectAll()
            copyBuffer.copy()
            copied = lines.length > 0
        }
        root.showActionStatus(copied ? i18n.text("log_copied") : i18n.text("log_copy_failed"))
    }

    function exportLogs() {
        if (!root.controller)
            return
        let path = root.controller.exportLog()
        root.showActionStatus(path ? i18n.text("log_exported") : i18n.text("log_export_empty"))
    }

    function clearLogs() {
        if (!root.controller)
            return
        root.controller.clearLog()
        root.refreshFilter()
        root.showActionStatus(i18n.text("log_cleared"))
    }

    function showActionStatus(message) {
        root.actionStatus = message || ""
        if (root.actionStatus.length > 0)
            actionStatusTimer.restart()
    }

    function levelColor(level) {
        if (level === "success") return theme.success
        if (level === "warning") return theme.warning
        if (level === "error") return theme.error
        if (level === "debug") return theme.textMuted
        return theme.info
    }

    function levelSoftColor(level) {
        if (level === "success") return theme.successSoft
        if (level === "warning") return theme.warningSoft
        if (level === "error") return theme.errorSoft
        if (level === "debug") return theme.surfaceSoft
        return theme.accentSofter
    }
}
