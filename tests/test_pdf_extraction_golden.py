from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from omnilit_qt.pdf_extraction_core import analyze_pdf
from omnilit_qt.pdf_extraction_eval import evaluate_extraction_index

try:
    from tests.test_pdf_extraction_core import write_sample_pdf
except unittest.SkipTest as exc:  # pragma: no cover - depends on local test runtime.
    raise exc


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "pdf_extraction"


class PdfExtractionGoldenTests(unittest.TestCase):
    def test_sample_academic_pdf_matches_golden_structure(self) -> None:
        golden = json.loads((FIXTURE_ROOT / "sample_academic.expected.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pdf_path = root / "sample_academic.pdf"
            output_dir = root / "out"
            write_sample_pdf(pdf_path)

            actual = analyze_pdf(pdf_path, output_dir)
            report = evaluate_extraction_index(actual, golden)

            self.assertTrue(report["summary"]["passed"], json.dumps(report["issues"], ensure_ascii=False, indent=2))
            self.assertEqual(report["summary"]["byType"]["table"], {"expected": 1, "actual": 1, "matched": 1})
            self.assertEqual(report["summary"]["byType"]["formula"], {"expected": 2, "actual": 2, "matched": 2})
            self.assertEqual(report["summary"]["byType"]["figure"], {"expected": 1, "actual": 1, "matched": 1})
            self.assertGreaterEqual(report["summary"]["meanBBoxIoU"], 0.95)
            self.assertTrue((output_dir / "parsed.md").exists())
            self.assertTrue((output_dir / "quality_report.json").exists())


if __name__ == "__main__":
    unittest.main()
