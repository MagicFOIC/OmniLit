import QtQuick

Item {
    id: root
    property Item target
    property int duration: 180
    visible: false

    function play() {
        if (!target || !target.visible)
            return
        fade.restart()
        slide.restart()
    }

    Component.onCompleted: play()

    Connections {
        target: root.target
        function onVisibleChanged() { root.play() }
    }

    NumberAnimation {
        id: fade
        target: root.target
        property: "opacity"
        from: 0
        to: 1
        duration: root.duration
        easing.type: Easing.OutCubic
    }
    NumberAnimation {
        id: slide
        target: root.target
        property: "x"
        from: 8
        to: 0
        duration: root.duration
        easing.type: Easing.OutCubic
    }
}
