"""Regression test for load_company_info_sec.py's WeightedAverageNumberOfSharesOutstandingBasic
last-resort shares_outstanding source.

FIXED 2026-09-02 (SEC/XBRL missing-data sweep): when a filer tags NEITHER
dei:EntityCommonStockSharesOutstanding NOR us-gaap:CommonStockSharesOutstanding at all, and the
raw-filing-text fallback also finds nothing, shares_outstanding was left permanently NULL
(shares_outstanding_unavailable_reason="shares_outstanding_not_in_xbrl_or_filing_text") even
when a fresh, real WeightedAverageNumberOfSharesOutstandingBasic value exists every quarter -
live-confirmed via AMRC (Ameresco) and MWH, both real active symbols with zero entries for
either instant concept in their entire companyfacts history. Only trusted for a single-common-
ticker CIK (no dual/multi-class ambiguity) - same guard as the filing-text fallback's
multi_ticker_cik check.
"""

from unittest.mock import MagicMock

from loaders.load_company_info_sec import CompanyInfoSECLoader


def _loader() -> CompanyInfoSECLoader:
    loader = CompanyInfoSECLoader.__new__(CompanyInfoSECLoader)
    loader.sec_client = MagicMock()
    return loader


def _submissions(tickers: list[str]) -> dict:
    return {
        "name": "Test Co.",
        "sic": "1600",
        "sicDescription": "TEST",
        "entityType": "operating",
        "filings": {"recent": {"form": ["10-K", "10-Q"]}},
        "tickers": tickers,
    }


class TestWeightedAverageSharesLastResort:
    def test_recovers_shares_outstanding_from_weighted_average_when_single_ticker(self):
        """AMRC-shaped fixture: dei and us-gaap instant concepts both entirely absent, but a
        real, fresh WeightedAverageNumberOfSharesOutstandingBasic exists. Single registered
        ticker (no dual-class ambiguity) - should be trusted as the shares_outstanding value."""
        loader = _loader()
        loader.sec_client.symbol_to_cik.return_value = "0001488139"
        loader.sec_client.get_submissions.return_value = _submissions(["AMRC"])
        loader.sec_client.get_company_facts.return_value = {
            "facts": {
                "dei": {},
                "us-gaap": {
                    "WeightedAverageNumberOfSharesOutstandingBasic": {
                        "units": {
                            "shares": [
                                {"start": "2026-01-01", "end": "2026-06-30", "val": 52_937_000, "form": "10-Q"},
                                {"start": "2026-04-01", "end": "2026-06-30", "val": 52_987_000, "form": "10-Q"},
                            ]
                        }
                    }
                },
            }
        }
        loader.sec_client.get_filing_plaintext.return_value = ""

        result = loader.fetch_incremental("AMRC", None)

        assert result[0]["shares_outstanding"] == 52_937_000
        assert result[0]["shares_outstanding_unavailable_reason"] is None

    def test_does_not_fire_for_dual_class_cik(self):
        """MKC-shaped fixture: this CIK has two registered common tickers (MKC/MKC-V) - the
        combined weighted-average total can't be safely assigned to one specific class, so
        this must stay unresolved rather than assign the same combined figure to both."""
        loader = _loader()
        loader.sec_client.symbol_to_cik.return_value = "0000063754"
        loader.sec_client.get_submissions.return_value = _submissions(["MKC", "MKC-V"])
        loader.sec_client.get_company_facts.return_value = {
            "facts": {
                "dei": {},
                "us-gaap": {
                    "WeightedAverageNumberOfSharesOutstandingBasic": {
                        "units": {"shares": [{"start": "2025-12-01", "end": "2026-05-31", "val": 269_000_000}]}
                    }
                },
            }
        }
        loader.sec_client.get_filing_plaintext.return_value = ""

        result = loader.fetch_incremental("MKC", None)

        assert result[0]["shares_outstanding"] is None
        assert result[0]["shares_outstanding_unavailable_reason"] == "shares_outstanding_not_in_xbrl_or_filing_text"

    def test_does_not_fire_when_an_instant_concept_already_resolved(self):
        """When dei already produced a value, the weighted-average tier must never be
        reached at all - it's a last resort, not a competing candidate."""
        loader = _loader()
        loader.sec_client.symbol_to_cik.return_value = "0000320193"
        loader.sec_client.get_submissions.return_value = _submissions(["AAPL"])
        loader.sec_client.get_company_facts.return_value = {
            "facts": {
                "dei": {
                    "EntityCommonStockSharesOutstanding": {
                        "units": {"shares": [{"end": "2026-06-30", "val": 14_594_180_000}]}
                    }
                },
                "us-gaap": {
                    "WeightedAverageNumberOfSharesOutstandingBasic": {
                        "units": {"shares": [{"start": "2026-01-01", "end": "2026-06-30", "val": 1}]}
                    }
                },
            }
        }

        result = loader.fetch_incremental("AAPL", None)

        assert result[0]["shares_outstanding"] == 14_594_180_000
