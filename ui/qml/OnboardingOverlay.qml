import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: root
    property var controller: onboardingController
    property var targetRectProvider
    property int pageIndex: -1
    property var targetRect: ({ "x": 0, "y": 0, "width": 0, "height": 0, "valid": false })
    signal pageIndexRequested(int index)

    anchors.fill: parent
    visible: controller.active && !controller.needsWorkdir
    z: 1000
    focus: visible

    I18n { id: i18n }
    Theme { id: theme }
    Motion { id: motion }

    onVisibleChanged: if(visible) refreshSoon.restart()
    onWidthChanged: refreshSoon.restart()
    onHeightChanged: refreshSoon.restart()
    onPageIndexChanged: refreshSoon.restart()

    Connections {
        target: controller
        function onChanged() {
            const step = controller.currentStep || {}
            if(step.pageIndex !== undefined && step.pageIndex >= 0 && step.pageIndex !== root.pageIndex)
                root.pageIndexRequested(step.pageIndex)
            refreshSoon.restart()
        }
    }

    Timer {
        id: refreshSoon
        interval: 90
        repeat: false
        onTriggered: root.refreshTarget()
    }

    MouseArea {
        anchors.fill: parent
        hoverEnabled: true
        acceptedButtons: Qt.AllButtons
    }

    Rectangle {
        x: 0
        y: 0
        width: parent.width
        height: root.targetRect.valid ? Math.max(0, root.targetRect.y - 10) : parent.height
        color: "#99000000"
    }
    Rectangle {
        visible: root.targetRect.valid
        x: 0
        y: Math.max(0, root.targetRect.y - 10)
        width: Math.max(0, root.targetRect.x - 10)
        height: Math.min(parent.height, root.targetRect.height + 20)
        color: "#99000000"
    }
    Rectangle {
        visible: root.targetRect.valid
        x: Math.min(parent.width, root.targetRect.x + root.targetRect.width + 10)
        y: Math.max(0, root.targetRect.y - 10)
        width: Math.max(0, parent.width - x)
        height: Math.min(parent.height, root.targetRect.height + 20)
        color: "#99000000"
    }
    Rectangle {
        visible: root.targetRect.valid
        x: 0
        y: Math.min(parent.height, root.targetRect.y + root.targetRect.height + 10)
        width: parent.width
        height: Math.max(0, parent.height - y)
        color: "#99000000"
    }

    Rectangle {
        visible: root.targetRect.valid
        x: Math.max(8, root.targetRect.x - 8)
        y: Math.max(8, root.targetRect.y - 8)
        width: Math.min(parent.width - x - 8, root.targetRect.width + 16)
        height: Math.min(parent.height - y - 8, root.targetRect.height + 16)
        radius: 12
        color: "transparent"
        border.width: 2
        border.color: theme.accent
        antialiasing: true
        SequentialAnimation on opacity {
            running: root.visible
            loops: Animation.Infinite
            NumberAnimation { from: 1; to: 0.52; duration: 680; easing.type: Easing.InOutQuad }
            NumberAnimation { from: 0.52; to: 1; duration: 680; easing.type: Easing.InOutQuad }
        }
    }

    Card {
        id: guideCard
        width: Math.min(420, root.width - 40)
        height: guideContent.implicitHeight + 28
        x: root.cardX()
        y: root.cardY()
        Behavior on x { NumberAnimation { duration: motion.normal; easing.type: Easing.OutCubic } }
        Behavior on y { NumberAnimation { duration: motion.normal; easing.type: Easing.OutCubic } }

        ColumnLayout {
            id: guideContent
            anchors.fill: parent
            anchors.margins: 14
            spacing: 10

            RowLayout {
                Layout.fillWidth: true
                Text {
                    Layout.fillWidth: true
                    text: i18n.text((controller.currentStep || {}).titleKey || "")
                    color: theme.text
                    font.pixelSize: theme.baseFontSize + 5
                    font.weight: Font.Bold
                    wrapMode: Text.WordWrap
                }
                Text {
                    text: String(Math.max(1, controller.stepIndex)) + "/" + String(Math.max(1, controller.steps.length - 1))
                    color: theme.textMuted
                    font.pixelSize: Math.max(11, theme.baseFontSize - 2)
                }
            }

            Text {
                Layout.fillWidth: true
                text: i18n.text((controller.currentStep || {}).bodyKey || "")
                color: theme.textSecondary
                wrapMode: Text.WordWrap
                lineHeight: 1.12
            }

            ModernCheckBox {
                text: i18n.text("onboarding_show_every_login")
                checked: controller.showEveryLogin
                onToggled: controller.setShowEveryLogin(checked)
            }

            RowLayout {
                Layout.fillWidth: true
                PillButton {
                    text: i18n.text("onboarding_skip")
                    onClicked: controller.skip()
                }
                Item { Layout.fillWidth: true }
                PillButton {
                    text: i18n.text("onboarding_previous")
                    enabled: controller.stepIndex > 1
                    onClicked: controller.previous()
                }
                PillButton {
                    text: controller.stepIndex >= controller.steps.length - 1 ? i18n.text("onboarding_finish") : i18n.text("onboarding_next")
                    primary: true
                    onClicked: controller.stepIndex >= controller.steps.length - 1 ? controller.finish() : controller.next()
                }
            }
        }
    }

    function refreshTarget() {
        if(!root.visible)
            return
        const step = controller.currentStep || {}
        const targetId = step.targetId || ""
        if(root.targetRectProvider && targetId) {
            const rect = root.targetRectProvider(targetId)
            if(rect && rect.valid && rect.width > 0 && rect.height > 0) {
                root.targetRect = rect
                return
            }
        }
        root.targetRect = { "x": 0, "y": 0, "width": 0, "height": 0, "valid": false }
    }

    function cardX() {
        const margin = 20
        if(!root.targetRect.valid)
            return Math.max(margin, (root.width - guideCard.width) / 2)
        const placement = (controller.currentStep || {}).preferPlacement || "right"
        if(placement === "left" && root.targetRect.x - guideCard.width - margin > margin)
            return root.targetRect.x - guideCard.width - margin
        if(placement === "right" && root.targetRect.x + root.targetRect.width + margin + guideCard.width < root.width - margin)
            return root.targetRect.x + root.targetRect.width + margin
        return Math.max(margin, Math.min(root.width - guideCard.width - margin, root.targetRect.x + root.targetRect.width / 2 - guideCard.width / 2))
    }

    function cardY() {
        const margin = 20
        if(!root.targetRect.valid)
            return Math.max(margin, (root.height - guideCard.height) / 2)
        const placement = (controller.currentStep || {}).preferPlacement || "right"
        if(placement === "bottom" && root.targetRect.y + root.targetRect.height + margin + guideCard.height < root.height - margin)
            return root.targetRect.y + root.targetRect.height + margin
        if(placement === "top" && root.targetRect.y - guideCard.height - margin > margin)
            return root.targetRect.y - guideCard.height - margin
        return Math.max(margin, Math.min(root.height - guideCard.height - margin, root.targetRect.y + root.targetRect.height / 2 - guideCard.height / 2))
    }
}
