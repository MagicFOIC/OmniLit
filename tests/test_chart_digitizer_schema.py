from __future__ import annotations

import json
import unittest

from omnilit_qt.chart_digitizer_schema import make_empty_result, normalize_sample_count, validate_chart_result


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


if __name__ == "__main__":
    unittest.main()
