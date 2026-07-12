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
    property int renderZoomKey: Math.round(root.effectiveZoom * 100)
    property int renderRevision: 0
    property int textRevision: 0
    property int currentPage: 0
    property string activeOpenKey: ""
    property bool deferPageRendering: true
    property string operationStatus: ""

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
        interval: 90
        repeat: false
        onTriggered: {
            root.deferPageRendering = false
            root.renderRevision += 1
            root.textRevision += 1
        }
    }

    Component.onCompleted: {
        root.applyInitialZoom()
        root.scheduleOpenRecord()
    }

    onInitialZoomChanged: root.applyInitialZoom()
    onRecordIdChanged: root.handleTargetChanged()
    onPdfPathChanged: root.handleTargetChanged()
    onVisibleChanged: {
        if (visible)
            root.scheduleOpenRecord()
        else {
            if (pdfExtractionController.loading)
                pdfExtractionController.cancelAnalysis()
        }
    }

    Connections {
        target: pdfExtractionController

        function onAnalysisReady(recordId) {
            if (recordId === root.recordId) {
                root.recalculateFitWidthZoom()
                root.renderRevision += 1
                root.textRevision += 1
                root.operationStatus = "快速解析已完成，可以点击或框选正文翻译。"
            }
        }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 10

        Rectangle {
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
                    text: root.title || "翻译阅读"
                    color: theme.text
                    font.weight: Font.Bold
                    elide: Text.ElideRight
                }

                Label {
                    text: selectionTranslationController.modelLabel
                    color: theme.textMuted
                    elide: Text.ElideRight
                    Layout.maximumWidth: 260
                    background: Rectangle { color: theme.surfaceSoft; radius: 5 }
                    padding: 6
                }

                PillButton { text: "-"; onClicked: root.adjustZoom(-0.15) }

                Text {
                    text: Math.round(root.zoom * 100) + "%"
                    color: theme.textMuted
                    Layout.preferredWidth: 48
                    horizontalAlignment: Text.AlignHCenter
                }

                PillButton { text: "+"; onClicked: root.adjustZoom(0.15) }
                PillButton { text: "适宽"; onClicked: root.resetFitWidthZoom() }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 10

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
                    clip: true
                    boundsBehavior: Flickable.StopAtBounds
                    flickDeceleration: 4800
                    maximumFlickVelocity: 2800
                    pixelAligned: true

                    onWidthChanged: {
                        root.recalculateFitWidthZoom()
                        root.deferPageRendering = true
                        renderResumeTimer.restart()
                    }
                    onMovementStarted: {
                        root.deferPageRendering = true
                        renderResumeTimer.stop()
                    }
                    onMovementEnded: renderResumeTimer.restart()

                    ScrollBar.vertical: StyledScrollBar { policy: ScrollBar.AsNeeded }
                    ScrollBar.horizontal: StyledScrollBar { policy: ScrollBar.AsNeeded }

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
                                property bool nearViewport: y + height > pageFlick.contentY - pageFlick.height * 0.5 && y < pageFlick.contentY + pageFlick.height * 1.35
                                property string pageSource: ""
                                property int sourceZoomKey: 0
                                property bool renderPending: false
                                property var textItems: []

                                width: Number(sizeInfo[0] || 612) * root.effectiveZoom + 20
                                height: Number(sizeInfo[1] || 792) * root.effectiveZoom + 20
                                radius: 4
                                color: "#ffffff"
                                border.color: index === root.currentPage ? theme.accent : theme.border
                                anchors.horizontalCenter: parent.horizontalCenter

                                Component.onCompleted: {
                                    refreshSource()
                                    refreshTextItems()
                                }
                                onNearViewportChanged: {
                                    refreshSource()
                                    refreshTextItems()
                                }

                                Connections {
                                    target: root
                                    function onRenderRevisionChanged() { pageFrame.refreshSource() }
                                    function onTextRevisionChanged() { pageFrame.refreshTextItems() }
                                    function onDeferPageRenderingChanged() {
                                        if (!root.deferPageRendering) {
                                            pageFrame.refreshSource()
                                            pageFrame.refreshTextItems()
                                        } else {
                                            pageFrame.renderPending = false
                                        }
                                    }
                                }

                                Connections {
                                    target: pdfExtractionController
                                    function onPageRenderReady(recordId, page, zoomKey, url) {
                                        if (recordId === root.recordId && page === index && zoomKey === root.renderZoomKey) {
                                            pageFrame.pageSource = url
                                            pageFrame.sourceZoomKey = zoomKey
                                            pageFrame.renderPending = false
                                        }
                                    }

                                    function onTextWordsReady(recordId, pdfPath, page, items) {
                                        if (recordId === root.recordId && page === index)
                                            pageFrame.textItems = items
                                    }
                                }

                                function refreshSource() {
                                    if (!pageFrame.nearViewport || root.deferPageRendering || root.renderRevision < 0)
                                        return

                                    var cached = pdfExtractionController.cachedRenderedPage(root.recordId, index, root.effectiveZoom)
                                    if (cached && cached.length > 0) {
                                        pageFrame.pageSource = cached
                                        pageFrame.sourceZoomKey = root.renderZoomKey
                                        pageFrame.renderPending = false
                                    } else {
                                        pageFrame.pageSource = ""
                                        pageFrame.sourceZoomKey = 0
                                        pageFrame.renderPending = true
                                        pdfExtractionController.renderPageAsync(root.recordId, index, root.effectiveZoom)
                                    }
                                }

                                function refreshTextItems() {
                                    if (pageFrame.nearViewport && !root.deferPageRendering && root.recordId !== "" && root.pdfPath !== "")
                                        pdfExtractionController.requestTextWordsForPdfPage(root.recordId, root.pdfPath, index)
                                    else
                                        pageFrame.textItems = []
                                }

                                Loader {
                                    id: pageContentLoader
                                    anchors.centerIn: parent
                                    width: Number(pageFrame.sizeInfo[0] || 612) * root.effectiveZoom
                                    height: Number(pageFrame.sizeInfo[1] || 792) * root.effectiveZoom
                                    active: pageFrame.nearViewport
                                    asynchronous: true
                                    sourceComponent: pageContentComponent
                                }

                                Component {
                                    id: pageContentComponent

                                    Item {
                                        Image {
                                            id: pageImage
                                            anchors.fill: parent
                                            source: pageFrame.pageSource
                                            visible: pageFrame.sourceZoomKey === root.renderZoomKey && pageFrame.pageSource.length > 0
                                            fillMode: Image.Stretch
                                            asynchronous: true
                                            cache: true
                                        }

                                        BusyIndicator {
                                            anchors.centerIn: parent
                                            running: pageFrame.renderPending && pageFrame.nearViewport
                                            visible: running
                                        }

                                        PdfTextSelectionOverlay {
                                            anchors.fill: parent
                                            pageSize: pageFrame.sizeInfo
                                            renderedSize: Qt.size(parent.width, parent.height)
                                            elements: pageFrame.textItems
                                            selectedText: selectionTranslationController.sourceText
                                            onTextSelected: function(text) {
                                                root.translateSelection(text)
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }

                Text {
                    anchors.centerIn: parent
                    width: parent.width - 40
                    text: pdfExtractionController.loading ? pdfExtractionController.progressText :
                          pdfExtractionController.pageCount === 0 ? "正在准备 PDF 翻译阅读视图..." :
                          ""
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

            Rectangle {
                Layout.preferredWidth: 340
                Layout.minimumWidth: 300
                Layout.maximumWidth: 420
                Layout.fillHeight: true
                radius: theme.radiusMedium
                color: theme.surface
                border.color: theme.border

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 12
                    spacing: 10

                    Text {
                        Layout.fillWidth: true
                        text: "划词翻译"
                        color: theme.text
                        font.pixelSize: theme.baseFontSize + 4
                        font.weight: Font.Bold
                    }

                    StatusBanner {
                        Layout.fillWidth: true
                        text: selectionTranslationController.statusText || root.operationStatus
                        busy: selectionTranslationController.loading
                        tone: selectionTranslationController.errorText.length > 0 ? "error" : selectionTranslationController.cacheHit ? "success" : "neutral"
                        reserveSpace: true
                        maximumLines: 3
                    }

                    Text {
                        Layout.fillWidth: true
                        text: "原文"
                        color: theme.textMuted
                        font.weight: Font.DemiBold
                    }

                    SoftTextArea {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 140
                        readOnly: true
                        wrapMode: TextArea.Wrap
                        text: selectionTranslationController.sourceText || "选中文献中的词句后，将在这里显示翻译。"
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        PillButton {
                            text: "复制原文"
                            enabled: selectionTranslationController.sourceText.length > 0
                            onClicked: selectionTranslationController.copyText(selectionTranslationController.sourceText)
                        }
                        PillButton {
                            text: "重新翻译"
                            enabled: selectionTranslationController.sourceText.length > 0 && !selectionTranslationController.loading
                            onClicked: selectionTranslationController.retranslateSelection(root.recordId, root.pdfPath, selectionTranslationController.sourceText, "zh")
                        }
                    }

                    Text {
                        Layout.fillWidth: true
                        text: "译文"
                        color: theme.textMuted
                        font.weight: Font.DemiBold
                    }

                    SoftTextArea {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        readOnly: true
                        wrapMode: TextArea.Wrap
                        text: selectionTranslationController.translatedText || ""
                        placeholderText: "译文会显示在这里"
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        PillButton {
                            text: "复制译文"
                            enabled: selectionTranslationController.translatedText.length > 0
                            primary: true
                            onClicked: selectionTranslationController.copyText(selectionTranslationController.translatedText)
                        }
                        Item { Layout.fillWidth: true }
                    }
                }
            }
        }
    }

    function scheduleOpenRecord() {
        if (root.visible)
            openRecordTimer.restart()
    }

    function handleTargetChanged() {
        openRecordTimer.stop()
        renderResumeTimer.stop()
        root.activeOpenKey = ""
        root.currentPage = 0
        root.operationStatus = ""
        root.deferPageRendering = true
        root.renderRevision += 1
        root.textRevision += 1
        selectionTranslationController.clear()
        pdfExtractionController.clearPdfSession()
        Qt.callLater(function() {
            pageFlick.contentX = 0
            pageFlick.contentY = 0
        })
        root.scheduleOpenRecord()
    }

    function openRecordNow() {
        if (root.recordId === "" || root.pdfPath === "")
            return

        var openKey = root.recordId + "|" + root.pdfPath
        if (root.activeOpenKey === openKey && (pdfExtractionController.pageCount > 0 || pdfExtractionController.loading))
            return

        root.activeOpenKey = openKey
        root.currentPage = 0
        root.operationStatus = ""
        root.deferPageRendering = true
        pdfExtractionController.preparePdfSession(root.recordId, root.pdfPath)
        root.recalculateFitWidthZoom()
        root.applyInitialZoom()
        selectionTranslationController.clear()

        if (!pdfExtractionController.loadPdfPagesForTranslation(root.recordId, root.pdfPath)) {
            root.operationStatus = "正在生成快速解析索引，完成后即可划词翻译..."
            pdfExtractionController.analyzeRecordWithEngine(root.recordId, root.pdfPath, "fast")
        } else {
            root.operationStatus = ""
            root.textRevision += 1
        }

        root.renderRevision += 1
        renderResumeTimer.restart()
    }

    function translateSelection(text) {
        selectionTranslationController.translateSelection(root.recordId, root.pdfPath, text, "zh")
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

    function pageSize(page) {
        var pages = pdfExtractionController.pages || []
        if (page >= 0 && page < pages.length && Number(pages[page].page || 0) === page)
            return [Number(pages[page].width || 612), Number(pages[page].height || 792)]
        for (var p = 0; p < pages.length; p++) {
            if (Number(pages[p].page || 0) === page)
                return [Number(pages[p].width || 612), Number(pages[p].height || 792)]
        }

        return [612, 792]
    }

    function pageWidth(page) {
        return Number(root.pageSize(page)[0] || 612)
    }

    function pageHeight(page) {
        return Number(root.pageSize(page)[1] || 792)
    }
}
