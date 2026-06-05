from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from Download import literature_download_core as core


def valid_pdf_bytes() -> bytes:
    try:
        import fitz
    except ImportError:
        return b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\n%%EOF\n"
    document = fitz.open()
    document.new_page()
    try:
        return document.tobytes()
    finally:
        document.close()


class PdfResponse:
    status_code = 200
    headers = {"content-type": "application/pdf"}

    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def iter_content(self, chunk_size):
        del chunk_size
        yield self.payload


class HeadResponse:
    status_code = 200
    headers = {"content-type": "application/pdf"}


class BackfillSession:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.get_urls: list[str] = []
        self.head_urls: list[str] = []
        self.closed = False

    def head(self, url, **_kwargs):
        self.head_urls.append(url)
        return HeadResponse()

    def get(self, url, **_kwargs):
        self.get_urls.append(url)
        return PdfResponse(self.payload)

    def close(self) -> None:
        self.closed = True


class PdfBackfillTests(unittest.TestCase):
    def test_backfill_skips_existing_pdf_and_downloads_doi_and_arxiv_without_crawl_state(self) -> None:
        payload = valid_pdf_bytes()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pdf_dir = root / "pdfs"
            pdf_dir.mkdir()
            existing_pdf = pdf_dir / "existing.pdf"
            existing_pdf.write_bytes(payload)
            metadata_path = root / "metadata_battery.jsonl"
            crawl_state = root / "crawl_state.json"
            crawl_state.write_text('{"keep": true}', encoding="utf-8")
            records = [
                {
                    "title": "Already has PDF",
                    "doi": "10.1/existing",
                    "local_pdf_path": "pdfs/existing.pdf",
                    "download_status": "downloaded",
                },
                {
                    "title": "Missing DOI PDF",
                    "doi": "10.1/missing",
                    "download_status": "no_candidate",
                    "open_access": {"is_oa": True},
                },
                {
                    "title": "Missing arXiv PDF",
                    "arxiv_id": "2601.00001v1",
                    "download_status": "no_candidate",
                },
            ]
            metadata_path.write_text(
                "".join(json.dumps(record) + "\n" for record in records),
                encoding="utf-8",
            )
            session = BackfillSession(payload)
            config = core.CrawlConfig(
                email="qa@example.com",
                out_dir=pdf_dir,
                meta_path=metadata_path,
                state_path=crawl_state,
                min_pdf_bytes=8,
                request_delay=0,
                page_delay=0,
                resume=True,
            )

            with patch.object(core, "build_session", return_value=session), patch.object(
                core,
                "query_openalex_work",
                return_value=None,
            ), patch.object(
                core,
                "query_unpaywall",
                return_value={
                    "is_oa": True,
                    "pdf_url": "https://repo.example/doi.pdf",
                    "pdf_urls": ["https://repo.example/doi.pdf"],
                },
            ):
                stats = core.backfill_missing_pdfs_from_metadata(config)

            self.assertEqual(stats.backfill_scanned_records, 3)
            self.assertEqual(stats.backfill_missing_pdf_records, 2)
            self.assertEqual(stats.backfill_downloaded_pdfs, 2)
            self.assertEqual(stats.backfill_failed_pdfs, 0)
            self.assertIn("https://repo.example/doi.pdf", session.get_urls)
            self.assertIn("https://arxiv.org/pdf/2601.00001v1", session.get_urls)
            self.assertEqual(crawl_state.read_text(encoding="utf-8"), '{"keep": true}')
            appended = [
                json.loads(line)
                for line in metadata_path.read_text(encoding="utf-8").splitlines()
            ][3:]
            self.assertEqual([record["download_status"] for record in appended], ["downloaded", "downloaded"])
            self.assertTrue(all(record["resolver_version"] == core.PDF_RESOLVER_VERSION for record in appended))

    def test_not_open_access_old_resolver_version_can_retry(self) -> None:
        old_record = {
            "doi": "10.1/old",
            "download_status": "not_open_access",
            "resolver_version": "oa_pdf_resolver_v1",
            "pdf_retry_attempts": 99,
            "last_pdf_retry_at": "2026-06-05T00:00:00",
        }
        current_record = {
            "doi": "10.1/current",
            "download_status": "not_open_access",
            "resolver_version": core.PDF_RESOLVER_VERSION,
            "pdf_retry_attempts": core.MAX_PERMANENT_PDF_RETRY_ATTEMPTS,
            "last_pdf_retry_at": "2026-06-05T00:00:00",
        }

        self.assertTrue(core.record_needs_pdf_retry(old_record, now=core.datetime(2026, 6, 5, 1, 0, 0)))
        self.assertFalse(core.record_needs_pdf_retry(current_record, now=core.datetime(2026, 6, 5, 1, 0, 0)))


if __name__ == "__main__":
    unittest.main()
