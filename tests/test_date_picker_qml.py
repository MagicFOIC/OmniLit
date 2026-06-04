from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


class DatePickerQmlTests(unittest.TestCase):
    def test_date_picker_supports_three_layer_selection_and_bounds(self) -> None:
        qml = (ROOT / "ui" / "qml" / "DatePickerField.qml").read_text(encoding="utf-8")

        self.assertIn("property alias text: input.text", qml)
        self.assertIn('property string minDateText: ""', qml)
        self.assertIn('property string maxDateText: ""', qml)
        self.assertIn("id: dayLayer", qml)
        self.assertIn("id: monthLayer", qml)
        self.assertIn("id: yearLayer", qml)
        self.assertIn("function parseIsoDate", qml)
        self.assertIn("function isInRange", qml)
        self.assertIn("function chooseMonth", qml)
        self.assertIn("function chooseYear", qml)
        self.assertIn("function moveYear", qml)
        self.assertIn("function moveYearPage", qml)

    def test_date_picker_uses_motion_durations_and_i18n_actions(self) -> None:
        qml = (ROOT / "ui" / "qml" / "DatePickerField.qml").read_text(encoding="utf-8")

        for duration in ("motion.fast", "motion.normal", "motion.expand"):
            self.assertIn(duration, qml)
        for key in ('"clear"', '"cancel"', '"confirm"', '"select_month"', '"select_year"', '"year"', '"month"'):
            self.assertIn(f"i18n.text({key})", qml)
        self.assertNotIn("年份", qml)
        self.assertNotIn("楠", qml)

    def test_download_page_binds_date_picker_min_max(self) -> None:
        qml = (ROOT / "ui" / "qml" / "DownloadPage.qml").read_text(encoding="utf-8")

        self.assertIn("maxDateText: toDate.text", qml)
        self.assertIn("minDateText: fromDate.text", qml)

    def test_i18n_contains_date_picker_keys(self) -> None:
        i18n = (ROOT / "omnilit_qt" / "i18n.py").read_text(encoding="utf-8")

        for key in ("year", "month", "clear", "cancel", "confirm", "select_month", "select_year"):
            self.assertIn(f'"{key}"', i18n)


if __name__ == "__main__":
    unittest.main()
