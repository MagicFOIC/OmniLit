import QtQuick

QtObject {
    readonly property string language: localeController.language

    function text(key) {
        void language
        return localeController.text(key)
    }

    function formatText(key, values) {
        void language
        return localeController.formatText(key, values)
    }
}
