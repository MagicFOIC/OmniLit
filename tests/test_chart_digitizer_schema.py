from __future__ import annotations

import json
import unittest

from omnilit_qt.chart_digitizer_schema import (
    chart_result_rows,
    chart_result_to_csv,
    make_empty_result,
    normalize_sample_count,
    validate_chart_result,
)


class ChartDigitizerSchemaTests(unittest.TestCase):
    def test_empty_result_has_stable_versioned_shape(self) -> None:
        result = make_empty_result(
            {"id": "fig_1", "type": "figure", "page": 2, "pngPath": "figure.png", "caption": "Fig. 1"},
            {"sourcePath": "paper.pdf", "sourceSha256": "abc"},
            record_id="record-1",
            sample_count=10,
        )

        self.assertEqual(result["schemaVersion"], 1)
        self.assertEqual(result["source"]["recordId"], "record-1")
        self.assertEqual(result["source"]["elementId"], "fig_1")
        self.assertEqual(result["analysis"]["engine"], "omnilit_chart_digitizer")
        self.assertTrue(result["analysis"]["needsReview"])
        self.assertEqual(validate_chart_result(result), [])
        json.dumps(result, ensure_ascii=False)

    def test_sample_count_is_bounded_and_customizable(self) -> None:
        self.assertEqual(normalize_sample_count("5"), 5)
        self.assertEqual(normalize_sample_count("not-a-number"), 10)
        self.assertEqual(normalize_sample_count(1), 2)
        self.assertEqual(normalize_sample_count(900), 500)

    def test_unsupported_chart_is_skipped_without_requesting_calibration(self) -> None:
        result = make_empty_result({"id": "photo_1"}, chart_type="unsupported", warnings=["没有坐标轴"])
        self.assertFalse(result["analysis"]["eligible"])
        self.assertFalse(result["analysis"]["needsReview"])
        self.assertEqual(result["analysis"]["pipeline"][0]["status"], "rejected")

    def test_csv_is_a_reusable_long_table_with_axis_and_pixel_provenance(self) -> None:
        result = make_empty_result({"id": "fig_1", "page": 3}, record_id="paper-1")
        result["subplots"] = [{
            "subplotId": "subplot_1",
            "axes": {
                "x": {"label": "Time", "scale": "linear"},
                "y": {"label": "Rate", "scale": "log"},
            },
            "series": [{
                "seriesId": "series_1", "name": "control",
                "points": [{"index": 0, "x": 1.5, "y": 8.0, "pixel": [20, 40], "confidence": 0.9, "missing": False}],
            }],
        }]
        rows = chart_result_rows(result)
        self.assertEqual(rows[0]["subplot_id"], "subplot_1")
        self.assertEqual(rows[0]["pixel_x"], 20)
        self.assertEqual(rows[0]["y_axis_scale"], "log")
        csv_text = chart_result_to_csv(result)
        self.assertIn("record_id,element_id,page,subplot_id", csv_text)
        self.assertIn("paper-1,fig_1,3,subplot_1,series_1,control", csv_text)


if __name__ == "__main__":
    unittest.main()
