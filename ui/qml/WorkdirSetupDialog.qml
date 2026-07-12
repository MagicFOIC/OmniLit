import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Dialog {
    id: dialog
    property var controller: onboardingController
    property string localError: ""

    modal: true
    closePolicy: Popup.NoAutoClose
    title: i18n.text("onboarding_workdir_title")
    width: Math.min(620, Overlay.overlay ? Overlay.overlay.width - 48 : 620)
    anchors.centerIn: Overlay.overlay
    standardButtons: Dialog.NoButton
    visible: controller.needsWorkdir
    onVisibleChanged: {
        if(visible) {
            pathField.text = controller.workdir
            localError = ""
            open()
        }
    }

    I18n { id: i18n }
    Theme { id: theme }
    Motion { id: motion }

    enter: Transition {
        NumberAnimation { property: "opacity"; from: 0; to: 1; duration: motion.fast }
        NumberAnimation { property: "scale"; from: 0.98; to: 1; duration: motion.fast }
    }
    exit: Transition {
        NumberAnimation { property: "opacity"; from: 1; to: 0; duration: motion.fast }
        NumberAnimation { property: "scale"; from: 1; to: 0.98; duration: motion.fast }
    }

    background: Rectangle {
        color: theme.surfaceElevated
        radius: theme.radiusLarge
        border.color: theme.border
    }

    contentItem: ColumnLayout {
        spacing: 14

        Text {
            Layout.fillWidth: true
            text: i18n.text("onboarding_workdir_body")
            color: theme.textSecondary
            wrapMode: Text.WordWrap
        }

        RowLayout {
            Layout.fillWidth: true
            StyledTextField {
                id: pathField
                Layout.fillWidth: true
                text: controller.workdir
                placeholderText: i18n.text("onboarding_workdir_placeholder")
                onTextChanged: dialog.localError = ""
            }
            PillButton {
                text: i18n.text("choose")
                onClicked: {
                    const selected = controller.chooseWorkdir()
                    if(selected)
                        pathField.text = selected
                }
            }
        }

        Text {
            Layout.fillWidth: true
            visible: dialog.localError.length > 0
            text: dialog.localError
            color: theme.error
            wrapMode: Text.WordWrap
        }

        Text {
            Layout.fillWidth: true
            text: i18n.text("onboarding_workdir_dirs")
            color: theme.textMuted
            font.pixelSize: Math.max(11, theme.baseFontSize - 2)
            wrapMode: Text.WordWrap
        }

        RowLayout {
            Layout.fillWidth: true
            Item { Layout.fillWidth: true }
            PillButton {
                text: i18n.text("onboarding_use_default_workdir")
                onClicked: {
                    if(!controller.useDefaultWorkdir())
                        dialog.localError = i18n.text("onboarding_workdir_invalid")
                }
            }
            PillButton {
                text: i18n.text("onboarding_save_workdir")
                primary: true
                onClicked: {
                    if(!controller.setWorkdir(pathField.text))
                        dialog.localError = i18n.text("onboarding_workdir_invalid")
                }
            }
        }
    }
}
