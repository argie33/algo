"""Regression test for the 2026-09-09 fix (goal: SEC/XBRL missing-data count under 700):
recent IPOs (real 10-Qs filed, no 10-K yet) have zero annual_income_statement rows but real
quarterly_income_statement data. Previously this always fell to the generic
"no_income_statement" reason (blocking pe_ratio/ps_ratio/dividend_yield/sec_valuations)
even when 4 real quarters of revenue/net_income/EPS exist.

`_fetch_ttm_income_statement_row` builds a synthetic TTM "annual" row from the 4 most recent
real quarters, only when all 4 have real revenue, net_income, AND earnings_per_share.
"""

from loaders.load_sec_valuations import SecValuationsLoader


def _make_loader() -> SecValuationsLoader:
    return SecValuationsLoader.__new__(SecValuationsLoader)


class _FakeCursor:
    def __init__(self, quarters):
        self._quarters = quarters
        self._last_query = ""

    def execute(self, query, params=None):
        self._last_query = query

    def fetchall(self):
        if "FROM annual_income_statement" in self._last_query:
            return []
        if "FROM quarterly_income_statement" in self._last_query:
            return self._quarters
        return []

    def fetchone(self):
        if "company_info_sec" in self._last_query:
            return (False, "7372")
        return None


def _quarter(revenue, net_income, eps, fiscal_year=2026):
    # (revenue, net_income, earnings_per_share, operating_income, pretax_income,
    #  depreciation_expense, amortization_expense, shares_outstanding_basic,
    #  income_tax_expense, interest_expense, fiscal_year)
    return (revenue, net_income, eps, None, None, None, None, 10_000_000.0, None, None, fiscal_year)


class TestSecValuationsTtmQuarterlyIncomeFallback:
    def test_four_real_quarters_recover_income_statement_context(self):
        loader = _make_loader()
        quarters = [_quarter(50_000_000.0, 5_000_000.0, 0.50) for _ in range(4)]

        result = loader._fetch_income_statement_context(_FakeCursor(quarters), "RECENTIPO")

        assert not (isinstance(result, list) and result and result[0].get("data_unavailable"))

    def test_fewer_than_four_quarters_keeps_no_income_statement_reason(self):
        loader = _make_loader()
        quarters = [_quarter(50_000_000.0, 5_000_000.0, 0.50) for _ in range(2)]

        result = loader._fetch_income_statement_context(_FakeCursor(quarters), "TOOFRESH")

        assert result[0]["reason"] == "no_income_statement"

    def test_four_quarters_with_null_eps_keeps_no_income_statement_reason(self):
        loader = _make_loader()
        quarters = [_quarter(50_000_000.0, 5_000_000.0, None) for _ in range(4)]

        result = loader._fetch_income_statement_context(_FakeCursor(quarters), "PARTIALDATA")

        assert result[0]["reason"] == "no_income_statement"
