"""Regression test for the 2026-09-06 fix: the 2026-09-01 "all-None annual row" guard
(test_financial_statements_all_none_annual_row_force_nulled_20260901.py) checked every
preserve_on_missing_fields column for "any real data present" - but a cover-page/instant
fact that's essentially always available regardless of whether this fiscal year has a real
annual filing (entity_common_stock_shares_outstanding -> shares_outstanding_dei, or the
balance-sheet share-count facts -> shares_outstanding_basic) is also in that set, so it kept
`any(...)` true forever and permanently defeated the guard for any symbol whose cover page
still reports a share count.

Live-confirmed via a direct fetch_incremental("ALMR") call: fresh row was exactly
{"fiscal_year": 2026, "fiscal_period": "FY", "entity_common_stock_shares_outstanding":
69392766, "data_source": "sec_audited"} - no revenue/cost_of_revenue/gross_profit/
net_income at all - yet the DB's stale FY2026 gross_profit ($14.457M) exceeded revenue
($539K) by 26x, a hard accounting impossibility, and survived indefinitely via COALESCE
because that one DEI field kept the old guard from ever firing. MRLN's fresh row similarly
carried only common_stock_shares_issued/outstanding (-> shares_outstanding_basic) and the
DEI field.

Fix: use _REQUIRED_STATEMENT_FIELDS (the codebase's existing definition of "usable data" for
a statement type, already used by post_run()'s data_unavailable flag-sync) instead of the
full preserve_on_missing_fields set - a row missing every required field (revenue AND
net_income, for income) has no usable data regardless of what cover-page/share-count fields
it also carries.
"""

from unittest.mock import patch

from loaders.load_financial_statements import ConsolidatedFinancialStatementsLoader

SHARE_COUNT_ONLY_ROW = {
    "symbol": "ALMR",
    "fiscal_year": 2026,
    "fiscal_period": "FY",
    "entity_common_stock_shares_outstanding": 69392766,
    "data_source": "sec_audited",
}


def _make_loader(period: str = "annual") -> ConsolidatedFinancialStatementsLoader:
    return ConsolidatedFinancialStatementsLoader(statement_type="income", period=period)


class TestShareCountOnlyRowForceNulled:
    def test_dei_share_count_only_row_still_queues_force_null(self) -> None:
        loader = _make_loader()
        with patch.object(
            ConsolidatedFinancialStatementsLoader.__mro__[1],
            "fetch_incremental",
            return_value=[SHARE_COUNT_ONLY_ROW],
        ):
            result = loader.fetch_incremental("ALMR", None)
        assert result == [SHARE_COUNT_ONLY_ROW]
        assert ({"symbol": "ALMR", "fiscal_year": 2026}, "revenue") in loader._explicit_null_rejections
        assert ({"symbol": "ALMR", "fiscal_year": 2026}, "net_income") in loader._explicit_null_rejections

    def test_balance_sheet_share_count_only_row_still_queues_force_null(self) -> None:
        """MRLN's shape: basic-share-count facts (mapped from the balance-sheet-style
        common_stock_shares_issued/outstanding concepts) present, no income-statement
        fields at all."""
        loader = _make_loader()
        row = {
            "symbol": "MRLN",
            "fiscal_year": 2026,
            "fiscal_period": "FY",
            "common_stock_shares_issued": 100592160,
            "common_stock_shares_outstanding": 100592160,
            "entity_common_stock_shares_outstanding": 101067784,
            "data_source": "sec_audited",
        }
        with patch.object(
            ConsolidatedFinancialStatementsLoader.__mro__[1],
            "fetch_incremental",
            return_value=[row],
        ):
            result = loader.fetch_incremental("MRLN", None)
        assert result == [row]
        assert ({"symbol": "MRLN", "fiscal_year": 2026}, "revenue") in loader._explicit_null_rejections
        assert ({"symbol": "MRLN", "fiscal_year": 2026}, "net_income") in loader._explicit_null_rejections

    def test_revenue_present_still_does_not_queue(self) -> None:
        """A row with a real required field populated must never trigger this, even
        alongside share-count fields.

        Uses a raw pre-transform concept key, not the canonical "revenue" column name -
        see the 2026-09-07 fix comment in fetch_incremental (CELH/DXCM/SHOP/NU regression)
        for why a fixture keyed by the canonical name doesn't actually exercise this check.
        """
        loader = _make_loader()
        row = {
            "symbol": "AAPL",
            "fiscal_year": 2024,
            "revenue_from_contract_with_customer_excluding_assessed_tax": 391_035_000_000,
            "net_income_loss": None,
            "entity_common_stock_shares_outstanding": 15_000_000_000,
        }
        with patch.object(
            ConsolidatedFinancialStatementsLoader.__mro__[1],
            "fetch_incremental",
            return_value=[row],
        ):
            result = loader.fetch_incremental("AAPL", None)
        assert result == [row]
        assert loader._explicit_null_rejections == []
