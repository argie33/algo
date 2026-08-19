"""Regression test for the 2026-08-19 fix ("no SEC data"/missing factor inputs audit):
load_company_info_sec.py's dei:EntityCommonStockSharesOutstanding extraction had no
domestic-forms restriction, unlike the equivalent extraction in
utils/external/sec_statements.py (which a prior session already restricted after live-
catching this exact trap via SRAD/BP/TV).

Live-confirmed via TSM (Taiwan Semiconductor, 5 ordinary shares = 1 ADS): its 20-F reports
dei:EntityCommonStockSharesOutstanding=25,932,524,521, the real, correctly-filed LOCAL
ordinary-share count - but load_sec_valuations.py multiplies this against the US ADS
trading price ($413.41), producing market_cap=$10.7 TRILLION and pe_ratio=304.
Independently cross-checked against yfinance's live sharesOutstanding (5,186,474,013,
matching our raw count divided by ~5.000) and marketCap ($2.14T)/trailingPE (30.9),
confirming the ADS ratio and that the stored figure was ~5x too high. The same corruption
reached positioning_metrics.institutional_ownership_pct too (TSM showed 4.26%, implausibly
low for one of the most widely-held ADRs).
"""

from unittest.mock import MagicMock

from loaders.load_company_info_sec import CompanyInfoSECLoader


def _loader() -> CompanyInfoSECLoader:
    loader = CompanyInfoSECLoader.__new__(CompanyInfoSECLoader)
    loader.sec_client = MagicMock()
    return loader


def _submissions(form: str) -> dict:
    return {
        "name": "Taiwan Semiconductor Manufacturing Co Ltd",
        "sic": "3674",
        "sicDescription": "SEMICONDUCTORS & RELATED DEVICES",
        "entityType": "operating",
        "filings": {"recent": {"form": [form]}},
    }


class TestDeiSharesOutstandingForeignFormGuard:
    def test_20f_filed_dei_fact_is_rejected_not_trusted(self):
        """The real TSM shape: dei:EntityCommonStockSharesOutstanding exists and has a
        real-looking value, but it's filed under a 20-F - the local ordinary-share count,
        not the ADS-equivalent count the US trading price implies. Must not be trusted."""
        loader = _loader()
        loader.sec_client.symbol_to_cik.return_value = "1046179"
        loader.sec_client.get_submissions.return_value = _submissions("20-F")
        loader.sec_client.get_company_facts.return_value = {
            "facts": {
                "dei": {
                    "EntityCommonStockSharesOutstanding": {
                        "units": {"shares": [{"end": "2025-12-31", "val": 25_932_524_521, "form": "20-F"}]}
                    }
                },
                "us-gaap": {},
            }
        }
        loader.sec_client.get_filing_plaintext.return_value = ""

        result = loader.fetch_incremental("TSM", None)

        assert result[0]["shares_outstanding"] is None

    def test_10k_filed_dei_fact_is_still_trusted(self):
        """Companion case: a domestic 10-K filer's dei fact must still be used exactly as
        before - this fix must not become a blanket rejection of the dei concept."""
        loader = _loader()
        loader.sec_client.symbol_to_cik.return_value = "0000320193"
        loader.sec_client.get_submissions.return_value = _submissions("10-K")
        loader.sec_client.get_company_facts.return_value = {
            "facts": {
                "dei": {
                    "EntityCommonStockSharesOutstanding": {
                        "units": {"shares": [{"end": "2026-06-30", "val": 14_594_180_000, "form": "10-K"}]}
                    }
                },
                "us-gaap": {},
            }
        }

        result = loader.fetch_incremental("AAPL", None)

        assert result[0]["shares_outstanding"] == 14_594_180_000

    def test_missing_form_key_is_still_trusted(self):
        """Backward compatibility: real companyfacts entries always carry a form field, but
        this must not regress on a fact shape that omits it (defensive default - unknown
        form is not assumed foreign)."""
        loader = _loader()
        loader.sec_client.symbol_to_cik.return_value = "0000320193"
        loader.sec_client.get_submissions.return_value = _submissions("10-K")
        loader.sec_client.get_company_facts.return_value = {
            "facts": {
                "dei": {
                    "EntityCommonStockSharesOutstanding": {
                        "units": {"shares": [{"end": "2026-06-30", "val": 14_594_180_000}]}
                    }
                },
                "us-gaap": {},
            }
        }

        result = loader.fetch_incremental("AAPL", None)

        assert result[0]["shares_outstanding"] == 14_594_180_000

    def test_40f_and_6k_forms_also_rejected(self):
        """Same trap, different foreign-filer form types (Canadian MJDS annual reports and
        6-K interim/current reports)."""
        for form in ("40-F", "6-K"):
            loader = _loader()
            loader.sec_client.symbol_to_cik.return_value = "1046179"
            loader.sec_client.get_submissions.return_value = _submissions(form)
            loader.sec_client.get_company_facts.return_value = {
                "facts": {
                    "dei": {
                        "EntityCommonStockSharesOutstanding": {
                            "units": {"shares": [{"end": "2025-12-31", "val": 25_932_524_521, "form": form}]}
                        }
                    },
                    "us-gaap": {},
                }
            }
            loader.sec_client.get_filing_plaintext.return_value = ""

            result = loader.fetch_incremental("TSM", None)

            assert result[0]["shares_outstanding"] is None, f"form={form} should be rejected"

    def test_foreign_form_fact_falls_through_to_us_gaap(self):
        """A rejected 20-F dei fact must still let the us-gaap fallback fire, same as if
        dei had nothing at all - not short-circuit the whole extraction."""
        loader = _loader()
        loader.sec_client.symbol_to_cik.return_value = "1046179"
        loader.sec_client.get_submissions.return_value = _submissions("20-F")
        loader.sec_client.get_company_facts.return_value = {
            "facts": {
                "dei": {
                    "EntityCommonStockSharesOutstanding": {
                        "units": {"shares": [{"end": "2025-12-31", "val": 25_932_524_521, "form": "20-F"}]}
                    }
                },
                "us-gaap": {
                    "CommonStockSharesOutstanding": {"units": {"shares": [{"end": "2025-12-31", "val": 5_186_504_904}]}}
                },
            }
        }

        result = loader.fetch_incremental("TSM", None)

        assert result[0]["shares_outstanding"] == 5_186_504_904

    def test_us_gaap_fallback_also_rejects_foreign_form_facts(self):
        """FIXED 2026-08-19 (migration 1211 follow-up): the us-gaap:CommonStockSharesOutstanding
        fallback (added for Alphabet/GOOG, a domestic 10-K filer) was assumed safe without this
        same restriction. Live-confirmed WRONG via AEM (Agnico Eagle Mines): its only
        us-gaap:CommonStockSharesOutstanding fact anywhere in its real companyfacts history is a
        single, 14-year-stale value (170,880,330, filed under a 6-K in 2012) - independently
        cross-checked against yfinance's live sharesOutstanding (506,364,864, ~3x higher, not
        even a clean ADS-style ratio, just genuinely stale data from before a merger)."""
        loader = _loader()
        loader.sec_client.symbol_to_cik.return_value = "2809"
        loader.sec_client.get_submissions.return_value = _submissions("40-F")
        loader.sec_client.get_company_facts.return_value = {
            "facts": {
                "dei": {},
                "us-gaap": {
                    "CommonStockSharesOutstanding": {
                        "units": {"shares": [{"end": "2012-03-31", "val": 170_880_330, "form": "6-K"}]}
                    }
                },
            }
        }
        loader.sec_client.get_filing_plaintext.return_value = ""

        result = loader.fetch_incremental("AEM", None)

        assert result[0]["shares_outstanding"] is None

    def test_us_gaap_fallback_domestic_form_still_trusted(self):
        """Companion case: the original Alphabet/GOOG shape (a real domestic 10-K filer) must
        still work exactly as before this fix."""
        loader = _loader()
        loader.sec_client.symbol_to_cik.return_value = "1652044"
        loader.sec_client.get_submissions.return_value = _submissions("10-K")
        loader.sec_client.get_company_facts.return_value = {
            "facts": {
                "dei": {},
                "us-gaap": {
                    "CommonStockSharesOutstanding": {
                        "units": {"shares": [{"end": "2026-06-30", "val": 12_230_000_000, "form": "10-K"}]}
                    }
                },
            }
        }

        result = loader.fetch_incremental("GOOGL", None)

        assert result[0]["shares_outstanding"] == 12_230_000_000
