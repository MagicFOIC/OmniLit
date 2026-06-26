import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: root
    property bool registerMode: false
    readonly property int authSpacing: 6
    readonly property int authFieldHeight: 42
    Motion { id: motion }
    I18n { id: i18n }
    Theme { id: theme; dynamic: false }
    LayoutMetrics { id: metrics; viewportWidth: root.width; viewportHeight: root.height }

    Rectangle {
        anchors.fill: parent
        color: theme.canvasTop
    }
    Rectangle {
        width: 196
        height: 196
        radius: 72
        x: -78
        y: -82
        rotation: -12
        color: theme.accentSofter
        border.color: theme.border
    }
    Rectangle {
        width: 150
        height: 150
        radius: 54
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.rightMargin: -58
        anchors.bottomMargin: -54
        rotation: 18
        color: theme.accentSofter
        border.color: theme.border
    }
    Card {
        id: loginCard
        width: Math.min(440, parent.width - metrics.pageMargin * 2)
        height: Math.min(596, parent.height - metrics.pageMargin * 2)
        anchors.centerIn: parent
        opacity: 0
        scale: 0.98

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 18
            spacing: root.authSpacing

            Text {
                text: registerMode ? i18n.text("auth_register_eyebrow") : i18n.text("auth_login_eyebrow")
                color: theme.accent
                font.pixelSize: 10
                font.weight: Font.Bold
                font.letterSpacing: 1.0
            }

            RowLayout {
                id: titleRow
                Layout.fillWidth: true
                spacing: 12

                Rectangle {
                    Layout.preferredWidth: 52
                    Layout.preferredHeight: 52
                    radius: 16
                    color: theme.accentSofter
                    border.color: theme.accentSoft
                    Image { anchors.fill: parent; anchors.margins: 8; source: appController.logoUrl; fillMode: Image.PreserveAspectFit }
                }

                ColumnLayout {
                    spacing: 1
                    Text { text: "OmniLit"; color: theme.text; font.pixelSize: 26; font.weight: Font.Bold; font.letterSpacing: -0.5 }
                    Text { text: i18n.text(registerMode ? "local_account" : "workspace_login"); color: theme.textMuted; font.pixelSize: 12 }
                }

                Item { Layout.fillWidth: true }

                Button {
                    id: languageButton
                    implicitHeight: 32
                    leftPadding: 10
                    rightPadding: 10
                    hoverEnabled: true
                    text: root.currentLanguageLabel()
                    onClicked: languageMenu.open()

                    HoverHandler { cursorShape: Qt.PointingHandCursor }
                    background: Rectangle {
                        radius: 9
                        color: languageButton.hovered ? theme.accentSoft : theme.surfaceSoft
                        border.color: languageButton.hovered ? theme.accent : theme.border
                        Behavior on color { ColorAnimation { duration: motion.fast } }
                        Behavior on border.color { ColorAnimation { duration: motion.fast } }
                    }
                    contentItem: Item {
                        implicitWidth: languageRow.implicitWidth
                        implicitHeight: languageRow.implicitHeight
                        Row {
                            id: languageRow
                            anchors.centerIn: parent
                            spacing: 5
                            VectorIcon {
                                anchors.verticalCenter: parent.verticalCenter
                                width: 16
                                height: 16
                                name: "language"
                                color: theme.accentStrong
                                strokeWidth: 2
                            }
                            Text {
                                anchors.verticalCenter: parent.verticalCenter
                                text: languageButton.text
                                color: theme.accentStrong
                                font.pixelSize: 12
                                font.weight: Font.DemiBold
                            }
                        }
                    }
                }
                Menu {
                    id: languageMenu
                    y: languageButton.height + 6
                    Repeater {
                        model: localeController.availableLanguages
                        MenuItem {
                            text: modelData.label
                            checkable: true
                            checked: localeController.language === modelData.value
                            onTriggered: localeController.setLanguage(modelData.value)
                        }
                    }
                }
            }

            Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: theme.divider }

            Text {
                Layout.fillWidth: true
                text: i18n.text(registerMode ? "auth_register_desc" : "auth_login_desc")
                color: theme.textMuted
                font.pixelSize: 12
                wrapMode: Text.WordWrap
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: root.authSpacing

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 3
                    Text { text: i18n.text("username"); color: theme.textMuted; font.pixelSize: 12; font.weight: Font.DemiBold }
                    AuthTextField {
                        id: username
                        Layout.fillWidth: true
                        Layout.preferredHeight: root.authFieldHeight
                        iconName: "user"
                        placeholderText: i18n.text("username")
                        text: authController.rememberedUsername
                        onAccepted: registerMode ? contactEmail.forceActiveFocus() : password.forceActiveFocus()
                    }
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 3
                    enabled: registerMode
                    opacity: registerMode ? 1 : 0
                    Text { text: i18n.text("contact_email_settings"); color: theme.textMuted; font.pixelSize: 12; font.weight: Font.DemiBold }
                    AuthTextField {
                        id: contactEmail
                        Layout.fillWidth: true
                        Layout.preferredHeight: root.authFieldHeight
                        iconName: "email"
                        placeholderText: i18n.text("email")
                        onAccepted: password.forceActiveFocus()
                    }
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 3
                    Text { text: i18n.text("password"); color: theme.textMuted; font.pixelSize: 12; font.weight: Font.DemiBold }
                    AuthTextField {
                        id: password
                        Layout.fillWidth: true
                        Layout.preferredHeight: root.authFieldHeight
                        iconName: "lock"
                        placeholderText: i18n.text("password")
                        text: authController.rememberedPassword
                        echoMode: showPassword.checked ? TextInput.Normal : TextInput.Password
                        onAccepted: root.submit()
                    }
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 3
                    enabled: registerMode
                    opacity: registerMode ? 1 : 0
                    Text { text: i18n.text("confirm_password"); color: theme.textMuted; font.pixelSize: 12; font.weight: Font.DemiBold }
                    AuthTextField {
                        id: confirm
                        Layout.fillWidth: true
                        Layout.preferredHeight: root.authFieldHeight
                        iconName: "lock"
                        placeholderText: i18n.text("confirm_password")
                        echoMode: showPassword.checked ? TextInput.Normal : TextInput.Password
                        onAccepted: root.submit()
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                ModernCheckBox { id: remember; text: i18n.text("remember_password"); checked: authController.rememberPasswordChecked; font.pixelSize: 12 }
                Item { Layout.fillWidth: true }
                ModernCheckBox { id: showPassword; text: i18n.text("show_password"); font.pixelSize: 12 }
            }

            StatusBanner {
                Layout.fillWidth: true
                Layout.preferredHeight: reserveSpace ? reservedHeight : implicitHeight
                text: authController.statusText
                reserveSpace: true
                maximumLines: 1
            }

            PillButton {
                Layout.fillWidth: true
                Layout.preferredHeight: 44
                primary: true
                text: i18n.text(registerMode ? "register_login" : "login")
                onClicked: root.submit()
            }

            Button {
                id: modeSwitch
                Layout.fillWidth: true
                Layout.preferredHeight: 44
                implicitHeight: 44
                hoverEnabled: true
                text: i18n.text(registerMode ? "back_login" : "create_account")
                onClicked: {
                    registerMode = !registerMode
                    if (registerMode)
                        contactEmail.forceActiveFocus()
                    else
                        username.forceActiveFocus()
                }

                HoverHandler { cursorShape: Qt.PointingHandCursor }
                background: Rectangle {
                    radius: 10
                    color: modeSwitch.hovered ? theme.accentSoft : theme.surface
                    border.color: modeSwitch.hovered ? theme.accent : theme.border
                    Behavior on color { ColorAnimation { duration: motion.fast } }
                    Behavior on border.color { ColorAnimation { duration: motion.fast } }
                }
                contentItem: Text {
                    text: modeSwitch.text
                    color: theme.accentStrong
                    font.pixelSize: 13
                    font.weight: Font.DemiBold
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
            }

            Item { Layout.fillHeight: true }
            Text { text: "v" + appController.version; color: "#94a3b8"; font.pixelSize: 12; Layout.alignment: Qt.AlignHCenter }
        }
    }

    ParallelAnimation {
        id: appear
        NumberAnimation { target: loginCard; property: "opacity"; from: 0; to: 1; duration: motion.normal; easing.type: Easing.OutCubic }
        NumberAnimation { target: loginCard; property: "scale"; from: 0.98; to: 1; duration: motion.normal; easing.type: Easing.OutCubic }
    }

    Component.onCompleted: {
        appear.start()
        username.forceActiveFocus()
    }

    function submit() {
        if (registerMode)
            authController.registerUser(username.text, password.text, confirm.text, contactEmail.text, remember.checked)
        else
            authController.login(username.text, password.text, remember.checked)
    }

    function currentLanguageLabel() {
        for (let item of localeController.availableLanguages)
            if (item.value === localeController.language)
                return item.label
        return "Language"
    }
}
