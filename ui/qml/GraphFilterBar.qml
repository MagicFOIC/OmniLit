pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts

ColumnLayout {
    id: root
    property bool comparisonMode: false
    property var filterCounts: ({})
    property string searchText: ""
    property var facetOptions: ({})
    property var facetFilters: ({})
    property bool facetsOpen: false
    signal filterRequested(string mode)
    signal searchRequested(string text)
    signal facetRequested(string facet, string value)
    signal facetsCleared()

    spacing: 6
    readonly property var baseFilters: [
        { label: "全部", mode: "all" }, { label: "结构", mode: "structure" },
        { label: "方法", mode: "method" }, { label: "实验", mode: "experiment" },
        { label: "结果", mode: "result" }, { label: "图表", mode: "figure" },
        { label: "引用", mode: "citation" }, { label: "局限", mode: "limitation" }
    ]
    readonly property var comparisonFilters: [
        { label: "共同点", mode: "common" }, { label: "不同点", mode: "different" },
        { label: "冲突点", mode: "conflict" }, { label: "方法对比", mode: "method" },
        { label: "实验对比", mode: "experiment" }, { label: "结果对比", mode: "result" },
        { label: "局限对比", mode: "limitation" }
    ]
    readonly property var facetDefinitions: [
        { key: "year", label: "年份" }, { key: "topic", label: "主题" },
        { key: "author", label: "作者" }, { key: "institution", label: "机构" },
        { key: "venue", label: "期刊" }
    ]

    onFacetFiltersChanged: {
        if (Object.keys(root.facetFilters || {}).length > 0)
            root.facetsOpen = true
    }

    RowLayout {
        Layout.fillWidth: true
        spacing: 6
        Repeater {
            model: root.comparisonMode ? root.comparisonFilters : root.baseFilters
            PillButton {
                required property var modelData
                property int availableCount: Number(root.filterCounts[modelData.mode] || 0)
                text: modelData.label + (modelData.mode === "all" ? "" : " " + availableCount)
                enabled: modelData.mode === "all" || availableCount > 0
                primary: knowledgeGraphController.filterMode === modelData.mode
                onClicked: root.filterRequested(modelData.mode)
            }
        }
        PillButton {
            visible: !root.comparisonMode
            text: (root.facetsOpen ? "收起分面" : "分面筛选")
                  + (Object.keys(root.facetFilters || {}).length > 0
                     ? " " + Object.keys(root.facetFilters).length : "")
            primary: root.facetsOpen || Object.keys(root.facetFilters || {}).length > 0
            onClicked: root.facetsOpen = !root.facetsOpen
        }
        Item { Layout.fillWidth: true }
        StyledTextField {
            Layout.preferredWidth: 220
            placeholderText: "搜索节点、标签或正文"
            text: root.searchText
            selectByMouse: true
            onTextChanged: root.searchRequested(text)
        }
    }

    RowLayout {
        Layout.fillWidth: true
        visible: !root.comparisonMode && root.facetsOpen
        spacing: 6
        Text { text: "分面筛选"; color: theme.textMuted }
        Repeater {
            model: root.facetDefinitions
            StyledComboBox {
                required property var modelData
                property var choices: [{ label: modelData.label, value: "", count: 0 }]
                                      .concat(root.facetOptions[modelData.key] || [])
                Layout.preferredWidth: modelData.key === "institution" ? 190 : 150
                model: choices
                textRole: "label"
                valueRole: "value"
                currentIndex: {
                    var selected = String(root.facetFilters[modelData.key] || "")
                    for (var i = 0; i < choices.length; ++i)
                        if (String(choices[i].value || "") === selected) return i
                    return 0
                }
                displayText: currentIndex > 0
                             ? String(choices[currentIndex].label) + " · " + Number(choices[currentIndex].count || 0)
                             : modelData.label
                onActivated: function(index) {
                    root.facetRequested(modelData.key, String(choices[index].value || ""))
                }
            }
        }
        PillButton {
            text: "清除分面"
            enabled: Object.keys(root.facetFilters || {}).length > 0
            onClicked: root.facetsCleared()
        }
        Item { Layout.fillWidth: true }
        Text {
            text: Object.keys(root.facetFilters || {}).length > 0
                  ? "已应用 " + Object.keys(root.facetFilters).length + " 个分面（交集）"
                  : "年份、主题、作者、机构、期刊可组合筛选"
            color: theme.textMuted
        }
    }

    Theme { id: theme }
}
