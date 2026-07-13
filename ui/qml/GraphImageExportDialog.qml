pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Popup {
    id: root

    property var targetView: null
    property string defaultName: "knowledge-graph"
    property bool exporting: false
    property string errorMessage: ""

    parent: Overlay.overlay
    anchors.centerIn: parent
    modal: true
    focus: true
    closePolicy: root.exporting ? Popup.NoAutoClose : Popup.CloseOnEscape | Popup.CloseOnPressOutside
    padding: 18

    Theme { id: theme }

    function openForExport() {
        nameField.text = root.defaultName || "knowledge-graph"
        scopeBox.currentIndex = 0
        scaleBox.currentIndex = 1
        backgroundBox.currentIndex = 0
        root.exporting = false
        root.errorMessage = ""
        root.open()
        nameField.forceActiveFocus()
        nameField.selectAll()
    }

    function startExport() {
        if (!root.targetView || root.exporting)
            return
        root.errorMessage = ""
        var scope = scopeBox.currentIndex === 1 ? "full" : "viewport"
        var scale = scaleBox.currentIndex + 1
        var transparent = backgroundBox.currentIndex === 1
        var dimensions = knowledgeGraphController.validateImageExport(root.targetView.width, root.targetView.height, scale)
        if (!dimensions.ok) {
            root.errorMessage = String(dimensions.message || "导出尺寸超出安全范围")
            return
        }
        var prepared = knowledgeGraphController.prepareImageExport(nameField.text, scope, scale, transparent)
        if (!prepared.ok) {
            root.errorMessage = String(prepared.message || "无法准备图片导出")
            return
        }
        root.exporting = true
        if (!root.targetView.exportPng(String(prepared.path || ""), Number(prepared.scale || scale),
                                       String(prepared.scope || scope) === "full", !!prepared.transparent)) {
            root.exporting = false
        }
    }

    Connections {
        target: root.targetView
        enabled: !!root.targetView
        function onImageExportFinished(path, success, message) {
            var completed = knowledgeGraphController.completeImageExport(path, success, message)
            root.exporting = false
            if (completed) {
                root.close()
            } else {
                root.errorMessage = String(knowledgeGraphController.imageExportStatus.message || message || "图片导出失败")
            }
        }
    }

    background: Rectangle {
        color: theme.surfaceElevated
        border.color: theme.border
        radius: theme.radiusMedium
    }

    contentItem: ColumnLayout {
        spacing: 13

        Text {
            text: "导出知识图谱图片"
            color: theme.text
            font.bold: true
            font.pixelSize: 18
        }
        Text {
            Layout.preferredWidth: 390
            text: "生成无损 PNG。完整图谱会自动排版并适配画布，导出后恢复当前视图。"
            color: theme.textMuted
            wrapMode: Text.WordWrap
        }
        Text { text: "文件名"; color: theme.text; font.bold: true }
        StyledTextField {
            id: nameField
            Layout.fillWidth: true
            placeholderText: "knowledge-graph"
            enabled: !root.exporting
            selectByMouse: true
            onAccepted: exportButton.clicked()
        }
        GridLayout {
            Layout.fillWidth: true
            columns: 2
            columnSpacing: 12
            rowSpacing: 10

            Text { text: "范围"; color: theme.text }
            StyledComboBox {
                id: scopeBox
                Layout.fillWidth: true
                model: ["当前视口", "完整探索图谱"]
                enabled: !root.exporting
            }
            Text { text: "分辨率"; color: theme.text }
            StyledComboBox {
                id: scaleBox
                Layout.fillWidth: true
                model: ["1×", "2×（推荐）", "3×", "4×"]
                currentIndex: 1
                enabled: !root.exporting
            }
            Text { text: "背景"; color: theme.text }
            StyledComboBox {
                id: backgroundBox
                Layout.fillWidth: true
                model: ["当前主题", "透明背景"]
                enabled: !root.exporting
            }
        }
        Text {
            Layout.fillWidth: true
            visible: root.errorMessage.length > 0
            text: root.errorMessage
            color: theme.error
            wrapMode: Text.WordWrap
        }
        RowLayout {
            Layout.fillWidth: true
            BusyIndicator {
                visible: root.exporting
                running: visible
                Layout.preferredWidth: 28
                Layout.preferredHeight: 28
            }
            Text {
                visible: root.exporting
                text: "正在渲染 PNG…"
                color: theme.textMuted
            }
            Item { Layout.fillWidth: true }
            PillButton { text: "取消"; enabled: !root.exporting; onClicked: root.close() }
            PillButton {
                id: exportButton
                text: root.exporting ? "导出中…" : "导出 PNG"
                primary: true
                enabled: !root.exporting && nameField.text.trim().length > 0 && !!root.targetView
                onClicked: root.startExport()
            }
        }
    }
}
