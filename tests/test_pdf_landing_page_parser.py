from __future__ import annotations

import unittest

from Download import literature_download_core as core


class PdfLandingPageParserTests(unittest.TestCase):
    def test_extract_citation_pdf_url_meta(self) -> None:
        html = '<html><meta name="citation_pdf_url" content="/downloads/article.pdf"></html>'

        self.assertEqual(
            core.extract_pdf_candidates_from_html("https://publisher.test/article", html),
            ["https://publisher.test/downloads/article.pdf"],
        )

    def test_extract_link_rel_alternate_pdf(self) -> None:
        html = '<link rel="alternate" type="application/pdf" href="https://repo.test/open.pdf#page=2">'

        self.assertEqual(
            core.extract_pdf_candidates_from_html("https://publisher.test/article", html),
            ["https://repo.test/open.pdf"],
        )

    def test_extract_anchor_pdf_relative_url(self) -> None:
        html = '<a href="../pdf/article.pdf">Download PDF</a>'

        self.assertEqual(
            core.extract_pdf_candidates_from_html("https://publisher.test/articles/123", html),
            ["https://publisher.test/pdf/article.pdf"],
        )

    def test_extract_anchor_pdf_from_aria_label(self) -> None:
        html = '<a href="/download?format=pdf" aria-label="Download PDF"></a>'

        self.assertEqual(
            core.extract_pdf_candidates_from_html("https://publisher.test/articles/123", html),
            ["https://publisher.test/download?format=pdf"],
        )

    def test_extract_embedded_pdf_resources(self) -> None:
        html = """
        <iframe src="/viewer/fulltext.pdf"></iframe>
        <embed type="application/pdf" src="/embed/article?download=1"></embed>
        <object data="/object?format=pdf"></object>
        """

        self.assertEqual(
            core.extract_pdf_candidates_from_html("https://publisher.test/articles/123", html),
            [
                "https://publisher.test/viewer/fulltext.pdf",
                "https://publisher.test/embed/article?download=1",
                "https://publisher.test/object?format=pdf",
            ],
        )

    def test_extract_jsonld_content_url(self) -> None:
        html = """
        <script type="application/ld+json">
        {"@type": "ScholarlyArticle", "encoding": {"contentUrl": "/files/open.pdf"}}
        </script>
        """

        self.assertEqual(
            core.extract_pdf_candidates_from_html("https://publisher.test/article", html),
            ["https://publisher.test/files/open.pdf"],
        )

    def test_shadow_library_candidate_is_rejected(self) -> None:
        html = '<meta name="citation_pdf_url" content="https://sci-hub.example/paper.pdf">'

        self.assertEqual(core.extract_pdf_candidates_from_html("https://publisher.test/article", html), [])


if __name__ == "__main__":
    unittest.main()
