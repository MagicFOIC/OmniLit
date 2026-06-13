from __future__ import annotations

import unittest

from omnilit_qt.pdf_extraction_caption import find_nearby_caption


class PdfExtractionCaptionTests(unittest.TestCase):
    def test_figure_caption_binds_below(self) -> None:
        caption = find_nearby_caption(
            [100, 100, 300, 220],
            [{"bbox": [110, 230, 290, 250], "text": "Figure 2. Model architecture"}],
            [400, 600],
            "figure",
        )

        self.assertEqual(caption["text"], "Figure 2. Model architecture")
        self.assertEqual(caption["bbox"], [110.0, 230.0, 290.0, 250.0])

    def test_far_caption_is_ignored(self) -> None:
        caption = find_nearby_caption(
            [100, 100, 300, 150],
            [{"bbox": [110, 400, 290, 420], "text": "Figure 1. Too far"}],
            [400, 600],
            "figure",
        )

        self.assertEqual(caption, {})


if __name__ == "__main__":
    unittest.main()
