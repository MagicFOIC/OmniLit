import QtQuick
import QtQuick.Layouts

ColumnLayout {
    id: root
    property string title: ""
    property string subtitle: ""
    property string eyebrow: i18n.text("workspace_eyebrow")
    property int titleSize: 25
    spacing: 3
    Theme { id: theme }
    I18n { id: i18n }

    Text {
        text: root.eyebrow
        color: theme.accent
        font.pixelSize: 10
        font.weight: Font.Bold
        font.letterSpacing: 1.1
    }
    RowLayout {
        spacing: 9
        Rectangle {
            Layout.preferredWidth: 5
            Layout.preferredHeight: root.titleSize - 2
            radius: 3
            color: theme.accent
        }
        Text {
            text: root.title
            color: theme.text
            font.pixelSize: root.titleSize
            font.weight: Font.Bold
        }
    }
    Text {
        visible: !!root.subtitle
        text: root.subtitle
        color: theme.textMuted
        font.pixelSize: 13
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
    }
}
