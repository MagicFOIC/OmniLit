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
            "图例候选",
            "需要复核",
            "选子图左上",
            "选子图右下",
        ):
            self.assertIn(phrase, text)

        self.assertNotIn("闇€", text)
        self.assertNotIn("鍥", text)

    def test_chart_data_dialog_is_centered_closable_and_expandable(self) -> None:
        text = Path("ui/qml/ChartDataDialog.qml").read_text(encoding="utf-8")

        self.assertIn("parent: Overlay.overlay", text)
        self.assertIn("property bool expanded", text)
        self.assertIn("function centerDialog()", text)
        self.assertIn("onOpened: root.centerDialog()", text)
        self.assertIn("Qt.callLater(root.centerDialog)", text)
        self.assertIn('root.expanded ? "还原" : "放大"', text)
        self.assertIn("onClicked: root.close()", text)

    def test_chart_data_dialog_reuses_results_and_syncs_subplot_calibration(self) -> None:
        text = Path("ui/qml/ChartDataDialog.qml").read_text(encoding="utf-8")

        self.assertIn("root.refreshResult()", text)
        self.assertIn("if (!root.chartResult || !root.chartResult.schemaVersion)", text)
        self.assertIn("if (root.calibrationVisible)", text)
        self.assertIn("root.populateCalibrationFields()", text)

    def test_plot_connects_samples_and_caches_bounds(self) -> None:
        text = Path("ui/qml/ScatterPlotCanvas.qml").read_text(encoding="utf-8")

        self.assertIn("property var cachedBounds", text)
        self.assertIn("ctx.lineTo", text)
        self.assertIn("bestDistanceSquared", text)
        self.assertNotIn("Math.sqrt", text)


if __name__ == "__main__":
    unittest.main()
