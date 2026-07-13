import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: root
    property string recordId: ""
    property string pdfPath: ""
    property var replayEvent: ({})
    property int replayIndex: -1
    property string pageSource: ""
    property int sourceZoomKey: 100
    property real renderScale: 1.0
    property bool renderPending: false
    readonly property bool fullDocumentMode: knowledgeGraphController.replayComplete

    Theme { id: theme }
    color: theme.surface
    border.color: theme.border
    radius: theme.radiusMedium
    clip: true

    Component.onCompleted: openDocument()
    onRecordIdChanged: openDocument()
    onPdfPathChanged: openDocument()
    onReplayIndexChanged: {
        refreshPage()
        extractionPulse.restart()
    }

    Connections {
        target: pdfExtractionController
        function onAnalysisReady(readyRecordId) {
            if (readyRecordId === root.recordId)
                root.refreshPage()
        }
        function onPageRenderReady(readyRecordId, page, zoomKey, url) {
            if (readyRecordId === root.recordId && page === root.currentPage() && zoomKey === root.sourceZoomKey) {
                root.pageSource = url
                root.renderPending = false
            }
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 8
        spacing: 7

        RowLayout {
            Layout.fillWidth: true
            Text { text: "原文分析"; color: theme.text; font.bold: true }
            Item { Layout.fillWidth: true }
            Label {
                text: root.replayIndex < 0 ? "等待回放" : "第 " + (root.currentPage() + 1) + " 页"
                color: theme.accent
            }
        }

        Flickable {
            id: pageFlick
            visible: !root.fullDocumentMode
            Layout.fillWidth: true
            Layout.fillHeight: true
            contentWidth: Math.max(width, pageFrame.width)
            contentHeight: Math.max(height, pageFrame.height)
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            flickableDirection: Flickable.VerticalFlick
            ScrollBar.vertical: StyledScrollBar { policy: ScrollBar.AlwaysOn }

            Rectangle {
                id: pageFrame
                width: Math.max(320, root.pageWidth() * root.pageScale())
                height: Math.max(420, root.pageHeight() * root.pageScale())
                anchors.horizontalCenter: parent.horizontalCenter
                color: "white"
                border.color: theme.border

                Image {
                    id: pageImage
                    anchors.fill: parent
                    source: root.pageSource
                    fillMode: Image.Stretch
                    asynchronous: true
                    cache: true
                }

                BusyIndicator { anchors.centerIn: parent; running: root.renderPending; visible: running }

                Rectangle {
                    id: evidenceHalo
                    property var box: root.replayEvent.bbox || []
                    visible: box.length >= 4
                    x: Number(box[0] || 0) * root.pageScale() - 6
                    y: Number(box[1] || 0) * root.pageScale() - 6
                    width: Math.max(18, (Number(box[2] || 0) - Number(box[0] || 0)) * root.pageScale() + 12)
                    height: Math.max(18, (Number(box[3] || 0) - Number(box[1] || 0)) * root.pageScale() + 12)
                    radius: 9
                    color: "#18f59e0b"
                    border.width: 3
                    border.color: "#f59e0b"
                    opacity: 0.92
                }

            }
        }

        Flickable {
            id: fullDocumentFlick
            visible: root.fullDocumentMode
            Layout.fillWidth: true
            Layout.fillHeight: true
            contentWidth: width
            contentHeight: fullPageColumn.height
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            flickableDirection: Flickable.VerticalFlick
            ScrollBar.vertical: StyledScrollBar { policy: ScrollBar.AlwaysOn }

            Column {
                id: fullPageColumn
                width: fullDocumentFlick.width
                spacing: 18

                Repeater {
                    model: root.fullDocumentMode ? Math.max(0, pdfExtractionController.pageCount) : 0

                    delegate: Rectangle {
                        id: fullPageFrame
                        required property int index
                        property string renderedSource: ""
                        property bool renderRequested: false
                        property var info: root.pageInfoFor(index)
                        property real scaleFactor: root.fullPageScale(index)
                        property bool nearViewport: y + height > fullDocumentFlick.contentY - fullDocumentFlick.height
                                                           && y < fullDocumentFlick.contentY + fullDocumentFlick.height * 2
                        width: Math.max(280, Number(info.width || 612) * scaleFactor)
                        height: Math.max(360, Number(info.height || 792) * scaleFactor)
                        anchors.horizontalCenter: parent.horizontalCenter
                        color: "white"
                        border.color: theme.border
                        radius: 3

                        Component.onCompleted: Qt.callLater(refreshSource)
                        onNearViewportChanged: refreshSource()

                        Connections {
                            target: pdfExtractionController
                            function onPageRenderReady(readyRecordId, page, zoomKey, url) {
                                if (readyRecordId === root.recordId && page === fullPageFrame.index && zoomKey === 100) {
                                    fullPageFrame.renderedSource = url
                                    fullPageFrame.renderRequested = false
                                }
                            }
                        }

                        Image {
                            anchors.fill: parent
                            source: fullPageFrame.renderedSource
                            fillMode: Image.Stretch
                            asynchronous: true
                            cache: true
                        }
                        BusyIndicator {
                            anchors.centerIn: parent
                            running: fullPageFrame.renderRequested
                            visible: running
                        }
                        Text {
                            anchors.right: parent.right
                            anchors.bottom: parent.bottom
                            anchors.margins: 8
                            text: (fullPageFrame.index + 1) + " / " + pdfExtractionController.pageCount
                            color: "#64748b"
                            font.pixelSize: 11
                        }

                        function refreshSource() {
                            if (!nearViewport || renderRequested || !root.fullDocumentMode) return
                            var cached = pdfExtractionController.cachedRenderedPage(root.recordId, index, 1.0)
                            if (cached) renderedSource = cached
                            else {
                                renderRequested = true
                                pdfExtractionController.renderPageAsync(root.recordId, index, 1.0)
                            }
                        }
                    }
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: Math.min(112, excerptText.implicitHeight + 20)
            radius: theme.radiusSmall
            color: theme.surfaceSoft
            border.color: theme.border
            Text {
                id: excerptText
                anchors.fill: parent
                anchors.margins: 10
                textFormat: Text.RichText
                text: root.markedExcerpt()
                color: theme.text
                wrapMode: Text.WordWrap
                elide: Text.ElideRight
            }
        }
    }

    SequentialAnimation {
        id: extractionPulse
        NumberAnimation { target: evidenceHalo; property: "scale"; from: 0.92; to: 1.06; duration: 260; easing.type: Easing.OutQuad }
        NumberAnimation { target: evidenceHalo; property: "scale"; to: 1.0; duration: 300; easing.type: Easing.InOutQuad }
        NumberAnimation { target: evidenceHalo; property: "opacity"; from: 0.55; to: 1.0; duration: 280 }
    }

    function openDocument() {
        if (root.recordId && root.pdfPath)
            pdfExtractionController.openRecordAsync(root.recordId, root.pdfPath)
    }
    function currentPage() { return Math.max(0, Number(root.replayEvent.page || 0)) }
    function pageInfo() {
        return pageInfoFor(currentPage())
    }
    function pageInfoFor(pageNumber) {
        var pages = pdfExtractionController.pages || []
        for (var i = 0; i < pages.length; ++i)
            if (Number(pages[i].page || 0) === Number(pageNumber)) return pages[i]
        return ({ width: 612, height: 792 })
    }
    function pageWidth() { return Number(pageInfo().width || 612) }
    function pageHeight() { return Number(pageInfo().height || 792) }
    function pageScale() { return Math.max(0.35, (pageFlick.width - 28) / Math.max(1, pageWidth())) }
    function fullPageScale(pageNumber) {
        var info = pageInfoFor(pageNumber)
        return Math.max(0.35, (fullDocumentFlick.width - 34) / Math.max(1, Number(info.width || 612)))
    }
    function evidencePointIn(targetItem) {
        if (!targetItem || !evidenceHalo.visible)
            return mapToItem(targetItem, width * 0.75, height * 0.5)
        return evidenceHalo.mapToItem(targetItem, evidenceHalo.width / 2, evidenceHalo.height / 2)
    }
    function refreshPage() {
        if (!root.recordId || root.replayIndex < 0) return
        root.renderScale = 1.0
        root.sourceZoomKey = 100
        var cached = pdfExtractionController.cachedRenderedPage(root.recordId, currentPage(), root.renderScale)
        if (cached) { root.pageSource = cached; root.renderPending = false }
        else { root.pageSource = ""; root.renderPending = true; pdfExtractionController.renderPageAsync(root.recordId, currentPage(), root.renderScale) }
    }
    function escaped(value) {
        return String(value || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    }
    function markedExcerpt() {
        var text = String(root.replayEvent.excerpt || "等待从原文阅读顺序开始分析…")
        var cues = root.replayEvent.relationCues || []
        if (!cues.length) return escaped(text)
        var cue = cues[0]
        var start = Number(cue.start || 0), length = Number(cue.length || 0)
        return escaped(text.slice(0, start)) + "<u><b><font color='#f59e0b'>" + escaped(text.slice(start, start + length)) + "</font></b></u>" + escaped(text.slice(start + length))
    }
}
