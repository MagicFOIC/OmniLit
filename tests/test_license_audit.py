from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.license_audit.generate_compliance import ROOT, generate


class LicenseAuditTests(unittest.TestCase):
    def test_generates_deterministic_source_sbom_notices_and_release_blockers(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            first = generate(ROOT, output, strict=True, release=False)
            first_sbom = (output / "omnilit-source.cdx.json").read_bytes()
            second = generate(ROOT, output, strict=True, release=False)
            self.assertEqual(first, second)
            self.assertEqual(first_sbom, (output / "omnilit-source.cdx.json").read_bytes())

            sbom = json.loads(first_sbom)
            self.assertEqual((sbom["bomFormat"], sbom["specVersion"]), ("CycloneDX", "1.6"))
            self.assertGreater(first["npmComponentCount"], 200)
            self.assertEqual(first["pythonComponentCount"], 2)
            self.assertIn("missing_release_file:LICENSE", first["releaseBlockers"])
            self.assertIn("cryptography==48.0.0", (ROOT / "services/cloud_api/requirements.in").read_text(encoding="utf-8"))
            notices = (output / "THIRD_PARTY_NOTICES.txt").read_text(encoding="utf-8")
            self.assertIn("@antv/g6@", notices)
            self.assertIn("cryptography@48.0.0", notices)
            self.assertIn("psycopg@3.2.9", notices)
            with self.assertRaisesRegex(RuntimeError, "Release compliance is blocked"):
                generate(ROOT, output, strict=True, release=True)


if __name__ == "__main__":
    unittest.main()
