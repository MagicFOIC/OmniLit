from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


class DatePickerQmlTests(unittest.TestCase):
    def test_date_picker_supports_year_selection(self) -> None:
        qml = (ROOT / "ui" / "qml" / "DatePickerField.qml").read_text(encoding="utf-8")

        self.assertIn("id: yearPicker", qml)
        self.assertIn("function moveYear", qml)
        self.assertIn("function setYear", qml)
        self.assertIn("onValueModified: root.setYear(value)", qml)
        self.assertIn("root.moveYear(-1)", qml)
        self.assertIn("root.moveYear(1)", qml)


if __name__ == "__main__":
    unittest.main()
