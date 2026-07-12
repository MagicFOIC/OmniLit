from __future__ import annotations

import tempfile
import unittest
import json
from pathlib import Path

try:
    from PySide6.QtGui import QColor, QImage, QPainter, QPen
except ModuleNotFoundError:  # pragma: no cover - depends on local test runtime.
    QColor = None
    QImage = None
    QPainter = None
    QPen = None

from omnilit_qt.chart_digitizer_validation import (
    format_manifest_validation_markdown,
    format_synthetic_validation_markdown,
    main,
    run_manifest_validation,
    run_synthetic_validation,
    run_validation_report,
)


@unittest.skipUnless(QImage is not None, "PySide6 is not installed in this environment")
class ChartDigitizerValidationTests(unittest.TestCase):
    def test_synthetic_validation_runs_all_required_cases(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            report = run_synthetic_validation(Path(temp))

        self.assertFalse(report["skipped"])
        self.assertEqual(report["caseCount"], 10)
        case_ids = {item["caseId"] for item in report["cases"]}
        self.assertEqual(case_ids, {f"V{i}" for i in range(1, 11)})
        self.assertGreaterEqual(report["metrics"]["chartRecognitionSuccessRate"], 0.9)
        self.assertGreaterEqual(report["metrics"]["seriesSeparationAccuracy"], 0.8)
        self.assertGreaterEqual(report["metrics"]["legendMatchedCount"], 1)

    def test_synthetic_validation_markdown_contains_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            markdown = format_synthetic_validation_markdown(run_synthetic_validation(Path(temp)))

        self.assertIn("Synthetic Baseline", markdown)
        self.assertIn("Automatic chart recognition success rate", markdown)
        self.assertIn("V10", markdown)

    def test_manifest_validation_runs_local_figure_images(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            image_path = root / "figure.png"
            _write_manifest_chart_image(image_path)
            manifest_path = root / "manifest.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "pdfPath": str(root / "paper.pdf"),
                        "sourceSha256": "sha",
                        "cases": [
                            {
                                "caseId": "R1",
                                "pdfName": "local-paper.pdf",
                                "figure": "Fig. 1",
                                "chartKind": "single line",
                                "figureImagePath": "figure.png",
                                "expectedSubplots": 1,
                                "expectedSeries": 1,
                                "sampleCount": 3,
                                "expectedPoints": [
                                    {"seriesIndex": 0, "index": 0, "x": 0, "y": 0.076923},
                                    {"seriesIndex": 0, "index": 1, "x": 50, "y": 0.461538},
                                    {"seriesIndex": 0, "index": 2, "x": 100, "y": 0.846154},
                                ],
                                "calibration": _manifest_calibration(),
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            report = run_manifest_validation(manifest_path)
            markdown = format_manifest_validation_markdown(report)

        self.assertFalse(report["skipped"])
        self.assertEqual(report["caseCount"], 1)
        self.assertEqual(report["cases"][0]["caseId"], "R1")
        self.assertEqual(report["cases"][0]["status"], "pass")
        self.assertEqual(report["cases"][0]["pointError"]["count"], 3)
        self.assertLess(report["cases"][0]["pointRmse"], 0.05)
        self.assertLess(report["metrics"]["meanPointRmse"], 0.05)
        self.assertIn("Local Manifest Validation", markdown)
        self.assertIn("Mean point RMSE", markdown)
        self.assertIn("local-paper.pdf", markdown)

    def test_manifest_validation_marks_missing_local_images(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            manifest_path = Path(temp) / "manifest.json"
            manifest_path.write_text(
                json.dumps({"cases": [{"caseId": "R2", "figureImagePath": "missing.png"}]}),
                encoding="utf-8",
            )

            report = run_manifest_validation(manifest_path)

        self.assertEqual(report["caseCount"], 1)
        self.assertEqual(report["cases"][0]["status"], "missing")
        self.assertTrue(report["cases"][0]["needsReview"])

    def test_validation_report_writes_markdown_and_json_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            report = run_validation_report(
                synthetic=True,
                synthetic_output_dir=root / "images",
                markdown_path=root / "report.md",
                json_path=root / "report.json",
            )

            markdown = (root / "report.md").read_text(encoding="utf-8")
            payload = json.loads((root / "report.json").read_text(encoding="utf-8"))

        self.assertEqual(report["caseCount"], 10)
        self.assertIn("Synthetic Baseline", markdown)
        self.assertEqual(payload["validationKind"], "synthetic")
        self.assertNotIn("markdown", payload)

    def test_validation_cli_quiet_mode_writes_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            exit_code = main(
                [
                    "--synthetic",
                    "--synthetic-output-dir",
                    str(root / "images"),
                    "--out",
                    str(root / "report.md"),
                    "--json-out",
                    str(root / "report.json"),
                    "--quiet",
                ]
            )

            markdown = (root / "report.md").read_text(encoding="utf-8")
            payload = json.loads((root / "report.json").read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertIn("Automatic chart recognition success rate", markdown)
        self.assertEqual(payload["caseCount"], 10)


if __name__ == "__main__":
    unittest.main()


def _write_manifest_chart_image(path: Path) -> None:
    image = QImage(260, 180, QImage.Format_RGB32)
    image.fill(QColor("#ffffff"))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing, False)
    painter.setPen(QPen(QColor("#111111"), 2))
    painter.drawLine(40, 150, 230, 150)
    painter.drawLine(40, 20, 40, 150)
    painter.setPen(QPen(QColor("#d62728"), 3))
    painter.drawLine(40, 140, 220, 40)
    painter.end()
    image.save(str(path))


def _manifest_calibration() -> dict[str, object]:
    return {
        "plotAreaPx": [40, 20, 220, 150],
        "xAxis": {"calibration": [{"pixel": [40, 150], "value": 0}, {"pixel": [220, 150], "value": 100}]},
        "yAxis": {"calibration": [{"pixel": [40, 150], "value": 0}, {"pixel": [40, 20], "value": 1}]},
    }
