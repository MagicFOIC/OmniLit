from __future__ import annotations

import unittest

from omnilit_qt.pdf_extraction_table_utils import html_table_to_rows, markdown_table_to_rows


class PdfExtractionTableUtilsTests(unittest.TestCase):
    def test_markdown_table_to_rows(self) -> None:
        rows = markdown_table_to_rows("| A | B |\n|---|---|\n| 1 | 2 |")
        self.assertEqual(rows, [["A", "B"], ["1", "2"]])

    def test_html_table_to_rows(self) -> None:
        rows = html_table_to_rows("<table><tr><th>A</th><th>B</th></tr><tr><td>1</td><td>2</td></tr></table>")
        self.assertEqual(rows, [["A", "B"], ["1", "2"]])

    def test_empty_table_does_not_crash(self) -> None:
        self.assertEqual(markdown_table_to_rows(""), [])
        self.assertEqual(html_table_to_rows("<table></table>"), [])


if __name__ == "__main__":
    unittest.main()
