from __future__ import annotations

import unittest

from omnilit_qt.chart_digitizer_ocr import _axis_from_ticks


class ChartDigitizerOcrTests(unittest.TestCase):
    def test_robust_axis_fit_rejects_single_bad_ocr_tick(self) -> None:
        ticks = [
            {"pixel": [10, 50], "value": 0, "text": "0", "confidence": 0.99},
            {"pixel": [20, 50], "value": 10, "text": "10", "confidence": 0.99},
            {"pixel": [30, 50], "value": 99, "text": "99", "confidence": 0.80},
            {"pixel": [40, 50], "value": 30, "text": "30", "confidence": 0.99},
            {"pixel": [50, 50], "value": 40, "text": "40", "confidence": 0.99},
        ]
        axis = _axis_from_ticks(ticks, axis="x", source="rapidocr")
        self.assertIsNotNone(axis)
        self.assertEqual(axis["source"], "rapidocr")
        self.assertGreaterEqual(axis["tickCount"], 4)
        self.assertAlmostEqual(axis["calibration"][0]["value"], 0.0, delta=0.1)
        self.assertAlmostEqual(axis["calibration"][1]["value"], 40.0, delta=0.1)

    def test_two_high_confidence_rapidocr_ticks_can_calibrate_axis(self) -> None:
        ticks = [
            {"pixel": [30, 100], "value": -2, "text": "-2", "confidence": 0.99},
            {"pixel": [30, 20], "value": 2, "text": "2", "confidence": 0.99},
        ]
        axis = _axis_from_ticks(ticks, axis="y", source="rapidocr")
        self.assertIsNotNone(axis)
        self.assertAlmostEqual(axis["calibration"][0]["value"], -2.0)
        self.assertAlmostEqual(axis["calibration"][1]["value"], 2.0)

    def test_two_low_confidence_template_ticks_are_not_trusted(self) -> None:
        ticks = [
            {"pixel": [10, 20], "value": 0, "text": "0", "confidence": 0.7},
            {"pixel": [50, 20], "value": 10, "text": "10", "confidence": 0.7},
        ]
        self.assertIsNone(_axis_from_ticks(ticks, axis="x", source="image_template_ocr"))


if __name__ == "__main__":
    unittest.main()
