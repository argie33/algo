"""Regression test for a 2026-08-20 fix (goal: finance-accuracy audit) to
load_company_info_sec.py's _latest_shares_value(): the AEM comment in this same file already
diagnosed this failure mode ("the real risk demonstrated here is a stale historical fact never
refreshed once a filer stopped tagging us-gaap concepts") but only addressed it via
restrict_to_domestic_forms - which does nothing for a DOMESTIC filer whose own dei concept goes
stale.

Live-confirmed via AI (C3.ai): its dei:EntityCommonStockSharesOutstanding history's newest entry
is {"end": "2021-...", "val": 3499992} - a real, once-valid, now 5-year-stale filing (C3.ai IPO'd
Dec 2020) - while annual_income_statement.shares_outstanding_basic (a different concept,
refreshed every fiscal year) correctly shows 140,513,000 for FY2026, ~40x higher.
_latest_shares_value only ever compared candidates against EACH OTHER (via "latest end date
wins"), never against today - so a real-but-stale entry within the same narrow concept's history
"won" purely for being the newest thing it happened to find, not because it was actually recent.

The stale value then propagated into sec_valuations (via its company_info_sec cross-check, since
both agreed - the same shared-root-cause blind spot as the ONC/BeOne Medicines case earlier this
session) and into short_interest_finra, where it inflated short_pct to 1323% for a stock with
genuinely single-digit-to-teens real short interest.

Fixed: any candidate entry whose "end" date is more than 730 days (2 years) old is now skipped,
falling through to the next candidate/fallback (or an honest shares_outstanding=None) instead of
being trusted just because it was the newest entry within its own concept's history.
"""

from unittest.mock import MagicMock

from loaders.load_company_info_sec import CompanyInfoSECLoader


def _loader() -> CompanyInfoSECLoader:
    loader = CompanyInfoSECLoader.__new__(CompanyInfoSECLoader)
    loader.sec_client = MagicMock()
    return loader


def _submissions() -> dict:
    return {
        "name": "C3.ai, Inc.",
        "sic": "7372",
        "sicDescription": "SERVICES-PREPACKAGED SOFTWARE",
        "entityType": "operating",
        "filings": {"recent": {"form": ["10-K"]}},
    }


class TestSharesOutstandingStaleEntryRejected:
    def test_stale_dei_entry_falls_through_to_recent_gaap_value(self) -> None:
        """AI/C3.ai-shaped: the only dei entry is 5 years stale; a recent, plausible
        us-gaap value exists and must be used instead."""
        loader = _loader()
        loader.sec_client.symbol_to_cik.return_value = "0001721947"
        loader.sec_client.get_submissions.return_value = _submissions()
        loader.sec_client.get_company_facts.return_value = {
            "facts": {
                "dei": {
                    "EntityCommonStockSharesOutstanding": {
                        "units": {"shares": [{"end": "2021-03-15", "val": 3_499_992}]}
                    }
                },
                "us-gaap": {
                    "CommonStockSharesOutstanding": {"units": {"shares": [{"end": "2026-06-30", "val": 140_513_000}]}}
                },
            }
        }

        result = loader.fetch_incremental("AI", None)

        assert result[0]["shares_outstanding"] == 140_513_000

    def test_stale_entry_with_no_fallback_leaves_shares_outstanding_none(self) -> None:
        """When every available entry is stale and there's no fallback, the honest result
        is None, not a 5-year-old number presented as current."""
        loader = _loader()
        loader.sec_client.symbol_to_cik.return_value = "0001721947"
        loader.sec_client.get_submissions.return_value = _submissions()
        loader.sec_client.get_company_facts.return_value = {
            "facts": {
                "dei": {
                    "EntityCommonStockSharesOutstanding": {
                        "units": {"shares": [{"end": "2021-03-15", "val": 3_499_992}]}
                    }
                },
                "us-gaap": {},
            }
        }

        result = loader.fetch_incremental("AI", None)

        assert result[0]["shares_outstanding"] is None

    def test_recent_entry_within_two_years_still_accepted(self) -> None:
        """A genuinely recent entry (well within the 2-year staleness window) must still be
        used normally - this fix only rejects entries that are actually old."""
        loader = _loader()
        loader.sec_client.symbol_to_cik.return_value = "0001721947"
        loader.sec_client.get_submissions.return_value = _submissions()
        loader.sec_client.get_company_facts.return_value = {
            "facts": {
                "dei": {
                    "EntityCommonStockSharesOutstanding": {
                        "units": {"shares": [{"end": "2026-06-30", "val": 140_513_000}]}
                    }
                },
                "us-gaap": {},
            }
        }

        result = loader.fetch_incremental("AI", None)

        assert result[0]["shares_outstanding"] == 140_513_000


class TestFilingTextFallbackStaleEntryRejected:
    """FIXED 2026-08-30 (goal: full-data audit): same staleness bug class as above, but in
    _fetch_shares_outstanding_from_filing_text (the last-resort inline-XBRL filing-text
    parser, used when the companyfacts JSON has nothing usable) - that function never had a
    staleness check at all, unlike _latest_shares_value's identical 730-day cutoff above.

    Live-confirmed via AKTX (Akari Therapeutics): its most recent 10-K predates its later
    conversion to a 20-F foreign-private-issuer filer by years, and this fallback trusted its
    stale cover-page share count (155,758,529,533 - 6.4x NVDA, the real largest share count on
    file) with no age check, corrupting company_info_sec.shares_outstanding for every
    downstream consumer (including load_institutional_holdings_13f.py, which reads this column
    with no plausibility ceiling of its own)."""

    def _loader(self) -> CompanyInfoSECLoader:
        loader = CompanyInfoSECLoader.__new__(CompanyInfoSECLoader)
        loader.sec_client = MagicMock()
        return loader

    def test_stale_10k_filing_text_rejected(self) -> None:
        loader = self._loader()
        loader.sec_client.get_filing_plaintext.return_value = (
            '<ix:nonFraction name="dei:EntityCommonStockSharesOutstanding" scale="0">155758529533</ix:nonFraction>'
        )
        submissions = {
            "filings": {
                "recent": {
                    "form": ["10-K"],
                    "accessionNumber": ["0000000000-18-000001"],
                    "filingDate": ["2018-03-01"],  # far past the 730-day cutoff
                }
            }
        }

        result = loader._fetch_shares_outstanding_from_filing_text("AKTX", "0000000000", submissions)

        assert result is None

    def test_recent_10k_filing_text_still_accepted(self) -> None:
        loader = self._loader()
        loader.sec_client.get_filing_plaintext.return_value = (
            '<ix:nonFraction name="dei:EntityCommonStockSharesOutstanding" scale="0">79697889</ix:nonFraction>'
        )
        submissions = {
            "filings": {
                "recent": {
                    "form": ["10-K"],
                    "accessionNumber": ["0000000000-26-000001"],
                    "filingDate": ["2026-06-15"],  # well within the 730-day cutoff
                }
            }
        }

        result = loader._fetch_shares_outstanding_from_filing_text("PLNT", "0000000000", submissions)

        assert result == 79_697_889

    def test_missing_filing_date_treated_as_stale(self) -> None:
        """A malformed/short filingDate array must not be trusted just because it's
        absent - fail closed (None), same as the primary-path fix above."""
        loader = self._loader()
        loader.sec_client.get_filing_plaintext.return_value = (
            '<ix:nonFraction name="dei:EntityCommonStockSharesOutstanding" scale="0">79697889</ix:nonFraction>'
        )
        submissions = {
            "filings": {
                "recent": {
                    "form": ["10-K"],
                    "accessionNumber": ["0000000000-26-000001"],
                    # filingDate deliberately omitted
                }
            }
        }

        result = loader._fetch_shares_outstanding_from_filing_text("ZZZZ", "0000000000", submissions)

        assert result is None
