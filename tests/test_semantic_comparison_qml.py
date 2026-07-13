from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
QML_DIR = ROOT / "ui" / "qml"


class SemanticComparisonQmlTests(unittest.TestCase):
    def test_matrix_exposes_orkg_dimensions_provenance_and_missing_semantics(self) -> None:
        matrix = (QML_DIR / "ComparisonMatrix.qml").read_text(encoding="utf-8")
        for token in (
            "ORKG 对比维度", "comparison.dimensions", "comparison.papers", "置信", "证据",
            "自动抽取", "人工审阅", "待核验", "信息缺失", "未识别（不等于不存在）",
            "Accessible.name", "cellRequested",
        ):
            self.assertIn(token, matrix)

    def test_review_panel_preserves_automatic_extraction_and_supports_four_actions(self) -> None:
        panel = (QML_DIR / "SemanticReviewPanel.qml").read_text(encoding="utf-8")
        page = (QML_DIR / "LiteratureCompareGraphPage.qml").read_text(encoding="utf-8")
        for token in (
            "确认自动结果", "修正为", "补充一项", "排除自动结果", "automaticItems",
            "自动抽取始终保留", "撤销人工审阅", "reviewRequested", "clearRequested",
        ):
            self.assertIn(token, panel)
        for token in (
            "semanticComparison", "selectedSemanticCell", "selectSemanticCell", "reviewSemanticCell",
            "clearSemanticReview", "待核验冲突", "缺失表示未识别到",
        ):
            self.assertIn(token, page)


if __name__ == "__main__":
    unittest.main()
