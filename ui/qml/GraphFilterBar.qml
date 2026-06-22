import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

RowLayout {
    id: root
    property bool comparisonMode: false
    property var filterCounts: ({})
    signal filterRequested(string mode)
    signal searchRequested(string text)

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
    Item { Layout.fillWidth: true }
    TextField {
        Layout.preferredWidth: 220
        placeholderText: "搜索节点、标签或正文"
        selectByMouse: true
        onTextChanged: root.searchRequested(text)
    }
}
