from __future__ import annotations

import unittest
from pathlib import Path

from omnilit_qt.chart_digitizer_core import analyze_chart_element


ROOT = Path("Workspace/chart_digitizer_pdf_study/rendered_pages")
FIXED_HOLDOUT = (
    ("pdf_10_page_003_clip_02", "Table 1. Summary of cathode composition"),
    ("pdf_04_page_003_clip_01", ""),
    ("pdf_09_page_002_clip_02", ""),
    ("pdf_13_page_001_clip_02", ""),
    ("pdf_12_page_002_clip_02", ""),
    ("pdf_05_page_003_clip_02", ""),
    ("pdf_07_page_001_clip_02", ""),
    ("pdf_20_page_003_clip_01", ""),
    ("pdf_08_page_004_clip_02", ""),
    ("pdf_18_page_003_clip_01", "Figure 1. Schematic illustration of interfacial compatibility"),
)


@unittest.skipUnless(all(ROOT.joinpath(f"{name}.png").exists() for name, _ in FIXED_HOLDOUT), "local fixed holdout images are unavailable")
class ChartDigitizerRealHoldoutTests(unittest.TestCase):
    def test_original_sixty_percent_review_set_is_now_rejected_without_review(self) -> None:
        results = []
        for name, caption in FIXED_HOLDOUT:
            results.append(analyze_chart_element({
                "id": name,
                "type": "figure",
                "pngPath": str(ROOT / f"{name}.png"),
                "caption": caption,
            }))

        self.assertEqual(len(results), 10)
        self.assertTrue(all(result["analysis"]["chartType"] == "unsupported" for result in results))
        self.assertTrue(all(not result["analysis"]["needsReview"] for result in results))


if __name__ == "__main__":
    unittest.main()
