import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: root
    property var elements: []
    property string selectedElementId: ""
    signal elementSelected(string elementId)

    color: theme.surface
    border.color: theme.border
    radius: theme.radiusMedium

    Theme { id: theme }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 10
        spacing: 8

        Text {
            Layout.fillWidth: true
            text: "元素书签"
            color: theme.text
            font.weight: Font.Bold
        }

        ListView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            model: root.elements || []
            spacing: 5
            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

            delegate: Button {
                id: itemButton
                property bool selected: String(modelData.id || "") === root.selectedElementId
                width: ListView.view.width
                height: 42
                hoverEnabled: true
                onClicked: root.elementSelected(String(modelData.id || ""))
                background: Rectangle {
                    radius: 7
                    color: itemButton.selected ? theme.navSelected : itemButton.hovered ? theme.navHover : "transparent"
                    border.color: itemButton.selected ? theme.accent : itemButton.hovered ? theme.borderStrong : "transparent"
                }
                contentItem: RowLayout {
                    spacing: 8
                    Text {
                        text: modelData.type === "table" ? "表" : modelData.type === "figure" ? "图" : "式"
                        color: modelData.type === "table" ? theme.accent : modelData.type === "figure" ? theme.success : theme.error
                        font.weight: Font.Bold
                    }
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 1
                        Text {
                            Layout.fillWidth: true
                            text: (modelData.label || modelData.id || "Element") + " · p." + (Number(modelData.page || 0) + 1)
                            color: itemButton.selected ? theme.accentStrong : theme.text
                            elide: Text.ElideRight
                            font.pixelSize: 12
                            font.weight: itemButton.selected ? Font.DemiBold : Font.Normal
                        }
                        Text {
                            Layout.fillWidth: true
                            text: modelData.caption || modelData.text || ""
                            color: theme.textMuted
                            elide: Text.ElideRight
                            font.pixelSize: 10
                        }
                    }
                }
            }
        }

        Text {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: !root.elements || root.elements.length === 0
            text: "暂无图、表或公式"
            color: theme.textMuted
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            wrapMode: Text.WordWrap
        }
    }
}
