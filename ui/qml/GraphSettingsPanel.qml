import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: root

    property bool showArrows: false
    property bool showLabels: false
    property bool dimUnrelated: true
    property real textFadeThreshold: 1.15
    property real nodeSizeScale: 1.0
    property real linkThickness: 1.0
    property bool animateLayout: false

    signal resetRequested()

    Theme { id: theme }
    I18n { id: i18n }

    width: 240
    radius: 10
    color: theme.surfaceElevated
    border.color: theme.border

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 12
        spacing: 10

        RowLayout {
            Layout.fillWidth: true
            Text {
                Layout.fillWidth: true
                text: i18n.text("graph_settings")
                color: theme.text
                font.bold: true
            }
            ToolButton {
                text: i18n.text("graph_reset")
                onClicked: root.resetRequested()
            }
        }

        Rectangle { Layout.fillWidth: true; height: 1; color: theme.border }

        Text { text: i18n.text("graph_display"); color: theme.text; font.bold: true }

        RowLayout {
            Layout.fillWidth: true
            Text { Layout.fillWidth: true; text: i18n.text("graph_arrows"); color: theme.textMuted }
            Switch { checked: root.showArrows; onToggled: root.showArrows = checked }
        }

        RowLayout {
            Layout.fillWidth: true
            Text { Layout.fillWidth: true; text: i18n.text("graph_labels"); color: theme.textMuted }
            Switch { checked: root.showLabels; onToggled: root.showLabels = checked }
        }

        RowLayout {
            Layout.fillWidth: true
            Text { Layout.fillWidth: true; text: i18n.text("graph_dim_unrelated"); color: theme.textMuted }
            Switch { checked: root.dimUnrelated; onToggled: root.dimUnrelated = checked }
        }

        Text { text: i18n.text("graph_text_fade_threshold"); color: theme.textMuted }
        Slider {
            Layout.fillWidth: true
            from: 0.6
            to: 2.0
            value: root.textFadeThreshold
            onValueChanged: root.textFadeThreshold = value
        }

        Text { text: i18n.text("graph_node_size"); color: theme.textMuted }
        Slider {
            Layout.fillWidth: true
            from: 0.6
            to: 2.0
            value: root.nodeSizeScale
            onValueChanged: root.nodeSizeScale = value
        }

        Text { text: i18n.text("graph_link_thickness"); color: theme.textMuted }
        Slider {
            Layout.fillWidth: true
            from: 0.4
            to: 3.0
            value: root.linkThickness
            onValueChanged: root.linkThickness = value
        }

        Rectangle { Layout.fillWidth: true; height: 1; color: theme.border }

        Text { text: i18n.text("graph_layout"); color: theme.text; font.bold: true }

        RowLayout {
            Layout.fillWidth: true
            Text { Layout.fillWidth: true; text: i18n.text("graph_animate"); color: theme.textMuted }
            Switch { checked: root.animateLayout; onToggled: root.animateLayout = checked }
        }

        Item { Layout.fillHeight: true }
    }
}
