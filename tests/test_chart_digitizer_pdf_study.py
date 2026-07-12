from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from omnilit_qt.chart_digitizer_pdf_study import (
    _balanced_case_validation_split,
    _candidate_rank,
    discover_pdf_paths,
    format_case_study_markdown,
    format_validation_markdown,
    write_study_reports,
)


class ChartDigitizerPdfStudyTests(unittest.TestCase):
    def test_discover_pdf_paths_finds_sorted_limited_pdfs(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "b.pdf").write_bytes(b"%PDF-1.4\n")
            (root / "a.pdf").write_bytes(b"%PDF-1.4\n")
            (root / "note.txt").write_text("not a pdf", encoding="utf-8")

            paths = discover_pdf_paths(root, limit=1)

        self.assertEqual([path.name for path in paths], ["a.pdf"])

    def test_reports_include_10_plus_10_metrics_and_readable_warnings(self) -> None:
        report = _fake_report()

        case_markdown = format_case_study_markdown(report)
        validation_markdown = format_validation_markdown(report)

        self.assertIn("Chart Digitizer Case Study", case_markdown)
        self.assertIn("paper-001.pdf", case_markdown)
        self.assertIn("Automatic recognition rate", validation_markdown)
        self.assertIn("需要手动校准", validation_markdown)
        self.assertNotIn("闇", validation_markdown)

    def test_write_study_reports_writes_markdown_and_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            write_study_reports(
                _fake_report(),
                case_report=root / "case.md",
                validation_report=root / "validation.md",
                json_report=root / "report.json",
            )

            case_text = (root / "case.md").read_text(encoding="utf-8")
            payload = json.loads((root / "report.json").read_text(encoding="utf-8"))

        self.assertIn("paper-001.pdf", case_text)
        self.assertEqual(payload["caseCount"], 1)
        self.assertEqual(payload["validationCount"], 1)

    def test_candidate_rank_prefers_split_and_calibrated_chart_candidates(self) -> None:
        single = {"recognized": True, "confidence": 0.80, "needsReview": True, "subplotCount": 1, "seriesCount": 1, "axisCalibrated": False, "page": 0}
        split = {"recognized": True, "confidence": 0.74, "needsReview": True, "subplotCount": 4, "seriesCount": 4, "axisCalibrated": False, "page": 0}
        calibrated = {"recognized": True, "confidence": 0.74, "needsReview": True, "subplotCount": 1, "seriesCount": 1, "axisCalibrated": True, "page": 0}

        self.assertGreater(_candidate_rank(split), _candidate_rank(single))
        self.assertGreater(_candidate_rank(calibrated), _candidate_rank(single))

    def test_balanced_split_keeps_multi_subplot_cases_in_validation(self) -> None:
        selected = [{"subplotCount": 4, "pdfName": f"multi-{index}.pdf"} for index in range(4)]
        selected.extend({"subplotCount": 1, "pdfName": f"single-{index}.pdf"} for index in range(8))

        cases, validation = _balanced_case_validation_split(selected, 6, 6)

        self.assertEqual(len(cases), 6)
        self.assertEqual(len(validation), 6)
        self.assertGreaterEqual(sum(1 for item in cases if item["subplotCount"] > 1), 1)
        self.assertGreaterEqual(sum(1 for item in validation if item["subplotCount"] > 1), 1)


def _fake_report() -> dict[str, object]:
    item = {
        "pdfName": "paper-001.pdf",
        "page": 2,
        "figure": "Fig. 2",
        "chartType": "line_chart",
        "subplotCount": 1,
        "seriesCount": 2,
        "autoResult": "success",
        "axisResult": "auto_geometry_preview",
        "curveResult": "2 series across 1 subplot(s)",
        "failureAttribution": "axis values need manual/PDF-text calibration",
        "improvement": "add OCR/manual tick calibration",
        "needsReview": True,
        "warnings": ["需要手动校准。"],
        "jsonSample": {"schemaVersion": 1, "analysis": {"chartType": "line_chart"}},
        "conclusion": "Usable after review/calibration.",
    }
    return {
        "caseCount": 1,
        "validationCount": 1,
        "cases": [item],
        "validation": [item],
        "validationMetrics": {
            "recognitionRate": 1.0,
            "subplotSplitRate": 0.0,
            "axisCalibratedRate": 0.0,
            "seriesExtractedRate": 1.0,
            "needsReviewRate": 1.0,
        },
    }


if __name__ == "__main__":
    unittest.main()
