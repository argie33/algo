"""Regression test for load_company_info_sec.py's us-gaap shares-outstanding fallback.

FIXED 2026-08-18 (goal: "no SEC data" loader audit): the primary path only ever checked
dei:EntityCommonStockSharesOutstanding, never falling back to us-gaap:CommonStockSharesOutstanding
when the dei tag is absent entirely. Live-confirmed via Alphabet's real companyfacts JSON
(CIK 0001652044): the dei namespace has zero share-count facts (only EntityPublicFloat) -
multi-class filers apparently skip the single-class-assuming dei cover-page tag - while the
real, usable combined share count (12,230,000,000 as of 2026-06-30) sits right there under
us-gaap:CommonStockSharesOutstanding in the same {end, val} shape. This left GOOG/GOOGL/GTLB
and other real, heavily-covered companies with shares_outstanding permanently NULL, which
cascades into institutional_holdings_13f's institutional_ownership_pct calc (needs
shares_outstanding as the denominator) and therefore positioning_metrics/positioning_score.
"""

from unittest.mock import MagicMock

from loaders.load_company_info_sec import CompanyInfoSECLoader


def _loader() -> CompanyInfoSECLoader:
    loader = CompanyInfoSECLoader.__new__(CompanyInfoSECLoader)
    loader.sec_client = MagicMock()
    return loader


def _submissions() -> dict:
    return {
        "name": "Alphabet Inc.",
        "sic": "7370",
        "sicDescription": "SERVICES-COMPUTER PROGRAMMING, DATA PROCESSING, ETC.",
        "entityType": "operating",
        "filings": {"recent": {"form": ["10-K"]}},
    }


class TestSharesOutstandingGaapFallback:
    def test_falls_back_to_us_gaap_when_dei_has_no_share_facts(self):
        """Alphabet-shaped fixture: dei namespace exists but has no share-count fact at
        all (only EntityPublicFloat); the real combined count is under us-gaap instead."""
        loader = _loader()
        loader.sec_client.symbol_to_cik.return_value = "1652044"
        loader.sec_client.get_submissions.return_value = _submissions()
        loader.sec_client.get_company_facts.return_value = {
            "facts": {
                "dei": {"EntityPublicFloat": {"units": {"USD": [{"end": "2026-06-30", "val": 2_000_000_000_000}]}}},
                "us-gaap": {
                    "CommonStockSharesOutstanding": {
                        "units": {
                            "shares": [
                                {"end": "2025-12-31", "val": 12_088_000_000},
                                {"end": "2026-06-30", "val": 12_230_000_000},
                                {"end": "2026-03-31", "val": 12_116_000_000},
                            ]
                        }
                    }
                },
            }
        }

        result = loader.fetch_incremental("GOOGL", None)

        assert result[0]["shares_outstanding"] == 12_230_000_000

    def test_dei_tag_present_still_wins_over_us_gaap(self):
        """When dei:EntityCommonStockSharesOutstanding IS present, it must still be used -
        the us-gaap fallback only fires when dei has nothing."""
        loader = _loader()
        loader.sec_client.symbol_to_cik.return_value = "0000320193"
        loader.sec_client.get_submissions.return_value = _submissions()
        loader.sec_client.get_company_facts.return_value = {
            "facts": {
                "dei": {
                    "EntityCommonStockSharesOutstanding": {
                        "units": {"shares": [{"end": "2026-06-30", "val": 14_594_180_000}]}
                    }
                },
                "us-gaap": {"CommonStockSharesOutstanding": {"units": {"shares": [{"end": "2026-06-30", "val": 999}]}}},
            }
        }

        result = loader.fetch_incremental("AAPL", None)

        assert result[0]["shares_outstanding"] == 14_594_180_000

    def test_neither_namespace_has_shares_leaves_none(self):
        """No fabrication: if neither dei nor us-gaap has a usable share fact, stay None
        (the filing-text fallback, tested separately, gets the next chance)."""
        loader = _loader()
        loader.sec_client.symbol_to_cik.return_value = "0001653482"
        loader.sec_client.get_submissions.return_value = _submissions()
        loader.sec_client.get_company_facts.return_value = {"facts": {"dei": {}, "us-gaap": {}}}
        loader.sec_client.get_filing_plaintext.return_value = ""

        result = loader.fetch_incremental("GTLB", None)

        assert result[0]["shares_outstanding"] is None
