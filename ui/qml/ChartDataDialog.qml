import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Dialog {
    id: root

    property string elementId: ""
    property var chartResult: ({})
    property int sampleCount: 10
    property int customSampleCount: 10
    property int currentSubplotIndex: 0
    property string selectedSeriesId: ""
    property bool calibrationVisible: false
    property string calibrationPickTarget: "xMin"
    property var seriesSeeds: []
    property string nextSeriesSeedName: ""
    property string feedbackText: ""
    property bool expanded: false

    parent: Overlay.overlay
    modal: true
    title: "分析图数据"
    width: root.dialogWidth()
    height: root.dialogHeight()
    x: parent ? Math.max(12, Math.round((parent.width - width) / 2)) : 0
    y: parent ? Math.max(12, Math.round((parent.height - height) / 2)) : 0
    standardButtons: Dialog.NoButton
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

    onOpened: root.centerDialog()
    onExpandedChanged: Qt.callLater(root.centerDialog)

    Theme { id: theme }

    Connections {
        target: pdfExtractionController
        function onChartDataReady(elementId) {
            if (String(elementId || "") === root.elementId)
                root.refreshResult()
        }
    }

    contentItem: Rectangle {
        color: theme.surface
        implicitWidth: root.width
        implicitHeight: root.height

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 14
            spacing: 10

            RowLayout {
                Layout.fillWidth: true
                spacing: 8

                Text {
                    Layout.fillWidth: true
                    text: root.statusText()
                    color: root.needsReview() ? theme.warning : theme.text
                    font.weight: Font.DemiBold
                    wrapMode: Text.WordWrap
                }

                PillButton {
                    text: root.expanded ? "还原" : "放大"
                    onClicked: root.expanded = !root.expanded
                }

                PillButton {
                    text: "关闭"
                    onClicked: root.close()
                }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 10

                Text { text: "分段"; color: theme.textSecondary }

                StyledComboBox {
                    id: samplePreset
                    Layout.preferredWidth: 118
                    model: ["5", "10", "15", "20", "自定义"]
                    currentIndex: 1
                    onActivated: root.applySamplePreset(currentText)
                }

                StyledTextField {
                    Layout.preferredWidth: 90
                    visible: samplePreset.currentText === "自定义"
                    text: String(root.customSampleCount)
                    validator: IntValidator { bottom: 2; top: 500 }
                    onEditingFinished: {
                        root.customSampleCount = Math.max(2, Number(text || 10))
                        root.sampleCount = root.customSampleCount
                        root.runAnalysis()
                    }
                }

                StyledComboBox {
                    id: subplotChooser
                    Layout.preferredWidth: 150
                    model: root.subplotLabels()
                    onActivated: {
                        root.currentSubplotIndex = currentIndex
                        root.selectedSeriesId = ""
                        seriesChooser.model = root.seriesChoices()
                        seriesChooser.currentIndex = 0
                        if (root.calibrationVisible)
                            root.populateCalibrationFields()
                    }
                }

                StyledComboBox {
                    id: seriesChooser
                    Layout.preferredWidth: 170
                    textRole: "label"
                    valueRole: "id"
                    model: root.seriesChoices()
                    onActivated: root.selectedSeriesId = currentValue || ""
                }

                Item { Layout.fillWidth: true }

                PillButton { text: "重新分析"; onClicked: root.runAnalysis() }
                PillButton { text: "手动校准"; onClicked: root.toggleCalibration() }
            }

            RowLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 12

                ColumnLayout {
                    Layout.preferredWidth: 330
                    Layout.fillHeight: true
                    spacing: 8

                    Item {
                        id: figurePreviewFrame
                        Layout.fillWidth: true
                        Layout.preferredHeight: 220

                        Image {
                            id: figurePreview
                            anchors.fill: parent
                            source: root.elementId ? pdfExtractionController.cropElement(root.elementId) : ""
                            fillMode: Image.PreserveAspectFit
                            asynchronous: true
                            cache: false
                            onStatusChanged: calibrationOverlay.requestPaint()
                        }

                        Canvas {
                            id: calibrationOverlay
                            anchors.fill: parent
                            visible: root.calibrationVisible
                            onPaint: root.paintCalibrationOverlay()
                        }

                        MouseArea {
                            anchors.fill: parent
                            visible: root.calibrationVisible
                            enabled: root.calibrationVisible
                            hoverEnabled: true
                            cursorShape: Qt.CrossCursor
                            onClicked: root.captureCalibrationPoint(mouse.x, mouse.y)
                        }
                    }

                    Text {
                        Layout.fillWidth: true
                        text: root.axisStatusText()
                        color: root.needsReview() ? theme.warning : theme.textSecondary
                        wrapMode: Text.WordWrap
                    }

                    Text {
                        Layout.fillWidth: true
                        text: root.warningText()
                        color: theme.warning
                        visible: text.length > 0
                        wrapMode: Text.WordWrap
                        maximumLineCount: 5
                        elide: Text.ElideRight
                    }

                    Text {
                        Layout.fillWidth: true
                        text: root.legendText()
                        color: theme.textSecondary
                        visible: text.length > 0
                        wrapMode: Text.WordWrap
                        maximumLineCount: 4
                        elide: Text.ElideRight
                    }

                    Text {
                        Layout.fillWidth: true
                        text: root.seriesReviewText()
                        color: text.indexOf("需要复核") >= 0 ? theme.warning : theme.textSecondary
                        visible: text.length > 0
                        wrapMode: Text.WordWrap
                        maximumLineCount: 5
                        elide: Text.ElideRight
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        visible: root.calibrationVisible
                        spacing: 6

                        Text {
                            Layout.fillWidth: true
                            text: "手动校准"
                            color: theme.text
                            font.weight: Font.DemiBold
                        }

                        Text {
                            Layout.fillWidth: true
                            text: "选择刻度点，然后在原图上点击；至少需要 x 轴两个刻度点和 y 轴两个刻度点。当前：" + root.calibrationPickLabel()
                            color: theme.textSecondary
                            wrapMode: Text.WordWrap
                        }

                        Flow {
                            Layout.fillWidth: true
                            spacing: 6
                            clip: true

                            PillButton { text: "选 x min"; onClicked: root.calibrationPickTarget = "xMin" }
                            PillButton { text: "选 x max"; onClicked: root.calibrationPickTarget = "xMax" }
                            PillButton { text: "选 y min"; onClicked: root.calibrationPickTarget = "yMin" }
                            PillButton { text: "选 y max"; onClicked: root.calibrationPickTarget = "yMax" }
                            PillButton { text: "选曲线"; onClicked: root.calibrationPickTarget = "seriesSeed" }
                            PillButton { text: "选子图左上"; onClicked: root.calibrationPickTarget = "subplotMin" }
                            PillButton { text: "选子图右下"; onClicked: root.calibrationPickTarget = "subplotMax" }
                            PillButton { text: "清空曲线"; onClicked: { root.seriesSeeds = []; calibrationOverlay.requestPaint() } }
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 6

                            Text {
                                text: "曲线名"
                                color: theme.textSecondary
                            }

                            StyledTextField {
                                Layout.fillWidth: true
                                text: root.nextSeriesSeedName
                                placeholderText: "下一条曲线名称"
                                onTextChanged: root.nextSeriesSeedName = text
                            }
                        }

                        Text {
                            Layout.fillWidth: true
                            text: "曲线种子：" + root.seriesSeedText()
                            color: theme.textMuted
                            wrapMode: Text.WrapAnywhere
                            maximumLineCount: 2
                            elide: Text.ElideRight
                        }

                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 4
                            visible: root.seriesSeeds && root.seriesSeeds.length > 0

                            Repeater {
                                model: root.seriesSeeds ? root.seriesSeeds.length : 0

                                delegate: RowLayout {
                                    Layout.fillWidth: true
                                    spacing: 6

                                    Text {
                                        text: "s" + (index + 1)
                                        color: theme.textSecondary
                                    }

                                    StyledTextField {
                                        Layout.fillWidth: true
                                        text: String((root.seriesSeeds[index] || {}).name || ("Series " + (index + 1)))
                                        onEditingFinished: root.updateSeriesSeedName(index, text)
                                    }

                                    Text {
                                        text: root.seriesSeedPixelText(index)
                                        color: theme.textMuted
                                    }
                                }
                            }
                        }

                        GridLayout {
                            Layout.fillWidth: true
                            columns: 4
                            columnSpacing: 6
                            rowSpacing: 6

                            Text { text: "x min"; color: theme.textSecondary }
                            StyledTextField { id: xMinField; text: "0"; Layout.fillWidth: true }
                            Text { text: "x max"; color: theme.textSecondary }
                            StyledTextField { id: xMaxField; text: "1"; Layout.fillWidth: true }
                            Text { text: "x min px"; color: theme.textSecondary }
                            StyledTextField { id: xMinXField; text: "0"; Layout.fillWidth: true }
                            Text { text: "x min py"; color: theme.textSecondary }
                            StyledTextField { id: xMinYField; text: "1"; Layout.fillWidth: true }
                            Text { text: "x max px"; color: theme.textSecondary }
                            StyledTextField { id: xMaxXField; text: "1"; Layout.fillWidth: true }
                            Text { text: "x max py"; color: theme.textSecondary }
                            StyledTextField { id: xMaxYField; text: "1"; Layout.fillWidth: true }
                            Text { text: "y min"; color: theme.textSecondary }
                            StyledTextField { id: yMinField; text: "0"; Layout.fillWidth: true }
                            Text { text: "y max"; color: theme.textSecondary }
                            StyledTextField { id: yMaxField; text: "1"; Layout.fillWidth: true }
                            Text { text: "y min px"; color: theme.textSecondary }
                            StyledTextField { id: yMinXField; text: "0"; Layout.fillWidth: true }
                            Text { text: "y min py"; color: theme.textSecondary }
                            StyledTextField { id: yMinYField; text: "1"; Layout.fillWidth: true }
                            Text { text: "y max px"; color: theme.textSecondary }
                            StyledTextField { id: yMaxXField; text: "0"; Layout.fillWidth: true }
                            Text { text: "y max py"; color: theme.textSecondary }
                            StyledTextField { id: yMaxYField; text: "0"; Layout.fillWidth: true }
                            Text { text: "subplot x0"; color: theme.textSecondary }
                            StyledTextField { id: subplotX0Field; text: "0"; Layout.fillWidth: true }
                            Text { text: "subplot y0"; color: theme.textSecondary }
                            StyledTextField { id: subplotY0Field; text: "0"; Layout.fillWidth: true }
                            Text { text: "subplot x1"; color: theme.textSecondary }
                            StyledTextField { id: subplotX1Field; text: "1"; Layout.fillWidth: true }
                            Text { text: "subplot y1"; color: theme.textSecondary }
                            StyledTextField { id: subplotY1Field; text: "1"; Layout.fillWidth: true }
                        }

                        PillButton {
                            text: "保存校准并重新分析"
                            onClicked: root.saveCalibration()
                        }
                    }

                    Item { Layout.fillHeight: true }
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    spacing: 8

                    ScatterPlotCanvas {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 300
                        subplot: root.currentSubplot()
                        selectedSeriesId: root.selectedSeriesId
                    }

                    TextArea {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        readOnly: true
                        wrapMode: TextArea.NoWrap
                        text: root.jsonText()
                        font.family: "Consolas"
                        font.pixelSize: 11
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8

                        Text {
                            Layout.fillWidth: true
                            text: root.feedbackText
                            color: theme.textMuted
                            elide: Text.ElideRight
                        }

                        PillButton {
                            text: "复制 JSON"
                            onClicked: root.copyJson()
                        }

                        PillButton {
                            text: "导出 JSON"
                            onClicked: root.exportJson()
                        }
                    }
                }
            }
        }
    }

    function openFor(elementId) {
        root.elementId = String(elementId || "")
        root.currentSubplotIndex = 0
        root.selectedSeriesId = ""
        root.calibrationVisible = false
        root.seriesSeeds = []
        root.feedbackText = ""
        root.expanded = false
        root.open()
        Qt.callLater(root.centerDialog)
        // Reuse a persisted result when the chart was analyzed before.  The
        // explicit re-analysis action remains available when fresh sampling is
        // wanted, while reopening a chart becomes immediate.
        root.refreshResult()
        if (!root.chartResult || !root.chartResult.schemaVersion)
            root.runAnalysis()
    }

    function dialogWidth() {
        var available = parent ? Math.max(360, parent.width - 32) : 980
        var desired = root.expanded ? 1280 : 980
        return Math.min(desired, available)
    }

    function dialogHeight() {
        var available = parent ? Math.max(420, parent.height - 32) : 760
        var desired = root.expanded ? 900 : 760
        return Math.min(desired, available)
    }

    function centerDialog() {
        if (!parent)
            return
        root.x = Math.max(12, Math.round((parent.width - root.width) / 2))
        root.y = Math.max(12, Math.round((parent.height - root.height) / 2))
    }

    function runAnalysis() {
        if (!root.elementId)
            return
        root.feedbackText = "正在分析…"
        root.chartResult = pdfExtractionController.analyzeChartData(root.elementId, root.sampleCount)
        root.refreshCombos()
        root.feedbackText = root.chartResult && root.chartResult.schemaVersion ? "分析完成。" : pdfExtractionController.statusText
    }

    function refreshResult() {
        root.chartResult = pdfExtractionController.chartDataResult(root.elementId)
        root.refreshCombos()
    }

    function refreshCombos() {
        subplotChooser.model = root.subplotLabels()
        if (root.currentSubplotIndex >= subplotChooser.model.length)
            root.currentSubplotIndex = 0
        subplotChooser.currentIndex = root.currentSubplotIndex
        seriesChooser.model = root.seriesChoices()
        seriesChooser.currentIndex = 0
        root.selectedSeriesId = ""
    }

    function applySamplePreset(value) {
        if (value === "自定义") {
            root.sampleCount = Math.max(2, root.customSampleCount)
            return
        }
        root.sampleCount = Number(value || 10)
        root.runAnalysis()
    }

    function toggleCalibration() {
        root.calibrationVisible = !root.calibrationVisible
        if (root.calibrationVisible)
            root.populateCalibrationFields()
    }

    function populateCalibrationFields() {
        var subplot = root.currentSubplot()
        var area = subplot.plotAreaPx || [0, 0, 1, 1]
        var bbox = subplot.bboxPx || area
        root.seriesSeeds = root.seriesSeedsFromCurrentSubplot()
        xMinXField.text = String(Math.round(Number(area[0] || 0)))
        xMinYField.text = String(Math.round(Number(area[3] || 1)))
        xMaxXField.text = String(Math.round(Number(area[2] || 1)))
        xMaxYField.text = String(Math.round(Number(area[3] || 1)))
        yMinXField.text = String(Math.round(Number(area[0] || 0)))
        yMinYField.text = String(Math.round(Number(area[3] || 1)))
        yMaxXField.text = String(Math.round(Number(area[0] || 0)))
        yMaxYField.text = String(Math.round(Number(area[1] || 0)))
        subplotX0Field.text = String(Math.round(Number(bbox[0] || 0)))
        subplotY0Field.text = String(Math.round(Number(bbox[1] || 0)))
        subplotX1Field.text = String(Math.round(Number(bbox[2] || 1)))
        subplotY1Field.text = String(Math.round(Number(bbox[3] || 1)))
        calibrationOverlay.requestPaint()
    }

    function saveCalibration() {
        var xMin = Number(xMinField.text)
        var xMax = Number(xMaxField.text)
        var yMin = Number(yMinField.text)
        var yMax = Number(yMaxField.text)
        var xMinX = Number(xMinXField.text)
        var xMinY = Number(xMinYField.text)
        var xMaxX = Number(xMaxXField.text)
        var xMaxY = Number(xMaxYField.text)
        var yMinX = Number(yMinXField.text)
        var yMinY = Number(yMinYField.text)
        var yMaxX = Number(yMaxXField.text)
        var yMaxY = Number(yMaxYField.text)
        var subplotX0 = Number(subplotX0Field.text)
        var subplotY0 = Number(subplotY0Field.text)
        var subplotX1 = Number(subplotX1Field.text)
        var subplotY1 = Number(subplotY1Field.text)
        if (!isFinite(xMin) || !isFinite(xMax) || !isFinite(yMin) || !isFinite(yMax)
                || !isFinite(xMinX) || !isFinite(xMinY) || !isFinite(xMaxX) || !isFinite(xMaxY)
                || !isFinite(yMinX) || !isFinite(yMinY) || !isFinite(yMaxX) || !isFinite(yMaxY)
                || !isFinite(subplotX0) || !isFinite(subplotY0) || !isFinite(subplotX1) || !isFinite(subplotY1)) {
            root.feedbackText = "校准值无效。"
            return
        }
        var subplotBbox = [
            Math.min(subplotX0, subplotX1),
            Math.min(subplotY0, subplotY1),
            Math.max(subplotX0, subplotX1),
            Math.max(subplotY0, subplotY1)
        ]
        var subplot = root.currentSubplot()
        var area = subplot.plotAreaPx || [0, 0, 1, 1]
        var subplotCalibration = {
            bboxPx: subplotBbox,
            plotAreaPx: area,
            xAxis: {
                scale: "linear",
                calibration: [
                    { pixel: [xMinX, xMinY], value: xMin },
                    { pixel: [xMaxX, xMaxY], value: xMax }
                ]
            },
            yAxis: {
                scale: "linear",
                calibration: [
                    { pixel: [yMinX, yMinY], value: yMin },
                    { pixel: [yMaxX, yMaxY], value: yMax }
                ]
            },
            seriesSeeds: root.seriesSeeds
        }
        var payload = {
            subplotIndex: root.currentSubplotIndex,
            calibration: subplotCalibration
        }
        if (pdfExtractionController.saveChartCalibration(root.elementId, payload)) {
            root.feedbackText = "校准已保存。"
            root.runAnalysis()
        } else {
            root.feedbackText = pdfExtractionController.statusText
        }
    }

    function copyJson() {
        root.feedbackText = pdfExtractionController.copyChartData(root.elementId) ? "JSON 已复制。" : pdfExtractionController.statusText
    }

    function exportJson() {
        var path = pdfExtractionController.exportChartData(root.elementId)
        root.feedbackText = path ? ("已导出：" + path) : pdfExtractionController.statusText
    }

    function currentSubplot() {
        var items = root.chartResult && root.chartResult.subplots ? root.chartResult.subplots : []
        if (items.length === 0)
            return ({})
        return items[Math.max(0, Math.min(root.currentSubplotIndex, items.length - 1))]
    }

    function subplotLabels() {
        var items = root.chartResult && root.chartResult.subplots ? root.chartResult.subplots : []
        var labels = []
        for (var i = 0; i < items.length; i++) {
            var label = String(items[i].label || items[i].subplotId || ("subplot " + (i + 1)))
            labels.push(label)
        }
        return labels.length > 0 ? labels : ["无子图"]
    }

    function seriesChoices() {
        var choices = [{ label: "全部曲线", id: "" }]
        var subplot = root.currentSubplot()
        var items = subplot.series || []
        for (var i = 0; i < items.length; i++) {
            var label = String(items[i].name || items[i].seriesId)
            if (items[i].nameSource && items[i].nameSource !== "default")
                label += " · " + String(items[i].nameSource)
            if (items[i].needsReview)
                label += " · 需要复核"
            choices.push({ label: label, id: String(items[i].seriesId || "") })
        }
        return choices
    }

    function statusText() {
        var analysis = root.chartResult.analysis || ({})
        var confidence = Math.round(Number(analysis.confidence || 0) * 100)
        return String(analysis.status || "等待分析") + " / confidence " + confidence + "%"
    }

    function needsReview() {
        return !!(root.chartResult.analysis && root.chartResult.analysis.needsReview)
    }

    function warningText() {
        var warnings = root.chartResult.analysis && root.chartResult.analysis.warnings ? root.chartResult.analysis.warnings : []
        return warnings.join("\n")
    }

    function axisStatusText() {
        var subplot = root.currentSubplot()
        if (!subplot.axes)
            return "坐标轴：等待识别"
        var x = subplot.axes.x || {}
        var y = subplot.axes.y || {}
        return "坐标轴：x=" + String(x.source || "unknown") + " (" + Math.round(Number(x.confidence || 0) * 100) + "%), y=" +
            String(y.source || "unknown") + " (" + Math.round(Number(y.confidence || 0) * 100) + "%)"
    }

    function legendText() {
        var subplot = root.currentSubplot()
        var candidates = subplot.legendCandidates || []
        if (!candidates.length)
            return "图例：未识别到可靠候选"
        var labels = []
        for (var i = 0; i < Math.min(candidates.length, 6); i++)
            labels.push(String(candidates[i].text || "") + " (" + Math.round(Number(candidates[i].confidence || 0) * 100) + "%)")
        return "图例候选：" + labels.join("; ")
    }

    function seriesReviewText() {
        var subplot = root.currentSubplot()
        var items = subplot.series || []
        if (!items.length)
            return ""
        var labels = []
        for (var i = 0; i < items.length; i++) {
            var item = items[i] || {}
            var prefix = String(item.name || item.seriesId || ("Series " + (i + 1)))
            var confidence = Math.round(Number(item.confidence || 0) * 100)
            var source = String(item.nameSource || "default")
            var text = prefix + "：confidence " + confidence + "%, nameSource=" + source
            var warnings = item.warnings || []
            if (item.needsReview)
                text += "，需要复核"
            if (warnings.length)
                text += "，" + warnings.join("; ")
            labels.push(text)
        }
        return labels.join("\n")
    }

    function jsonText() {
        if (!root.chartResult || !root.chartResult.schemaVersion)
            return ""
        return JSON.stringify(root.chartResult, null, 2)
    }

    function calibrationPickLabel() {
        if (root.calibrationPickTarget === "xMin")
            return "x min"
        if (root.calibrationPickTarget === "xMax")
            return "x max"
        if (root.calibrationPickTarget === "yMin")
            return "y min"
        if (root.calibrationPickTarget === "yMax")
            return "y max"
        if (root.calibrationPickTarget === "seriesSeed")
            return "曲线"
        if (root.calibrationPickTarget === "subplotMin")
            return "子图左上"
        if (root.calibrationPickTarget === "subplotMax")
            return "子图右下"
        return "-"
    }

    function captureCalibrationPoint(mouseX, mouseY) {
        var point = root.previewToImagePixel(mouseX, mouseY)
        if (!point.valid) {
            root.feedbackText = "请点击图像区域内的刻度点。"
            return
        }
        var px = String(Math.round(point.x))
        var py = String(Math.round(point.y))
        if (root.calibrationPickTarget === "seriesSeed") {
            root.addSeriesSeed(Number(px), Number(py))
        } else if (root.calibrationPickTarget === "subplotMin") {
            subplotX0Field.text = px
            subplotY0Field.text = py
            root.calibrationPickTarget = "subplotMax"
        } else if (root.calibrationPickTarget === "subplotMax") {
            subplotX1Field.text = px
            subplotY1Field.text = py
            root.calibrationPickTarget = "xMin"
        } else if (root.calibrationPickTarget === "xMin") {
            xMinXField.text = px
            xMinYField.text = py
            root.calibrationPickTarget = "xMax"
        } else if (root.calibrationPickTarget === "xMax") {
            xMaxXField.text = px
            xMaxYField.text = py
            root.calibrationPickTarget = "yMin"
        } else if (root.calibrationPickTarget === "yMin") {
            yMinXField.text = px
            yMinYField.text = py
            root.calibrationPickTarget = "yMax"
        } else {
            yMaxXField.text = px
            yMaxYField.text = py
            root.calibrationPickTarget = "xMin"
        }
        root.feedbackText = "已记录：" + px + ", " + py
        calibrationOverlay.requestPaint()
    }

    function addSeriesSeed(px, py) {
        var next = []
        for (var i = 0; i < root.seriesSeeds.length; i++)
            next.push(root.seriesSeeds[i])
        var name = String(root.nextSeriesSeedName || "").trim()
        next.push({ pixel: [px, py], name: name.length > 0 ? name : ("Series " + (next.length + 1)) })
        root.seriesSeeds = next
        root.nextSeriesSeedName = ""
    }

    function updateSeriesSeedName(seedIndex, name) {
        var next = []
        for (var i = 0; i < root.seriesSeeds.length; i++) {
            var seed = root.seriesSeeds[i] || {}
            next.push({ pixel: seed.pixel || [], name: i === seedIndex ? String(name || "").trim() : String(seed.name || "") })
        }
        root.seriesSeeds = next
    }

    function seriesSeedsFromCurrentSubplot() {
        var result = []
        var subplot = root.currentSubplot()
        var series = subplot.series || []
        for (var i = 0; i < series.length; i++) {
            var pixel = series[i].seedPixel || []
            if (pixel.length >= 2)
                result.push({ pixel: [Number(pixel[0]), Number(pixel[1])], name: String(series[i].name || ("Series " + (result.length + 1))) })
        }
        return result
    }

    function seriesSeedText() {
        if (!root.seriesSeeds || root.seriesSeeds.length === 0)
            return "未指定，自动识别全部曲线"
        var labels = []
        for (var i = 0; i < root.seriesSeeds.length; i++) {
            var pixel = root.seriesSeeds[i].pixel || []
            labels.push(String(root.seriesSeeds[i].name || ("Series " + (i + 1))) + "@(" + Math.round(Number(pixel[0] || 0)) + "," + Math.round(Number(pixel[1] || 0)) + ")")
        }
        return labels.join("; ")
    }

    function seriesSeedPixelText(seedIndex) {
        if (!root.seriesSeeds || seedIndex < 0 || seedIndex >= root.seriesSeeds.length)
            return ""
        var pixel = root.seriesSeeds[seedIndex].pixel || []
        return "(" + Math.round(Number(pixel[0] || 0)) + ", " + Math.round(Number(pixel[1] || 0)) + ")"
    }

    function previewToImagePixel(mouseX, mouseY) {
        var sw = Number(figurePreview.sourceSize.width || 0)
        var sh = Number(figurePreview.sourceSize.height || 0)
        var pw = Number(figurePreview.paintedWidth || figurePreview.width)
        var ph = Number(figurePreview.paintedHeight || figurePreview.height)
        if (sw <= 0 || sh <= 0 || pw <= 0 || ph <= 0)
            return { valid: false, x: 0, y: 0 }
        var ox = (figurePreview.width - pw) / 2
        var oy = (figurePreview.height - ph) / 2
        if (mouseX < ox || mouseX > ox + pw || mouseY < oy || mouseY > oy + ph)
            return { valid: false, x: 0, y: 0 }
        return {
            valid: true,
            x: (mouseX - ox) * sw / pw,
            y: (mouseY - oy) * sh / ph
        }
    }

    function imagePixelToPreview(px, py) {
        var sw = Number(figurePreview.sourceSize.width || 0)
        var sh = Number(figurePreview.sourceSize.height || 0)
        var pw = Number(figurePreview.paintedWidth || figurePreview.width)
        var ph = Number(figurePreview.paintedHeight || figurePreview.height)
        if (sw <= 0 || sh <= 0 || pw <= 0 || ph <= 0)
            return { valid: false, x: 0, y: 0 }
        var ox = (figurePreview.width - pw) / 2
        var oy = (figurePreview.height - ph) / 2
        return {
            valid: true,
            x: ox + Number(px || 0) * pw / sw,
            y: oy + Number(py || 0) * ph / sh
        }
    }

    function calibrationFieldPoints() {
        var points = [
            { label: "x0", x: Number(xMinXField.text), y: Number(xMinYField.text), color: "#dc2626" },
            { label: "x1", x: Number(xMaxXField.text), y: Number(xMaxYField.text), color: "#dc2626" },
            { label: "y0", x: Number(yMinXField.text), y: Number(yMinYField.text), color: "#2563eb" },
            { label: "y1", x: Number(yMaxXField.text), y: Number(yMaxYField.text), color: "#2563eb" }
        ]
        for (var i = 0; i < root.seriesSeeds.length; i++) {
            var pixel = root.seriesSeeds[i].pixel || []
            points.push({ label: "s" + (i + 1), x: Number(pixel[0]), y: Number(pixel[1]), color: "#16a34a" })
        }
        return points
    }

    function paintCalibrationOverlay() {
        var ctx = calibrationOverlay.getContext("2d")
        ctx.clearRect(0, 0, calibrationOverlay.width, calibrationOverlay.height)
        if (!root.calibrationVisible)
            return
        var subplotBox = root.subplotPreviewBox()
        if (subplotBox.valid) {
            ctx.strokeStyle = "#f59e0b"
            ctx.fillStyle = "rgba(245, 158, 11, 0.10)"
            ctx.lineWidth = 2
            ctx.fillRect(subplotBox.x, subplotBox.y, subplotBox.w, subplotBox.h)
            ctx.strokeRect(subplotBox.x, subplotBox.y, subplotBox.w, subplotBox.h)
        }
        var points = root.calibrationFieldPoints()
        ctx.font = "11px sans-serif"
        ctx.lineWidth = 1.5
        for (var i = 0; i < points.length; i++) {
            var item = points[i]
            if (!isFinite(item.x) || !isFinite(item.y))
                continue
            var pos = root.imagePixelToPreview(item.x, item.y)
            if (!pos.valid)
                continue
            ctx.strokeStyle = item.color
            ctx.fillStyle = item.color
            ctx.beginPath()
            ctx.moveTo(pos.x - 7, pos.y)
            ctx.lineTo(pos.x + 7, pos.y)
            ctx.moveTo(pos.x, pos.y - 7)
            ctx.lineTo(pos.x, pos.y + 7)
            ctx.stroke()
            ctx.fillText(item.label, pos.x + 8, pos.y - 8)
        }
    }

    function subplotPreviewBox() {
        var p0 = root.imagePixelToPreview(Number(subplotX0Field.text), Number(subplotY0Field.text))
        var p1 = root.imagePixelToPreview(Number(subplotX1Field.text), Number(subplotY1Field.text))
        if (!p0.valid || !p1.valid)
            return { valid: false, x: 0, y: 0, w: 0, h: 0 }
        return {
            valid: true,
            x: Math.min(p0.x, p1.x),
            y: Math.min(p0.y, p1.y),
            w: Math.abs(p1.x - p0.x),
            h: Math.abs(p1.y - p0.y)
        }
    }
}
