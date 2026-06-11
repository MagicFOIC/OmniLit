import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: root
    property var tourHost: null
    property string recordId: ""
    property string pdfPath: ""
    property string title: ""
    property real initialZoom: 1.0
    property real zoom: 1.0
    property bool showAnnotations: true
    property int renderRevision: 0
    property int currentPage: 0
    property string operationStatus: ""
    property string activeOpenKey: ""
    property string exportedPath: ""

    signal backRequested()
    signal zoomPersistRequested(real value)

    Motion { id: motion }
    Theme { id: theme }
    LayoutMetrics { id: metrics; viewportWidth: root.width; viewportHeight: root.height }
    Timer { id: openRecordTimer; interval: 0; repeat: false; onTriggered: root.openRecordNow() }

    Component.onCompleted: { root.scheduleOpenRecord(); root.registerTourTargets() }
    Component.onDestruction: root.unregisterTourTargets()
    onRecordIdChanged: root.scheduleOpenRecord()
    onPdfPathChanged: root.scheduleOpenRecord()
    onVisibleChanged: {
        if(visible) {
            root.scheduleOpenRecord()
        }
    }

    Connections {
        target: pdfExtractionController
        function onAnalysisReady(recordId) {
            if(recordId === root.recordId) {
                root.renderRevision += 1
                root.operationStatus = "解析完成。"
            }
        }
        function onElementFocused(elementId, page, bbox) {
            root.currentPage = page
            root.scrollToPage(page)
        }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 10

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 58
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
                Text { text: Math.round(root.zoom * 100) + "%"; color: theme.textMuted; Layout.preferredWidth: 48; horizontalAlignment: Text.AlignHCenter }
                PillButton { text: "+"; onClicked: root.adjustZoom(0.15) }
                PillButton {
                    text: "打开 PNG 目录"
                    visible: root.exportedPath !== ""
                    enabled: visible
                    onClicked: pdfExtractionController.openExportDirectory(root.exportedPath)
                }
                PillButton { text: "重新解析"; enabled: !pdfExtractionController.loading; onClicked: root.reanalyze() }
                PillButton { text: "导出全部"; onClicked: root.exportAll() }
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
                    clip: true
                    boundsBehavior: Flickable.StopAtBounds
                    ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
                    ScrollBar.horizontal: ScrollBar { policy: ScrollBar.AsNeeded }
                    contentWidth: Math.max(width, pageColumn.width)
                    contentHeight: pageColumn.height

                    WheelHandler {
                        acceptedModifiers: Qt.ControlModifier
                        target: null
                        onWheel: function(event) {
                            root.adjustZoom(event.angleDelta.y > 0 ? 0.1 : -0.1)
                            event.accepted = true
                        }
                    }

                    Column {
                        id: pageColumn
                        width: Math.max(pageFlick.width, root.pageWidth(root.currentPage) * root.displayScale(root.currentPage) + 40)
                        spacing: 18

                        Repeater {
                            model: Math.max(0, pdfExtractionController.pageCount)
                            delegate: Rectangle {
                                id: pageFrame
                                property var sizeInfo: root.pageSize(index)
                                property real scale: root.displayScale(index)
                                property bool nearViewport: y + height > pageFlick.contentY - pageFlick.height
                                    && y < pageFlick.contentY + pageFlick.height * 2.0
                                width: root.pageWidth(index) * pageFrame.scale + 20
                                height: root.pageHeight(index) * pageFrame.scale + 20
                                radius: 4
                                color: "#ffffff"
                                border.color: index === root.currentPage ? theme.accent : theme.border
                                anchors.horizontalCenter: parent.horizontalCenter

                                Image {
                                    id: pageImage
                                    anchors.centerIn: parent
                                    width: root.pageWidth(index) * pageFrame.scale
                                    height: root.pageHeight(index) * pageFrame.scale
                                    source: pageFrame.nearViewport && root.renderRevision >= 0
                                        ? pdfExtractionController.renderPage(root.recordId, index, pageFrame.scale)
                                        : ""
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
                Layout.maximumWidth: 340
                Layout.fillHeight: true
                element: pdfExtractionController.selectedElement
                documentKey: root.recordId + "|" + root.pdfPath

                onLastExportPathChanged: {
                    if (lastExportPath.length > 0)
                        root.exportedPath = lastExportPath
                }
            }
        }

    }

    function scheduleOpenRecord() {
        if(root.visible)
            openRecordTimer.restart()
    }

    function openRecordNow() {
        if(root.recordId === "" || root.pdfPath === "")
            return

        var openKey = root.recordId + "|" + root.pdfPath

        if(root.activeOpenKey === openKey && (pdfExtractionController.pageCount > 0 || pdfExtractionController.loading))
            return

        root.activeOpenKey = openKey
        root.currentPage = 0
        root.restoreZoom()
        root.exportedPath = ""
        root.operationStatus = ""

        if(!pdfExtractionController.loadIndexForPdf(root.recordId, root.pdfPath))
            pdfExtractionController.analyzeRecord(root.recordId, root.pdfPath)

        root.renderRevision += 1
    }

    function reanalyze() {
        root.operationStatus = ""
        pdfExtractionController.analyzeRecord(root.recordId, root.pdfPath)
    }

    function exportAll() {
        var path = pdfExtractionController.exportElement("__all__", "dir")
        root.exportedPath = path || ""
        root.operationStatus = path ? ("已导出到：" + path) : pdfExtractionController.statusText
    }

    function restoreZoom() {
        var value = Number(root.initialZoom || 1.25)
        root.zoom = Math.max(0.6, Math.min(3.2, value))
    }

    function adjustZoom(delta) {
        root.zoom = Math.max(0.6, Math.min(3.2, root.zoom + delta))
        root.zoomPersistRequested(root.zoom)
        root.renderRevision += 1
    }

    function elementsOnPage(page) {
        var result = []
        var items = pdfExtractionController.elements || []
        for(var i = 0; i < items.length; i++) {
            if(Number(items[i].page || 0) === page)
                result.push(items[i])
        }
        return result
    }

    function pageSize(page) {
        var pages = pdfExtractionController.pages || []
        for(var p = 0; p < pages.length; p++) {
            if(Number(pages[p].page || 0) === page)
                return [Number(pages[p].width || 612), Number(pages[p].height || 792)]
        }
        var items = pdfExtractionController.elements || []
        for(var i = 0; i < items.length; i++) {
            if(Number(items[i].page || 0) === page && items[i].pageSize && items[i].pageSize.length >= 2)
                return items[i].pageSize
        }
        return [612, 792]
    }

    function fitScale(page) {
        var viewport = Math.max(1, pageFlick.width || root.width)
        var raw = (viewport - 56) / Math.max(1, root.pageWidth(page))
        return Math.max(0.35, Math.min(1.0, raw))
    }

    function displayScale(page) {
        return root.zoom * root.fitScale(page)
    }

    function pageWidth(page) {
        return Number(root.pageSize(page)[0] || 612)
    }

    function pageHeight(page) {
        return Number(root.pageSize(page)[1] || 792)
    }

    function scrollToPage(page) {
        var y = 0
        for(var i = 0; i < page; i++)
            y += root.pageHeight(i) * root.displayScale(i) + 38
        pageFlick.contentY = Math.max(0, Math.min(y, pageFlick.contentHeight - pageFlick.height))
    }
    function registerTourTargets() {
        if(root.tourHost)
            root.tourHost.registerTourTarget("reader.panel", root)
    }
    function unregisterTourTargets() {
        if(root.tourHost)
            root.tourHost.unregisterTourTarget("reader.panel", root)
    }
}
