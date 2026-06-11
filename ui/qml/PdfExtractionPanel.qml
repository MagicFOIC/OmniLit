import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: root

    property var element: ({})
    property string documentKey: ""
    property string feedbackText: ""
    property string lastExportPath: ""

    onDocumentKeyChanged: {
        lastExportPath = ""
        feedbackText = ""
    }

    color: theme.surface
    border.color: theme.border
    radius: theme.radiusMedium

    Theme { id: theme }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 12
        spacing: 10

        Text {
            Layout.fillWidth: true
            text: root.element && root.element.id
                ? (root.kindName(root.element.type) + "详情")
                : "元素详情"
            color: theme.text
            font.weight: Font.Bold
            font.pixelSize: theme.baseFontSize + 2
        }

        Text {
            Layout.fillWidth: true
            text: root.element && root.element.id
                ? ((root.element.label || root.element.id) + " · Page " + (Number(root.element.page || 0) + 1))
                : "请选择页面上的框或左侧书签。"
            color: theme.textMuted
            wrapMode: Text.WrapAnywhere
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            color: theme.border
        }

        ColumnLayout {
            Layout.fillWidth: true
            visible: root.element && root.element.type === "table"
            spacing: 8

            Text {
                Layout.fillWidth: true
                text: "预览"
                color: theme.text
                font.weight: Font.DemiBold
            }

            ListView {
                Layout.fillWidth: true
                Layout.preferredHeight: 190
                clip: true
                model: root.tablePreviewRows()

                delegate: Text {
                    width: ListView.view.width
                    text: modelData.join(" ")
                    color: theme.textSecondary
                    elide: Text.ElideRight
                    font.family: "Consolas"
                    font.pixelSize: 11
                }
            }

            Flow {
                Layout.fillWidth: true
                spacing: 8
                clip: true

                PillButton {
                    text: "复制表格"
                    onClicked: root.copyCurrent()
                }

                PillButton {
                    text: "导出 CSV"
                    onClicked: root.exportCurrent("csv")
                }

                PillButton {
                    text: "导出 JSON"
                    onClicked: root.exportCurrent("json")
                }

                PillButton {
                    text: "打开表格导出目录"
                    visible: root.lastExportPath.length > 0
                    enabled: visible
                    onClicked: root.openLastExportDirectory()
                }
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            visible: root.element && root.element.type === "figure"
            spacing: 8

            Image {
                Layout.fillWidth: true
                Layout.preferredHeight: 220
                source: root.element && root.element.id
                    ? pdfExtractionController.cropElement(root.element.id)
                    : ""
                fillMode: Image.PreserveAspectFit
                asynchronous: true
                cache: false
            }

            Text {
                Layout.fillWidth: true
                text: root.element.caption || "暂无图注。"
                color: theme.textSecondary
                wrapMode: Text.WordWrap
            }

            Flow {
                Layout.fillWidth: true
                spacing: 8
                clip: true

                PillButton {
                    text: "复制图片"
                    onClicked: root.copyImageCurrent()
                }

                PillButton {
                    text: "导出图片"
                    onClicked: root.exportCurrent("png")
                }

                PillButton {
                    text: "打开图片导出目录"
                    visible: root.lastExportPath.length > 0
                    enabled: visible
                    onClicked: root.openLastExportDirectory()
                }

                PillButton {
                    text: "图数据提取（实验）"
                    onClicked: root.feedbackText = "需要手动坐标轴标定，后续 PR 实现。"
                }
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            visible: root.element && root.element.type === "formula"
            spacing: 8

            TextArea {
                Layout.fillWidth: true
                Layout.preferredHeight: 88
                text: root.element.text || ""
                readOnly: true
                wrapMode: TextArea.Wrap
            }

            Image {
                Layout.fillWidth: true
                Layout.preferredHeight: 130
                source: root.element && root.element.id
                    ? pdfExtractionController.cropElement(root.element.id)
                    : ""
                fillMode: Image.PreserveAspectFit
                asynchronous: true
                cache: false
            }

            Flow {
                Layout.fillWidth: true
                spacing: 8
                clip: true

                PillButton {
                    text: "复制公式文本"
                    onClicked: root.copyCurrent()
                }

                PillButton {
                    text: "复制公式图片"
                    onClicked: root.copyImageCurrent()
                }
            }
        }

        Text {
            Layout.fillWidth: true
            visible: root.feedbackText.length > 0
            text: root.feedbackText
            color: theme.textMuted
            wrapMode: Text.WrapAnywhere
            maximumLineCount: 2
            elide: Text.ElideRight
        }

        Item { Layout.fillHeight: true }
    }

    function kindName(kind) {
        if (kind === "table")
            return "表格"
        if (kind === "figure")
            return "图"
        if (kind === "formula")
            return "公式"
        return "元素"
    }

    function tablePreviewRows() {
        if (!root.element || !root.element.table)
            return []
        return root.element.table.slice(0, 8)
    }

    function copyCurrent() {
        if (!root.element || !root.element.id)
            return
        root.feedbackText = pdfExtractionController.copyElement(root.element.id)
            ? "操作成功。"
            : pdfExtractionController.statusText
    }

    function exportCurrent(fmt) {
        if (!root.element || !root.element.id)
            return

        var path = pdfExtractionController.exportElement(root.element.id, fmt)
        if (path) {
            root.lastExportPath = path
            root.feedbackText = "已导出：" + path
        } else {
            root.feedbackText = pdfExtractionController.statusText
        }
    }

    function openLastExportDirectory() {
        if (root.lastExportPath.length === 0)
            return

        root.feedbackText = pdfExtractionController.openExportDirectory(root.lastExportPath)
            ? "已打开导出目录。"
            : pdfExtractionController.statusText
    }

    function copyImageCurrent() {
        if (!root.element || !root.element.id)
            return
        root.feedbackText = pdfExtractionController.copyElementImage(root.element.id)
            ? "操作成功。"
            : pdfExtractionController.statusText
    }
}