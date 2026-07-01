from __future__ import annotations

import unittest

from Download import literature_download_core as core


class DownloadSourceTests(unittest.TestCase):
    def test_source_maps_include_crossref_doaj(self) -> None:
        sources = {item["key"]: item["label"] for item in core.source_maps()}

        self.assertEqual(sources[core.SOURCE_CROSSREF], "Crossref")
        self.assertEqual(sources[core.SOURCE_DOAJ], "DOAJ")

    def test_default_sources_enable_all_supported_legal_sources(self) -> None:
        self.assertEqual(
            core.DEFAULT_SOURCES,
            [
                core.SOURCE_OPENALEX,
                core.SOURCE_EUROPE_PMC,
                core.SOURCE_ARXIV,
                core.SOURCE_CROSSREF,
                core.SOURCE_DOAJ,
            ],
        )

    def test_arxiv_query_preserves_user_inflections_for_recall(self) -> None:
        query = core.arxiv_query("lithium-sulfur batteries")

        self.assertIn('all:"lithium sulfur batteries"', query)
        self.assertIn("all:batteries", query)
        self.assertIn("all:battery", query)

    def test_arxiv_query_includes_plural_and_normalized_forms(self) -> None:
        query = core.arxiv_query("polysulfides")

        self.assertIn("all:polysulfides", query)
        self.assertIn("all:polysulfide", query)

    def test_arxiv_state_key_is_versioned(self) -> None:
        config = core.CrawlConfig()

        arxiv_key = core.state_key("battery", config, core.SOURCE_ARXIV)
        openalex_key = core.state_key("battery", config, core.SOURCE_OPENALEX)

        self.assertIn(core.ARXIV_QUERY_STATE_VERSION, arxiv_key)
        self.assertNotIn(core.ARXIV_QUERY_STATE_VERSION, openalex_key)

    def test_crossref_search_normalizes_metadata(self) -> None:
        class Response:
            @staticmethod
            def raise_for_status() -> None:
                return None

            @staticmethod
            def json() -> dict:
                return {
                    "message": {
                        "next-cursor": "next-cursor",
                        "items": [{
                            "DOI": "10.1234/example",
                            "URL": "https://doi.org/10.1234/example",
                            "title": ["Lithium-sulfur batteries with polysulfide conversion"],
                            "container-title": ["ACS Omega"],
                            "publisher": "American Chemical Society",
                            "published-online": {"date-parts": [[2024, 2, 3]]},
                            "is-referenced-by-count": 12,
                            "author": [{"given": "Ada", "family": "Lovelace"}],
                            "abstract": "<jats:p>Polysulfide shuttle suppression.</jats:p>",
                            "license": [{"URL": "https://creativecommons.org/licenses/by/4.0/"}],
                            "ISSN": ["2470-1343"],
                            "ISSN-L": "2470-1343",
                            "link": [{
                                "URL": "https://example.test/article.pdf",
                                "content-type": "application/pdf",
                            }],
                        }],
                    }
                }

        class Session:
            def __init__(self) -> None:
                self.params = None

            def get(self, _url, params=None, **_kwargs):
                self.params = params
                return Response()

        session = Session()
        config = core.CrawlConfig(email="qa@example.com", per_page=25, oa_only=True)
        data = core.search_crossref(session, "lithium-sulfur batteries", config, "*")
        item = data["results"][0]

        self.assertIn("has-license:true", session.params["filter"])
        self.assertEqual(data["meta"]["next_cursor"], "next-cursor")
        self.assertEqual(item["literature_source"], core.SOURCE_CROSSREF)
        self.assertEqual(item["source_record_id"], "crossref:10.1234/example")
        self.assertEqual(item["doi"], "10.1234/example")
        self.assertEqual(item["publication_date"], "2024-02-03")
        self.assertEqual(item["publication_year"], 2024)
        self.assertEqual(item["cited_by_count"], 12)
        self.assertEqual(item["authorships"][0]["author"]["display_name"], "Ada Lovelace")
        self.assertEqual(item["primary_location"]["source"]["display_name"], "ACS Omega")
        self.assertEqual(item["primary_location"]["source"]["issn"], ["2470-1343"])
        self.assertTrue(item["open_access"]["is_oa"])

    def test_crossref_pdf_link_without_content_type_is_kept(self) -> None:
        item = core.normalize_crossref_item({
            "DOI": "10.1234/crossref-pdf",
            "URL": "https://doi.org/10.1234/crossref-pdf",
            "title": ["Crossref PDF by URL"],
            "license": [{"URL": "https://creativecommons.org/licenses/by/4.0/"}],
            "link": [
                {"URL": "https://publisher.test/download?format=pdf"},
                {"URL": "https://publisher.test/supplement", "content-type": "text/html"},
            ],
        })

        self.assertEqual(item["primary_location"]["pdf_url"], "https://publisher.test/download?format=pdf")
        self.assertEqual(core.iter_pdf_candidates(item, None), ["https://publisher.test/download?format=pdf"])
        self.assertEqual(core.iter_pdf_candidate_details(item, None)[0].candidate_source, "publisher_rule")

    def test_crossref_resource_primary_pdf_is_kept(self) -> None:
        item = core.normalize_crossref_item({
            "DOI": "10.1234/resource-pdf",
            "URL": "https://doi.org/10.1234/resource-pdf",
            "title": ["Crossref resource PDF"],
            "license": [{"URL": "https://creativecommons.org/licenses/by/4.0/"}],
            "resource": {"primary": {"URL": "https://publisher.test/article.pdf"}},
        })

        self.assertEqual(item["primary_location"]["pdf_url"], "https://publisher.test/article.pdf")
        self.assertEqual(core.iter_pdf_candidates(item, None), ["https://publisher.test/article.pdf"])

    def test_doaj_search_normalizes_metadata(self) -> None:
        class Response:
            @staticmethod
            def raise_for_status() -> None:
                return None

            @staticmethod
            def json() -> dict:
                return {
                    "total": 2,
                    "results": [{
                        "id": "doaj-article-1",
                        "bibjson": {
                            "title": "Lithium polysulfides in sulfur cathodes",
                            "abstract": "Functional separator and Li2S8 conversion.",
                            "year": "2023",
                            "month": "7",
                            "identifier": [
                                {"type": "doi", "id": "10.5678/doaj"},
                                {"type": "eissn", "id": "23130105"},
                            ],
                            "journal": {
                                "title": "Batteries",
                                "publisher": "MDPI",
                                "eissn": "2313-0105",
                            },
                            "author": [{"name": "Jane Doe"}],
                            "license": [{"type": "CC BY", "url": "https://creativecommons.org/licenses/by/4.0/"}],
                            "link": [{
                                "type": "fulltext",
                                "url": "https://example.test/doaj.pdf",
                                "content_type": "application/pdf",
                            }],
                        },
                    }],
                }

        class Session:
            def __init__(self) -> None:
                self.url = None
                self.params = None

            def get(self, url, params=None, **_kwargs):
                self.url = url
                self.params = params
                return Response()

        session = Session()
        config = core.CrawlConfig(per_page=1, from_date="2020-01-01", to_date="2025-12-31")
        data = core.search_doaj(session, "polysulfides", config, "1")
        item = data["results"][0]

        self.assertTrue(session.url.endswith("/polysulfides"))
        self.assertEqual(session.params["page"], 1)
        self.assertEqual(session.params["pageSize"], 1)
        self.assertEqual(data["meta"]["next_cursor"], "2")
        self.assertEqual(item["literature_source"], core.SOURCE_DOAJ)
        self.assertEqual(item["source_record_id"], "doaj:doaj-article-1")
        self.assertEqual(item["doi"], "10.5678/doaj")
        self.assertEqual(item["publication_date"], "2023-07-01")
        self.assertEqual(item["authorships"][0]["author"]["display_name"], "Jane Doe")
        self.assertEqual(item["primary_location"]["source"]["display_name"], "Batteries")
        self.assertEqual(item["primary_location"]["source"]["issn"], ["2313-0105"])
        self.assertTrue(item["open_access"]["is_oa"])
        self.assertEqual(item["doaj_fulltext_links"], ["https://example.test/doaj.pdf"])

    def test_europe_pmc_search_preserves_fulltext_links_for_backfill(self) -> None:
        class Response:
            @staticmethod
            def raise_for_status() -> None:
                return None

            @staticmethod
            def json() -> dict:
                return {
                    "nextCursorMark": "next",
                    "resultList": {
                        "result": [{
                            "source": "PMC",
                            "id": "123",
                            "doi": "10.9999/epmc",
                            "title": "Lithium sulfur full text",
                            "pubYear": "2024",
                            "isOpenAccess": "Y",
                            "fullTextUrlList": {
                                "fullTextUrl": [
                                    {
                                        "availabilityCode": "OA",
                                        "documentStyle": "pdf",
                                        "url": "europepmc.test/article.pdf",
                                    }
                                ]
                            },
                        }]
                    },
                }

        class Session:
            def get(self, *_args, **_kwargs):
                return Response()

        data = core.search_europe_pmc(Session(), "lithium sulfur", core.CrawlConfig(), "*")
        item = data["results"][0]

        self.assertEqual(item["primary_location"]["pdf_url"], "europepmc.test/article.pdf")
        self.assertEqual(
            core.iter_pdf_candidates(item, None),
            [
                "https://pmc.ncbi.nlm.nih.gov/articles/PMC123/pdf/",
                "https://europepmc.test/article.pdf",
            ],
        )
        self.assertEqual(
            item["fullTextUrlList"]["fullTextUrl"][0]["url"],
            "europepmc.test/article.pdf",
        )

    def test_europe_pmc_pmcid_adds_official_pmc_pdf_candidate(self) -> None:
        class Response:
            @staticmethod
            def raise_for_status() -> None:
                return None

            @staticmethod
            def json() -> dict:
                return {
                    "nextCursorMark": "next",
                    "resultList": {
                        "result": [{
                            "source": "PMC",
                            "id": "1234567",
                            "title": "PMC open article",
                            "pubYear": "2024",
                            "isOpenAccess": "Y",
                            "fullTextUrlList": {
                                "fullTextUrl": [{
                                    "availabilityCode": "OA",
                                    "documentStyle": "html",
                                    "url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC1234567/",
                                }]
                            },
                        }]
                    },
                }

        class Session:
            def get(self, *_args, **_kwargs):
                return Response()

        data = core.search_europe_pmc(Session(), "battery", core.CrawlConfig(), "*")
        item = data["results"][0]

        self.assertEqual(item["pmcid"], "PMC1234567")
        self.assertIn(
            "https://pmc.ncbi.nlm.nih.gov/articles/PMC1234567/pdf/",
            core.iter_pdf_candidates(item, None),
        )

    def test_europe_pmc_doi_lookup_returns_pmc_and_fulltext_candidates(self) -> None:
        class Response:
            status_code = 200
            headers: dict[str, str] = {}

            @staticmethod
            def raise_for_status() -> None:
                return None

            @staticmethod
            def json() -> dict:
                return {
                    "resultList": {
                        "result": [{
                            "source": "MED",
                            "id": "987",
                            "pmcid": "PMC9876543",
                            "doi": "10.9999/epmc-doi",
                            "title": "Europe PMC DOI full text",
                            "pubYear": "2025",
                            "isOpenAccess": "Y",
                            "fullTextUrlList": {
                                "fullTextUrl": [{
                                    "availabilityCode": "OA",
                                    "documentStyle": "pdf",
                                    "url": "https://europepmc.org/articles/PMC9876543?pdf=render",
                                }]
                            },
                        }]
                    }
                }

        class Session:
            def __init__(self) -> None:
                self.params = None

            def get(self, _url, params=None, **_kwargs):
                self.params = params
                return Response()

        session = Session()
        record = core.query_europe_pmc_work_by_doi(
            session,
            "https://doi.org/10.9999/epmc-doi",
            core.CrawlConfig(request_delay=0),
        )

        self.assertEqual(session.params["query"], 'OPEN_ACCESS:Y AND DOI:"10.9999/epmc-doi"')
        self.assertEqual(record["pmcid"], "PMC9876543")
        self.assertEqual(
            core.iter_pdf_candidates(record, None),
            [
                "https://pmc.ncbi.nlm.nih.gov/articles/PMC9876543/pdf/",
                "https://europepmc.org/articles/PMC9876543?pdf=render",
            ],
        )

    def test_extract_pmcid_from_fulltext_url(self) -> None:
        record = {
            "fullTextUrlList": {
                "fullTextUrl": [{
                    "availabilityCode": "OA",
                    "documentStyle": "html",
                    "url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC7654321/",
                }]
            }
        }

        self.assertEqual(core.extract_pmcid(record), "PMC7654321")


if __name__ == "__main__":
    unittest.main()
