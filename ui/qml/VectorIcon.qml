import QtQuick
import QtQuick.Shapes

Item {
    id: root
    property string name: ""
    property color color: "#2563eb"
    property real strokeWidth: 1.9

    implicitWidth: 24
    implicitHeight: 24

    Shape {
        width: 24
        height: 24
        anchors.centerIn: parent
        scale: Math.min(root.width / 24, root.height / 24)

        ShapePath {
            strokeColor: root.color
            strokeWidth: root.strokeWidth
            fillColor: "transparent"
            capStyle: ShapePath.RoundCap
            joinStyle: ShapePath.RoundJoin
            PathSvg { path: root.pathData(root.name) }
        }
    }

    function pathData(iconName) {
        if (iconName === "download") return "M12 3 L12 14 M7.5 10 L12 14.5 L16.5 10 M5 17 L5 20 L19 20 L19 17"
        if (iconName === "library") return "M5 4 L15 4 L19 8 L19 20 L5 20 Z M15 4 L15 8 L19 8 M8 12 L16 12 M8 16 L16 16"
        if (iconName === "translate") return "M4 5 L14 5 M9 3 L9 5 M6 8 C7 11 9 13 12 15 M12 8 C11 11 8 14 5 16 M14.5 20 L18 11 L21.5 20 M15.8 17 L20.2 17"
        if (iconName === "back") return "M15 5 L8 12 L15 19"
        if (iconName === "power") return "M12 3.2 L12 11.2 M7.5 5.8 C5 7.3 3.8 10.1 4.5 13 C5.2 16 7.9 18.2 11 18.6 C14.3 19 17.5 17.2 18.8 14.2 C20.2 10.9 19 7.5 16.5 5.8"
        if (iconName === "appearance") return "M12 3 C7 3 3 7 3 12 C3 17 7 21 12 21 C14 21 15 19 13 18 C12 17 13 15 15 15 L17 15 C19 15 21 13 21 11 C21 7 17 3 12 3 M7 11 L7 11 M9 7 L9 7 M13 6 L13 6 M17 9 L17 9"
        if (iconName === "language") return "M12 3 A9 9 0 1 0 12 21 A9 9 0 1 0 12 3 M3 12 L21 12 M12 3 C15 7 15 17 12 21 M12 3 C9 7 9 17 12 21"
        if (iconName === "update") return "M19 8 L19 4 M19 8 L15 8 M19 8 A8 8 0 1 0 20 13"
        if (iconName === "sidebar-expand") return "M5 4 L19 4 L19 20 L5 20 Z M10 4 L10 20 M13 9 L16 12 L13 15"
        if (iconName === "sidebar-collapse") return "M5 4 L19 4 L19 20 L5 20 Z M10 4 L10 20 M16 9 L13 12 L16 15"
        if (iconName === "calendar") return "M5 4 L19 4 L19 20 L5 20 Z M8 2 L8 6 M16 2 L16 6 M5 9 L19 9"
        if (iconName === "chevron-left") return "M15 5 L8 12 L15 19"
        if (iconName === "chevron-right") return "M9 5 L16 12 L9 19"
        if (iconName === "image") return "M4 5 L20 5 L20 19 L4 19 Z M7 15 L10.5 11.5 L13 14 L15 12 L20 17 M8 9 L8.1 9"
        if (iconName === "status") return "M12 4 A8 8 0 1 0 12 20 A8 8 0 1 0 12 4 M8 12 L11 15 L16 9"
        if (iconName === "user") return "M12 12 A4 4 0 1 0 12 4 A4 4 0 1 0 12 12 M4.5 21 C5.2 16.8 7.7 15 12 15 C16.3 15 18.8 16.8 19.5 21"
        if (iconName === "lock") return "M6 10 L18 10 L18 21 L6 21 Z M8.5 10 L8.5 7.5 C8.5 3 15.5 3 15.5 7.5 L15.5 10 M12 14 L12 17"
        return ""
    }
}
