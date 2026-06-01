import QtQuick

QtObject {
    property Theme theme: Theme {}
    readonly property int fast: theme.reduceMotion ? 0 : 120
    readonly property int normal: theme.reduceMotion ? 0 : 180
    readonly property int expand: theme.reduceMotion ? 0 : 220
}
