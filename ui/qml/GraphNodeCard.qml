import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: root

    property var node: ({})
    readonly property bool hasSelection: Object.keys(root.node || {}).length > 0
    readonly property bool isEdge: root.node.source !== undefined && root.node.target !== undefined
    readonly property var evidenceItems: (root.node.relation_evidence || []).length > 0 ? root.node.relation_evidence : (root.node.evidence || [])

    signal evidenceRequested(int index)

    spacing: 10

    Theme { id: theme }

    Text {
        Layout.fillWidth: true
        text: root.hasSelection ? (root.node.label || root.node.type || "Untitled") : "Select a node or relation"
        color: theme.text
        font.bold: true
        font.pixelSize: 18
        wrapMode: Text.Wrap
    }

    Flow {
        Layout.fillWidth: true
        Layout.preferredHeight: childrenRect.height
        spacing: 6
        visible: root.hasSelection

        Label {
            text: String(root.node.type || "Node")
            color: theme.accent
            background: Rectangle { color: theme.accentSofter; radius: 8; border.color: theme.border }
            padding: 5
        }
        Label {
            text: root.node.confidence === undefined ? "Confidence -" : "Confidence " + Math.round(Number(root.node.confidence) * 100) + "%"
            color: root.node.needs_review || Number(root.node.confidence) < 0.6 ? theme.error : theme.textMuted
            background: Rectangle { color: root.node.needs_review ? theme.errorSoft : theme.surfaceSoft; radius: 8; border.color: theme.border }
            padding: 5
        }
        Label {
            visible: !!root.node.needs_review
            text: "Needs review"
            color: theme.error
            background: Rectangle { color: theme.errorSoft; radius: 8; border.color: theme.errorBorder }
            padding: 5
        }
        Label {
            visible: root.evidenceItems.length > 0
            text: root.evidenceItems.length + " evidence"
            color: theme.textMuted
            background: Rectangle { color: theme.surfaceSoft; radius: 8; border.color: theme.border }
            padding: 5
        }
    }

    Text {
        Layout.fillWidth: true
        visible: root.hasSelection
        text: root.node.summary || "No summary"
        color: theme.text
        wrapMode: Text.WrapAnywhere
        lineHeight: 1.25
    }

    Rectangle { Layout.fillWidth: true; height: 1; color: theme.divider; visible: root.hasSelection }

    GridLayout {
        Layout.fillWidth: true
        visible: root.hasSelection
        columns: 2
        columnSpacing: 8
        rowSpacing: 6

        Text { text: "Normalized"; color: theme.textMuted; font.pixelSize: 11 }
        Text { Layout.fillWidth: true; text: root.node.normalized_label || "-"; color: theme.text; wrapMode: Text.WrapAnywhere }
        Text { text: "Canonical ID"; color: theme.textMuted; font.pixelSize: 11 }
        Text { Layout.fillWidth: true; text: root.node.canonical_id || "-"; color: theme.text; wrapMode: Text.WrapAnywhere; font.family: "monospace"; font.pixelSize: 11 }
        Text { text: "Extraction"; color: theme.textMuted; font.pixelSize: 11 }
        Text { Layout.fillWidth: true; text: root.node.extraction_method || "-"; color: theme.text; wrapMode: Text.WrapAnywhere }
        Text { text: "Section"; color: theme.textMuted; font.pixelSize: 11 }
        Text { Layout.fillWidth: true; text: root.node.source_section || "-"; color: theme.text; wrapMode: Text.WrapAnywhere }
        Text { visible: root.isEdge; text: "Relation"; color: theme.textMuted; font.pixelSize: 11 }
        Text { visible: root.isEdge; Layout.fillWidth: true; text: root.node.relation_method || "-"; color: theme.text; wrapMode: Text.WrapAnywhere }
    }

    Rectangle {
        Layout.fillWidth: true
        visible: root.isEdge && !!root.node.direction_reason
        implicitHeight: directionText.implicitHeight + 18
        radius: 8
        color: theme.surfaceSoft
        border.color: theme.border

        Text {
            id: directionText
            anchors.fill: parent
            anchors.margins: 9
            text: "Direction: " + (root.node.direction_reason || "")
            color: theme.textMuted
            wrapMode: Text.WrapAnywhere
        }
    }

    Text {
        visible: (root.node.confidence_reason || []).length > 0
        text: "Confidence reasons"
        color: theme.text
        font.bold: true
    }
    Flow {
        Layout.fillWidth: true
        Layout.preferredHeight: childrenRect.height
        spacing: 5
        visible: (root.node.confidence_reason || []).length > 0

        Repeater {
            model: root.node.confidence_reason || []
            delegate: Label {
                required property var modelData
                text: String(modelData).replace(/_/g, " ")
                color: theme.textMuted
                background: Rectangle { color: theme.surfaceSoft; radius: 7; border.color: theme.border }
                padding: 4
                font.pixelSize: 10
            }
        }
    }

    Text {
        visible: (root.node.review_reasons || []).length > 0
        text: "Review reasons"
        color: theme.text
        font.bold: true
    }
    Flow {
        Layout.fillWidth: true
        Layout.preferredHeight: childrenRect.height
        spacing: 5
        visible: (root.node.review_reasons || []).length > 0

        Repeater {
            model: root.node.review_reasons || []
            delegate: Label {
                required property var modelData
                text: String(modelData).replace(/_/g, " ")
                color: theme.warning
                background: Rectangle { color: theme.warningSoft; radius: 7; border.color: theme.warning }
                padding: 4
                font.pixelSize: 10
            }
        }
    }

    Text {
        text: "Evidence " + root.evidenceItems.length
        visible: root.evidenceItems.length > 0
        color: theme.text
        font.bold: true
    }
    Repeater {
        model: root.evidenceItems
        delegate: Rectangle {
            required property var modelData
            required property int index

            Layout.fillWidth: true
            Layout.preferredHeight: evidenceColumn.implicitHeight + 18
            radius: 8
            color: theme.surfaceSoft
            border.color: theme.border

            ColumnLayout {
                id: evidenceColumn
                anchors.fill: parent
                anchors.margins: 9
                spacing: 5

                RowLayout {
                    Layout.fillWidth: true
                    Text {
                        Layout.fillWidth: true
                        text: modelData.page >= 0 ? "Page " + (Number(modelData.page) + 1) : (modelData.source || "Metadata")
                        color: theme.accent
                        font.bold: true
                    }
                    PillButton {
                        text: "Locate"
                        enabled: modelData.page >= 0 || !!modelData.element_id
                        onClicked: root.evidenceRequested(index)
                    }
                }
                Text {
                    Layout.fillWidth: true
                    text: modelData.excerpt || modelData.source || ""
                    color: theme.textMuted
                    wrapMode: Text.WrapAnywhere
                    maximumLineCount: 6
                    elide: Text.ElideRight
                }
                Text {
                    Layout.fillWidth: true
                    visible: !!modelData.section || !!modelData.extraction_method || !!modelData.source
                    text: [modelData.section || "", modelData.extraction_method || "", modelData.source || ""].filter(function(item) { return !!item }).join(" / ")
                    color: theme.textMuted
                    font.pixelSize: 10
                    elide: Text.ElideRight
                }
            }
        }
    }

    Item { Layout.fillHeight: true; Layout.minimumHeight: 4 }
}
