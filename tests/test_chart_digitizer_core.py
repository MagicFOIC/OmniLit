from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

try:
    from PySide6.QtGui import QColor, QImage, QPainter, QPen
except ModuleNotFoundError:  # pragma: no cover - depends on local test runtime.
    QColor = None
    QImage = None
    QPainter = None
    QPen = None

from omnilit_qt.chart_digitizer_core import analyze_chart_element
from omnilit_qt.chart_digitizer_schema import validate_chart_result


@unittest.skipUnless(QImage is not None, "PySide6 is not installed in this environment")
class ChartDigitizerCoreTests(unittest.TestCase):
    def test_single_curve_sampling_with_manual_calibration(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            image_path = Path(temp) / "single_curve.png"
            _write_chart_image(image_path, lines=[("#d62728", [(40, 140), (220, 40)])])
            element = _figure_element(image_path, "Fig. 1 curve over time")
            result = analyze_chart_element(element, _index(), record_id="rec", sample_count=5, calibration=_calibration())

        self.assertEqual(validate_chart_result(result), [])
        self.assertFalse(result["analysis"]["needsReview"])
        series = result["subplots"][0]["series"]
        self.assertGreaterEqual(len(series), 1)
        points = series[0]["points"]
        self.assertEqual(len(points), 5)
        self.assertAlmostEqual(points[0]["x"], 0.0, delta=0.001)
        self.assertAlmostEqual(points[-1]["x"], 100.0, delta=0.001)
        self.assertFalse(points[2]["missing"])

    def test_manual_calibration_preserves_full_pixel_points(self) -> None:
        calibration = {
            "plotAreaPx": [40, 20, 220, 150],
            "xAxis": {
                "calibration": [
                    {"pixel": [41, 149], "value": 0},
                    {"pixel": [219, 151], "value": 100},
                ]
            },
            "yAxis": {
                "calibration": [
                    {"pixel": [39, 150], "value": 0},
                    {"pixel": [42, 20], "value": 1},
                ]
            },
        }
        with tempfile.TemporaryDirectory() as temp:
            image_path = Path(temp) / "calibrated_curve.png"
            _write_chart_image(image_path, lines=[("#d62728", [(40, 140), (220, 40)])])
            result = analyze_chart_element(_figure_element(image_path), _index(), sample_count=5, calibration=calibration)

        axes = result["subplots"][0]["axes"]
        self.assertEqual(axes["x"]["source"], "manual_calibration")
        self.assertEqual(axes["x"]["calibration"][0]["pixel"], [41.0, 149.0])
        self.assertEqual(axes["x"]["calibration"][1]["pixel"], [219.0, 151.0])
        self.assertEqual(axes["y"]["calibration"][0]["pixel"], [39.0, 150.0])
        self.assertEqual(axes["y"]["calibration"][1]["pixel"], [42.0, 20.0])

    def test_pdf_text_ticks_calibrate_axes_without_manual_values(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            image_path = Path(temp) / "pdf_text_ticks.png"
            _write_chart_image(image_path, lines=[("#d62728", [(40, 140), (220, 40)])])
            element = _figure_element(image_path, "Fig. 1 line chart")
            element["metadata"] = {"clipBBox": [0, 0, 260, 180], "zoom": 1.0, "imageWidth": 260}
            index = {
                "sourcePath": "paper.pdf",
                "sourceSha256": "sha",
                "pages": [
                    {
                        "page": 0,
                        "textBlocks": [
                            {"bbox": [35, 160, 45, 170], "text": "0"},
                            {"bbox": [210, 160, 230, 170], "text": "100"},
                            {"bbox": [12, 145, 28, 155], "text": "0"},
                            {"bbox": [12, 15, 28, 25], "text": "1"},
                            {"bbox": [224, 42, 255, 54], "text": "Red curve"},
                        ],
                    }
                ],
            }
            result = analyze_chart_element(element, index, sample_count=5, calibration={"plotAreaPx": [40, 20, 220, 150]})

        axes = result["subplots"][0]["axes"]
        self.assertEqual(axes["x"]["source"], "pdf_text")
        self.assertEqual(axes["y"]["source"], "pdf_text")
        self.assertAlmostEqual(axes["x"]["min"], 0.0)
        self.assertAlmostEqual(axes["x"]["max"], 100.0)
        self.assertAlmostEqual(axes["y"]["min"], 0.0)
        self.assertAlmostEqual(axes["y"]["max"], 1.0)
        self.assertFalse(result["analysis"]["needsReview"])
        legend_candidates = result["subplots"][0]["legendCandidates"]
        self.assertEqual(legend_candidates[0]["text"], "Red curve")
        self.assertEqual(legend_candidates[0]["source"], "pdf_text")
        series = result["subplots"][0]["series"][0]
        self.assertEqual(series["name"], "Red curve")
        self.assertEqual(series["nameSource"], "pdf_text_legend")
        self.assertEqual(series["legendCandidate"]["text"], "Red curve")

    def test_pdf_text_tick_blocks_with_multiple_numbers_calibrate_axes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            image_path = Path(temp) / "pdf_text_tick_blocks.png"
            _write_chart_image(image_path, lines=[("#d62728", [(40, 140), (220, 40)])])
            element = _figure_element(image_path, "Fig. 1 line chart")
            element["metadata"] = {"clipBBox": [0, 0, 260, 180], "zoom": 1.0, "imageWidth": 260}
            index = {
                "sourcePath": "paper.pdf",
                "sourceSha256": "sha",
                "pages": [
                    {
                        "page": 0,
                        "textBlocks": [
                            {"bbox": [40, 160, 220, 170], "text": "0 50 100"},
                            {"bbox": [10, 20, 28, 150], "text": "1 0.5 0"},
                        ],
                    }
                ],
            }
            result = analyze_chart_element(element, index, sample_count=5, calibration={"plotAreaPx": [40, 20, 220, 150]})

        axes = result["subplots"][0]["axes"]
        self.assertEqual(axes["x"]["source"], "pdf_text")
        self.assertEqual(axes["y"]["source"], "pdf_text")
        self.assertAlmostEqual(axes["x"]["min"], 0.0)
        self.assertAlmostEqual(axes["x"]["max"], 100.0)
        self.assertAlmostEqual(axes["y"]["min"], 0.0)
        self.assertAlmostEqual(axes["y"]["max"], 1.0)

    def test_pdf_text_axes_reduce_review_when_geometry_axis_confidence_is_low(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            image_path = Path(temp) / "weak_axes_pdf_text.png"
            _write_chart_image(image_path, lines=[("#d62728", [(40, 140), (220, 40)])], axis_color="#eeeeee")
            element = _figure_element(image_path, "Fig. 1 line chart")
            element["metadata"] = {"clipBBox": [0, 0, 260, 180], "zoom": 1.0, "imageWidth": 260}
            index = {
                "sourcePath": "paper.pdf",
                "sourceSha256": "sha",
                "pages": [
                    {
                        "page": 0,
                        "textBlocks": [
                            {"bbox": [40, 160, 220, 170], "text": "0 50 100"},
                            {"bbox": [10, 20, 28, 150], "text": "1 0.5 0"},
                        ],
                    }
                ],
            }
            result = analyze_chart_element(element, index, sample_count=5, calibration={"plotAreaPx": [40, 20, 220, 150]})

        self.assertFalse(result["analysis"]["needsReview"])
        self.assertEqual(result["analysis"]["status"], "自动结果")
        self.assertNotIn("坐标轴识别置信度低", "\n".join(result["analysis"]["warnings"]))

    def test_multiple_colored_series_are_kept_separate(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            image_path = Path(temp) / "multi_series.png"
            _write_chart_image(
                image_path,
                lines=[
                    ("#d62728", [(40, 140), (220, 42)]),
                    ("#1f77b4", [(40, 58), (220, 120)]),
                ],
            )
            result = analyze_chart_element(_figure_element(image_path), _index(), sample_count=10, calibration=_calibration())

        self.assertGreaterEqual(len(result["subplots"][0]["series"]), 2)
        colors = {entry["color"] for entry in result["subplots"][0]["series"]}
        self.assertGreaterEqual(len(colors), 2)

    def test_gray_curve_with_grid_is_extracted_as_one_series(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            image_path = Path(temp) / "gray_grid_curve.png"
            _write_chart_image(
                image_path,
                lines=[("#777777", [(40, 135), (120, 76), (220, 44)])],
                grid_color="#b9b9b9",
                vertical_grid=True,
            )
            result = analyze_chart_element(_figure_element(image_path), _index(), sample_count=8, calibration=_calibration())

        series = result["subplots"][0]["series"]
        self.assertEqual(len(series), 1)
        self.assertGreaterEqual(series[0]["confidence"], 0.70)
        self.assertFalse(series[0]["points"][3]["missing"])

    def test_broken_line_marks_missing_points_for_review(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            image_path = Path(temp) / "broken_line.png"
            _write_chart_image(
                image_path,
                lines=[
                    ("#d62728", [(52, 132), (75, 118)]),
                    ("#d62728", [(108, 96), (130, 82)]),
                    ("#d62728", [(165, 60), (188, 48)]),
                ],
            )
            result = analyze_chart_element(_figure_element(image_path), _index(), sample_count=10, calibration=_calibration())

        series = result["subplots"][0]["series"][0]
        self.assertTrue(series["needsReview"])
        self.assertTrue(any(point["missing"] for point in series["points"]))
        self.assertTrue(series["warnings"])
        self.assertTrue(result["analysis"]["needsReview"])

    def test_manual_series_seed_filters_to_selected_curve(self) -> None:
        calibration = dict(_calibration())
        calibration["seriesSeeds"] = [{"pixel": [100, 108], "name": "Red curve"}]
        with tempfile.TemporaryDirectory() as temp:
            image_path = Path(temp) / "seeded_series.png"
            _write_chart_image(
                image_path,
                lines=[
                    ("#d62728", [(40, 140), (220, 42)]),
                    ("#1f77b4", [(40, 58), (220, 120)]),
                ],
            )
            result = analyze_chart_element(_figure_element(image_path), _index(), sample_count=10, calibration=calibration)

        series = result["subplots"][0]["series"]
        self.assertEqual(len(series), 1)
        self.assertEqual(series[0]["name"], "Red curve")
        self.assertEqual(series[0]["seedPixel"], [100.0, 108.0])

    def test_multiple_subplots_keep_independent_result_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            image_path = Path(temp) / "subplots.png"
            _write_wide_subplot_image(image_path)
            result = analyze_chart_element(_figure_element(image_path, "Fig. 2 curves"), _index(), sample_count=5)

        self.assertEqual(validate_chart_result(result), [])
        self.assertEqual(len(result["subplots"]), 2)
        self.assertEqual(result["subplots"][0]["subplotId"], "subplot_1")
        self.assertEqual(result["subplots"][1]["subplotId"], "subplot_2")

    def test_four_panel_subplot_grid_is_split_into_independent_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            image_path = Path(temp) / "four_subplots.png"
            _write_four_subplot_image(image_path)
            result = analyze_chart_element(_figure_element(image_path, "Fig. 3 four curve panels"), _index(), sample_count=5)

        self.assertEqual(validate_chart_result(result), [])
        self.assertEqual(len(result["subplots"]), 4)
        self.assertEqual([item["subplotId"] for item in result["subplots"]], ["subplot_1", "subplot_2", "subplot_3", "subplot_4"])
        self.assertEqual(result["subplots"][0]["bboxPx"], [0.0, 0.0, 280.0, 190.0])
        self.assertEqual(result["subplots"][3]["bboxPx"], [280.0, 190.0, 560.0, 380.0])
        self.assertTrue(all(item["series"] for item in result["subplots"]))

    def test_three_panel_subplot_row_is_split_into_independent_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            image_path = Path(temp) / "three_subplots.png"
            _write_three_subplot_image(image_path)
            result = analyze_chart_element(_figure_element(image_path, "Fig. 4 three curve panels"), _index(), sample_count=5)

        self.assertEqual(validate_chart_result(result), [])
        self.assertEqual(len(result["subplots"]), 3)
        self.assertEqual([item["subplotId"] for item in result["subplots"]], ["subplot_1", "subplot_2", "subplot_3"])
        self.assertTrue(all(item["series"] for item in result["subplots"]))

    def test_manual_subplot_bbox_overrides_auto_split(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            image_path = Path(temp) / "manual_subplot.png"
            _write_wide_subplot_image(image_path)
            result = analyze_chart_element(
                _figure_element(image_path, "Fig. 2 curves"),
                _index(),
                sample_count=5,
                calibration={"subplots": [{"bboxPx": [280, 0, 560, 180]}]},
            )

        self.assertEqual(validate_chart_result(result), [])
        self.assertEqual(len(result["subplots"]), 1)
        self.assertEqual(result["subplots"][0]["bboxPx"], [280.0, 0.0, 560.0, 180.0])

    def test_non_line_or_low_confidence_image_is_skipped_by_axis_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            image_path = Path(temp) / "blank.png"
            image = QImage(160, 120, QImage.Format_RGB32)
            image.fill(QColor("#ffffff"))
            image.save(str(image_path))
            result = analyze_chart_element(_figure_element(image_path, "SEM photo of sample"), _index(), sample_count=10)

        self.assertFalse(result["analysis"]["needsReview"])
        self.assertFalse(result["analysis"]["eligible"])
        self.assertEqual(result["analysis"]["chartType"], "unsupported")
        self.assertEqual(result["subplots"], [])

    def test_dense_text_rows_do_not_impersonate_coordinate_axes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            image_path = Path(temp) / "dense_text.png"
            image = QImage(320, 220, QImage.Format_RGB32)
            image.fill(QColor("#ffffff"))
            painter = QPainter(image)
            painter.setPen(QPen(QColor("#111111"), 2))
            for y in range(18, 205, 13):
                for x in range(16, 300, 34):
                    painter.drawLine(x, y, min(310, x + 20), y)
            painter.end()
            image.save(str(image_path))
            result = analyze_chart_element(_figure_element(image_path, "Fig. 1 line profile"), _index(), sample_count=10)

        self.assertEqual(result["analysis"]["chartType"], "unsupported")
        self.assertFalse(result["analysis"]["eligible"])

    def test_table_grid_is_not_treated_as_multiple_chart_axes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            image_path = Path(temp) / "table.png"
            image = QImage(360, 240, QImage.Format_RGB32)
            image.fill(QColor("#ffffff"))
            painter = QPainter(image)
            painter.setPen(QPen(QColor("#111111"), 2))
            for y in (20, 60, 100, 140, 180, 220):
                painter.drawLine(15, y, 345, y)
            for x in (15, 120, 240, 345):
                painter.drawLine(x, 20, x, 220)
            painter.end()
            image.save(str(image_path))
            result = analyze_chart_element(_figure_element(image_path, "Fig. line data"), _index())

        self.assertEqual(result["analysis"]["chartType"], "unsupported")
        self.assertIn("表格", " ".join(result["analysis"]["warnings"]))

    def test_review_warnings_use_readable_chinese(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            image_path = Path(temp) / "review.png"
            _write_chart_image(image_path, lines=[("#d62728", [(52, 132), (75, 118)])])
            result = analyze_chart_element(_figure_element(image_path), _index(), sample_count=10, calibration=_calibration())

        analysis = result["analysis"]
        warnings = "`n".join(analysis["warnings"])
        self.assertIn("需要手动校准", analysis["status"])
        self.assertIn("需要手动校准", warnings)
        self.assertNotIn("闇", warnings)
        self.assertNotIn("鍥", warnings)


def _write_chart_image(
    path: Path,
    lines: list[tuple[str, list[tuple[int, int]]]],
    *,
    grid_color: str = "#e5e7eb",
    vertical_grid: bool = False,
    axis_color: str = "#111111",
) -> None:
    image = QImage(260, 180, QImage.Format_RGB32)
    image.fill(QColor("#ffffff"))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing, False)
    painter.setPen(QPen(QColor(axis_color), 2))
    painter.drawLine(40, 150, 230, 150)
    painter.drawLine(40, 20, 40, 150)
    painter.setPen(QPen(QColor(grid_color), 1))
    for y in (52, 85, 118):
        painter.drawLine(41, y, 230, y)
    if vertical_grid:
        for x in (85, 130, 175):
            painter.drawLine(x, 20, x, 149)
    for color, points in lines:
        painter.setPen(QPen(QColor(color), 3))
        for start, end in zip(points, points[1:]):
            painter.drawLine(start[0], start[1], end[0], end[1])
    painter.end()
    image.save(str(path))


def _write_wide_subplot_image(path: Path) -> None:
    image = QImage(560, 180, QImage.Format_RGB32)
    image.fill(QColor("#ffffff"))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing, False)
    for offset, color in ((0, "#d62728"), (280, "#1f77b4")):
        painter.setPen(QPen(QColor("#111111"), 2))
        painter.drawLine(offset + 40, 150, offset + 250, 150)
        painter.drawLine(offset + 40, 20, offset + 40, 150)
        painter.setPen(QPen(QColor(color), 3))
        painter.drawLine(offset + 40, 135, offset + 250, 45)
    painter.end()
    image.save(str(path))


def _write_four_subplot_image(path: Path) -> None:
    image = QImage(560, 380, QImage.Format_RGB32)
    image.fill(QColor("#ffffff"))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing, False)
    panels = [
        (0, 0, "#d62728", [(40, 150), (250, 50)]),
        (280, 0, "#1f77b4", [(320, 55), (530, 145)]),
        (0, 190, "#2ca02c", [(40, 330), (250, 240)]),
        (280, 190, "#9467bd", [(320, 315), (410, 265), (530, 240)]),
    ]
    for offset_x, offset_y, color, points in panels:
        painter.setPen(QPen(QColor("#111111"), 2))
        painter.drawLine(offset_x + 40, offset_y + 150, offset_x + 250, offset_y + 150)
        painter.drawLine(offset_x + 40, offset_y + 20, offset_x + 40, offset_y + 150)
        painter.setPen(QPen(QColor(color), 3))
        for start, end in zip(points, points[1:]):
            painter.drawLine(start[0], start[1], end[0], end[1])
    painter.end()
    image.save(str(path))


def _write_three_subplot_image(path: Path) -> None:
    image = QImage(780, 180, QImage.Format_RGB32)
    image.fill(QColor("#ffffff"))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing, False)
    panels = [
        (0, "#d62728", [(40, 135), (230, 45)]),
        (260, "#1f77b4", [(300, 55), (490, 130)]),
        (520, "#2ca02c", [(560, 135), (750, 50)]),
    ]
    for offset_x, color, points in panels:
        painter.setPen(QPen(QColor("#111111"), 2))
        painter.drawLine(offset_x + 40, 150, offset_x + 245, 150)
        painter.drawLine(offset_x + 40, 20, offset_x + 40, 150)
        painter.setPen(QPen(QColor(color), 3))
        for start, end in zip(points, points[1:]):
            painter.drawLine(start[0], start[1], end[0], end[1])
    painter.end()
    image.save(str(path))


def _figure_element(path: Path, caption: str = "Fig. 1 line chart") -> dict[str, object]:
    return {"id": "figure_1", "type": "figure", "page": 0, "pngPath": str(path), "caption": caption}


def _index() -> dict[str, object]:
    return {"sourcePath": "paper.pdf", "sourceSha256": "sha"}


def _calibration() -> dict[str, object]:
    return {
        "plotAreaPx": [40, 20, 220, 150],
        "xAxis": {
            "calibration": [
                {"pixel": [40, 150], "value": 0},
                {"pixel": [220, 150], "value": 100},
            ]
        },
        "yAxis": {
            "calibration": [
                {"pixel": [40, 150], "value": 0},
                {"pixel": [40, 20], "value": 1},
            ]
        },
    }


if __name__ == "__main__":
    unittest.main()
