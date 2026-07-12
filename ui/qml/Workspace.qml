import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: root
    property int pageIndex: 0
    property int drawerPage: 0
    property string draftAvatarStatus: ""
    property string systemSettingsWorkdirDraft: ""
    property string systemContactEmailDraft: ""
    property string systemSettingsMessage: ""
    property bool systemSettingsMessageIsError: false
    property string mineruApiUrlDraft: ""
    property string paddleocrApiUrlDraft: ""
    property string mineruTokenDraft: ""
    property string paddleocrTokenDraft: ""
    property var tourTargets: ({})
    property bool libraryPageRequested: true
    onDrawerPageChanged: {
        if(drawerPage === 6) {
            root.systemSettingsWorkdirDraft = onboardingController.workdir
            root.systemContactEmailDraft = downloadController.contactEmail
            root.mineruApiUrlDraft = pdfExtractionController.mineruApiUrl
            root.paddleocrApiUrlDraft = pdfExtractionController.paddleocrApiUrl
            root.mineruTokenDraft = ""
            root.paddleocrTokenDraft = ""
            root.systemSettingsMessage = ""
            root.systemSettingsMessageIsError = false
        }
    }
    readonly property bool sidebarExpanded: preferencesController.sidebarExpanded
    property int sidebarWidth: sidebarExpanded ? metrics.sidebarExpandedWidth : metrics.sidebarCollapsedWidth
    Motion { id: motion }
    I18n { id: i18n }
    Theme { id: theme }
    LayoutMetrics { id: metrics; viewportWidth: root.width; viewportHeight: root.height }

    onPageIndexChanged: {
        if(pageIndex === 1) {
            literatureLibraryController.preload()
            root.libraryPageRequested = true
        }
    }

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
                        { label: "nav_library", icon: "library" },
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
                        Component.onCompleted: root.registerTourTarget(root.tourTargetForNavLabel(modelData.label), navigationButton)
                        Component.onDestruction: root.unregisterTourTarget(root.tourTargetForNavLabel(modelData.label), navigationButton)
                        HoverHandler { cursorShape: Qt.PointingHandCursor }
                        background: Rectangle {
                            radius: 15
                            color: navigationButton.selected ? theme.navSelected : "transparent"
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
                        contentItem: Item {
                            Row {
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
                    contentItem: Item {
                        Row {
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
                    Component.onCompleted: root.registerTourTarget("account.avatar", avatarButton)
                    Component.onDestruction: root.unregisterTourTarget("account.avatar", avatarButton)
                    HoverHandler { cursorShape: Qt.PointingHandCursor }
                    background: Rectangle {
                        radius: 17
                        color: avatarButton.hovered ? theme.navHover : theme.surfaceElevated
                        border.color: avatarButton.hovered ? theme.borderStrong : theme.border
                    }
                    contentItem: RowLayout {
                        spacing: 9
                        Item {
                            Layout.preferredWidth: 42
                            Layout.preferredHeight: 42
                            RoundedAvatar {
                                id: sidebarAvatar
                                anchors.fill: parent
                                source: preferencesController.avatarUrl
                                fallbackText: preferencesController.avatarInitial
                                backgroundColor: theme.accent
                                borderColor: theme.borderStrong
                            }
                            AvatarStatusBadge {
                                anchors.right: parent.right
                                anchors.bottom: parent.bottom
                                status: preferencesController.avatarStatus
                                statusColor: preferencesController.avatarStatusColor
                                compact: true
                            }
                            Rectangle {
                                visible: updateController.available
                                anchors.right: parent.right
                                anchors.top: parent.top
                                anchors.rightMargin: -2
                                anchors.topMargin: -2
                                width: 10
                                height: 10
                                radius: 5
                                color: theme.error
                                border.color: theme.surfaceSoft
                            }
                        }
                        ColumnLayout {
                            visible: root.sidebarExpanded
                            Layout.fillWidth: true
                            spacing: 1
                            Text { text: authController.username; color: theme.text; font.pixelSize: 12; font.weight: Font.DemiBold; elide: Text.ElideRight; Layout.fillWidth: true }
                            Text { text: preferencesController.avatarStatusLabel; color: theme.textMuted; font.pixelSize: 10; elide: Text.ElideRight; Layout.fillWidth: true }
                        }
                    }
                }
            }
        }

        StackLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            currentIndex: root.pageIndex
            DownloadPage { tourHost: root }
            Item {
                Layout.fillWidth: true
                Layout.fillHeight: true

                Loader {
                    id: literatureLibraryPageLoader
                    anchors.fill: parent
                    active: root.libraryPageRequested
                    asynchronous: true
                    sourceComponent: literatureLibraryPageComponent
                }
            }
            TranslationPage { tourHost: root }
        }
    }

    Component {
        id: literatureLibraryPageComponent
        LiteratureLibraryPage { tourHost: root }
    }

    Popup {
        id: accountDrawer
        parent: Overlay.overlay
        x: root.sidebarWidth
        y: 0
        width: Math.min(root.drawerPage === 1 ? 920 : (root.drawerPage === 6 ? 560 : 380), root.width - root.sidebarWidth)
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
                ScrollBar.vertical: StyledScrollBar { policy: ScrollBar.AsNeeded }
                ScrollBar.horizontal: StyledScrollBar { policy: ScrollBar.AsNeeded }
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
                                        statusColor: preferencesController.avatarStatusColor
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
                    Rectangle { Layout.fillWidth: true; Layout.leftMargin: 16; Layout.rightMargin: 16; implicitHeight: 1; color: theme.border }

                    DrawerMenuItem {
                        id: avatarSettingsEntry
                        Layout.fillWidth: true
                        Layout.leftMargin: 14
                        Layout.rightMargin: 14
                        iconName: "user"
                        label: i18n.text("avatar_settings")
                        detail: preferencesController.avatarStatusLabel
                        onClicked: root.drawerPage = 3
                    }

                    DrawerMenuItem {
                        id: languageEntry
                        Layout.fillWidth: true
                        Layout.leftMargin: 14
                        Layout.rightMargin: 14
                        iconName: "language"
                        label: i18n.text("interface_language")
                        detail: i18n.text("language_detail")
                        Component.onCompleted: root.registerTourTarget("account.language", languageEntry)
                        Component.onDestruction: root.unregisterTourTarget("account.language", languageEntry)
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
                        Component.onCompleted: root.registerTourTarget("account.appearance", appearanceEntry)
                        Component.onDestruction: root.unregisterTourTarget("account.appearance", appearanceEntry)
                        onClicked: root.drawerPage = 1
                    }

                    DrawerMenuItem {
                        id: updateEntry
                        Layout.fillWidth: true
                        Layout.leftMargin: 14
                        Layout.rightMargin: 14
                        iconName: "update"
                        label: i18n.text("update_management")
                        detail: updateController.hasCheckStatus ? updateController.statusText : i18n.text("update_detail")
                        attention: updateController.available
                        Component.onCompleted: root.registerTourTarget("account.update", updateEntry)
                        Component.onDestruction: root.unregisterTourTarget("account.update", updateEntry)
                        onClicked: root.drawerPage = 2
                    }

                    DrawerMenuItem {
                        id: systemSettingsEntry
                        Layout.fillWidth: true
                        Layout.leftMargin: 14
                        Layout.rightMargin: 14
                        iconName: "settings"
                        label: i18n.text("system_settings")
                        detail: i18n.text("system_settings_detail")
                        onClicked: root.openSystemSettings()
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
                    }
                    Item { Layout.preferredHeight: 14 }
                }
            }

            ScrollView {
                ScrollBar.vertical: StyledScrollBar { policy: ScrollBar.AsNeeded }
                ScrollBar.horizontal: StyledScrollBar { policy: ScrollBar.AsNeeded }
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
                            id: appearancePanelCard
                            Layout.fillWidth: true
                            Layout.alignment: Qt.AlignTop
                            implicitHeight: appearanceSettings.implicitHeight + 28
                            Component.onCompleted: root.registerTourTarget("appearance.panel", appearancePanelCard)
                            Component.onDestruction: root.unregisterTourTarget("appearance.panel", appearancePanelCard)
                            ColumnLayout {
                                id: appearanceSettings
                                anchors.fill: parent
                                anchors.margins: 14
                                spacing: 12

                                Text { text: i18n.text("academic_theme_presets"); color: theme.text; font.pixelSize: theme.baseFontSize + 2; font.weight: Font.Bold }
                                Flow {
                                    Layout.fillWidth: true
                                    spacing: 8
                                    Repeater {
                                        model: preferencesController.themePresets
                                        Button {
                                            implicitWidth: 142
                                            implicitHeight: 52
                                            hoverEnabled: true
                                            onClicked: preferencesController.setThemePreset(modelData.value)
                                            HoverHandler { cursorShape: Qt.PointingHandCursor }
                                            background: Rectangle {
                                                radius: theme.radiusMedium
                                                color: preferencesController.themePreset === modelData.value ? theme.navSelected : parent.hovered ? theme.navHover : theme.surface
                                                border.width: preferencesController.themePreset === modelData.value ? 2 : 1
                                                border.color: preferencesController.themePreset === modelData.value ? theme.accent : theme.border
                                            }
                                            contentItem: RowLayout {
                                                spacing: 7
                                                Rectangle { Layout.preferredWidth: 18; Layout.preferredHeight: 28; radius: 6; color: modelData.preview; border.color: modelData.swatch }
                                                Text { Layout.fillWidth: true; text: i18n.text(modelData.label); color: theme.text; font.pixelSize: 11; wrapMode: Text.WordWrap }
                                            }
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
                                        { value: "adaptive", label: "theme_adaptive" }
                                    ]
                                    onSelected: value => preferencesController.setThemeMode(value)
                                }
                                Text {
                                    visible: preferencesController.themeMode === "adaptive"
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
                                                target: parent
                                                placement: "bottom"
                                                shown: parent.hovered
                                                text: i18n.text(modelData.label)
                                            }
                                        }
                                    }
                                }
                                RowLayout {
                                    Layout.fillWidth: true
                                    StyledTextField {
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
                                Flow {
                                    Layout.fillWidth: true
                                    spacing: 8
                                    Repeater {
                                        model: preferencesController.backgroundPresets
                                        Button {
                                            implicitWidth: 142
                                            implicitHeight: 44
                                            hoverEnabled: true
                                            onClicked: preferencesController.setBackgroundMode(modelData.value)
                                            HoverHandler { cursorShape: Qt.PointingHandCursor }
                                            background: Rectangle {
                                                radius: theme.radiusMedium
                                                color: preferencesController.backgroundMode === modelData.value ? theme.navSelected : parent.hovered ? theme.navHover : theme.surface
                                                border.width: preferencesController.backgroundMode === modelData.value ? 2 : 1
                                                border.color: preferencesController.backgroundMode === modelData.value ? theme.accent : theme.border
                                            }
                                            contentItem: RowLayout {
                                                spacing: 7
                                                Rectangle { Layout.preferredWidth: 22; Layout.preferredHeight: 22; radius: 7; color: modelData.swatch; border.color: theme.borderStrong }
                                                Text { Layout.fillWidth: true; text: i18n.text(modelData.label); color: theme.text; font.pixelSize: 11; wrapMode: Text.WordWrap }
                                            }
                                        }
                                    }
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
                                StyledSlider { Layout.fillWidth: true; from: 0; to: 1; stepSize: 0.05; value: preferencesController.backgroundOpacity; onMoved: preferencesController.setBackgroundOpacity(value) }
                                Text { text: i18n.text("background_blur") + ": " + preferencesController.backgroundBlur; color: theme.textMuted; font.pixelSize: theme.baseFontSize - 2 }
                                StyledSlider { Layout.fillWidth: true; from: 0; to: 32; stepSize: 2; value: preferencesController.backgroundBlur; onMoved: preferencesController.setBackgroundBlur(value) }

                                Text { text: i18n.text("advanced_appearance"); color: theme.text; font.pixelSize: theme.baseFontSize + 2; font.weight: Font.Bold }
                                RowLayout {
                                    ModernCheckBox { text: i18n.text("high_contrast"); checked: preferencesController.highContrast; onToggled: preferencesController.setHighContrast(checked) }
                                    ModernCheckBox { text: i18n.text("reduce_motion"); checked: preferencesController.reduceMotion; onToggled: preferencesController.setReduceMotion(checked) }
                                }
                                RowLayout {
                                    visible: preferencesController.themeMode === "adaptive"
                                    Text { text: i18n.text("night_start"); color: theme.textMuted }
                                    StyledTextField { implicitWidth: 76; text: preferencesController.autoNightStart; onEditingFinished: preferencesController.setAutoNightStart(text) }
                                    Text { text: i18n.text("night_end"); color: theme.textMuted }
                                    StyledTextField { implicitWidth: 76; text: preferencesController.autoNightEnd; onEditingFinished: preferencesController.setAutoNightEnd(text) }
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
                UpdatePage { Layout.fillWidth: true; Layout.fillHeight: true; tourHost: root }
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
                            status: preferencesController.avatarStatusLabel
                            statusColor: preferencesController.avatarStatusColor
                        }
                        DrawerMenuItem {
                            Layout.fillWidth: true
                            iconName: "status"
                            label: i18n.text("avatar_status")
                            detail: preferencesController.avatarStatusLabel
                            onClicked: root.drawerPage = 4
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
                ScrollBar.vertical: StyledScrollBar { policy: ScrollBar.AsNeeded }
                ScrollBar.horizontal: StyledScrollBar { policy: ScrollBar.AsNeeded }
                contentWidth: availableWidth
                ColumnLayout {
                    width: accountDrawer.availableWidth
                    spacing: 12
                    DrawerPageHeader {
                        title: i18n.text("avatar_status")
                        detail: i18n.text("avatar_status_detail")
                        onBack: root.drawerPage = 3
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
                            AvatarStatusBadge { status: preferencesController.avatarStatusLabel; statusColor: preferencesController.avatarStatusColor }
                            StyledTextField {
                                Layout.fillWidth: true
                                text: root.draftAvatarStatus
                                placeholderText: i18n.text("status_placeholder")
                                onTextChanged: root.draftAvatarStatus = text
                            }
                            RowLayout {
                                Item { Layout.fillWidth: true }
                                PillButton {
                                    text: i18n.text("add_status")
                                    primary: true
                                    enabled: !!root.draftAvatarStatus.trim()
                                    onClicked: {
                                        if (preferencesController.addCustomAvatarStatus(root.draftAvatarStatus))
                                            root.draftAvatarStatus = ""
                                    }
                                }
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
                            model: root.defaultStatuses()
                            Button {
                                implicitWidth: 150
                                implicitHeight: 40
                                hoverEnabled: true
                                onClicked: preferencesController.setAvatarStatusId(modelData.id)
                                HoverHandler { cursorShape: Qt.PointingHandCursor }
                                background: Rectangle {
                                    radius: theme.radiusMedium
                                    color: preferencesController.avatarStatusId === modelData.id ? theme.navSelected : parent.hovered ? theme.navHover : theme.surface
                                    border.color: preferencesController.avatarStatusId === modelData.id ? theme.accent : theme.border
                                }
                                contentItem: AvatarStatusBadge { status: modelData.label; statusColor: modelData.color }
                            }
                        }
                    }
                    Text { Layout.leftMargin: 18; text: i18n.text("custom_statuses"); color: theme.textMuted; font.pixelSize: 12 }
                    ColumnLayout {
                        Layout.fillWidth: true
                        Layout.leftMargin: 18
                        Layout.rightMargin: 18
                        spacing: 7
                        Repeater {
                            model: root.customStatuses()
                            RowLayout {
                                Layout.fillWidth: true
                                AvatarStatusBadge { status: modelData.label; statusColor: modelData.color }
                                StyledTextField {
                                    Layout.fillWidth: true
                                    text: modelData.label
                                    onEditingFinished: preferencesController.renameCustomAvatarStatus(modelData.id, text)
                                }
                                PillButton { text: i18n.text("apply"); onClicked: preferencesController.setAvatarStatusId(modelData.id) }
                                PillButton { text: i18n.text("delete_status"); onClicked: preferencesController.deleteCustomAvatarStatus(modelData.id) }
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
                            { value: "en", label: "language_en" },
                            { value: "ru", label: "language_ru" }
                        ]
                        onSelected: value => localeController.setLanguage(value)
                    }
                }
                Item { Layout.fillHeight: true }
            }

            ScrollView {
                ScrollBar.vertical: StyledScrollBar { policy: ScrollBar.AsNeeded }
                ScrollBar.horizontal: StyledScrollBar { policy: ScrollBar.AsNeeded }
                contentWidth: availableWidth
                ColumnLayout {
                    width: accountDrawer.availableWidth
                    spacing: 12

                    DrawerPageHeader {
                        title: i18n.text("system_settings")
                        detail: i18n.text("system_settings_detail")
                        onBack: root.drawerPage = 0
                    }

                    Card {
                        id: systemPromptSettingsCard
                        Layout.fillWidth: true
                        Layout.leftMargin: 14
                        Layout.rightMargin: 14
                        implicitHeight: systemPromptSettingsContent.implicitHeight + 32
                        Component.onCompleted: root.registerTourTarget("system.prompt_settings", systemPromptSettingsCard)
                        Component.onDestruction: root.unregisterTourTarget("system.prompt_settings", systemPromptSettingsCard)
                        ColumnLayout {
                            id: systemPromptSettingsContent
                            anchors.fill: parent
                            anchors.margins: 16
                            spacing: 12

                            Text {
                                Layout.fillWidth: true
                                text: i18n.text("login_prompt_settings")
                                color: theme.text
                                font.pixelSize: theme.baseFontSize + 3
                                font.weight: Font.Bold
                            }
                            Text {
                                Layout.fillWidth: true
                                text: i18n.text("login_prompt_settings_detail")
                                color: theme.textMuted
                                font.pixelSize: Math.max(11, theme.baseFontSize - 1)
                                wrapMode: Text.WordWrap
                            }

                            Text {
                                Layout.fillWidth: true
                                text: i18n.text("workspace_folder")
                                color: theme.text
                                font.pixelSize: theme.baseFontSize
                                font.weight: Font.DemiBold
                            }
                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 8
                                StyledTextField {
                                    id: systemWorkdirField
                                    Layout.fillWidth: true
                                    text: root.systemSettingsWorkdirDraft
                                    placeholderText: i18n.text("onboarding_workdir_placeholder")
                                    onTextChanged: {
                                        root.systemSettingsWorkdirDraft = text
                                        root.systemSettingsMessage = ""
                                    }
                                }
                                PillButton {
                                    text: i18n.text("choose")
                                    onClicked: {
                                        const selected = onboardingController.chooseWorkdir()
                                        if(selected) {
                                            root.systemSettingsWorkdirDraft = selected
                                            systemWorkdirField.text = selected
                                            root.systemSettingsMessage = ""
                                        }
                                    }
                                }
                            }

                            Text {
                                Layout.fillWidth: true
                                text: i18n.text("contact_email_settings")
                                color: theme.text
                                font.pixelSize: theme.baseFontSize
                                font.weight: Font.DemiBold
                            }
                            Text {
                                Layout.fillWidth: true
                                text: i18n.text("contact_email_settings_detail")
                                color: theme.textMuted
                                font.pixelSize: Math.max(11, theme.baseFontSize - 1)
                                wrapMode: Text.WordWrap
                            }
                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 8
                                StyledTextField {
                                    id: systemContactEmailField
                                    Layout.fillWidth: true
                                    text: root.systemContactEmailDraft
                                    placeholderText: i18n.text("email")
                                    onTextChanged: {
                                        root.systemContactEmailDraft = text
                                        root.systemSettingsMessage = ""
                                    }
                                }
                                PillButton {
                                    text: i18n.text("save")
                                    onClicked: {
                                        if(downloadController.saveContactEmail(root.systemContactEmailDraft)) {
                                            root.systemContactEmailDraft = downloadController.contactEmail
                                            root.systemSettingsMessage = i18n.text("contact_email_saved")
                                            root.systemSettingsMessageIsError = false
                                        } else {
                                            root.systemSettingsMessage = i18n.text("contact_email_invalid")
                                            root.systemSettingsMessageIsError = true
                                        }
                                    }
                                }
                            }

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 8
                                ModernCheckBox {
                                    text: i18n.text("show_guide_every_open")
                                    checked: onboardingController.showEveryLogin
                                    onToggled: onboardingController.setShowEveryLogin(checked)
                                }
                                Item { Layout.fillWidth: true }
                            }

                            Text {
                                Layout.fillWidth: true
                                visible: root.systemSettingsMessage.length > 0
                                text: root.systemSettingsMessage
                                color: root.systemSettingsMessageIsError ? theme.error : theme.success
                                font.pixelSize: Math.max(11, theme.baseFontSize - 1)
                                wrapMode: Text.WordWrap
                            }

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 8
                                PillButton {
                                    text: i18n.text("restart_onboarding")
                                    onClicked: onboardingController.startTour()
                                }
                                Item { Layout.fillWidth: true }
                                PillButton {
                                    text: i18n.text("save_workspace_folder")
                                    primary: true
                                    onClicked: {
                                        root.systemSettingsWorkdirDraft = systemWorkdirField.text
                                        if(onboardingController.saveWorkdirPreference(systemWorkdirField.text)) {
                                            root.systemSettingsWorkdirDraft = onboardingController.workdir
                                            systemWorkdirField.text = onboardingController.workdir
                                            root.systemSettingsMessage = i18n.text("workspace_folder_saved")
                                            root.systemSettingsMessageIsError = false
                                        } else {
                                            root.systemSettingsMessage = i18n.text("onboarding_workdir_invalid")
                                            root.systemSettingsMessageIsError = true
                                        }
                                    }
                                }
                            }
                        }
                    }

                    Card {
                        Layout.fillWidth: true
                        Layout.leftMargin: 14
                        Layout.rightMargin: 14
                        implicitHeight: parserApiSettingsContent.implicitHeight + 32
                        ColumnLayout {
                            id: parserApiSettingsContent
                            anchors.fill: parent
                            anchors.margins: 16
                            spacing: 10

                            Text { Layout.fillWidth: true; text: i18n.text("parser_cloud_services"); color: theme.text; font.pixelSize: theme.baseFontSize + 3; font.weight: Font.Bold }
                            Text { Layout.fillWidth: true; text: i18n.text("parser_cloud_services_detail"); color: theme.textMuted; wrapMode: Text.WordWrap }

                            Text { text: "MinerU"; color: theme.text; font.weight: Font.DemiBold }
                            ModernCheckBox { id: mineruApiEnabled; text: i18n.text("service_enabled"); checked: pdfExtractionController.mineruApiEnabled }
                            StyledTextField {
                                Layout.fillWidth: true
                                text: root.mineruApiUrlDraft
                                placeholderText: i18n.text("api_url")
                                onTextChanged: root.mineruApiUrlDraft = text
                            }
                            StyledTextField {
                                Layout.fillWidth: true
                                echoMode: TextInput.Password
                                text: root.mineruTokenDraft
                                placeholderText: pdfExtractionController.mineruTokenConfigured ? i18n.text("token_saved_placeholder") : i18n.text("api_token")
                                onTextChanged: root.mineruTokenDraft = text
                            }
                            Flow {
                                Layout.fillWidth: true
                                spacing: 8
                                PillButton { text: i18n.text("save"); primary: true; onClicked: pdfExtractionController.saveParserService("mineru", root.mineruApiUrlDraft, root.mineruTokenDraft, mineruApiEnabled.checked) }
                                PillButton { text: i18n.text("test_connection"); onClicked: pdfExtractionController.testParserService("mineru") }
                                PillButton { text: i18n.text("clear_token"); onClicked: pdfExtractionController.clearParserServiceToken("mineru") }
                            }

                            Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: theme.border }
                            Text { text: "PaddleOCR-VL"; color: theme.text; font.weight: Font.DemiBold }
                            ModernCheckBox { id: paddleApiEnabled; text: i18n.text("service_enabled"); checked: pdfExtractionController.paddleocrApiEnabled }
                            StyledTextField {
                                Layout.fillWidth: true
                                text: root.paddleocrApiUrlDraft
                                placeholderText: i18n.text("api_url")
                                onTextChanged: root.paddleocrApiUrlDraft = text
                            }
                            StyledTextField {
                                Layout.fillWidth: true
                                echoMode: TextInput.Password
                                text: root.paddleocrTokenDraft
                                placeholderText: pdfExtractionController.paddleocrTokenConfigured ? i18n.text("token_saved_placeholder") : i18n.text("api_token")
                                onTextChanged: root.paddleocrTokenDraft = text
                            }
                            Flow {
                                Layout.fillWidth: true
                                spacing: 8
                                PillButton { text: i18n.text("save"); primary: true; onClicked: pdfExtractionController.saveParserService("paddleocr_vl", root.paddleocrApiUrlDraft, root.paddleocrTokenDraft, paddleApiEnabled.checked) }
                                PillButton { text: i18n.text("test_connection"); onClicked: pdfExtractionController.testParserService("paddleocr_vl") }
                                PillButton { text: i18n.text("clear_token"); onClicked: pdfExtractionController.clearParserServiceToken("paddleocr_vl") }
                            }
                            Text { Layout.fillWidth: true; visible: pdfExtractionController.parserSettingsStatus.length > 0; text: pdfExtractionController.parserSettingsStatus; color: theme.textMuted; wrapMode: Text.WordWrap }
                        }
                    }
                    Item { Layout.fillHeight: true }
                }
            }
        }
    }

    WorkdirSetupDialog {
        parent: Overlay.overlay
        controller: onboardingController
    }

    OnboardingOverlay {
        parent: Overlay.overlay
        width: root.width
        height: root.height
        controller: onboardingController
        pageIndex: root.pageIndex
        targetRectProvider: root.targetRect
        onPageIndexRequested: index => root.pageIndex = index
    }

    Connections {
        target: onboardingController
        function onChanged() {
            root.applyTourNavigation(onboardingController.currentStep || {})
        }
    }

    function navigationTooltip(index, fallbackLabel) {
        if(index === 0 && downloadController.running && downloadController.activeTaskText.length > 0)
            return downloadController.activeTaskText
        if(index === 2 && translationController.running && translationController.activeTaskText.length > 0)
            return translationController.activeTaskText
        return i18n.text(fallbackLabel)
    }
    function defaultStatuses() {
        return preferencesController.avatarStatusOptions.filter(item => !item.custom)
    }
    function customStatuses() {
        return preferencesController.avatarStatusOptions.filter(item => item.custom)
    }
    function openSystemSettings() {
        root.systemSettingsWorkdirDraft = onboardingController.workdir
        root.systemContactEmailDraft = downloadController.contactEmail
        root.systemSettingsMessage = ""
        root.systemSettingsMessageIsError = false
        root.drawerPage = 6
    }
    function tourTargetForNavLabel(label) {
        if(label === "nav_download")
            return "nav.download"
        if(label === "nav_library")
            return "nav.library"
        if(label === "nav_translate")
            return "nav.translate"
        return ""
    }
    function registerTourTarget(key, item) {
        if(!key || !item)
            return
        let next = Object.assign({}, root.tourTargets)
        next[key] = item
        root.tourTargets = next
    }
    function unregisterTourTarget(key, item) {
        if(!key || root.tourTargets[key] !== item)
            return
        let next = Object.assign({}, root.tourTargets)
        delete next[key]
        root.tourTargets = next
    }
    function targetVisible(item) {
        let current = item
        while(current) {
            if(current.visible === false)
                return false
            if(current === root)
                return true
            current = current.parent
        }
        return true
    }
    function targetRect(key) {
        const item = root.tourTargets[key]
        if(!item || !root.targetVisible(item) || item.width <= 0 || item.height <= 0)
            return { "x": 0, "y": 0, "width": 0, "height": 0, "valid": false }
        const pos = item.mapToItem(root, 0, 0)
        const x = Math.max(0, pos.x)
        const y = Math.max(0, pos.y)
        const right = Math.min(root.width, pos.x + item.width)
        const bottom = Math.min(root.height, pos.y + item.height)
        const w = Math.max(0, right - x)
        const h = Math.max(0, bottom - y)
        return { "x": x, "y": y, "width": w, "height": h, "valid": w > 0 && h > 0 }
    }
    function applyTourNavigation(step) {
        if(!onboardingController.active || onboardingController.needsWorkdir)
            return
        if(step.pageIndex !== undefined && step.pageIndex >= 0) {
            root.pageIndex = step.pageIndex
            if(step.drawerPage === undefined && accountDrawer.opened)
                accountDrawer.close()
        }
        if(step.drawerPage !== undefined && step.drawerPage >= 0) {
            root.drawerPage = step.drawerPage
            if(!accountDrawer.opened)
                accountDrawer.open()
        } else if(step.id === "account.avatar" && accountDrawer.opened) {
            accountDrawer.close()
        }
    }
}
