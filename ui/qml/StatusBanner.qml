import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: root
    property string text: ""
    property bool busy: false
    property string tone: "neutral"
    Theme { id: theme }
    implicitHeight: row.implicitHeight + 14
    radius: 8
    color: tone === "error" ? theme.errorSoft : tone === "success" ? theme.successSoft : theme.accentSofter
    border.color: tone === "error" ? theme.errorBorder : tone === "success" ? theme.successBorder : theme.border
    visible: !!text
    opacity: visible ? 1 : 0

    Behavior on opacity { NumberAnimation { duration: 120 } }
    Behavior on color { ColorAnimation { duration: 120 } }

    RowLayout {
        id: row
        anchors.fill: parent
        anchors.margins: 7
        spacing: 8
        BusyIndicator {
            Layout.preferredWidth: 18
            Layout.preferredHeight: 18
            running: root.busy
            visible: running
        }
        Text {
            Layout.fillWidth: true
            text: root.text
            color: root.tone === "error" ? theme.error : root.tone === "success" ? theme.success : theme.textMuted
            wrapMode: Text.WordWrap
            font.pixelSize: 13
        }
    }
}
