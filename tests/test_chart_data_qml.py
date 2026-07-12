from __future__ import annotations

import unittest
from pathlib import Path


class ChartDataQmlTests(unittest.TestCase):
    def test_chart_data_dialog_contains_readable_core_actions(self) -> None:
        text = Path("ui/qml/ChartDataDialog.qml").read_text(encoding="utf-8")

        for phrase in (
            "分析图数据",
            "手动校准",
            "保存校准并重新分析",
            "复制 JSON",
            "导出 JSON",
            "复制 CSV",
            "导出 CSV",
            "结构化数据",
            "图例候选",
            "需要复核",
            "选子图左上",
            "选子图右下",
        ):
            self.assertIn(phrase, text)

        self.assertNotIn("闇€", text)
        self.assertNotIn("鍥", text)

        self.assertNotIn("function stageLabel", text)
        self.assertNotIn("function stageColor", text)

    def test_chart_data_dialog_is_centered_closable_and_expandable(self) -> None:
        text = Path("ui/qml/ChartDataDialog.qml").read_text(encoding="utf-8")

        self.assertIn("Window {", text)
        self.assertIn("modality: Qt.NonModal", text)
        self.assertIn("Qt.WindowTitleHint", text)
        self.assertIn("property bool expanded", text)
        self.assertIn("function centerDialog()", text)
        self.assertIn("Qt.callLater(root.centerDialog)", text)
        self.assertIn("root.show()", text)
        self.assertIn('root.expanded ? "还原" : "放大"', text)
        self.assertIn("onClicked: root.close()", text)

    def test_chart_data_dialog_reuses_results_and_syncs_subplot_calibration(self) -> None:
        text = Path("ui/qml/ChartDataDialog.qml").read_text(encoding="utf-8")

        self.assertIn("root.refreshResult()", text)
        self.assertIn("if (!root.chartResult || !root.chartResult.schemaVersion)", text)
        self.assertIn("if (root.calibrationVisible)", text)
        self.assertIn("root.populateCalibrationFields()", text)
        self.assertIn("pdfExtractionController.requestChartDataAnalysis", text)
        self.assertIn("property bool analysisRunning", text)
        self.assertNotIn("root.chartResult = pdfExtractionController.analyzeChartData", text)

    def test_plot_connects_samples_and_caches_bounds(self) -> None:
        text = Path("ui/qml/ScatterPlotCanvas.qml").read_text(encoding="utf-8")

        self.assertIn("property var cachedBounds", text)
        self.assertIn("ctx.lineTo", text)
        self.assertNotIn("tooltipText", text)
        self.assertNotIn("hoveredPoint", text)
        self.assertNotIn("Math.sqrt", text)

    def test_selected_subplot_drives_image_and_scrollable_data_previews(self) -> None:
        text = Path("ui/qml/ChartDataDialog.qml").read_text(encoding="utf-8")

        self.assertIn("sourceClipRect: root.calibrationVisible", text)
        self.assertIn("function currentSubplotClipRect()", text)
        self.assertIn("function csvPreviewCells()", text)
        self.assertIn("function previewSeries()", text)
        self.assertIn("ScrollBar.horizontal: StyledScrollBar", text)
        self.assertIn("ScrollBar.vertical: StyledScrollBar", text)
        self.assertNotIn("text: root.axisStatusText()", text)
        self.assertNotIn("text: root.legendText()", text)

    def test_subplots_open_large_preview_and_native_window_can_move_outside_parent(self) -> None:
        text = Path("ui/qml/ChartDataDialog.qml").read_text(encoding="utf-8")

        self.assertIn("id: subplotPreviewPopup", text)
        self.assertIn("subplotPreviewPopup.open()", text)
        self.assertIn("sourceClipRect: root.currentSubplotClipRect()", text)
        self.assertIn("flags: Qt.Window", text)
        self.assertIn("transientParent.x", text)
        self.assertNotIn("function moveDialogDrag", text)


if __name__ == "__main__":
    unittest.main()
