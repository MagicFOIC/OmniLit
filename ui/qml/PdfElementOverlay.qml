import QtQuick
import QtQuick.Controls

Item {
    id: root
    property var pageSize: [1, 1]
    property size renderedSize: Qt.size(width, height)
    property var elements: []
    signal elementClicked(string elementId)

    Repeater {
        model: root.elements || []
        delegate: Rectangle {
            id: box
            property var bbox: modelData.bbox || [0, 0, 0, 0]
            property real sx: root.renderedSize.width / Math.max(1, Number(root.pageSize[0] || 1))
            property real sy: root.renderedSize.height / Math.max(1, Number(root.pageSize[1] || 1))
            x: Number(bbox[0] || 0) * sx
            y: Number(bbox[1] || 0) * sy
            width: Math.max(8, (Number(bbox[2] || 0) - Number(bbox[0] || 0)) * sx)
            height: Math.max(8, (Number(bbox[3] || 0) - Number(bbox[1] || 0)) * sy)
            radius: 3
            color: hover.containsMouse ? "#332563eb" : "#142563eb"
            border.color: modelData.type === "table" ? "#2563eb" : modelData.type === "figure" ? "#16a34a" : "#dc2626"
            border.width: hover.containsMouse ? 2 : 1

            MouseArea {
                id: hover
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: root.elementClicked(String(modelData.id || ""))
            }

            ModernToolTip {
                anchors.left: parent.right
                anchors.leftMargin: 8
                anchors.top: parent.top
                shown: hover.containsMouse
                text: root.tooltipText(modelData)
            }
        }
    }

    function tooltipText(element) {
        var kind = element.type === "table" ? "表格" : element.type === "figure" ? "图" : "公式"
        var caption = element.caption || element.text || ""
        var bbox = element.bbox || []
        var summary = kind + "  Page " + (Number(element.page || 0) + 1)
        if(caption)
            summary += "\n" + caption
        if(bbox.length >= 4)
            summary += "\nbbox: " + bbox.map(v => Math.round(Number(v))).join(", ")
        var meta = element.metadata || ({})
        if(element.type === "table" && (meta.rows || meta.columns))
            summary += "\n" + "rows: " + Number(meta.rows || 0) + ", columns: " + Number(meta.columns || 0)
        if((element.type === "figure" || element.type === "formula") && (meta.imageWidth || meta.imageHeight))
            summary += "\n" + "image: " + Number(meta.imageWidth || 0) + " × " + Number(meta.imageHeight || 0) + " px"
        return summary
    }
}
