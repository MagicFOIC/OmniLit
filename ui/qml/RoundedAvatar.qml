import QtQuick
import QtQuick.Effects

Item {
    id: root
    property url source
    property string fallbackText: "?"
    property color backgroundColor: "#2563eb"
    property color borderColor: "#c5d8eb"
    property int fallbackFontSize: 17

    Rectangle {
        anchors.fill: parent
        radius: width / 2
        antialiasing: true
        color: root.backgroundColor
        border.color: root.borderColor
    }

    Text {
        anchors.centerIn: parent
        visible: root.source.toString().length === 0
        text: root.fallbackText
        color: "#ffffff"
        font.pixelSize: root.fallbackFontSize
        font.weight: Font.Bold
    }

    Image {
        id: avatarSource
        anchors.fill: parent
        visible: false
        source: root.source
        fillMode: Image.PreserveAspectCrop
        asynchronous: true
        cache: false
        smooth: true
        mipmap: true
    }

    Rectangle {
        id: avatarMask
        anchors.fill: parent
        visible: false
        radius: width / 2
        antialiasing: true
        color: "#ffffff"
        layer.enabled: true
    }

    MultiEffect {
        anchors.fill: parent
        visible: root.source.toString().length > 0
        source: avatarSource
        maskEnabled: true
        maskSource: avatarMask
        maskThresholdMin: 0.5
        maskSpreadAtMin: 1.0
    }
}
