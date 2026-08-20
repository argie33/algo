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
