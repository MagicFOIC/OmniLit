import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: root
    property int pageIndex: 0
    property int drawerPage: 0
    readonly property bool sidebarExpanded: preferencesController.sidebarExpanded
    property int sidebarWidth: sidebarExpanded ? metrics.sidebarExpandedWidth : metrics.sidebarCollapsedWidth
    Motion { id: motion }
    I18n { id: i18n }
    Theme { id: theme }
    LayoutMetrics { id: metrics; viewportWidth: root.width; viewportHeight: root.height }

    WorkspaceBackground { anchors.fill: parent }

    RowLayout {
        anchors.fill: parent
        spacing: 0

        Rectangle {
            Layout.preferredWidth: root.sidebarWidth
            Layout.fillHeight: true
            color: theme.surfaceSoft
            border.color: theme.border
            z: 2
            Behavior on Layout.preferredWidth { NumberAnimation { duration: motion.expand; easing.type: Easing.OutCubic } }

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: metrics.sidebarMargin
                spacing: 10

                Image {
                    Layout.alignment: Qt.AlignHCenter
                    source: appController.logoUrl
                    Layout.preferredWidth: 42
                    Layout.preferredHeight: 42
                    fillMode: Image.PreserveAspectFit
                }

                Item { Layout.preferredHeight: 4 }

                Repeater {
                    model: [
                        { label: "nav_download", icon: "download" },
                        { label: "nav_translate", icon: "translate" }
                    ]
                    Button {
                        id: navigationButton
                        property bool selected: root.pageIndex === index
                        Layout.alignment: Qt.AlignHCenter
                        Layout.preferredWidth: root.sidebarExpanded ? root.sidebarWidth - metrics.sidebarMargin * 2 : 52
                        Layout.preferredHeight: 52
                        hoverEnabled: true
                        onClicked: root.pageIndex = index
                        HoverHandler { cursorShape: Qt.PointingHandCursor }
                        background: Rectangle {
                            radius: 15
                            color: navigationButton.selected ? theme.navSelected
                                                             : navigationButton.down ? theme.navPressed
                                                             : navigationButton.hovered || navigationButton.activeFocus ? theme.navHover
                                                             : "transparent"
                            Behavior on color { ColorAnimation { duration: motion.normal; easing.type: Easing.OutCubic } }
                        }
                        contentItem: Row {
                            anchors.centerIn: parent
                            spacing: 12
                            VectorIcon {
                                anchors.verticalCenter: parent.verticalCenter
                                width: 24
                                height: 24
                                name: modelData.icon
                                color: navigationButton.selected || navigationButton.hovered ? theme.accent : theme.textMuted
                            }
                            Text {
                                anchors.verticalCenter: parent.verticalCenter
                                visible: root.sidebarExpanded
                                text: i18n.text(modelData.label)
                                color: navigationButton.selected || navigationButton.hovered ? theme.accent : theme.textMuted
                                font.pixelSize: 14
                                font.weight: navigationButton.selected ? Font.DemiBold : Font.Medium
                            }
                        }
                        ModernToolTip {
                            anchors.left: parent.right
                            anchors.leftMargin: 10
                            anchors.verticalCenter: parent.verticalCenter
                            shown: !root.sidebarExpanded && navigationButton.hovered
                            text: i18n.text(modelData.label)
                        }
                    }
                }

                Item { Layout.fillHeight: true }

                Button {
                    id: sidebarModeButton
                    Layout.alignment: Qt.AlignHCenter
                    Layout.preferredWidth: root.sidebarExpanded ? root.sidebarWidth - metrics.sidebarMargin * 2 : 52
                    Layout.preferredHeight: 44
                    hoverEnabled: true
                    onClicked: preferencesController.toggleSidebarExpanded()
                    HoverHandler { cursorShape: Qt.PointingHandCursor }
                    background: Rectangle {
                        radius: 13
                        color: sidebarModeButton.hovered ? theme.navHover : "transparent"
                    }
                    contentItem: Row {
                        anchors.centerIn: parent
                        spacing: 12
                        VectorIcon {
                            anchors.verticalCenter: parent.verticalCenter
                            width: 21
                            height: 21
                            name: root.sidebarExpanded ? "sidebar-collapse" : "sidebar-expand"
                            color: sidebarModeButton.hovered ? theme.accent : theme.textMuted
                        }
                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            visible: root.sidebarExpanded
                            text: i18n.text("sidebar_collapse")
                            color: sidebarModeButton.hovered ? theme.accent : theme.textMuted
                            font.pixelSize: 13
                        }
                    }
                    ModernToolTip {
                        anchors.left: parent.right
                        anchors.leftMargin: 10
                        anchors.verticalCenter: parent.verticalCenter
                        shown: !root.sidebarExpanded && sidebarModeButton.hovered
                        text: i18n.text("sidebar_expand")
                    }
                }

                Button {
                    id: avatarButton
                    Layout.alignment: Qt.AlignHCenter
                    Layout.preferredWidth: 52
                    Layout.preferredHeight: 52
                    hoverEnabled: true
                    onClicked: accountDrawer.open()
                    HoverHandler { cursorShape: Qt.PointingHandCursor }
                    background: Rectangle {
                        radius: 18
                        color: avatarButton.hovered ? theme.navHover : "transparent"
                    }
                    contentItem: Item {
                        RoundedAvatar {
                            id: sidebarAvatar
                            anchors.centerIn: parent
                            width: 42
                            height: 42
                            source: preferencesController.avatarUrl
                            fallbackText: preferencesController.avatarInitial
                            backgroundColor: theme.accent
                            borderColor: theme.borderStrong
                        }
                        Rectangle {
                            visible: !!preferencesController.avatarStatus
                            anchors.left: sidebarAvatar.right
                            anchors.leftMargin: -8
                            anchors.bottom: sidebarAvatar.bottom
                            width: 23
                            height: 23
                            radius: 12
                            color: theme.surface
                            border.color: theme.borderStrong
                            Text {
                                anchors.centerIn: parent
                                text: preferencesController.avatarStatus
                                font.pixelSize: 13
                            }
                        }
                        Rectangle {
                            visible: updateController.available
                            anchors.right: parent.right
                            anchors.top: parent.top
                            anchors.rightMargin: 2
                            anchors.topMargin: 2
                            width: 10
                            height: 10
                            radius: 5
                            color: theme.error
                            border.color: theme.surfaceSoft
                        }
                    }
                }
            }
        }

        StackLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            currentIndex: root.pageIndex
            DownloadPage {}
            TranslationPage {}
        }
    }

    Popup {
        id: accountDrawer
        parent: Overlay.overlay
        x: root.sidebarWidth
        y: 0
        width: Math.min(root.drawerPage === 1 ? 920 : 380, root.width - root.sidebarWidth)
        height: root.height
        modal: true
        focus: true
        padding: 0
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        onClosed: root.drawerPage = 0
        enter: Transition {
            NumberAnimation { property: "x"; from: root.sidebarWidth - accountDrawer.width; to: root.sidebarWidth; duration: motion.expand; easing.type: Easing.OutCubic }
        }
        exit: Transition {
            NumberAnimation { property: "x"; from: root.sidebarWidth; to: root.sidebarWidth - accountDrawer.width; duration: motion.normal; easing.type: Easing.InCubic }
        }
        Overlay.modal: Rectangle { color: theme.drawerScrim }
        background: Rectangle {
            color: theme.surface
            border.color: theme.border
        }
        Behavior on width { NumberAnimation { duration: motion.expand; easing.type: Easing.OutCubic } }

        contentItem: StackLayout {
            currentIndex: root.drawerPage

            ScrollView {
                contentWidth: availableWidth
                ColumnLayout {
                    width: accountDrawer.availableWidth
                    spacing: 12

                    Item { Layout.preferredHeight: 12 }
                    RoundedAvatar {
                        Layout.alignment: Qt.AlignHCenter
                        Layout.preferredWidth: 82
                        Layout.preferredHeight: 82
                        source: preferencesController.avatarUrl
                        fallbackText: preferencesController.avatarInitial
                        fallbackFontSize: 28
                        backgroundColor: theme.accent
                        borderColor: theme.borderStrong
                    }
                    RowLayout {
                        Layout.alignment: Qt.AlignHCenter
                        spacing: 8
                        Text {
                            text: authController.username
                            color: theme.text
                            font.pixelSize: 18
                            font.weight: Font.Bold
                        }
                        Text {
                            visible: !!preferencesController.avatarStatus
                            text: preferencesController.avatarStatus
                            font.pixelSize: 18
                        }
                    }
                    Text {
                        Layout.fillWidth: true
                        Layout.leftMargin: 18
                        Layout.rightMargin: 18
                        text: appController.statusText
                        color: theme.textMuted
                        horizontalAlignment: Text.AlignHCenter
                        wrapMode: Text.WordWrap
                        font.pixelSize: 12
                    }
                    RowLayout {
                        Layout.alignment: Qt.AlignHCenter
                        PillButton { text: i18n.text("upload_avatar"); onClicked: preferencesController.uploadAvatar() }
                        PillButton { text: i18n.text("clear_avatar"); enabled: !!preferencesController.avatarUrl; onClicked: preferencesController.clearAvatar() }
                    }
                    Text { Layout.leftMargin: 20; text: i18n.text("avatar_status"); color: theme.textMuted; font.pixelSize: 12 }
                    Flow {
                        Layout.fillWidth: true
                        Layout.leftMargin: 18
                        Layout.rightMargin: 18
                        spacing: 7
                        Repeater {
                            model: ["🟢", "☕", "📚", "🎯", "🌙", "🚫"]
                            PillButton {
                                text: modelData
                                primary: preferencesController.avatarStatus === modelData
                                onClicked: preferencesController.setAvatarStatus(modelData)
                            }
                        }
                        PillButton { text: i18n.text("clear_status"); enabled: !!preferencesController.avatarStatus; onClicked: preferencesController.setAvatarStatus("") }
                    }

                    Rectangle { Layout.fillWidth: true; Layout.leftMargin: 16; Layout.rightMargin: 16; implicitHeight: 1; color: theme.border }

                    AppearanceChoiceRow {
                        Layout.fillWidth: true
                        Layout.leftMargin: 18
                        Layout.rightMargin: 18
                        label: i18n.text("interface_language")
                        selectedValue: localeController.language
                        choices: [
                            { value: "zh", label: "language_zh" },
                            { value: "en", label: "language_en" }
                        ]
                        onSelected: value => localeController.setLanguage(value)
                    }

                    Button {
                        id: appearanceEntry
                        Layout.fillWidth: true
                        Layout.leftMargin: 14
                        Layout.rightMargin: 14
                        implicitHeight: 54
                        hoverEnabled: true
                        onClicked: root.drawerPage = 1
                        HoverHandler { cursorShape: Qt.PointingHandCursor }
                        background: Rectangle { radius: 12; color: appearanceEntry.hovered ? theme.navHover : "transparent" }
                        contentItem: RowLayout {
                            spacing: 12
                            VectorIcon { name: "appearance"; color: theme.accent; Layout.preferredWidth: 22; Layout.preferredHeight: 22 }
                            Text { text: i18n.text("appearance"); color: theme.text; Layout.fillWidth: true }
                            Text { text: ">"; color: theme.textMuted }
                        }
                    }

                    Button {
                        id: updateEntry
                        Layout.fillWidth: true
                        Layout.leftMargin: 14
                        Layout.rightMargin: 14
                        implicitHeight: 54
                        hoverEnabled: true
                        onClicked: root.drawerPage = 2
                        HoverHandler { cursorShape: Qt.PointingHandCursor }
                        background: Rectangle { radius: 12; color: updateEntry.hovered ? theme.navHover : "transparent" }
                        contentItem: RowLayout {
                            spacing: 12
                            VectorIcon { name: "update"; color: theme.accent; Layout.preferredWidth: 22; Layout.preferredHeight: 22 }
                            Text { text: i18n.text("update_management"); color: theme.text; Layout.fillWidth: true }
                            Rectangle { visible: updateController.available; width: 8; height: 8; radius: 4; color: theme.error }
                            Text { text: ">"; color: theme.textMuted }
                        }
                    }

                    Item { Layout.preferredHeight: 2 }
                    Text {
                        Layout.alignment: Qt.AlignHCenter
                        text: "OmniLit v" + appController.version
                        color: theme.textMuted
                        font.pixelSize: 12
                    }
                    Item { Layout.fillHeight: true; Layout.minimumHeight: 12 }

                    Button {
                        id: logoutButton
                        Layout.alignment: Qt.AlignHCenter
                        Layout.preferredWidth: 56
                        Layout.preferredHeight: 56
                        hoverEnabled: true
                        onClicked: authController.logout()
                        HoverHandler { cursorShape: Qt.PointingHandCursor }
                        background: Rectangle {
                            radius: 28
                            color: logoutButton.hovered ? theme.errorSoft : theme.accentSofter
                            border.color: logoutButton.hovered ? theme.errorBorder : theme.border
                        }
                        contentItem: VectorIcon {
                            name: "power"
                            color: logoutButton.hovered ? theme.error : theme.accent
                            strokeWidth: 2.05
                            Behavior on color { ColorAnimation { duration: motion.fast } }
                        }
                        ModernToolTip {
                            anchors.left: parent.right
                            anchors.leftMargin: 10
                            anchors.verticalCenter: parent.verticalCenter
                            shown: logoutButton.hovered
                            text: i18n.text("logout")
                        }
                    }
                    Item { Layout.preferredHeight: 14 }
                }
            }

            ScrollView {
                contentWidth: availableWidth
                ColumnLayout {
                    width: accountDrawer.availableWidth
                    spacing: 12

                    RowLayout {
                        Layout.fillWidth: true
                        Layout.margins: 12
                        Button {
                            id: appearanceBackButton
                            implicitWidth: 42
                            implicitHeight: 42
                            onClicked: root.drawerPage = 0
                            HoverHandler { cursorShape: Qt.PointingHandCursor }
                            background: Rectangle { radius: theme.radiusMedium; color: appearanceBackButton.hovered ? theme.navHover : "transparent" }
                            contentItem: VectorIcon { name: "back"; color: theme.text; }
                        }
                        ColumnLayout {
                            spacing: 1
                            Text { text: i18n.text("appearance"); color: theme.text; font.pixelSize: theme.baseFontSize + 6; font.weight: Font.Bold }
                            Text { text: i18n.text("academic_appearance_desc"); color: theme.textMuted; font.pixelSize: theme.baseFontSize - 2 }
                        }
                    }

                    GridLayout {
                        Layout.fillWidth: true
                        Layout.leftMargin: 12
                        Layout.rightMargin: 12
                        columns: accountDrawer.availableWidth >= 720 ? 2 : 1
                        columnSpacing: 12
                        rowSpacing: 12

                        Card {
                            Layout.fillWidth: true
                            Layout.alignment: Qt.AlignTop
                            implicitHeight: appearanceSettings.implicitHeight + 28
                            ColumnLayout {
                                id: appearanceSettings
                                anchors.fill: parent
                                anchors.margins: 14
                                spacing: 12

                                Text { text: i18n.text("academic_theme_presets"); color: theme.text; font.pixelSize: theme.baseFontSize + 2; font.weight: Font.Bold }
                                Flow {
                                    Layout.fillWidth: true
                                    spacing: 7
                                    Repeater {
                                        model: preferencesController.themePresets
                                        PillButton {
                                            text: i18n.text(modelData.label)
                                            primary: preferencesController.themePreset === modelData.value
                                            onClicked: preferencesController.setThemePreset(modelData.value)
                                        }
                                    }
                                }

                                AppearanceChoiceRow {
                                    Layout.fillWidth: true
                                    label: i18n.text("theme_mode")
                                    selectedValue: preferencesController.themeMode
                                    choices: [
                                        { value: "light", label: "theme_light" },
                                        { value: "dark", label: "theme_dark" },
                                        { value: "system", label: "theme_system" },
                                        { value: "auto_night", label: "theme_auto_night" }
                                    ]
                                    onSelected: value => preferencesController.setThemeMode(value)
                                }
                                Text {
                                    visible: preferencesController.themeMode === "auto_night"
                                    text: i18n.text("local_timezone") + ": " + preferencesController.localTimezoneName + "  ·  " + preferencesController.autoNightStart + "-" + preferencesController.autoNightEnd
                                    color: theme.textMuted
                                    font.pixelSize: theme.baseFontSize - 2
                                }

                                Text { text: i18n.text("accent_color"); color: theme.text; font.pixelSize: theme.baseFontSize + 2; font.weight: Font.Bold }
                                Flow {
                                    Layout.fillWidth: true
                                    spacing: 9
                                    Repeater {
                                        model: preferencesController.accentPresets
                                        Button {
                                            implicitWidth: 34
                                            implicitHeight: 34
                                            onClicked: preferencesController.setAccentName(modelData.value)
                                            HoverHandler { cursorShape: Qt.PointingHandCursor }
                                            background: Rectangle {
                                                radius: 17
                                                color: modelData.color
                                                border.width: preferencesController.accentName === modelData.value ? 3 : 1
                                                border.color: preferencesController.accentName === modelData.value ? theme.text : theme.border
                                            }
                                            ModernToolTip {
                                                anchors.top: parent.bottom
                                                anchors.topMargin: 7
                                                shown: parent.hovered
                                                text: i18n.text(modelData.label)
                                            }
                                        }
                                    }
                                }
                                RowLayout {
                                    Layout.fillWidth: true
                                    TextField {
                                        id: customAccent
                                        Layout.fillWidth: true
                                        text: preferencesController.customAccentColor
                                        placeholderText: "#2563eb"
                                        onAccepted: preferencesController.setCustomAccentColor(text)
                                    }
                                    PillButton { text: i18n.text("apply"); onClicked: preferencesController.setCustomAccentColor(customAccent.text) }
                                    PillButton { text: i18n.text("extract_background_accent"); enabled: !!preferencesController.workspaceBackgroundUrl; onClicked: preferencesController.extractAccentFromBackground() }
                                }

                                Text { text: i18n.text("reading_comfort"); color: theme.text; font.pixelSize: theme.baseFontSize + 2; font.weight: Font.Bold }
                                AppearanceChoiceRow {
                                    Layout.fillWidth: true
                                    label: i18n.text("font_size")
                                    selectedValue: preferencesController.fontSize
                                    choices: [
                                        { value: "small", label: "size_small" }, { value: "standard", label: "size_standard" },
                                        { value: "large", label: "size_large" }, { value: "xlarge", label: "size_xlarge" }
                                    ]
                                    onSelected: value => preferencesController.setFontSize(value)
                                }
                                AppearanceChoiceRow {
                                    Layout.fillWidth: true
                                    label: i18n.text("interface_density")
                                    selectedValue: preferencesController.density
                                    choices: [
                                        { value: "compact", label: "density_compact" }, { value: "standard", label: "density_standard" },
                                        { value: "relaxed", label: "density_relaxed" }
                                    ]
                                    onSelected: value => preferencesController.setDensity(value)
                                }
                                AppearanceChoiceRow {
                                    Layout.fillWidth: true
                                    label: i18n.text("corner_radius")
                                    selectedValue: preferencesController.radius
                                    choices: [
                                        { value: "square", label: "radius_square" }, { value: "subtle", label: "radius_subtle" },
                                        { value: "modern", label: "radius_modern" }
                                    ]
                                    onSelected: value => preferencesController.setRadius(value)
                                }
                                AppearanceChoiceRow {
                                    Layout.fillWidth: true
                                    label: i18n.text("pdf_reading_background")
                                    selectedValue: preferencesController.pdfBackground
                                    choices: [
                                        { value: "white", label: "background_white" }, { value: "sepia", label: "background_sepia" },
                                        { value: "gray", label: "background_gray" }, { value: "dark", label: "background_dark" }
                                    ]
                                    onSelected: value => preferencesController.setPdfBackground(value)
                                }
                                AppearanceChoiceRow {
                                    Layout.fillWidth: true
                                    label: i18n.text("translation_line_height")
                                    selectedValue: preferencesController.translationLineHeight
                                    choices: [
                                        { value: "compact", label: "density_compact" }, { value: "standard", label: "density_standard" },
                                        { value: "comfortable", label: "line_height_comfortable" }
                                    ]
                                    onSelected: value => preferencesController.setTranslationLineHeight(value)
                                }

                                Text { text: i18n.text("workspace_background"); color: theme.text; font.pixelSize: theme.baseFontSize + 2; font.weight: Font.Bold }
                                AppearanceChoiceRow {
                                    Layout.fillWidth: true
                                    selectedValue: preferencesController.backgroundMode
                                    choices: [
                                        { value: "none", label: "background_none" }, { value: "solid", label: "background_solid" },
                                        { value: "gradient", label: "background_gradient" }, { value: "paper", label: "background_paper" },
                                        { value: "grid", label: "background_grid" }, { value: "image", label: "background_image" }
                                    ]
                                    onSelected: value => preferencesController.setBackgroundMode(value)
                                }
                                Rectangle {
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: 86
                                    radius: theme.radiusMedium
                                    clip: true
                                    color: theme.surfaceSoft
                                    border.color: theme.border
                                    WorkspaceBackground { anchors.fill: parent }
                                    Text {
                                        anchors.centerIn: parent
                                        visible: preferencesController.backgroundMode === "image" && !preferencesController.workspaceBackgroundUrl
                                        text: i18n.text("no_background")
                                        color: theme.textMuted
                                    }
                                }
                                RowLayout {
                                    PillButton { text: i18n.text("upload_background"); onClicked: preferencesController.uploadWorkspaceBackground() }
                                    PillButton { text: i18n.text("clear_background"); enabled: !!preferencesController.workspaceBackgroundUrl; onClicked: preferencesController.clearWorkspaceBackground() }
                                }
                                Text { text: i18n.text("background_opacity") + ": " + Math.round(preferencesController.backgroundOpacity * 100) + "%"; color: theme.textMuted; font.pixelSize: theme.baseFontSize - 2 }
                                Slider { Layout.fillWidth: true; from: 0; to: 1; stepSize: 0.05; value: preferencesController.backgroundOpacity; onMoved: preferencesController.setBackgroundOpacity(value) }
                                Text { text: i18n.text("background_blur") + ": " + preferencesController.backgroundBlur; color: theme.textMuted; font.pixelSize: theme.baseFontSize - 2 }
                                Slider { Layout.fillWidth: true; from: 0; to: 32; stepSize: 2; value: preferencesController.backgroundBlur; onMoved: preferencesController.setBackgroundBlur(value) }

                                Text { text: i18n.text("advanced_appearance"); color: theme.text; font.pixelSize: theme.baseFontSize + 2; font.weight: Font.Bold }
                                RowLayout {
                                    CheckBox { text: i18n.text("high_contrast"); checked: preferencesController.highContrast; onToggled: preferencesController.setHighContrast(checked) }
                                    CheckBox { text: i18n.text("reduce_motion"); checked: preferencesController.reduceMotion; onToggled: preferencesController.setReduceMotion(checked) }
                                }
                                RowLayout {
                                    visible: preferencesController.themeMode === "auto_night"
                                    Text { text: i18n.text("night_start"); color: theme.textMuted }
                                    TextField { implicitWidth: 76; text: preferencesController.autoNightStart; onEditingFinished: preferencesController.setAutoNightStart(text) }
                                    Text { text: i18n.text("night_end"); color: theme.textMuted }
                                    TextField { implicitWidth: 76; text: preferencesController.autoNightEnd; onEditingFinished: preferencesController.setAutoNightEnd(text) }
                                }
                                PillButton { text: i18n.text("reset_appearance"); onClicked: preferencesController.resetAppearance() }
                            }
                        }

                        AppearancePreview {
                            Layout.fillWidth: true
                            Layout.alignment: Qt.AlignTop
                        }
                    }
                    Item { Layout.preferredHeight: 8 }
                }
            }

            ColumnLayout {
                spacing: 0
                RowLayout {
                    Layout.fillWidth: true
                    Layout.margins: 12
                    Button {
                        id: updateBackButton
                        implicitWidth: 42
                        implicitHeight: 42
                        onClicked: root.drawerPage = 0
                        HoverHandler { cursorShape: Qt.PointingHandCursor }
                        background: Rectangle { radius: theme.radiusMedium; color: updateBackButton.hovered ? theme.navHover : "transparent" }
                        contentItem: VectorIcon { name: "back"; color: theme.text }
                    }
                    Text { text: i18n.text("update_management"); color: theme.text; font.pixelSize: 20; font.weight: Font.Bold }
                }
                UpdatePage { Layout.fillWidth: true; Layout.fillHeight: true }
            }
        }
    }
}
