from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from Download import literature_download_core as core


class DownloadDuplicatePreventionTests(unittest.TestCase):
    def test_markup_titles_keep_chemical_subscripts_without_raw_jats(self) -> None:
        self.assertEqual(
            core.clean_markup_text("<scp>RuO <sub>2</sub></scp>-Based High-Entropy Oxide"),
            "RuO₂-Based High-Entropy Oxide",
        )
        self.assertEqual(
            core.clean_markup_text("Synergistic <scp>S</scp> n <scp>S</scp> e <sub>2</sub> @Ti <sub>3</sub> C <sub>2</sub> T <sub>x</sub> / <scp>MX</scp> ene"),
            "Synergistic SnSe₂ @Ti₃C₂Tₓ/MXene",
        )
        self.assertEqual(core.clean_markup_text("<p>First sentence.</p><p>Second sentence.</p>"), "First sentence. Second sentence.")

    def test_doi_canonical_key_normalizes_prefix_and_case(self) -> None:
        left = core.canonical_record_key({"doi": "https://doi.org/10.1000/ABC"})
        right = core.canonical_record_key({"doi": "doi:10.1000/abc"})
        self.assertEqual(left, right)
        self.assertEqual(left, "doi:10.1000/abc")

    def test_arxiv_canonical_key_strips_versions(self) -> None:
        keys = {
            core.canonical_record_key({"arxiv_id": "2301.12345v1"}),
            core.canonical_record_key({"source_record_id": "2301.12345v2"}),
            core.canonical_record_key({"url": "https://arxiv.org/abs/2301.12345v3"}),
        }
        self.assertEqual(keys, {"arxiv:2301.12345"})
        self.assertEqual(core.normalize_arxiv_id("math/0301234v2"), "math/0301234")

    def test_title_year_fallback_requires_meaningful_title_and_year(self) -> None:
        left = core.canonical_record_key({"title": "A Better Lithium Sulfur Battery Separator", "publication_year": 2024})
        right = core.canonical_record_key({"title": "A better lithium-sulfur battery separator", "year": "2024"})
        self.assertEqual(left, right)
        self.assertTrue(str(left).startswith("titleyear:"))
        self.assertIsNone(core.normalized_title_year_key({"title": "Short", "year": 2024}))

    def test_openalex_canonical_key(self) -> None:
        self.assertEqual(
            core.canonical_record_key({"openalex_id": "https://openalex.org/W123"}),
            core.canonical_record_key({"id": "W123"}),
        )

    def test_load_existing_index_tracks_downloaded_canonical_pdf_and_sha(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pdf_dir = root / "pdfs"
            pdf_dir.mkdir()
            pdf_path = pdf_dir / "paper.pdf"
            pdf_path.write_bytes(b"%PDF duplicate bytes")
            metadata = root / "metadata_battery.jsonl"
            record = {
                "title": "A Better Lithium Sulfur Battery Separator",
                "publication_year": 2024,
                "source_record_id": "source-a",
                "local_pdf_path": "pdfs/paper.pdf",
                "download_status": "downloaded",
                "pdf_url": "https://example.org/paper.pdf",
            }
            metadata.write_text(json.dumps(record) + "\n", encoding="utf-8")

            with mock.patch.object(core, "validate_existing_pdf", return_value=True):
                index = core.load_existing_index(metadata, 1, pdf_dir)
            canonical = core.canonical_record_key(record)
            self.assertIn(canonical, index.downloaded_canonical_keys)
            self.assertEqual(Path(index.canonical_pdf_paths[canonical]), pdf_path)
            self.assertIn(core.pdf_sha256(pdf_path), index.pdf_sha256_paths)
            self.assertIn("https://example.org/paper.pdf", index.pdf_url_keys)

    def test_duplicate_content_reuses_existing_path_and_deletes_new_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            old_pdf = root / "old.pdf"
            new_pdf = root / "new.pdf"
            old_pdf.write_bytes(b"%PDF same content")
            new_pdf.write_bytes(b"%PDF same content")
            digest = core.pdf_sha256(old_pdf)
            index = core.ExistingIndex(set(), set(), set(), pdf_sha256_paths={digest: str(old_pdf)})

            result = core.reuse_duplicate_content_pdf(core.DownloadResult(str(new_pdf), "downloaded"), index)

            self.assertEqual(result.status, "duplicate_content_reused")
            self.assertEqual(Path(result.path), old_pdf)
            self.assertFalse(new_pdf.exists())

    def test_same_round_canonical_duplicate_downloads_once(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            meta_path = root / "metadata_battery.jsonl"
            out_dir = root / "pdfs"
            out_dir.mkdir()
            downloaded_pdf = out_dir / "downloaded.pdf"

            config = core.CrawlConfig(
                out_dir=out_dir,
                meta_path=meta_path,
                state_path=root / "crawl_state.json",
                keywords=["battery"],
                sources=[core.SOURCE_OPENALEX],
                max_pages_per_keyword=1,
                request_delay=0,
                page_delay=0,
                strict_keyword_match=False,
                min_topic_score=0,
                min_pdf_bytes=1,
                fast_forward_existing_pages=False,
                resume=False,
            )
            stats = core.CrawlStats()
            existing = core.ExistingIndex(set(), set(), set())
            records = [
                {
                    "source_record_id": "source-a",
                    "title": "A Better Lithium Sulfur Battery Separator",
                    "publication_year": 2024,
                    "open_access": {"is_oa": True, "oa_url": "https://example.org/a.pdf"},
                },
                {
                    "source_record_id": "source-b",
                    "title": "A better lithium-sulfur battery separator",
                    "publication_year": 2024,
                    "open_access": {"is_oa": True, "oa_url": "https://example.org/b.pdf"},
                },
            ]

            def fake_download(*_args, **_kwargs):
                downloaded_pdf.write_bytes(b"%PDF first download")
                return core.DownloadResult(str(downloaded_pdf), "downloaded", "https://example.org/a.pdf"), ["https://example.org/a.pdf"]

            with meta_path.open("a", encoding="utf-8") as fout:
                with mock.patch.object(core, "search_literature_source", return_value={"results": records, "meta": {"next_cursor": None}}):
                    with mock.patch.object(core, "record_passes_relevance_filters", return_value=(True, 10, "")):
                        with mock.patch.object(core, "record_passes_impact_factor_filter", return_value=(True, {})):
                            with mock.patch.object(core, "download_first_available_pdf", side_effect=fake_download) as download:
                                core.crawl_keyword(
                                    core.build_session(""),
                                    core.SOURCE_OPENALEX,
                                    "battery",
                                    existing,
                                    fout,
                                    config,
                                    stats,
                                    {},
                                )

            self.assertEqual(download.call_count, 1)
            lines = [json.loads(line) for line in meta_path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(lines), 2)
            self.assertEqual(lines[1]["download_status"], "duplicate_reused")
            self.assertEqual(lines[1]["local_pdf_path"], lines[0]["local_pdf_path"])


if __name__ == "__main__":
    unittest.main()
