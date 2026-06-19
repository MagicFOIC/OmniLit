import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: root

    property string recordId: ""
    property string pdfPath: ""
    property string title: ""
    property real zoom: 1.0
    property real initialZoom: 1.0
    property real fitWidthZoom: 1.0
    property real effectiveZoom: Math.max(0.1, root.fitWidthZoom * root.zoom)
    property bool showAnnotations: true
    property int renderRevision: 0
    property int currentPage: 0
    property string operationStatus: ""
    property string activeOpenKey: ""
    property string lastExportPath: ""
    property string allExportedPath: ""
    property var elementExportPaths: ({})
    property var elementFeedbackTexts: ({})
    property string selectedEngine: "fast"
    property bool deferPageRendering: false
    property var engineStatusInfo: ({})
    readonly property var analysisModes: [
        { engine: "fast", label: "快速解析（PyMuPDF）" },
        { engine: "mineru", label: "深度解析（MinerU）" },
        { engine: "paddleocr_vl", label: "高精度解析（PaddleOCR-VL）" }
    ]

    signal backRequested()
    signal zoomPersistRequested(real zoom)

    Motion { id: motion }
    Theme { id: theme }
    LayoutMetrics { id: metrics; viewportWidth: root.width; viewportHeight: root.height }

    Timer {
        id: openRecordTimer
        interval: 0
        repeat: false
        onTriggered: root.openRecordNow()
    }

    Timer {
        id: renderResumeTimer
        interval: 120
        repeat: false
        onTriggered: {
            root.deferPageRendering = false
            root.renderRevision += 1
        }
    }

    Component.onCompleted: {
        root.applyInitialZoom()
        root.scheduleOpenRecord()
    }
    onInitialZoomChanged: root.applyInitialZoom()
    onVisibleChanged: {
        if (visible)
            root.scheduleOpenRecord()
        else if (pdfExtractionController.loading)
            pdfExtractionController.cancelAnalysis()
    }

    Connections {
        target: pdfExtractionController

        function onAnalysisReady(recordId) {
            if (recordId === root.recordId) {
                root.recalculateFitWidthZoom()
                root.renderRevision += 1
                root.operationStatus = pdfExtractionController.currentEngine === "pymupdf" ? "快速解析已完成。可按需选择 MinerU 或 PaddleOCR-VL 深度解析。" : "解析完成。"
            }
        }

        function onRuntimeInstallProgress(engine, percent, message) {
            root.operationStatus = message || ("正在初始化解析组件..." + percent + "%")
        }

        function onElementFocused(elementId, page, bbox) {
            root.currentPage = page
            root.scrollToElement(page, bbox)
        }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 10

        Rectangle {
            id: headerCard
            Layout.fillWidth: true
            Layout.preferredHeight: 72
            radius: theme.radiusMedium
            color: theme.surface
            border.color: theme.border

            RowLayout {
                anchors.fill: parent
                anchors.margins: 10
                spacing: 8

                PillButton { text: "返回"; onClicked: root.backRequested() }

                Text {
                    Layout.fillWidth: true
                    text: root.title || "解析阅读"
                    color: theme.text
                    font.weight: Font.Bold
                    elide: Text.ElideRight
                }

                Switch {
                    id: annotationSwitch
                    checked: root.showAnnotations
                    text: checked ? "标注版" : "原文"
                    onToggled: root.showAnnotations = checked
                }

                PillButton { text: "-"; onClicked: root.adjustZoom(-0.15) }

                Text {
                    text: Math.round(root.zoom * 100) + "%"
                    color: theme.textMuted
                    Layout.preferredWidth: 48
                    horizontalAlignment: Text.AlignHCenter
                }

                PillButton { text: "+"; onClicked: root.adjustZoom(0.15) }

                ComboBox {
                    id: analysisMode
                    Layout.preferredWidth: 250
                    model: root.analysisModes
                    textRole: "label"
                    currentIndex: 0
                    enabled: !pdfExtractionController.loading
                    onActivated: {
                        var item = root.analysisModes[currentIndex]
                        root.selectedEngine = item ? item.engine : "fast"
                        root.selectEngine(root.selectedEngine)
                    }
                }

                PillButton {
                    id: engineStatusButton
                    text: "解析引擎状态"
                    onClicked: {
                        root.engineStatusInfo = pdfExtractionController.engineStatus()

                        var pos = engineStatusButton.mapToItem(headerCard, 0, engineStatusButton.height + 8)
                        engineStatusPopup.x = Math.max(8, Math.min(pos.x, headerCard.width - engineStatusPopup.width - 8))
                        engineStatusPopup.y = pos.y
                        engineStatusPopup.open()
                    }
                }

                PillButton {
                    text: "导出全部"
                    enabled: !pdfExtractionController.loading && pdfExtractionController.pageCount > 0
                    onClicked: root.exportAll()
                }
            }

            Popup {
                id: engineStatusPopup
                width: 380
                modal: false
                focus: true
                closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
                padding: 12

                background: Rectangle {
                    radius: theme.radiusMedium
                    color: theme.surface
                    border.color: theme.border
                }

                contentItem: ColumnLayout {
                    spacing: 8

                    Text {
                        Layout.fillWidth: true
                        text: "解析引擎状态"
                        color: theme.text
                        font.weight: Font.Bold
                    }

                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 1
                        color: theme.border
                    }

                    Repeater {
                        model: root.engineStatusRows()

                        delegate: RowLayout {
                            Layout.fillWidth: true
                            spacing: 8

                            Text {
                                Layout.preferredWidth: 96
                                text: modelData.label
                                color: theme.text
                                font.weight: Font.DemiBold
                                elide: Text.ElideRight
                            }

                            Text {
                                Layout.fillWidth: true
                                text: modelData.state + " · " + modelData.message
                                color: modelData.available
                                    ? theme.success
                                    : (modelData.installable ? theme.warning : theme.textMuted)
                                wrapMode: Text.WrapAnywhere
                                maximumLineCount: 3
                                elide: Text.ElideRight
                            }

                            PillButton {
                                visible: modelData.key !== "pymupdf" && !modelData.available
                                text: "配置服务"
                                onClicked: {
                                    pdfExtractionController.bootstrapEngine(modelData.key)
                                    root.operationStatus = "请在系统设置中配置 " + modelData.label + " API。"
                                }
                            }
                        }
                    }
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 10

            PdfElementBookmarkBar {
                Layout.preferredWidth: 220
                Layout.fillHeight: true
                elements: pdfExtractionController.elements
                selectedElementId: pdfExtractionController.selectedElement && pdfExtractionController.selectedElement.id
                    ? String(pdfExtractionController.selectedElement.id)
                    : ""
                onElementSelected: elementId => pdfExtractionController.focusElement(elementId)
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.fillHeight: true
                radius: theme.radiusMedium
                color: theme.surfaceSoft
                border.color: theme.border
                clip: true

                Flickable {
                    id: pageFlick
                    anchors.fill: parent
                    anchors.margins: 10

                    onWidthChanged: root.recalculateFitWidthZoom()

                    clip: true
                    boundsBehavior: Flickable.StopAtBounds
                    flickDeceleration: 4800
                    maximumFlickVelocity: 2800
                    pixelAligned: true

                    onMovementStarted: {
                        root.deferPageRendering = true
                        renderResumeTimer.stop()
                    }
                    onMovementEnded: renderResumeTimer.restart()

                    ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
                    ScrollBar.horizontal: ScrollBar { policy: ScrollBar.AsNeeded }

                    contentWidth: Math.max(width, pageColumn.width)
                    contentHeight: pageColumn.height

                    WheelHandler {
                        acceptedModifiers: Qt.ControlModifier
                        target: null
                        onWheel: function(event) {
                            var point = event.point && event.point.position ? event.point.position : Qt.point(pageFlick.width / 2, pageFlick.height / 2)
                            root.adjustZoomAt(event.angleDelta.y > 0 ? 0.10 : -0.10, point.x, point.y)
                            event.accepted = true
                        }
                    }

                    Column {
                        id: pageColumn
                        width: Math.max(pageFlick.width, root.pageWidth(root.currentPage) * root.effectiveZoom + 40)
                        spacing: 18

                        Repeater {
                            model: Math.max(0, pdfExtractionController.pageCount)

                            delegate: Rectangle {
                                id: pageFrame
                                property var sizeInfo: root.pageSize(index)
                                property bool nearViewport: y + height > pageFlick.contentY - pageFlick.height && y < pageFlick.contentY + pageFlick.height * 2.0
                                property string pageSource: ""

                                width: root.pageWidth(index) * root.effectiveZoom + 20
                                height: root.pageHeight(index) * root.effectiveZoom + 20
                                radius: 4
                                color: "#ffffff"
                                border.color: index === root.currentPage ? theme.accent : theme.border
                                anchors.horizontalCenter: parent.horizontalCenter

                                Component.onCompleted: refreshSource()
                                onNearViewportChanged: refreshSource()

                                Connections {
                                    target: root
                                    function onRenderRevisionChanged() { pageFrame.refreshSource() }
                                    function onDeferPageRenderingChanged() {
                                        if (!root.deferPageRendering)
                                            pageFrame.refreshSource()
                                    }
                                }

                                function refreshSource() {
                                    if (pageFrame.nearViewport && !root.deferPageRendering && root.renderRevision >= 0)
                                        pageFrame.pageSource = pdfExtractionController.renderPage(root.recordId, index, root.effectiveZoom)
                                }

                                Image {
                                    id: pageImage
                                    anchors.centerIn: parent
                                    width: root.pageWidth(index) * root.effectiveZoom
                                    height: root.pageHeight(index) * root.effectiveZoom
                                    source: pageFrame.pageSource
                                    fillMode: Image.Stretch
                                    asynchronous: true
                                    cache: false
                                }

                                PdfElementOverlay {
                                    visible: root.showAnnotations
                                    anchors.fill: pageImage
                                    pageSize: pageFrame.sizeInfo
                                    renderedSize: Qt.size(pageImage.width, pageImage.height)
                                    elements: root.elementsOnPage(index)
                                    onElementClicked: elementId => pdfExtractionController.focusElement(elementId)
                                }
                            }
                        }
                    }
                }

                Text {
                    anchors.centerIn: parent
                    width: parent.width - 40
                    text: pdfExtractionController.loading ? pdfExtractionController.progressText :
                          pdfExtractionController.pageCount === 0 ? "尚未生成解析阅读页。" : ""
                    color: theme.textMuted
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.WordWrap
                    visible: text.length > 0
                }

                BusyIndicator {
                    anchors.horizontalCenter: parent.horizontalCenter
                    anchors.bottom: parent.verticalCenter
                    anchors.bottomMargin: 18
                    running: pdfExtractionController.loading
                    visible: running
                }
            }

            PdfExtractionPanel {
                Layout.preferredWidth: 300
                Layout.minimumWidth: 260
                Layout.maximumWidth: 360
                Layout.fillHeight: true
                element: pdfExtractionController.selectedElement
                index: pdfExtractionController.currentIndex
                recordId: root.recordId
                statusText: root.operationStatus
                documentKey: root.recordId + "|" + root.pdfPath
                elementExportPaths: root.elementExportPaths
                elementFeedbackTexts: root.elementFeedbackTexts

                onExportCompleted: function(elementKey, path) {
                    root.rememberElementExport(elementKey, path)
                    root.lastExportPath = path || ""
                }

                onElementFeedbackChanged: function(elementKey, text) {
                    root.rememberElementFeedback(elementKey, text)
                }
            }
        }
    }

    function scheduleOpenRecord() {
        if (root.visible)
            openRecordTimer.restart()
    }

    function openRecordNow() {
        if (root.recordId === "" || root.pdfPath === "")
            return

        var openKey = root.recordId + "|" + root.pdfPath
        if (root.activeOpenKey === openKey && (pdfExtractionController.pageCount > 0 || pdfExtractionController.loading))
            return

        root.activeOpenKey = openKey
        root.currentPage = 0
        root.recalculateFitWidthZoom()
        root.applyInitialZoom()
        root.operationStatus = ""
        root.lastExportPath = ""
        root.allExportedPath = ""
        root.elementExportPaths = ({})
        root.elementFeedbackTexts = ({})

        if (!pdfExtractionController.loadIndexForPdf(root.recordId, root.pdfPath)) {
            root.operationStatus = "正在生成快速解析阅读视图..."
            pdfExtractionController.analyzeRecordWithEngine(root.recordId, root.pdfPath, "fast")
        }

        root.renderRevision += 1
    }

    function selectEngine(engine) {
        if (root.recordId === "" || root.pdfPath === "")
            return
        var nextEngine = engine || root.selectedEngine
        root.operationStatus = ""
        root.lastExportPath = ""
        root.allExportedPath = ""
        root.elementExportPaths = ({})
        root.elementFeedbackTexts = ({})
        if (nextEngine === "mineru")
            root.operationStatus = "MinerU 深度解析正在准备..."
        else if (nextEngine === "paddleocr_vl")
            root.operationStatus = "PaddleOCR-VL 高精度解析正在准备..."
        pdfExtractionController.selectExtractionEngine(root.recordId, root.pdfPath, nextEngine)
    }

    function exportAll() {
        var path = pdfExtractionController.exportElement("__all__", "dir")
        root.allExportedPath = path || ""
        root.lastExportPath = path || ""
        root.operationStatus = path ? ("已导出到：" + path) : pdfExtractionController.statusText
    }

    function rememberElementExport(elementKey, path) {
        if (!elementKey || !path)
            return

        var next = {}
        for (var existingKey in root.elementExportPaths)
            next[existingKey] = root.elementExportPaths[existingKey]

        next[String(elementKey)] = String(path)
        root.elementExportPaths = next
    }

    function rememberElementFeedback(elementKey, text) {
        if (!elementKey)
            return

        var next = {}
        for (var existingKey in root.elementFeedbackTexts)
            next[existingKey] = root.elementFeedbackTexts[existingKey]

        next[String(elementKey)] = String(text || "")
        root.elementFeedbackTexts = next
    }

    function openLastExportDirectory() {
        if (root.lastExportPath.length === 0)
            return
        root.operationStatus = pdfExtractionController.openExportDirectory(root.lastExportPath) ? "导出目录已在文件管理器中打开。" : pdfExtractionController.statusText
    }

    function adjustZoom(delta) {
        root.adjustZoomAt(delta, pageFlick.width / 2, pageFlick.height / 2)
    }

    function adjustZoomAt(delta, viewportX, viewportY) {
        var oldScale = root.effectiveZoom
        var oldZoom = root.zoom
        var anchorX = Number(viewportX || 0)
        var anchorY = Number(viewportY || 0)
        var contentAnchorX = pageFlick.contentX + anchorX
        var contentAnchorY = pageFlick.contentY + anchorY

        root.zoom = Math.max(0.6, Math.min(3.2, root.zoom + delta))
        if (root.zoom === oldZoom)
            return

        root.renderRevision += 1
        root.zoomPersistRequested(root.zoom)

        var ratio = oldScale > 0 ? root.effectiveZoom / oldScale : 1
        var targetX = contentAnchorX * ratio - anchorX
        var targetY = contentAnchorY * ratio - anchorY
        Qt.callLater(function() {
            pageFlick.contentX = root.clampContentX(targetX)
            pageFlick.contentY = root.clampContentY(targetY)
        })
    }

    function clampContentX(value) {
        var maxX = Math.max(0, pageFlick.contentWidth - pageFlick.width)
        return Math.max(0, Math.min(Number(value || 0), maxX))
    }

    function clampContentY(value) {
        var maxY = Math.max(0, pageFlick.contentHeight - pageFlick.height)
        return Math.max(0, Math.min(Number(value || 0), maxY))
    }

    function resetFitWidthZoom() {
        root.zoom = 1.0
        root.recalculateFitWidthZoom()
        root.renderRevision += 1
        root.zoomPersistRequested(root.zoom)
    }

    function recalculateFitWidthZoom() {
        if (!pageFlick || pageFlick.width <= 0)
            return

        var pageW = root.pageWidth(root.currentPage)
        if (!isFinite(pageW) || pageW <= 0)
            pageW = 612

        var availableW = Math.max(120, pageFlick.width - 40)
        root.fitWidthZoom = Math.max(0.1, Math.min(3.0, availableW / pageW))
    }

    function applyInitialZoom() {
        var z = Number(root.initialZoom || 1.25)
        if (!isFinite(z) || z <= 0)
            z = 1.25
        root.zoom = Math.max(0.6, Math.min(3.2, z))
        root.renderRevision += 1
    }

    function elementsOnPage(page) {
        var result = []
        var items = pdfExtractionController.elements || []
        for (var i = 0; i < items.length; i++) {
            var bbox = items[i].bbox || []
            if (Number(items[i].page || 0) === page && bbox.length >= 4)
                result.push(items[i])
        }
        return result
    }

    function pageSize(page) {
        var pages = pdfExtractionController.pages || []
        for (var p = 0; p < pages.length; p++) {
            if (Number(pages[p].page || 0) === page)
                return [Number(pages[p].width || 612), Number(pages[p].height || 792)]
        }

        var items = pdfExtractionController.elements || []
        for (var i = 0; i < items.length; i++) {
            if (Number(items[i].page || 0) === page && items[i].pageSize && items[i].pageSize.length >= 2)
                return items[i].pageSize
        }

        return [612, 792]
    }

    function pageWidth(page) {
        return Number(root.pageSize(page)[0] || 612)
    }

    function pageHeight(page) {
        return Number(root.pageSize(page)[1] || 792)
    }

    function scrollToPage(page) {
        var y = 0
        for (var i = 0; i < page; i++)
            y += root.pageHeight(i) * root.effectiveZoom + 38
        pageFlick.contentY = Math.max(0, Math.min(y, pageFlick.contentHeight - pageFlick.height))
    }

    function scrollToElement(page, bbox) {
        var pageIndex = Math.max(0, Number(page || 0))
        var pageTop = 0
        for (var i = 0; i < pageIndex; i++)
            pageTop += root.pageHeight(i) * root.effectiveZoom + 38

        var targetY = pageTop
        var targetX = 0
        var box = bbox || []
        if (box.length >= 4) {
            var pageW = root.pageWidth(pageIndex)
            var frameW = pageW * root.effectiveZoom + 20
            var frameLeft = Math.max(0, (pageColumn.width - frameW) / 2)
            var centerX = (Number(box[0] || 0) + Number(box[2] || 0)) / 2
            var centerY = (Number(box[1] || 0) + Number(box[3] || 0)) / 2
            targetX = frameLeft + 10 + centerX * root.effectiveZoom - pageFlick.width / 2
            targetY = pageTop + 10 + centerY * root.effectiveZoom - pageFlick.height / 2
        }

        Qt.callLater(function() {
            pageFlick.contentX = root.clampContentX(targetX)
            pageFlick.contentY = root.clampContentY(targetY)
        })
    }

    function engineLabel(engine) {
        var value = String(engine || "")
        if (value === "pymupdf" || value === "fast")
            return "PyMuPDF"
        if (value === "paddleocr_vl")
            return "PaddleOCR-VL"
        if (value === "mineru")
            return "MinerU"
        return value || "unknown"
    }

    function engineStatusName(value) {
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

    function engineStatusRows() {
        var status = root.engineStatusInfo || ({})
        var order = ["pymupdf", "mineru", "paddleocr_vl"]
        var rows = []

        for (var i = 0; i < order.length; i++) {
            var key = order[i]
            var item = status[key] || ({
                available: false,
                installable: false,
                status: "unknown",
                message: "未知"
            })

            rows.push({
                key: key,
                label: root.engineLabel(key),
                available: !!item.available,
                installable: !!item.installable,
                state: item.available
                    ? "可用"
                    : (item.installable ? "可初始化" : root.engineStatusName(item.status)),
                message: String(item.message || "")
            })
        }

        return rows
    }

}
