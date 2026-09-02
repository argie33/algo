"""Regression test for the 2026-09-02 fix (goal: "get all the data we need" full-coverage
audit): total_cash/total_debt are pure balance-sheet facts with no income-statement
dependency, but the "no_income_statement" early return in
SecValuationsLoader.fetch_incremental (fired when annual_income_statement has zero usable
rows for a symbol) used to omit them entirely, nulling out both even when the balance sheet
data was real and available.

Live-confirmed via AADX: real, current, non-flagged cash_and_equivalents ($18.1M FY2026) in
annual_balance_sheet, but zero usable annual_income_statement rows - sec_valuations.total_cash
came back NULL purely because the "no income statement" early exit ran before any balance-
sheet-only recovery was attempted, cascading into quality_metrics.total_cash_unavailable_reason
= "missing_sec_data" even though nothing about the cash figure was actually missing.

Fixed by extracting the existing total_cash/total_debt balance-sheet queries into
_get_total_cash_and_debt() and calling it from the "no_income_statement" early return too
(previously only reachable from the main success path), passing the results into
_unavailable_marker's existing total_cash/total_debt override parameters (added 2026-08-19 for
the analogous shares_outstanding/price-gate case, but never applied to this earlier gate).
"""

from loaders.load_sec_valuations import SecValuationsLoader


class _FakeCursor:
    """Returns canned results in call order - first call is the total_cash query, second is
    the total_debt query, matching _get_total_cash_and_debt's own call sequence."""

    def __init__(self, cash_result, debt_result):
        self._results = [cash_result, debt_result]
        self._call = 0

    def execute(self, query, params=None):
        pass

    def fetchone(self):
        result = self._results[self._call]
        self._call += 1
        return result


def _make_loader() -> SecValuationsLoader:
    return SecValuationsLoader.__new__(SecValuationsLoader)


class TestGetTotalCashAndDebt:
    def test_recovers_real_cash_and_debt_from_balance_sheet_alone(self):
        loader = _make_loader()
        cur = _FakeCursor(cash_result=(18_100_000.0,), debt_result=(5_000_000.0, 1_000_000.0, None, None))

        total_cash, total_debt = loader._get_total_cash_and_debt(cur, "AADX")

        assert total_cash == 18_100_000.0
        assert total_debt == 6_000_000.0

    def test_no_rows_at_all_returns_none_for_both(self):
        loader = _make_loader()
        cur = _FakeCursor(cash_result=None, debt_result=None)

        total_cash, total_debt = loader._get_total_cash_and_debt(cur, "NOROWS")

        assert total_cash is None
        assert total_debt is None

    def test_all_debt_components_null_returns_none_not_zero(self):
        # A row exists but every component is NULL - must stay None (genuinely unknown), not
        # be coerced to a misleading 0.
        loader = _make_loader()
        cur = _FakeCursor(cash_result=(0,), debt_result=(None, None, None, None))

        _, total_debt = loader._get_total_cash_and_debt(cur, "ALLNULL")

        assert total_debt is None


class TestNoIncomeStatementMarkerCarriesCashAndDebt:
    """_unavailable_marker's total_cash/total_debt override parameters (2026-08-19) must
    actually be populated for the "no_income_statement" reason, not just theoretically
    supported - this is the exact wiring the fix above adds."""

    def test_marker_with_cash_and_debt_overrides_keeps_reason_and_values(self):
        loader = _make_loader()

        marker = loader._unavailable_marker(
            "AADX", "no_income_statement", total_cash=18_100_000.0, total_debt=6_000_000.0
        )

        assert marker["reason"] == "no_income_statement"
        assert marker["data_unavailable"] is True
        assert marker["total_cash"] == 18_100_000.0
        assert marker["total_debt"] == 6_000_000.0
        # ebitda genuinely needs the income statement - must stay None even when cash/debt
        # are recovered.
        assert marker["ebitda"] is None

    def test_marker_without_overrides_keeps_prior_all_null_behavior(self):
        loader = _make_loader()

        marker = loader._unavailable_marker("NODATA", "no_income_statement")

        assert marker["total_cash"] is None
        assert marker["total_debt"] is None
