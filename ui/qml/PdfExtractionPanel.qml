import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: root

    property var element: ({})
    property var index: ({})
    property string recordId: ""
    property string statusText: ""
    property string feedbackText: ""
    property string documentKey: ""
    property var elementExportPaths: ({})
    property var elementFeedbackTexts: ({})
    property string activeElementKey: root.element && root.element.id ? (String(root.element.type || "") + "|" + String(root.element.id || "")) : ""
    property string exportedPath: root.resolvedExportPath()
    property string currentFeedbackText: root.resolvedFeedbackText()
    property bool engineStatusOpen: false
    property var engineStatusMap: ({})

    signal exportCompleted(string elementKey, string path)
    signal elementFeedbackChanged(string elementKey, string text)

    onDocumentKeyChanged: root.resetLocalExportState()
    onActiveElementKeyChanged: {
        root.feedbackText = ""
    }
    color: theme.surface
    border.color: theme.border
    radius: theme.radiusMedium

    Theme { id: theme }

    ScrollView {
        id: panelScroll
        anchors.fill: parent
        anchors.margins: 12
        clip: true
        ScrollBar.vertical.policy: ScrollBar.AsNeeded
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

        ColumnLayout {
            width: panelScroll.availableWidth
            spacing: 10

        Text {
            Layout.fillWidth: true
            text: root.element && root.element.id ? (root.kindName(root.element.type) + "详情") : "元素详情"
            color: theme.text
            font.weight: Font.Bold
            font.pixelSize: theme.baseFontSize + 2
        }

        Text {
            Layout.fillWidth: true
            text: root.element && root.element.id ? ((root.element.label || root.element.id) + " · Page " + (Number(root.element.page || 0) + 1)) : "请选择页面上的框或左侧书签。"
            color: theme.textMuted
            wrapMode: Text.WrapAnywhere
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            color: theme.border
        }

        Flow {
            Layout.fillWidth: true
            spacing: 8
            clip: true

            PillButton {
                text: "解析引擎状态"
                onClicked: root.toggleEngineStatus()
            }
        }

        Rectangle {
            Layout.fillWidth: true
            visible: root.engineStatusOpen
            color: theme.surfaceSoft
            border.color: theme.border
            radius: 6
            implicitHeight: statusPopupColumn.implicitHeight + 16
            clip: true

            ColumnLayout {
                id: statusPopupColumn
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.margins: 8
                spacing: 6

                Repeater {
                    model: root.engineStatusRows()
                    delegate: RowLayout {
                        width: statusPopupColumn.width
                        spacing: 6

                        Text {
                            Layout.preferredWidth: 86
                            text: modelData.label
                            color: theme.text
                            font.weight: Font.DemiBold
                            elide: Text.ElideRight
                        }

                        Text {
                            Layout.fillWidth: true
                            text: modelData.state + " · " + modelData.message
                            color: modelData.available ? theme.success : (modelData.installable ? theme.warning : theme.textMuted)
                            wrapMode: Text.WrapAnywhere
                            maximumLineCount: 3
                            elide: Text.ElideRight
                        }

                        PillButton {
                            visible: !modelData.available && modelData.installable
                            text: modelData.key === "mineru" ? "一键初始化" : "初始化"
                            onClicked: pdfExtractionController.bootstrapEngine(modelData.key)
                        }
                    }
                }
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            visible: root.element && root.element.id
            spacing: 6

            Text {
                Layout.fillWidth: true
                text: "来源：" + root.engineLabel(root.element.engine) + root.sourceEnginesText(root.element) + "  ·  confidence " + root.confidenceText(root.element.confidence)
                color: theme.textSecondary
                wrapMode: Text.WrapAnywhere
            }

            Text {
                Layout.fillWidth: true
                visible: root.element && root.element.qualityFlags && root.element.qualityFlags.length > 0
                text: "质量标记：" + root.element.qualityFlags.join(", ")
                color: theme.warning
                wrapMode: Text.WrapAnywhere
            }

            Text {
                Layout.fillWidth: true
                visible: root.element && root.element.caption && String(root.element.caption).length > 0
                text: "Caption: " + String(root.element.caption)
                color: theme.textSecondary
                wrapMode: Text.WordWrap
                maximumLineCount: 4
                elide: Text.ElideRight
            }

            Text {
                Layout.fillWidth: true
                visible: root.element && root.element.needsReview
                text: "需要复核"
                color: theme.warning
                font.weight: Font.DemiBold
                wrapMode: Text.WordWrap
            }

            Text {
                Layout.fillWidth: true
                visible: root.element && (!root.element.bbox || root.element.bbox.length < 4)
                text: "该元素无可定位坐标，仅在解析结果中展示。"
                color: theme.textMuted
                wrapMode: Text.WordWrap
            }

            TextArea {
                Layout.fillWidth: true
                Layout.preferredHeight: 72
                visible: root.element && root.element.latex && String(root.element.latex).length > 0
                text: root.element && root.element.latex ? String(root.element.latex) : ""
                readOnly: true
                wrapMode: TextArea.Wrap
                placeholderText: "LaTeX"
            }

            TextArea {
                Layout.fillWidth: true
                Layout.preferredHeight: 90
                visible: root.element && root.element.markdown && String(root.element.markdown).length > 0
                text: root.element && root.element.markdown ? String(root.element.markdown) : ""
                readOnly: true
                wrapMode: TextArea.Wrap
                placeholderText: "Markdown"
            }
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

            Text {
                Layout.fillWidth: true
                text: root.tableStatsText()
                color: theme.textMuted
                wrapMode: Text.WordWrap
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

                PillButton { text: "复制表格"; onClicked: root.copyCurrent() }
                PillButton { text: "导出 CSV"; onClicked: root.exportCurrent("csv") }
                PillButton { text: "导出 JSON"; onClicked: root.exportCurrent("json") }
                PillButton {
                    text: "打开表格导出目录"
                    visible: root.exportedPath.length > 0
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
                source: root.element && root.element.id ? pdfExtractionController.cropElement(root.element.id) : ""
                fillMode: Image.PreserveAspectFit
                asynchronous: true
                cache: false
            }

            Text {
                Layout.fillWidth: true
                text: root.element && root.element.caption ? root.element.caption : "暂无图注。"
                color: theme.textSecondary
                wrapMode: Text.WordWrap
            }

            Flow {
                Layout.fillWidth: true
                spacing: 8
                clip: true

                PillButton { text: "复制图片"; onClicked: root.copyImageCurrent() }
                PillButton { text: "导出图片"; onClicked: root.exportCurrent("png") }
                PillButton {
                    text: "打开图片导出目录"
                    visible: root.exportedPath.length > 0
                    enabled: visible
                    onClicked: root.openLastExportDirectory()
                }
                PillButton {
                    text: "图数据提取（实验）"
                    onClicked: root.setCurrentFeedback("需要手动坐标轴标定，后续 PR 实现。")
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
                text: root.element && root.element.text ? root.element.text : ""
                readOnly: true
                wrapMode: TextArea.Wrap
            }

            Flow {
                Layout.fillWidth: true
                spacing: 8
                clip: true

                PillButton { text: "复制公式文本"; onClicked: root.copyCurrent() }
            }
        }

        Text {
            Layout.fillWidth: true
            visible: root.displayStatusText().length > 0
            text: root.displayStatusText()
            color: theme.textMuted
            wrapMode: Text.WrapAnywhere
            maximumLineCount: 3
            elide: Text.ElideRight
        }

        Item {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
        }
    }
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

    function engineLabel(engine) {
        var value = String(engine || "")
        if (value === "pymupdf" || value === "fast")
            return "PyMuPDF"
        if (value === "paddleocr_vl")
            return "PaddleOCR-VL"
        if (value === "mineru")
            return "MinerU"
        if (value === "hybrid")
            return "Hybrid"
        return value || "unknown"
    }

    function confidenceText(value) {
        var n = Number(value || 0)
        if (!isFinite(n) || n <= 0)
            return "-"
        return Math.round(n * 100) + "%"
    }

    function sourceEnginesText(item) {
        if (!item || !item.sourceEngines || item.sourceEngines.length === 0)
            return ""
        var labels = []
        for (var i = 0; i < item.sourceEngines.length; i++)
            labels.push(root.engineLabel(item.sourceEngines[i]))
        return "（" + labels.join(" + ") + "）"
    }

    function tableStatsText() {
        if (!root.element || !root.element.table)
            return "行数 0 · 列数 0 · 非空 0%"
        var rows = root.element.table
        var rowCount = rows.length
        var colCount = 0
        var total = 0
        var filled = 0
        for (var i = 0; i < rows.length; i++) {
            var row = rows[i] || []
            colCount = Math.max(colCount, row.length)
            for (var j = 0; j < row.length; j++) {
                total += 1
                if (String(row[j] || "").trim().length > 0)
                    filled += 1
            }
        }
        var ratio = total > 0 ? Math.round(filled * 100 / total) : 0
        return "行数 " + rowCount + " · 列数 " + colCount + " · 非空 " + ratio + "%"
    }

    function engineErrors() {
        if (!root.index || !root.index.engineErrors)
            return []
        return root.index.engineErrors
    }

    function showEngineStatus() {
        var status = pdfExtractionController.engineStatus()
        root.setCurrentFeedback(root.formatEngineStatus(status))
    }

    function toggleEngineStatus() {
        root.engineStatusMap = pdfExtractionController.engineStatus()
        root.engineStatusOpen = !root.engineStatusOpen
    }

    function engineStatusRows() {
        var status = root.engineStatusMap || ({})
        var order = ["pymupdf", "mineru", "paddleocr_vl"]
        var rows = []
        for (var i = 0; i < order.length; i++) {
            var key = order[i]
            var item = status[key] || ({ available: false, installable: false, status: "unknown", message: "未知" })
            rows.push({
                key: key,
                label: root.engineLabel(key),
                available: !!item.available,
                installable: !!item.installable,
                state: item.available ? "可用" : (item.installable ? "可初始化" : root.statusName(item.status)),
                message: String(item.message || "")
            })
        }
        return rows
    }

    function formatEngineStatus(status) {
        var lines = []
        var order = ["pymupdf", "paddleocr_vl", "mineru"]
        for (var i = 0; i < order.length; i++) {
            var key = order[i]
            var item = status && status[key] ? status[key] : ({ available: false, installable: false, status: "unknown", message: "未知" })
            var state = item.available ? "可用" : (item.installable ? "可自动安装" : root.statusName(item.status))
            lines.push(root.engineLabel(key) + "：" + state + "，" + String(item.message || ""))
        }
        return lines.join("\n")
    }

    function errorPrefix(item) {
        var level = String(item && item.level ? item.level : "warning")
        if (level === "info")
            return root.engineLabel(item.engine) + " 提示："
        return root.engineLabel(item.engine) + " 注意："
    }

    function statusName(value) {
        if (value === "not_initialized")
            return "未初始化"
        if (value === "failed")
            return "初始化失败"
        if (value === "off")
            return "已禁用"
        if (value === "docker_installable")
            return "可通过 Docker 启用"
        return "不可用"
    }

    function tablePreviewRows() {
        if (!root.element || !root.element.table)
            return []
        return root.element.table.slice(0, 8)
    }

    function resetLocalExportState() {
        root.feedbackText = ""
    }

    function resolvedExportPath() {
        var key = root.activeElementKey

        if (key !== "" && root.elementExportPaths && root.elementExportPaths[key])
            return String(root.elementExportPaths[key])

        return ""
    }

    function resolvedFeedbackText() {
        var key = root.activeElementKey

        if (key !== "" && root.elementFeedbackTexts && root.elementFeedbackTexts[key])
            return String(root.elementFeedbackTexts[key])

        return root.feedbackText
    }

    function displayStatusText() {
        if (root.currentFeedbackText.length > 0)
            return root.currentFeedbackText
        if (root.element && root.element.id)
            return root.statusText
        return root.statusText || pdfExtractionController.statusText
    }

    function setCurrentFeedback(text) {
        var value = String(text || "")
        var key = root.activeElementKey

        root.feedbackText = value
        if (key !== "")
            root.elementFeedbackChanged(key, value)
    }

    function copyCurrent() {
        if (!root.element || !root.element.id)
            return
        root.setCurrentFeedback(pdfExtractionController.copyElement(root.element.id) ? "操作成功。" : pdfExtractionController.statusText)
    }

    function exportCurrent(fmt) {
        if (!root.element || !root.element.id)
            return

        var path = pdfExtractionController.exportElement(root.element.id, fmt)
        if (path) {
            root.setCurrentFeedback("已导出：" + path)
            root.exportCompleted(root.activeElementKey, path)
        } else {
            root.setCurrentFeedback(pdfExtractionController.statusText)
        }
    }

    function openLastExportDirectory() {
        if (root.exportedPath.length === 0)
            return
        root.setCurrentFeedback(pdfExtractionController.openExportDirectory(root.exportedPath) ? "导出目录已在文件管理器中打开。" : pdfExtractionController.statusText)
    }

    function copyImageCurrent() {
        if (!root.element || !root.element.id)
            return
        root.setCurrentFeedback(pdfExtractionController.copyElementImage(root.element.id) ? "操作成功。" : pdfExtractionController.statusText)
    }
}
