import QtQuick
import QtQuick.Controls

Item {
    id: root

    property var pageSize: [1, 1]
    property size renderedSize: Qt.size(width, height)
    property var elements: []
    property string selectedText: ""
    property var selectedIds: ({})

    signal textSelected(string text)

    Theme { id: theme }

    Repeater {
        model: root.elements || []

        delegate: Rectangle {
            property var bbox: modelData.bbox || [0, 0, 0, 0]
            property real sx: root.renderedSize.width / Math.max(1, Number(root.pageSize[0] || 1))
            property real sy: root.renderedSize.height / Math.max(1, Number(root.pageSize[1] || 1))
            property string itemId: String(modelData.id || "")
            x: Number(bbox[0] || 0) * sx
            y: Number(bbox[1] || 0) * sy
            width: Math.max(8, (Number(bbox[2] || 0) - Number(bbox[0] || 0)) * sx)
            height: Math.max(8, (Number(bbox[3] || 0) - Number(bbox[1] || 0)) * sy)
            radius: 2
            color: root.selectedIds[itemId] ? "#333b82f6" : "#00000000"
            border.color: root.selectedIds[itemId] ? "#3b82f6" : "#00000000"
            border.width: 1
        }
    }

    Rectangle {
        id: selectionRect
        visible: selectionMouse.draggingSelection
        x: Math.min(selectionMouse.startX, selectionMouse.currentX)
        y: Math.min(selectionMouse.startY, selectionMouse.currentY)
        width: Math.abs(selectionMouse.currentX - selectionMouse.startX)
        height: Math.abs(selectionMouse.currentY - selectionMouse.startY)
        color: "#223b82f6"
        border.color: "#3b82f6"
        radius: 2
    }

    MouseArea {
        id: selectionMouse
        anchors.fill: parent
        hoverEnabled: true
        acceptedButtons: Qt.LeftButton
        preventStealing: true
        cursorShape: Qt.IBeamCursor

        property real startX: 0
        property real startY: 0
        property real currentX: 0
        property real currentY: 0
        property bool draggingSelection: false
        property bool suppressNextClick: false
        property var anchorItem: null

        onPressed: function(mouse) {
            startX = mouse.x
            startY = mouse.y
            currentX = mouse.x
            currentY = mouse.y
            anchorItem = root.itemForPoint(mouse.x, mouse.y)
            draggingSelection = false
            if (!anchorItem) {
                mouse.accepted = false
                return
            }
        }

        onPositionChanged: function(mouse) {
            if (!(mouse.buttons & Qt.LeftButton))
                return
            currentX = mouse.x
            currentY = mouse.y
            draggingSelection = Math.abs(currentX - startX) > 6 || Math.abs(currentY - startY) > 6
            if (draggingSelection && anchorItem) {
                var live = root.selectionForDrag(startX, startY, currentX, currentY)
                root.selectedIds = live.ids
                root.selectedText = live.text
            }
        }

        onReleased: function(mouse) {
            currentX = mouse.x
            currentY = mouse.y
            if (draggingSelection && anchorItem) {
                var selected = root.selectionForDrag(startX, startY, currentX, currentY)
                draggingSelection = false
                suppressNextClick = true
                if (selected.text.length > 0) {
                    root.selectedText = selected.text
                    root.selectedIds = selected.ids
                    root.textSelected(selected.text)
                }
            }
        }

        onClicked: function(mouse) {
            if (suppressNextClick) {
                suppressNextClick = false
                return
            }
            if (draggingSelection)
                return
            var item = root.itemForPoint(mouse.x, mouse.y)
            if (item && String(item.text || "").trim().length > 0) {
                root.selectedText = String(item.text || "").trim()
                root.selectedIds = root.idsForItems([item])
                root.textSelected(root.selectedText)
            }
        }

        onDoubleClicked: function(mouse) {
            var item = root.itemForPoint(mouse.x, mouse.y)
            if (item && String(item.text || "").trim().length > 0) {
                root.selectedText = String(item.text || "").trim()
                root.selectedIds = root.idsForItems([item])
                root.textSelected(root.selectedText)
            }
        }
    }

    function scaleX() {
        return root.renderedSize.width / Math.max(1, Number(root.pageSize[0] || 1))
    }

    function scaleY() {
        return root.renderedSize.height / Math.max(1, Number(root.pageSize[1] || 1))
    }

    function itemRect(item) {
        var bbox = item.bbox || [0, 0, 0, 0]
        var sx = root.scaleX()
        var sy = root.scaleY()
        return {
            x: Number(bbox[0] || 0) * sx,
            y: Number(bbox[1] || 0) * sy,
            w: Math.max(8, (Number(bbox[2] || 0) - Number(bbox[0] || 0)) * sx),
            h: Math.max(8, (Number(bbox[3] || 0) - Number(bbox[1] || 0)) * sy)
        }
    }

    function itemAt(x, y) {
        var items = root.elements || []
        for (var i = items.length - 1; i >= 0; --i) {
            var rect = root.itemRect(items[i])
            if (x >= rect.x && x <= rect.x + rect.w && y >= rect.y && y <= rect.y + rect.h)
                return items[i]
        }
        return null
    }

    function itemForPoint(x, y) {
        var direct = root.itemAt(x, y)
        if (direct)
            return direct
        return root.nearestTextItem(x, y)
    }

    function nearestTextItem(x, y) {
        var items = root.elements || []
        var best = null
        var bestScore = 999999
        for (var i = 0; i < items.length; ++i) {
            if (String(items[i].text || "").trim().length === 0)
                continue
            var rect = root.itemRect(items[i])
            var verticalGap = 0
            if (y < rect.y)
                verticalGap = rect.y - y
            else if (y > rect.y + rect.h)
                verticalGap = y - rect.y - rect.h
            if (verticalGap > Math.max(10, rect.h * 0.8))
                continue

            var horizontalGap = 0
            if (x < rect.x)
                horizontalGap = rect.x - x
            else if (x > rect.x + rect.w)
                horizontalGap = x - rect.x - rect.w
            if (horizontalGap > Math.max(36, rect.h * 2.4))
                continue

            var score = verticalGap * 4 + horizontalGap
            if (score < bestScore) {
                best = items[i]
                bestScore = score
            }
        }
        return best
    }

    function selectionForDrag(x1, y1, x2, y2) {
        var startItem = root.itemForPoint(x1, y1)
        var endItem = root.itemForPoint(x2, y2)
        if (!startItem || !endItem) {
            return root.selectionForRect(
                Math.min(x1, x2),
                Math.min(y1, y2),
                Math.abs(x2 - x1),
                Math.abs(y2 - y1)
            )
        }

        var startOrder = Number(startItem.order || 0)
        var endOrder = Number(endItem.order || 0)
        var first = Math.min(startOrder, endOrder)
        var last = Math.max(startOrder, endOrder)
        var selected = []
        var items = root.elements || []
        for (var i = 0; i < items.length; ++i) {
            var text = String(items[i].text || "").trim()
            if (text.length === 0)
                continue
            var order = Number(items[i].order || 0)
            if (order >= first && order <= last)
                selected.push(items[i])
        }
        selected.sort(root.compareItems)
        var parts = []
        for (var j = 0; j < selected.length; ++j)
            parts.push(String(selected[j].text || "").trim())
        return {
            text: root.cleanText(parts.join(" ")),
            ids: root.idsForItems(selected)
        }
    }

    function selectionForRect(x, y, w, h) {
        var items = root.elements || []
        var selected = []
        for (var i = 0; i < items.length; ++i) {
            var rect = root.itemRect(items[i])
            if (root.rectsIntersect(x, y, w, h, rect.x, rect.y, rect.w, rect.h)
                    && String(items[i].text || "").trim().length > 0)
                selected.push(items[i])
        }
        selected.sort(root.compareItems)
        var parts = []
        for (var j = 0; j < selected.length; ++j)
            parts.push(String(selected[j].text || "").trim())
        return {
            text: root.cleanText(parts.join(" ")),
            ids: root.idsForItems(selected)
        }
    }

    function compareItems(left, right) {
        var orderDelta = Number(left.order || 0) - Number(right.order || 0)
        if (orderDelta !== 0)
            return orderDelta
        var lb = left.bbox || [0, 0, 0, 0]
        var rb = right.bbox || [0, 0, 0, 0]
        var dy = Number(lb[1] || 0) - Number(rb[1] || 0)
        if (Math.abs(dy) > 8)
            return dy
        return Number(lb[0] || 0) - Number(rb[0] || 0)
    }

    function idsForItems(items) {
        var ids = {}
        for (var i = 0; i < items.length; ++i)
            ids[String(items[i].id || "")] = true
        return ids
    }

    function rectsIntersect(ax, ay, aw, ah, bx, by, bw, bh) {
        return ax < bx + bw && ax + aw > bx && ay < by + bh && ay + ah > by
    }

    function cleanText(text) {
        return String(text || "")
            .replace(/(\w)-\s+(\w)/g, "$1$2")
            .replace(/\s+([,.;:!?%)\]\}])/g, "$1")
            .replace(/([([{%])\s+/g, "$1")
            .replace(/\s+/g, " ")
            .trim()
    }
}
