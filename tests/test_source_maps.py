from __future__ import annotations

import unittest

from Download import literature_download_core as core


class SourceMapsTests(unittest.TestCase):
    def test_source_maps_include_all_supported_sources(self) -> None:
        sources = {item["key"] for item in core.source_maps()}

        self.assertIn("openalex", sources)
        self.assertIn("europe_pmc", sources)
        self.assertIn("arxiv", sources)
        self.assertIn("crossref", sources)
        self.assertIn("doaj", sources)


if __name__ == "__main__":
    unittest.main()
