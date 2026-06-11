import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ScrollView {
    id: scroll
    property var tourHost: null
    contentWidth: availableWidth
    Motion { id: motion }
    I18n { id: i18n }
    Theme { id: theme }

    Component.onCompleted: scroll.registerTourTargets()
    Component.onDestruction: scroll.unregisterTourTargets()

    Dialog {
        id: downloadConfirm
        title: i18n.text("download_update")
        modal: true
        anchors.centerIn: Overlay.overlay
        standardButtons: Dialog.Ok | Dialog.Cancel
        onAccepted: updateController.download()
        Text { text: i18n.text("download_confirm") + updateController.latestVersion + "?"; color: theme.text }
    }
    Dialog {
        id: applyConfirm
        title: i18n.text("apply_update")
        modal: true
        anchors.centerIn: Overlay.overlay
        standardButtons: Dialog.Ok | Dialog.Cancel
        onAccepted: updateController.apply()
        Text { text: i18n.text("apply_confirm"); color: theme.text }
    }

    ColumnLayout {
        width: scroll.availableWidth
        spacing: 12

        Card {
            Layout.fillWidth: true
            Layout.leftMargin: 12
            Layout.rightMargin: 12
            implicitHeight: updatePanel.implicitHeight + 24
            ColumnLayout {
                id: updatePanel
                anchors.fill: parent
                anchors.margins: 12
                spacing: 10
                Text { text: i18n.text("remote_update"); color: theme.text; font.pixelSize: 17; font.weight: Font.Bold }
                StatusBanner { Layout.fillWidth: true; text: updateController.statusText; busy: updateController.checking || updateController.downloading }
                Text { text: "SHA-256: " + updateController.sha256Text; color: theme.textMuted; Layout.fillWidth: true; elide: Text.ElideMiddle; font.pixelSize: 12 }
                PillButton { Layout.fillWidth: true; text: i18n.text("check_update"); primary: true; busy: updateController.checking; enabled: !updateController.checking && !updateController.downloading; onClicked: updateController.check() }
                PillButton { Layout.fillWidth: true; text: i18n.text("download_update"); busy: updateController.downloading; enabled: updateController.available && !updateController.downloading; onClicked: downloadConfirm.open() }
                PillButton { Layout.fillWidth: true; text: i18n.text("apply_update"); enabled: !!updateController.downloadedPath; onClicked: applyConfirm.open() }
                SoftProgressBar { Layout.fillWidth: true; value: updateController.progressValue }
                Text { text: updateController.progressText; color: theme.textMuted; Layout.fillWidth: true; wrapMode: Text.WordWrap; font.pixelSize: 12 }
            }
        }

        Card {
            Layout.fillWidth: true
            Layout.leftMargin: 12
            Layout.rightMargin: 12
            Layout.preferredHeight: 260
            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 12
                Text { text: i18n.text("version_history"); color: theme.text; font.pixelSize: 16; font.weight: Font.Bold }
                Text {
                    visible: updateController.historyItems.length === 0
                    text: i18n.text("no_update_history")
                    color: theme.textMuted
                    font.pixelSize: 12
                }
                ListView {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    spacing: 8
                    model: updateController.historyItems
                    delegate: Rectangle {
                        required property var modelData
                        width: ListView.view.width
                        implicitHeight: historyColumn.implicitHeight + 18
                        radius: theme.radiusMedium
                        color: theme.surfaceSoft
                        border.color: theme.border
                        ColumnLayout {
                            id: historyColumn
                            anchors.fill: parent
                            anchors.margins: 9
                            spacing: 4
                            RowLayout {
                                Layout.fillWidth: true
                                Text { text: "v" + modelData.version; color: theme.accent; font.weight: Font.Bold }
                                Item { Layout.fillWidth: true }
                                Text { visible: !!modelData.date; text: modelData.date; color: theme.textMuted; font.pixelSize: 11 }
                            }
                            Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: theme.divider }
                            Text { Layout.fillWidth: true; text: modelData.notes; color: theme.text; font.pixelSize: 12; wrapMode: Text.WordWrap }
                        }
                    }
                }
            }
        }
        Item { Layout.preferredHeight: 12 }
    }

    function registerTourTargets() {
        if(scroll.tourHost)
            scroll.tourHost.registerTourTarget("update.panel", updatePanel)
    }
    function unregisterTourTargets() {
        if(scroll.tourHost)
            scroll.tourHost.unregisterTourTarget("update.panel", updatePanel)
    }
}
