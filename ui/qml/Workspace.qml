import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: root
    property int pageIndex: 0
    property int drawerPage: 0
    property string draftAvatarStatus: ""
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
            color: theme.sidebarSurface
            border.color: theme.sidebarBorder
            z: 2
            Behavior on Layout.preferredWidth { NumberAnimation { duration: motion.expand; easing.type: Easing.OutCubic } }

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: metrics.sidebarMargin
                spacing: 10

                Rectangle {
                    Layout.alignment: Qt.AlignHCenter
                    Layout.preferredWidth: root.sidebarExpanded ? root.sidebarWidth - metrics.sidebarMargin * 2 : 52
                    Layout.preferredHeight: 58
                    radius: 16
                    color: theme.surfaceElevated
                    border.color: theme.border
                    RowLayout {
                        anchors.fill: parent
                        anchors.margins: 9
                        spacing: 9
                        Image {
                            source: appController.logoUrl
                            Layout.preferredWidth: 34
                            Layout.preferredHeight: 34
                            fillMode: Image.PreserveAspectFit
                        }
                        ColumnLayout {
                            visible: root.sidebarExpanded
                            spacing: 0
                            Text { text: "OmniLit"; color: theme.text; font.pixelSize: 16; font.weight: Font.Bold }
                            Text { text: "RESEARCH DESK"; color: theme.accent; font.pixelSize: 8; font.weight: Font.Bold; font.letterSpacing: 0.7 }
                        }
                    }
                }

                Text {
                    visible: root.sidebarExpanded
                    Layout.leftMargin: 8
                    text: "WORKSPACE"
                    color: theme.textMuted
                    font.pixelSize: 9
                    font.weight: Font.Bold
                    font.letterSpacing: 1.0
                }

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
                            Rectangle {
                                visible: navigationButton.selected
                                anchors.left: parent.left
                                anchors.verticalCenter: parent.verticalCenter
                                width: 3
                                height: 22
                                radius: 2
                                color: theme.accent
                            }
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
                            shown: navigationButton.hovered
                            text: root.navigationTooltip(index, modelData.label)
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
                    Layout.preferredWidth: root.sidebarExpanded ? root.sidebarWidth - metrics.sidebarMargin * 2 : 52
                    Layout.preferredHeight: root.sidebarExpanded ? 62 : 52
                    hoverEnabled: true
                    onClicked: accountDrawer.open()
                    HoverHandler { cursorShape: Qt.PointingHandCursor }
                    background: Rectangle {
                        radius: 17
                        color: avatarButton.hovered ? theme.navHover : theme.surfaceElevated
                        border.color: avatarButton.hovered ? theme.borderStrong : theme.border
                    }
                    contentItem: RowLayout {
                        spacing: 9
                        RoundedAvatar {
                            id: sidebarAvatar
                            Layout.preferredWidth: 42
                            Layout.preferredHeight: 42
                            source: preferencesController.avatarUrl
                            fallbackText: preferencesController.avatarInitial
                            backgroundColor: theme.accent
                            borderColor: theme.borderStrong
                        }
                        AvatarStatusBadge {
                            status: preferencesController.avatarStatus
                            compact: true
                            Layout.leftMargin: -18
                            Layout.topMargin: 26
                        }
                        ColumnLayout {
                            visible: root.sidebarExpanded
                            Layout.fillWidth: true
                            spacing: 1
                            Text { text: authController.username; color: theme.text; font.pixelSize: 12; font.weight: Font.DemiBold; elide: Text.ElideRight; Layout.fillWidth: true }
                            Text { text: preferencesController.avatarStatus || i18n.text("set_status"); color: theme.textMuted; font.pixelSize: 10; elide: Text.ElideRight; Layout.fillWidth: true }
                        }
                        Rectangle {
                            visible: updateController.available
                            Layout.alignment: Qt.AlignTop | Qt.AlignRight
                            Layout.preferredWidth: 10
                            Layout.preferredHeight: 10
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

                    Item { Layout.preferredHeight: 6 }
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.leftMargin: 14
                        Layout.rightMargin: 14
                        implicitHeight: 154
                        radius: theme.radiusLarge
                        color: theme.surfaceTint
                        border.color: theme.border
                        ColumnLayout {
                            anchors.fill: parent
                            anchors.margins: 14
                            spacing: 4
                            Button {
                                id: drawerAvatarButton
                                Layout.alignment: Qt.AlignHCenter
                                Layout.preferredWidth: 76
                                Layout.preferredHeight: 76
                                hoverEnabled: true
                                onClicked: root.drawerPage = 3
                                HoverHandler { cursorShape: Qt.PointingHandCursor }
                                background: Rectangle { radius: 38; color: drawerAvatarButton.hovered ? theme.accentSoft : "transparent" }
                                contentItem: Item {
                                    RoundedAvatar {
                                        anchors.centerIn: parent
                                        width: 68
                                        height: 68
                                        source: preferencesController.avatarUrl
                                        fallbackText: preferencesController.avatarInitial
                                        fallbackFontSize: 24
                                        backgroundColor: theme.accent
                                        borderColor: theme.borderStrong
                                    }
                                    AvatarStatusBadge {
                                        anchors.right: parent.right
                                        anchors.bottom: parent.bottom
                                        status: preferencesController.avatarStatus
                                        compact: true
                                    }
                                }
                            }
                            Text {
                                Layout.alignment: Qt.AlignHCenter
                                text: authController.username
                                color: theme.text
                                font.pixelSize: 18
                                font.weight: Font.Bold
                            }
                            Text {
                                Layout.alignment: Qt.AlignHCenter
                                text: i18n.text("account_center")
                                color: theme.textMuted
                                font.pixelSize: 11
                            }
                        }
                    }
                    RowLayout {
                        Layout.alignment: Qt.AlignHCenter
                        spacing: 8
                        PillButton {
                            text: preferencesController.avatarStatus || i18n.text("set_status")
                            onClicked: {
                                root.draftAvatarStatus = preferencesController.avatarStatus
                                root.drawerPage = 4
                            }
                        }
                    }
                    Text {
                        Layout.fillWidth: true
                        Layout.leftMargin: 18
                        Layout.rightMargin: 18
                        text: i18n.text("account_preferences")
                        color: theme.textMuted
                        horizontalAlignment: Text.AlignHCenter
                        wrapMode: Text.WordWrap
                        font.pixelSize: 11
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
                    Rectangle { Layout.fillWidth: true; Layout.leftMargin: 16; Layout.rightMargin: 16; implicitHeight: 1; color: theme.border }

                    DrawerMenuItem {
                        id: languageEntry
                        Layout.fillWidth: true
                        Layout.leftMargin: 14
                        Layout.rightMargin: 14
                        iconName: "language"
                        label: i18n.text("interface_language")
                        detail: i18n.text("language_detail")
                        onClicked: root.drawerPage = 5
                    }

                    DrawerMenuItem {
                        id: appearanceEntry
                        Layout.fillWidth: true
                        Layout.leftMargin: 14
                        Layout.rightMargin: 14
                        iconName: "appearance"
                        label: i18n.text("appearance")
                        detail: i18n.text("appearance_detail")
                        onClicked: root.drawerPage = 1
                    }

                    DrawerMenuItem {
                        id: updateEntry
                        Layout.fillWidth: true
                        Layout.leftMargin: 14
                        Layout.rightMargin: 14
                        iconName: "update"
                        label: i18n.text("update_management")
                        detail: i18n.text("update_detail")
                        attention: updateController.available
                        onClicked: root.drawerPage = 2
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
                        Layout.preferredWidth: accountDrawer.availableWidth - 28
                        Layout.preferredHeight: 48
                        hoverEnabled: true
                        onClicked: authController.logout()
                        HoverHandler { cursorShape: Qt.PointingHandCursor }
                        background: Rectangle {
                            radius: theme.radiusLarge
                            color: logoutButton.hovered ? theme.errorSoft : theme.accentSofter
                            border.color: logoutButton.hovered ? theme.errorBorder : theme.border
                        }
                        contentItem: RowLayout {
                            spacing: 8
                            Item { Layout.fillWidth: true }
                            VectorIcon {
                                name: "power"
                                color: logoutButton.hovered ? theme.error : theme.accent
                                strokeWidth: 2.05
                                Layout.preferredWidth: 20
                                Layout.preferredHeight: 20
                                Behavior on color { ColorAnimation { duration: motion.fast } }
                            }
                            Text { text: i18n.text("logout"); color: logoutButton.hovered ? theme.error : theme.accent; font.weight: Font.DemiBold }
                            Item { Layout.fillWidth: true }
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

                    DrawerPageHeader {
                        title: i18n.text("appearance")
                        detail: i18n.text("academic_appearance_desc")
                        onBack: root.drawerPage = 0
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
                DrawerPageHeader {
                    title: i18n.text("update_management")
                    detail: i18n.text("update_page_detail")
                    onBack: root.drawerPage = 0
                }
                UpdatePage { Layout.fillWidth: true; Layout.fillHeight: true }
            }

            ColumnLayout {
                spacing: 14
                DrawerPageHeader {
                    title: i18n.text("avatar_settings")
                    detail: i18n.text("avatar_settings_detail")
                    onBack: root.drawerPage = 0
                }
                Card {
                    Layout.fillWidth: true
                    Layout.leftMargin: 14
                    Layout.rightMargin: 14
                    implicitHeight: avatarSettingsContent.implicitHeight + 32
                    ColumnLayout {
                        id: avatarSettingsContent
                        anchors.fill: parent
                        anchors.margins: 16
                        spacing: 12
                        RoundedAvatar {
                            Layout.alignment: Qt.AlignHCenter
                            Layout.preferredWidth: 112
                            Layout.preferredHeight: 112
                            source: preferencesController.avatarUrl
                            fallbackText: preferencesController.avatarInitial
                            fallbackFontSize: 36
                            backgroundColor: theme.accent
                            borderColor: theme.borderStrong
                        }
                        AvatarStatusBadge {
                            Layout.alignment: Qt.AlignHCenter
                            status: preferencesController.avatarStatus
                        }
                        RowLayout {
                            Layout.alignment: Qt.AlignHCenter
                            PillButton { text: i18n.text("upload_avatar"); primary: true; onClicked: preferencesController.uploadAvatar() }
                            PillButton { text: i18n.text("clear_avatar"); enabled: !!preferencesController.avatarUrl; onClicked: preferencesController.clearAvatar() }
                        }
                    }
                }
                Item { Layout.fillHeight: true }
            }

            ScrollView {
                contentWidth: availableWidth
                ColumnLayout {
                    width: accountDrawer.availableWidth
                    spacing: 12
                    DrawerPageHeader {
                        title: i18n.text("avatar_status")
                        detail: i18n.text("avatar_status_detail")
                        onBack: root.drawerPage = 0
                    }
                    Card {
                        Layout.fillWidth: true
                        Layout.leftMargin: 14
                        Layout.rightMargin: 14
                        implicitHeight: statusEditor.implicitHeight + 28
                        ColumnLayout {
                            id: statusEditor
                            anchors.fill: parent
                            anchors.margins: 14
                            spacing: 9
                            AvatarStatusBadge { status: root.draftAvatarStatus || preferencesController.avatarStatus }
                            TextField {
                                Layout.fillWidth: true
                                text: root.draftAvatarStatus
                                placeholderText: i18n.text("status_placeholder")
                                onTextChanged: root.draftAvatarStatus = text
                            }
                            RowLayout {
                                Item { Layout.fillWidth: true }
                                PillButton { text: i18n.text("save"); primary: true; onClicked: root.applyAvatarStatus(root.draftAvatarStatus) }
                                PillButton { text: i18n.text("clear_status"); enabled: !!preferencesController.avatarStatus; onClicked: root.applyAvatarStatus("") }
                            }
                        }
                    }
                    Text { Layout.leftMargin: 18; text: i18n.text("status_quick"); color: theme.textMuted; font.pixelSize: 12 }
                    Flow {
                        Layout.fillWidth: true
                        Layout.leftMargin: 18
                        Layout.rightMargin: 18
                        spacing: 7
                        Repeater {
                            model: ["status_online", "status_focused", "status_writing", "status_away"]
                            PillButton {
                                text: i18n.text(modelData)
                                primary: preferencesController.avatarStatus === text
                                onClicked: root.applyAvatarStatus(text)
                            }
                        }
                    }
                    Text { Layout.leftMargin: 18; text: i18n.text("status_more_emoji"); color: theme.textMuted; font.pixelSize: 12 }
                    Flow {
                        Layout.fillWidth: true
                        Layout.leftMargin: 18
                        Layout.rightMargin: 18
                        spacing: 7
                        Repeater {
                            model: ["🟢", "☕", "📚", "🎯", "🌙", "🚫", "✍️", "🔬", "💡", "📖", "🧠", "🚀", "⏳", "🏠", "🎓", "💻", "📝", "🧪", "📊", "🔕"]
                            PillButton {
                                text: modelData
                                primary: preferencesController.avatarStatus === text
                                onClicked: root.applyAvatarStatus(text)
                            }
                        }
                    }
                    Item { Layout.preferredHeight: 8 }
                }
            }

            ColumnLayout {
                spacing: 12
                DrawerPageHeader {
                    title: i18n.text("interface_language")
                    detail: i18n.text("language_page_detail")
                    onBack: root.drawerPage = 0
                }
                Card {
                    Layout.fillWidth: true
                    Layout.leftMargin: 14
                    Layout.rightMargin: 14
                    implicitHeight: languageChoices.implicitHeight + 28
                    AppearanceChoiceRow {
                        id: languageChoices
                        anchors.fill: parent
                        anchors.margins: 14
                        label: i18n.text("interface_language")
                        selectedValue: localeController.language
                        choices: [
                            { value: "zh", label: "language_zh" },
                            { value: "en", label: "language_en" }
                        ]
                        onSelected: value => localeController.setLanguage(value)
                    }
                }
                Item { Layout.fillHeight: true }
            }
        }
    }

    function navigationTooltip(index, fallbackLabel) {
        if(index === 0 && downloadController.running && downloadController.activeTaskText.length > 0)
            return downloadController.activeTaskText
        if(index === 1 && translationController.running && translationController.activeTaskText.length > 0)
            return translationController.activeTaskText
        return i18n.text(fallbackLabel)
    }
    function applyAvatarStatus(status) {
        root.draftAvatarStatus = status
        preferencesController.setAvatarStatus(status)
    }
}
