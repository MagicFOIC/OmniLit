import QtQuick
import QtQuick.Layouts

ColumnLayout {
    id: root
    property string label: ""
    property var choices: []
    property string selectedValue: ""
    signal selected(string value)
    Theme { id: theme }
    I18n { id: i18n }
    spacing: 6

    Text {
        text: root.label
        color: theme.textMuted
        font.pixelSize: theme.baseFontSize - 2
    }
    Flow {
        Layout.fillWidth: true
        spacing: 7
        Repeater {
            model: root.choices
            PillButton {
                text: i18n.text(modelData.label)
                primary: root.selectedValue === modelData.value
                onClicked: root.selected(modelData.value)
            }
        }
    }
}
