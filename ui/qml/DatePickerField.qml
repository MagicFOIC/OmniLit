import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

RowLayout {
    id: root
    property alias text: input.text
    property string minDateText: ""
    property string maxDateText: ""
    property date shownMonth: new Date()
    property int viewMode: 0 // 0 = day, 1 = month, 2 = year
    property int yearPageStart: Math.floor(shownMonth.getFullYear() / 12) * 12
    property string pendingText: ""
    property var monthNamesEn: ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    property var monthNamesRu: ["\u042f\u043d\u0432", "\u0424\u0435\u0432", "\u041c\u0430\u0440", "\u0410\u043f\u0440", "\u041c\u0430\u0439", "\u0418\u044e\u043d", "\u0418\u044e\u043b", "\u0410\u0432\u0433", "\u0421\u0435\u043d", "\u041e\u043a\u0442", "\u041d\u043e\u044f", "\u0414\u0435\u043a"]
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
    PillButton {
        iconName: "calendar"
        onClicked: root.openPicker()
    }

    ListModel { id: days }
    ListModel { id: years }

    Popup {
        id: popup
        width: 360
        height: 438
        modal: true
        focus: true
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        enter: Transition {
            NumberAnimation { property: "opacity"; from: 0; to: 1; duration: motion.fast }
            NumberAnimation { property: "scale"; from: 0.96; to: 1; duration: motion.expand; easing.type: Easing.OutCubic }
        }
        exit: Transition {
            NumberAnimation { property: "opacity"; from: 1; to: 0; duration: motion.fast }
            NumberAnimation { property: "scale"; from: 1; to: 0.98; duration: motion.fast; easing.type: Easing.InCubic }
        }
        background: Rectangle {
            radius: 16
            color: theme.surface
            border.color: theme.border
        }

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 14
            spacing: 10

            RowLayout {
                Layout.fillWidth: true
                PillButton { iconName: "chevron-left"; onClicked: root.movePage(-1) }
                Button {
                    id: titleButton
                    Layout.fillWidth: true
                    text: root.headerTitle()
                    hoverEnabled: true
                    ToolTip.delay: 350
                    ToolTip.timeout: 4000
                    ToolTip.visible: hovered
                    ToolTip.text: root.viewMode === 0 ? i18n.text("select_month") : i18n.text("select_year")
                    onClicked: root.promoteView()
                    background: Rectangle {
                        radius: 10
                        color: titleButton.down ? theme.navPressed : titleButton.hovered ? theme.navHover : theme.surfaceSoft
                        border.color: titleButton.hovered ? theme.borderStrong : theme.border
                        Behavior on color { ColorAnimation { duration: motion.fast } }
                        Behavior on border.color { ColorAnimation { duration: motion.fast } }
                    }
                    contentItem: Text {
                        text: titleButton.text
                        color: theme.text
                        font.weight: Font.Bold
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                    HoverHandler { cursorShape: Qt.PointingHandCursor }
                }
                PillButton { iconName: "chevron-right"; onClicked: root.movePage(1) }
            }

            Item {
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true

                ColumnLayout {
                    id: dayLayer
                    anchors.fill: parent
                    spacing: 7
                    opacity: root.viewMode === 0 ? 1 : 0
                    scale: root.viewMode === 0 ? 1 : 0.985
                    visible: opacity > 0
                    Behavior on opacity { NumberAnimation { duration: motion.normal } }
                    Behavior on scale { NumberAnimation { duration: motion.normal; easing.type: Easing.OutCubic } }

                    GridLayout {
                        columns: 7
                        Layout.fillWidth: true
                        Repeater {
                            model: root.weekdayLabels()
                            Text {
                                text: modelData
                                color: theme.textMuted
                                horizontalAlignment: Text.AlignHCenter
                                Layout.preferredWidth: 44
                                font.pixelSize: theme.baseFontSize - 2
                                font.weight: Font.DemiBold
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
                                Layout.preferredWidth: 44
                                Layout.preferredHeight: 34
                                enabled: selectable
                                text: String(day)
                                opacity: !selectable ? 0.25 : inMonth ? 1.0 : 0.42
                                hoverEnabled: selectable
                                onClicked: root.pendingText = iso
                                HoverHandler { cursorShape: dayButton.enabled ? Qt.PointingHandCursor : Qt.ArrowCursor }
                                background: Rectangle {
                                    radius: 9
                                    color: root.pendingText === iso ? theme.accent : dayButton.down ? theme.navPressed : dayButton.hovered ? theme.navSelected : "transparent"
                                    border.width: root.isTodayIso(iso) && root.pendingText !== iso ? 1 : 0
                                    border.color: theme.accent
                                    Behavior on color { ColorAnimation { duration: motion.fast } }
                                    Behavior on border.width { NumberAnimation { duration: motion.fast } }
                                }
                                contentItem: Text {
                                    text: dayButton.text
                                    color: root.pendingText === iso ? theme.accentText : theme.text
                                    horizontalAlignment: Text.AlignHCenter
                                    verticalAlignment: Text.AlignVCenter
                                    font.weight: root.pendingText === iso ? Font.Bold : Font.Normal
                                }
                                Behavior on opacity { NumberAnimation { duration: motion.fast } }
                            }
                        }
                    }
                }

                GridLayout {
                    id: monthLayer
                    anchors.fill: parent
                    columns: 3
                    rowSpacing: 10
                    columnSpacing: 10
                    opacity: root.viewMode === 1 ? 1 : 0
                    scale: root.viewMode === 1 ? 1 : 0.985
                    visible: opacity > 0
                    Behavior on opacity { NumberAnimation { duration: motion.normal } }
                    Behavior on scale { NumberAnimation { duration: motion.normal; easing.type: Easing.OutCubic } }
                    Repeater {
                        model: 12
                        Button {
                            id: monthButton
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            text: root.monthLabel(index)
                            hoverEnabled: true
                            onClicked: root.chooseMonth(index)
                            HoverHandler { cursorShape: Qt.PointingHandCursor }
                            background: Rectangle {
                                radius: 12
                                color: index === root.shownMonth.getMonth() ? theme.accent : monthButton.down ? theme.navPressed : monthButton.hovered ? theme.navHover : theme.surfaceSoft
                                border.color: monthButton.hovered ? theme.borderStrong : theme.border
                                Behavior on color { ColorAnimation { duration: motion.fast } }
                                Behavior on border.color { ColorAnimation { duration: motion.fast } }
                            }
                            contentItem: Text {
                                text: monthButton.text
                                color: index === root.shownMonth.getMonth() ? theme.accentText : theme.text
                                horizontalAlignment: Text.AlignHCenter
                                verticalAlignment: Text.AlignVCenter
                                font.weight: Font.DemiBold
                            }
                        }
                    }
                }

                GridLayout {
                    id: yearLayer
                    anchors.fill: parent
                    columns: 3
                    rowSpacing: 10
                    columnSpacing: 10
                    opacity: root.viewMode === 2 ? 1 : 0
                    scale: root.viewMode === 2 ? 1 : 0.985
                    visible: opacity > 0
                    Behavior on opacity { NumberAnimation { duration: motion.normal } }
                    Behavior on scale { NumberAnimation { duration: motion.normal; easing.type: Easing.OutCubic } }
                    Repeater {
                        model: years
                        Button {
                            id: yearButton
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            text: String(year)
                            hoverEnabled: true
                            onClicked: root.chooseYear(year)
                            HoverHandler { cursorShape: Qt.PointingHandCursor }
                            background: Rectangle {
                                radius: 12
                                color: year === root.shownMonth.getFullYear() ? theme.accent : yearButton.down ? theme.navPressed : yearButton.hovered ? theme.navHover : theme.surfaceSoft
                                border.color: yearButton.hovered ? theme.borderStrong : theme.border
                                Behavior on color { ColorAnimation { duration: motion.fast } }
                                Behavior on border.color { ColorAnimation { duration: motion.fast } }
                            }
                            contentItem: Text {
                                text: yearButton.text
                                color: year === root.shownMonth.getFullYear() ? theme.accentText : theme.text
                                horizontalAlignment: Text.AlignHCenter
                                verticalAlignment: Text.AlignVCenter
                                font.weight: Font.DemiBold
                            }
                        }
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                PillButton { text: i18n.text("clear"); onClicked: { input.text = ""; popup.close() } }
                Item { Layout.fillWidth: true }
                PillButton { text: i18n.text("cancel"); onClicked: popup.close() }
                PillButton {
                    text: i18n.text("confirm")
                    primary: true
                    onClicked: {
                        if (root.pendingText.length > 0)
                            input.text = root.pendingText
                        popup.close()
                    }
                }
            }
        }
    }

    function openPicker() {
        let parsed = parseIsoDate(input.text)
        if (parsed === null)
            parsed = validDateOrNull(shownMonth)
        if (parsed === null)
            parsed = new Date()
        shownMonth = new Date(parsed.getFullYear(), parsed.getMonth(), 1)
        pendingText = parseIsoDate(input.text) !== null ? iso(parsed) : ""
        viewMode = 0
        yearPageStart = Math.floor(shownMonth.getFullYear() / 12) * 12
        rebuild()
        popup.open()
    }

    function rebuild() {
        rebuildDays()
        rebuildYears()
    }

    function rebuildDays() {
        days.clear()
        let first = new Date(shownMonth.getFullYear(), shownMonth.getMonth(), 1)
        let mondayOffset = (first.getDay() + 6) % 7
        let start = new Date(first.getFullYear(), first.getMonth(), 1 - mondayOffset)
        for (let offset = 0; offset < 42; offset++) {
            let value = new Date(start.getFullYear(), start.getMonth(), start.getDate() + offset)
            days.append({
                day: value.getDate(),
                iso: iso(value),
                inMonth: value.getMonth() === shownMonth.getMonth(),
                selectable: isInRange(value)
            })
        }
    }

    function rebuildYears() {
        years.clear()
        for (let offset = 0; offset < 12; offset++)
            years.append({ year: yearPageStart + offset })
    }

    function movePage(offset) {
        if (viewMode === 0)
            moveMonth(offset)
        else if (viewMode === 1)
            moveYear(offset)
        else
            moveYearPage(offset)
    }

    function promoteView() {
        if (viewMode === 0)
            viewMode = 1
        else if (viewMode === 1) {
            yearPageStart = Math.floor(shownMonth.getFullYear() / 12) * 12
            rebuildYears()
            viewMode = 2
        }
    }

    function chooseMonth(monthIndex) {
        shownMonth = new Date(shownMonth.getFullYear(), monthIndex, 1)
        viewMode = 0
        rebuildDays()
    }

    function chooseYear(year) {
        shownMonth = new Date(year, shownMonth.getMonth(), 1)
        viewMode = 1
        rebuildDays()
    }

    function moveMonth(offset) {
        shownMonth = new Date(shownMonth.getFullYear(), shownMonth.getMonth() + offset, 1)
        yearPageStart = Math.floor(shownMonth.getFullYear() / 12) * 12
        rebuild()
    }

    function moveYear(offset) {
        shownMonth = new Date(shownMonth.getFullYear() + offset, shownMonth.getMonth(), 1)
        yearPageStart = Math.floor(shownMonth.getFullYear() / 12) * 12
        rebuild()
    }

    function moveYearPage(offset) {
        yearPageStart += offset * 12
        rebuildYears()
    }

    function headerTitle() {
        if (viewMode === 2)
            return yearPageStart + " - " + (yearPageStart + 11)
        if (viewMode === 1)
            return shownMonth.getFullYear() + " " + i18n.text("year")
        return monthTitle()
    }

    function monthTitle() {
        if (localeController.language === "en")
            return shownMonth.toLocaleString("en-US", { month: "long", year: "numeric" })
        if (localeController.language === "ru")
            return shownMonth.toLocaleString("ru-RU", { month: "long", year: "numeric" })
        return shownMonth.getFullYear() + "\u5e74" + (shownMonth.getMonth() + 1) + "\u6708"
    }

    function monthLabel(index) {
        if (localeController.language === "en")
            return monthNamesEn[index]
        if (localeController.language === "ru")
            return monthNamesRu[index]
        return (index + 1) + i18n.text("month")
    }

    function weekdayLabels() {
        if (localeController.language === "en")
            return ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]
        if (localeController.language === "ru")
            return ["\u041f\u043d", "\u0412\u0442", "\u0421\u0440", "\u0427\u0442", "\u041f\u0442", "\u0421\u0431", "\u0412\u0441"]
        return ["\u4e00", "\u4e8c", "\u4e09", "\u56db", "\u4e94", "\u516d", "\u65e5"]
    }

    function parseIsoDate(value) {
        let text = String(value || "").trim()
        let match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(text)
        if (!match)
            return null
        let year = Number(match[1])
        let month = Number(match[2]) - 1
        let day = Number(match[3])
        let date = new Date(year, month, day)
        if (date.getFullYear() !== year || date.getMonth() !== month || date.getDate() !== day)
            return null
        return date
    }

    function validDateOrNull(value) {
        if (value instanceof Date && !isNaN(value.getTime()))
            return value
        return null
    }

    function isInRange(value) {
        let minDate = parseIsoDate(minDateText)
        let maxDate = parseIsoDate(maxDateText)
        let dateValue = dayNumber(value)
        if (minDate !== null && dateValue < dayNumber(minDate))
            return false
        if (maxDate !== null && dateValue > dayNumber(maxDate))
            return false
        return true
    }

    function dayNumber(value) {
        return value.getFullYear() * 10000 + (value.getMonth() + 1) * 100 + value.getDate()
    }

    function isTodayIso(value) {
        return value === iso(new Date())
    }

    function iso(value) {
        function pad(number) { return String(number).padStart(2, "0") }
        return value.getFullYear() + "-" + pad(value.getMonth() + 1) + "-" + pad(value.getDate())
    }
}
