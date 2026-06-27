import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: root

    property var nodes: []
    property var edges: []

    Theme { id: theme }

    width: Math.min(460, Math.max(300, content.implicitWidth + 22))
    height: content.implicitHeight + 16
    radius: 8
    color: theme.surfaceElevated
    border.color: theme.border
    opacity: 0.94

    RowLayout {
        id: content
        anchors.fill: parent
        anchors.margins: 8
        spacing: 10

        Repeater {
            model: [
                { label: "Paper", color: root.typeColor("paper") },
                { label: "Method", color: root.typeColor("method") },
                { label: "Data", color: root.typeColor("dataset") },
                { label: "Result", color: root.typeColor("result") },
                { label: "Review", color: theme.warning }
            ]
            RowLayout {
                required property var modelData
                spacing: 4
                Rectangle {
                    Layout.preferredWidth: 9
                    Layout.preferredHeight: 9
                    radius: 5
                    color: modelData.color
                    border.color: theme.borderStrong
                }
                Text {
                    text: modelData.label
                    color: theme.textMuted
                    font.pixelSize: 10
                }
            }
        }

        Rectangle { Layout.preferredWidth: 1; Layout.preferredHeight: 18; color: theme.divider }

        Text { text: root.nodes.length + " nodes"; color: theme.textMuted; font.pixelSize: 10 }
        Text { text: root.edges.length + " edges"; color: theme.textMuted; font.pixelSize: 10 }
        Text { text: root.reviewCount() + " review"; color: root.reviewCount() > 0 ? theme.warning : theme.textMuted; font.pixelSize: 10 }
        Text { text: root.evidenceCount() + " evidence"; color: theme.textMuted; font.pixelSize: 10 }
    }

    function reviewCount() {
        var total = 0
        for (var i = 0; i < root.nodes.length; ++i) {
            if (root.nodes[i].needs_review || Number(root.nodes[i].confidence) < 0.6)
                total += 1
        }
        for (var j = 0; j < root.edges.length; ++j) {
            if (root.edges[j].needs_review || Number(root.edges[j].confidence) < 0.6)
                total += 1
        }
        return total
    }

    function evidenceCount() {
        var total = 0
        for (var i = 0; i < root.nodes.length; ++i)
            total += (root.nodes[i].evidence || []).length
        for (var j = 0; j < root.edges.length; ++j)
            total += ((root.edges[j].relation_evidence || root.edges[j].evidence || [])).length
        return total
    }

    function typeColor(type) {
        type = String(type || "").toLowerCase()
        if (type === "paper")
            return theme.mix(theme.accent, theme.surface, theme.dark ? 0.58 : 0.36)
        if (type === "method" || type === "algorithm" || type === "model")
            return theme.mix(theme.accent, theme.surface, theme.dark ? 0.72 : 0.44)
        if (type === "dataset" || type === "metric" || type === "experiment")
            return theme.mix(theme.warning, theme.surface, theme.dark ? 0.76 : 0.44)
        if (type === "result" || type === "claim")
            return theme.mix(theme.success, theme.surface, theme.dark ? 0.76 : 0.46)
        return theme.mix(theme.textMuted, theme.surface, theme.dark ? 0.42 : 0.22)
    }
}
