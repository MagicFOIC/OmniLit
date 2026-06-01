import QtQuick
import QtQuick.Layouts

ColumnLayout {
    id: root
    property string title: ""
    property string subtitle: ""
    property int titleSize: 25
    spacing: 4
    Theme { id: theme }

    RowLayout {
        spacing: 9
        Rectangle {
            Layout.preferredWidth: 4
            Layout.preferredHeight: root.titleSize - 3
            radius: 2
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
