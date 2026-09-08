"""Regression test for the 2026-09-07 fix: shares_outstanding_diluted was never sanity-checked
against the same row's shares_outstanding_basic - GAAP forbids diluted from being materially
below basic, so a value far below basic is a confidently-wrong filer/filing-agent XBRL tagging
error (same bug class already handled for absolute/company_info_sec-relative scale errors by
_reject_implausible_shares_outstanding), not real data.

Live-confirmed via direct SEC EDGAR companyfacts fetch: ADIL FY2022 Q2/Q3 tagged a diluted
share count ~25x below its real basic count in two independent quarters; AA FY2016 Q1-Q3
tagged a genuine, only-slightly-below-basic rounded diluted value (ratio ~1.003x) that must
NOT be rejected - that's real filer-reported data for a net-loss quarter, not a tagging error.
"""

from typing import Any

from loaders.load_financial_statements import ConsolidatedFinancialStatementsLoader


def _make_loader(statement_type: str = "income", period: str = "quarterly") -> ConsolidatedFinancialStatementsLoader:
    return ConsolidatedFinancialStatementsLoader(statement_type=statement_type, period=period)


class TestDilutedSharesBelowBasicRejected:
    def test_diluted_far_below_basic_is_rejected(self) -> None:
        """ADIL FY2022 Q2-shaped row: diluted ~25x below basic must be nulled out."""
        loader = _make_loader()
        row: dict[str, Any] = {
            "symbol": "ADIL",
            "fiscal_year": 2022,
            "fiscal_quarter": 2,
            "shares_outstanding_basic": 24_316_031,
            "shares_outstanding_diluted": 972_641,
        }
        loader._reject_diluted_shares_below_basic([row])
        assert row["shares_outstanding_diluted"] is None
        assert row["shares_outstanding_basic"] == 24_316_031  # basic is the reliable value, untouched

    def test_diluted_moderately_below_basic_is_rejected(self) -> None:
        """ABTC FY2020 Q1-shaped row: diluted ~2.2x below basic must also be nulled out."""
        loader = _make_loader()
        row: dict[str, Any] = {
            "symbol": "ABTC",
            "fiscal_year": 2020,
            "fiscal_quarter": 1,
            "shares_outstanding_basic": 12_856_302,
            "shares_outstanding_diluted": 5_836_424,
        }
        loader._reject_diluted_shares_below_basic([row])
        assert row["shares_outstanding_diluted"] is None

    def test_diluted_rounded_slightly_below_basic_is_not_rejected(self) -> None:
        """AA FY2016 Q1-shaped row: diluted only ~0.3% below basic is real filer-rounded
        data (a net-loss-quarter antidilution display value), not a tagging error - must
        survive untouched."""
        loader = _make_loader()
        row: dict[str, Any] = {
            "symbol": "AA",
            "fiscal_year": 2016,
            "fiscal_quarter": 1,
            "shares_outstanding_basic": 182_471_195,
            "shares_outstanding_diluted": 182_000_000,
        }
        loader._reject_diluted_shares_below_basic([row])
        assert row["shares_outstanding_diluted"] == 182_000_000

    def test_diluted_above_basic_is_not_rejected(self) -> None:
        """The normal, expected case: diluted > basic - must never be touched."""
        loader = _make_loader()
        row: dict[str, Any] = {
            "symbol": "MSFT",
            "fiscal_year": 2024,
            "fiscal_quarter": 1,
            "shares_outstanding_basic": 7_430_000_000,
            "shares_outstanding_diluted": 7_469_000_000,
        }
        loader._reject_diluted_shares_below_basic([row])
        assert row["shares_outstanding_diluted"] == 7_469_000_000

    def test_missing_fields_do_not_crash(self) -> None:
        loader = _make_loader()
        rows: list[dict[str, Any]] = [
            {"symbol": "X", "fiscal_year": 2020, "shares_outstanding_basic": None, "shares_outstanding_diluted": None},
            {"symbol": "Y", "fiscal_year": 2020, "shares_outstanding_basic": 1000},
            {"symbol": "Z", "fiscal_year": 2020, "shares_outstanding_diluted": 1000},
        ]
        loader._reject_diluted_shares_below_basic(rows)  # must not raise

    def test_rejection_recorded_for_post_run_force_null(self) -> None:
        """The rejection must be recorded in _explicit_null_rejections (same mechanism
        _reject_implausible_shares_outstanding uses) so post_run() force-nulls the stale
        DB value on a re-fetch, not just this run's in-memory row - see
        test_financial_statements_implausible_rejection_force_nulled_20260823.py for why
        that force-null path is required (COALESCE can't distinguish "missing" from
        "rejected")."""
        loader = _make_loader()
        row: dict[str, Any] = {
            "symbol": "ADIL",
            "fiscal_year": 2022,
            "fiscal_quarter": 2,
            "shares_outstanding_basic": 24_316_031,
            "shares_outstanding_diluted": 972_641,
        }
        loader._reject_diluted_shares_below_basic([row])
        assert any(
            field == "shares_outstanding_diluted" and pk.get("symbol") == "ADIL" and pk.get("fiscal_year") == 2022
            for pk, field in loader._explicit_null_rejections
        )
