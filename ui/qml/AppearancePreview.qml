import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Card {
    id: root
    Theme { id: theme }
    I18n { id: i18n }
    Layout.fillWidth: true
    implicitHeight: previewColumn.implicitHeight + 28

    ColumnLayout {
        id: previewColumn
        anchors.fill: parent
        anchors.margins: 14
        spacing: 10

        Text {
            text: i18n.text("appearance_preview")
            color: theme.text
            font.pixelSize: theme.baseFontSize + 3
            font.weight: Font.Bold
        }
        Text {
            text: i18n.text("appearance_preview_desc")
            color: theme.textMuted
            font.pixelSize: theme.baseFontSize - 2
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }

        Rectangle {
            Layout.fillWidth: true
            implicitHeight: paperColumn.implicitHeight + 20
            radius: theme.radiusLarge
            color: theme.surface
            border.color: theme.border

            Rectangle {
                width: 4
                anchors.left: parent.left
                anchors.top: parent.top
                anchors.bottom: parent.bottom
                color: theme.accent
                radius: 2
            }

            ColumnLayout {
                id: paperColumn
                anchors.fill: parent
                anchors.margins: 10
                anchors.leftMargin: 15
                spacing: 5
                Text {
                    Layout.fillWidth: true
                    text: "Attention Is All You Need"
                    color: theme.text
                    font.pixelSize: theme.baseFontSize + 1
                    font.weight: Font.Bold
                    wrapMode: Text.WordWrap
                }
                Text {
                    text: "Vaswani et al.  ·  NeurIPS 2017"
                    color: theme.textMuted
                    font.pixelSize: theme.baseFontSize - 2
                }
                Flow {
                    Layout.fillWidth: true
                    spacing: 6
                    Repeater {
                        model: ["DOI 10.5555/3295222.3295349", "arXiv 1706.03762", i18n.text("pdf_downloaded")]
                        Rectangle {
                            implicitWidth: chipText.implicitWidth + 14
                            implicitHeight: chipText.implicitHeight + 7
                            radius: implicitHeight / 2
                            color: theme.accentSofter
                            border.color: theme.border
                            Text {
                                id: chipText
                                anchors.centerIn: parent
                                text: modelData
                                color: theme.textMuted
                                font.pixelSize: theme.baseFontSize - 3
                            }
                        }
                    }
                }
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            spacing: 5
            RowLayout {
                Layout.fillWidth: true
                Text { text: i18n.text("pdf_download_progress"); color: theme.textMuted; font.pixelSize: theme.baseFontSize - 2 }
                Item { Layout.fillWidth: true }
                Text { text: "72%"; color: theme.accent; font.pixelSize: theme.baseFontSize - 2; font.weight: Font.Bold }
            }
            SoftProgressBar { Layout.fillWidth: true; value: 0.72 }
        }

        Rectangle {
            Layout.fillWidth: true
            implicitHeight: translationRow.implicitHeight + 18
            radius: theme.radiusMedium
            color: theme.pdfBackground
            border.color: theme.border
            RowLayout {
                id: translationRow
                anchors.fill: parent
                anchors.margins: 9
                spacing: 10
                Text {
                    Layout.fillWidth: true
                    text: "The dominant sequence transduction models are based on complex recurrent neural networks."
                    color: theme.dark && preferencesController.pdfBackground === "dark" ? theme.text : "#334155"
                    wrapMode: Text.WordWrap
                    font.pixelSize: theme.baseFontSize - 2
                    lineHeightMode: Text.ProportionalHeight
                    lineHeight: theme.translationLineHeight
                }
                Rectangle { Layout.preferredWidth: 1; Layout.fillHeight: true; color: theme.border }
                Text {
                    Layout.fillWidth: true
                    text: "主流的序列转换模型基于复杂的循环神经网络。"
                    color: theme.dark && preferencesController.pdfBackground === "dark" ? theme.text : "#334155"
                    wrapMode: Text.WordWrap
                    font.pixelSize: theme.baseFontSize - 2
                    lineHeightMode: Text.ProportionalHeight
                    lineHeight: theme.translationLineHeight
                }
            }
        }

        TextField {
            Layout.fillWidth: true
            placeholderText: i18n.text("search_papers")
        }
        RowLayout {
            spacing: 8
            PillButton { text: i18n.text("start_download"); primary: true }
            PillButton { text: i18n.text("open") }
            PillButton { text: i18n.text("stop"); enabled: false }
        }
    }
}
