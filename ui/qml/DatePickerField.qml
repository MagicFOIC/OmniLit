import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

RowLayout {
    id: root
    property alias text: input.text
    property date shownMonth: new Date()
    Layout.fillWidth: true
    Motion { id: motion }
    I18n { id: i18n }
    Theme { id: theme }

    TextField {
        id: input
        Layout.fillWidth: true
        placeholderText: "YYYY-MM-DD"
        selectByMouse: true
    }
    PillButton { text: "▼"; onClicked: { root.rebuild(); popup.open() } }

    ListModel { id: days }

    Popup {
        id: popup
        width: 330
        height: 355
        modal: true
        focus: true
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        enter: Transition {
            NumberAnimation { property: "opacity"; from: 0; to: 1; duration: motion.fast }
            NumberAnimation { property: "scale"; from: 0.98; to: 1; duration: motion.fast; easing.type: Easing.OutCubic }
        }
        exit: Transition {
            NumberAnimation { property: "opacity"; from: 1; to: 0; duration: motion.fast }
            NumberAnimation { property: "scale"; from: 1; to: 0.98; duration: motion.fast }
        }
        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 12
            RowLayout {
                Layout.fillWidth: true
                PillButton { text: "<"; onClicked: root.moveMonth(-1) }
                Text {
                    Layout.fillWidth: true
                    horizontalAlignment: Text.AlignHCenter
                    text: root.monthTitle()
                    color: theme.text
                    font.weight: Font.Bold
                }
                PillButton { text: ">"; onClicked: root.moveMonth(1) }
            }
            GridLayout {
                columns: 7
                Layout.fillWidth: true
                Repeater {
                    model: localeController.language === "en"
                           ? ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]
                           : ["一", "二", "三", "四", "五", "六", "日"]
                    Text {
                        text: modelData
                        color: theme.textMuted
                        horizontalAlignment: Text.AlignHCenter
                        Layout.preferredWidth: 38
                    }
                }
            }
            GridLayout {
                columns: 7
                Layout.fillWidth: true
                Layout.fillHeight: true
                Repeater {
                    model: days
                    Button {
                        id: dayButton
                        Layout.preferredWidth: 38
                        Layout.preferredHeight: 32
                        text: day
                        opacity: inMonth ? 1.0 : 0.45
                        HoverHandler { cursorShape: Qt.PointingHandCursor }
                        background: Rectangle {
                            radius: 8
                            color: dayButton.down ? theme.navPressed : dayButton.hovered ? theme.navSelected : "transparent"
                            Behavior on color { ColorAnimation { duration: motion.fast } }
                        }
                        Behavior on opacity { NumberAnimation { duration: motion.fast } }
                        onClicked: {
                            input.text = iso
                            popup.close()
                        }
                    }
                }
            }
            PillButton {
                Layout.fillWidth: true
                text: i18n.text("today")
                onClicked: {
                    let now = new Date()
                    input.text = root.iso(now)
                    root.shownMonth = now
                    root.rebuild()
                }
            }
        }
    }

    // 日期选择器固定生成 42 格，保证跨月时弹窗高度不会抖动。
    function rebuild() {
        days.clear()
        let first = new Date(shownMonth.getFullYear(), shownMonth.getMonth(), 1)
        let mondayOffset = (first.getDay() + 6) % 7
        let start = new Date(first.getFullYear(), first.getMonth(), 1 - mondayOffset)
        for (let offset = 0; offset < 42; offset++) {
            let value = new Date(start.getFullYear(), start.getMonth(), start.getDate() + offset)
            days.append({ day: value.getDate(), iso: iso(value), inMonth: value.getMonth() === shownMonth.getMonth() })
        }
    }

    function moveMonth(offset) {
        shownMonth = new Date(shownMonth.getFullYear(), shownMonth.getMonth() + offset, 1)
        rebuild()
    }

    function monthTitle() {
        let value = shownMonth
        if (localeController.language === "en")
            return value.toLocaleString("en-US", { month: "long", year: "numeric" })
        return value.getFullYear() + " 年 " + (value.getMonth() + 1) + " 月"
    }

    function iso(value) {
        function pad(number) { return String(number).padStart(2, "0") }
        return value.getFullYear() + "-" + pad(value.getMonth() + 1) + "-" + pad(value.getDate())
    }
}
