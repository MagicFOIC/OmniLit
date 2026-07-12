import QtQuick

QtObject {
    property real viewportWidth: 0
    property real viewportHeight: 0

    readonly property bool compact: viewportWidth < 1040 || viewportHeight < 760
    readonly property bool narrow: viewportWidth < 760
    property Theme theme: Theme {}
    readonly property int pageMargin: Math.round((compact ? 12 : 20) * theme.densityScale)
    readonly property int cardPadding: Math.round((compact ? 10 : 14) * theme.densityScale)
    readonly property int sectionSpacing: Math.round((compact ? 6 : 8) * theme.densityScale)
    readonly property int toolbarSpacing: Math.round((compact ? 6 : 8) * theme.densityScale)
    readonly property int headingSize: compact ? 22 : 25
    readonly property int sidebarCollapsedWidth: 72
    readonly property int sidebarExpandedWidth: 208
    readonly property int sidebarMargin: 10
}
