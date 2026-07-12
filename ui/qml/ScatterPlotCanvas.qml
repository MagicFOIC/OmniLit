import QtQuick

Item {
    id: root

    Theme { id: theme }

    property var subplot: ({})
    property string selectedSeriesId: ""
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

    onSubplotChanged: {
        root.cachedBounds = root.calculateDataBounds()
        canvas.requestPaint()
    }
    onSelectedSeriesIdChanged: {
        root.cachedBounds = root.calculateDataBounds()
        canvas.requestPaint()
    }
    onWidthChanged: canvas.requestPaint()
    onHeightChanged: canvas.requestPaint()

    function paintPlot() {
        var ctx = canvas.getContext("2d")
        ctx.clearRect(0, 0, canvas.width, canvas.height)
        ctx.fillStyle = theme.surface
        ctx.fillRect(0, 0, canvas.width, canvas.height)

        var plot = root.plotRect()
        ctx.strokeStyle = theme.border
        ctx.lineWidth = 1
        ctx.strokeRect(plot.x, plot.y, plot.w, plot.h)

        var bounds = root.cachedBounds
        ctx.fillStyle = theme.textMuted
        ctx.font = "11px sans-serif"
        var axes = root.subplot && root.subplot.axes ? root.subplot.axes : ({})
        var xAxis = axes.x || ({})
        var yAxis = axes.y || ({})
        ctx.fillText(String(xAxis.label || "x"), plot.x + plot.w - 18, canvas.height - 8)
        ctx.fillText(String(yAxis.label || "y"), 8, plot.y + 12)

        ctx.strokeStyle = theme.divider
        ctx.lineWidth = 0.6
        for (var tick = 0; tick <= 4; tick++) {
            var ratio = tick / 4
            var gx = plot.x + ratio * plot.w
            var gy = plot.y + ratio * plot.h
            ctx.beginPath()
            ctx.moveTo(gx, plot.y)
            ctx.lineTo(gx, plot.y + plot.h)
            ctx.moveTo(plot.x, gy)
            ctx.lineTo(plot.x + plot.w, gy)
            ctx.stroke()
            ctx.fillStyle = theme.textMuted
            ctx.fillText(root.formatNumber(bounds.minX + ratio * (bounds.maxX - bounds.minX)), gx - 8, plot.y + plot.h + 16)
            ctx.fillText(root.formatNumber(bounds.maxY - ratio * (bounds.maxY - bounds.minY)), 2, gy + 4)
        }

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

    function formatNumber(value) {
        var n = Number(value)
        if (!isFinite(n))
            return "-"
        if (Math.abs(n) >= 1000 || Math.abs(n) < 0.001)
            return n.toExponential(3)
        return String(Math.round(n * 10000) / 10000)
    }
}
