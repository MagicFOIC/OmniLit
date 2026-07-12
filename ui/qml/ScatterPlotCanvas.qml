import QtQuick
import QtQuick.Controls

Item {
    id: root

    property var subplot: ({})
    property string selectedSeriesId: ""
    property var hoveredPoint: ({})
    property real leftPad: 44
    property real rightPad: 16
    property real topPad: 18
    property real bottomPad: 34
    property var cachedBounds: ({ minX: 0, maxX: 1, minY: 0, maxY: 1 })

    implicitHeight: 260
    clip: true

    Canvas {
        id: canvas
        anchors.fill: parent
        antialiasing: true
        onPaint: root.paintPlot()
    }

    MouseArea {
        id: hoverArea
        anchors.fill: parent
        hoverEnabled: true
        onPositionChanged: root.updateHover(mouse.x, mouse.y)
        onExited: {
            root.hoveredPoint = ({})
            canvas.requestPaint()
        }
    }

    Rectangle {
        id: tooltip
        visible: root.hoveredPoint && root.hoveredPoint.point
        x: Math.min(parent.width - width - 8, Math.max(8, Number(root.hoveredPoint.screenX || 0) + 12))
        y: Math.min(parent.height - height - 8, Math.max(8, Number(root.hoveredPoint.screenY || 0) - height - 8))
        width: tooltipText.implicitWidth + 18
        height: tooltipText.implicitHeight + 12
        radius: 6
        color: "#f8fafc"
        border.color: "#cbd5e1"

        Text {
            id: tooltipText
            anchors.centerIn: parent
            text: root.tooltipText()
            color: "#0f172a"
            font.pixelSize: 11
            lineHeight: 1.15
        }
    }

    onSubplotChanged: {
        root.hoveredPoint = ({})
        root.cachedBounds = root.calculateDataBounds()
        canvas.requestPaint()
    }
    onSelectedSeriesIdChanged: {
        root.hoveredPoint = ({})
        root.cachedBounds = root.calculateDataBounds()
        canvas.requestPaint()
    }
    onWidthChanged: canvas.requestPaint()
    onHeightChanged: canvas.requestPaint()

    function paintPlot() {
        var ctx = canvas.getContext("2d")
        ctx.clearRect(0, 0, canvas.width, canvas.height)
        ctx.fillStyle = "#ffffff"
        ctx.fillRect(0, 0, canvas.width, canvas.height)

        var plot = root.plotRect()
        ctx.strokeStyle = "#cbd5e1"
        ctx.lineWidth = 1
        ctx.strokeRect(plot.x, plot.y, plot.w, plot.h)

        ctx.fillStyle = "#64748b"
        ctx.font = "11px sans-serif"
        ctx.fillText("x", plot.x + plot.w - 8, canvas.height - 8)
        ctx.fillText("y", 8, plot.y + 12)

        var bounds = root.cachedBounds
        var series = root.visibleSeries()
        for (var i = 0; i < series.length; i++) {
            var entry = series[i] || {}
            var points = entry.points || []
            ctx.fillStyle = entry.color || "#2563eb"
            ctx.strokeStyle = entry.color || "#2563eb"
            ctx.lineWidth = 1
            ctx.globalAlpha = 0.88
            ctx.beginPath()
            var lineStarted = false
            for (var p = 0; p < points.length; p++) {
                var point = points[p] || {}
                if (point.missing || point.x === null || point.y === null) {
                    lineStarted = false
                    continue
                }
                var pos = root.pointToScreen(point, bounds, plot)
                if (!lineStarted) {
                    ctx.moveTo(pos.x, pos.y)
                    lineStarted = true
                } else {
                    ctx.lineTo(pos.x, pos.y)
                }
            }
            ctx.stroke()
            for (var marker = 0; marker < points.length; marker++) {
                var markerPoint = points[marker] || {}
                if (markerPoint.missing || markerPoint.x === null || markerPoint.y === null)
                    continue
                var markerPos = root.pointToScreen(markerPoint, bounds, plot)
                ctx.beginPath()
                ctx.arc(markerPos.x, markerPos.y, 3.2, 0, Math.PI * 2)
                ctx.fill()
            }
        }
        ctx.globalAlpha = 1

        if (root.hoveredPoint && root.hoveredPoint.point) {
            ctx.strokeStyle = "#0f172a"
            ctx.lineWidth = 1.5
            ctx.beginPath()
            ctx.arc(root.hoveredPoint.screenX, root.hoveredPoint.screenY, 6, 0, Math.PI * 2)
            ctx.stroke()
        }
    }

    function updateHover(mx, my) {
        var plot = root.plotRect()
        var bounds = root.cachedBounds
        var best = null
        var bestDistanceSquared = 999999
        var series = root.visibleSeries()
        for (var i = 0; i < series.length; i++) {
            var entry = series[i] || {}
            var points = entry.points || []
            for (var p = 0; p < points.length; p++) {
                var point = points[p] || {}
                if (point.missing || point.x === null || point.y === null)
                    continue
                var pos = root.pointToScreen(point, bounds, plot)
                var dx = pos.x - mx
                var dy = pos.y - my
                var distanceSquared = dx * dx + dy * dy
                if (distanceSquared < bestDistanceSquared) {
                    bestDistanceSquared = distanceSquared
                    best = { point: point, series: entry, screenX: pos.x, screenY: pos.y }
                }
            }
        }
        root.hoveredPoint = best && bestDistanceSquared <= 196 ? best : ({})
        canvas.requestPaint()
    }

    function plotRect() {
        return {
            x: root.leftPad,
            y: root.topPad,
            w: Math.max(40, root.width - root.leftPad - root.rightPad),
            h: Math.max(40, root.height - root.topPad - root.bottomPad)
        }
    }

    function visibleSeries() {
        var items = root.subplot && root.subplot.series ? root.subplot.series : []
        if (!root.selectedSeriesId || root.selectedSeriesId === "")
            return items
        var result = []
        for (var i = 0; i < items.length; i++) {
            if (String(items[i].seriesId || "") === root.selectedSeriesId)
                result.push(items[i])
        }
        return result
    }

    function calculateDataBounds() {
        var minX = 999999999
        var maxX = -999999999
        var minY = 999999999
        var maxY = -999999999
        var series = root.visibleSeries()
        for (var i = 0; i < series.length; i++) {
            var points = (series[i] || {}).points || []
            for (var p = 0; p < points.length; p++) {
                var point = points[p] || {}
                if (point.missing || point.x === null || point.y === null)
                    continue
                minX = Math.min(minX, Number(point.x))
                maxX = Math.max(maxX, Number(point.x))
                minY = Math.min(minY, Number(point.y))
                maxY = Math.max(maxY, Number(point.y))
            }
        }
        if (minX === 999999999 || maxX === minX) {
            minX = 0
            maxX = 1
        }
        if (minY === 999999999 || maxY === minY) {
            minY = 0
            maxY = 1
        }
        return { minX: minX, maxX: maxX, minY: minY, maxY: maxY }
    }

    function pointToScreen(point, bounds, plot) {
        var xRatio = (Number(point.x) - bounds.minX) / Math.max(0.000001, bounds.maxX - bounds.minX)
        var yRatio = (Number(point.y) - bounds.minY) / Math.max(0.000001, bounds.maxY - bounds.minY)
        return {
            x: plot.x + xRatio * plot.w,
            y: plot.y + plot.h - yRatio * plot.h
        }
    }

    function tooltipText() {
        var item = root.hoveredPoint || {}
        var point = item.point || {}
        var series = item.series || {}
        if (!point)
            return ""
        return "subplot: " + String((root.subplot || {}).subplotId || "") +
            "\nseries: " + String(series.name || series.seriesId || "") +
            "\nx: " + root.formatNumber(point.x) +
            "\ny: " + root.formatNumber(point.y) +
            "\nconfidence: " + Math.round(Number(point.confidence || 0) * 100) + "%"
    }

    function formatNumber(value) {
        var n = Number(value)
        if (!isFinite(n))
            return "-"
        if (Math.abs(n) >= 1000 || Math.abs(n) < 0.001)
            return n.toExponential(3)
        return String(Math.round(n * 10000) / 10000)
    }
}
