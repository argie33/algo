"""Regression test for the 2026-09-09 fix (goal: SEC/XBRL missing-data count under 700):
recent IPOs (real 10-Qs filed, no 10-K yet) have zero annual_income_statement rows but real
quarterly_income_statement data. Previously this always fell to the generic
"no_income_statement" reason (blocking pe_ratio/ps_ratio/dividend_yield/sec_valuations)
even when 4 real quarters of revenue/net_income/EPS exist.

`_fetch_ttm_income_statement_row` builds a synthetic TTM "annual" row from the 4 most recent
real quarters. UPDATED 2026-09-10 (goal: "SEC/XBRL missing data under 500" sweep):
revenue/net_income/earnings_per_share are each independently required to have all 4 quarters
real before being summed - a gap in ONE no longer blocks the other two the way the original
single blanket gate did. Live-confirmed 13 real symbols (AADX/BRR/CSQR/DPC/KARD/LABT/LCLN/
LFTO/LIME/PBLS/RMIX/SIND/SSMR) have 4 complete real quarters of net_income+EPS but a real
revenue gap in 1+ quarters (pre-revenue/development-stage filers with milestone/collaboration-
only revenue some quarters, not others) - the old gate discarded real, complete EPS data
purely because revenue had a gap.
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

    def test_four_quarters_with_null_eps_recovers_via_revenue_and_net_income(self):
        """UPDATED 2026-09-10: EPS null across all 4 quarters no longer blocks the whole
        synthetic row when revenue/net_income are fully real - a real ps_ratio/revenue-based
        computation should still be possible even though pe_ratio (needs EPS) isn't."""
        loader = _make_loader()
        quarters = [_quarter(50_000_000.0, 5_000_000.0, None) for _ in range(4)]

        result = loader._fetch_income_statement_context(_FakeCursor(quarters), "PARTIALDATA")

        assert not (isinstance(result, list) and result and result[0].get("data_unavailable"))

    def test_four_quarters_with_revenue_gap_recovers_via_net_income_and_eps(self):
        """The real bug this fix targets: a revenue gap in some (not all) quarters must not
        block a real, complete net_income+EPS TTM figure - live-confirmed pattern for AADX/
        BRR/CSQR/DPC/KARD/LABT/LCLN/LFTO/LIME/PBLS/RMIX/SIND/SSMR (pre-revenue/development-
        stage filers with real net_income+EPS every quarter but revenue only some quarters)."""
        loader = _make_loader()
        quarters = [
            _quarter(None, -5_000_000.0, -0.10),
            _quarter(12_000_000.0, -5_000_000.0, -0.10),
            _quarter(None, -5_000_000.0, -0.10),
            _quarter(15_000_000.0, -5_000_000.0, -0.10),
        ]

        result = loader._fetch_income_statement_context(_FakeCursor(quarters), "PARTIALREVENUE")

        assert not (isinstance(result, list) and result and result[0].get("data_unavailable"))

    def test_all_three_fields_incomplete_keeps_no_income_statement_reason(self):
        """Only when NONE of revenue/net_income/EPS have a complete 4-quarter run does this
        still correctly fall through to no_income_statement."""
        loader = _make_loader()
        quarters = [
            _quarter(50_000_000.0 if i == 0 else None, 5_000_000.0 if i == 1 else None, 0.5 if i == 2 else None)
            for i in range(4)
        ]

        result = loader._fetch_income_statement_context(_FakeCursor(quarters), "STILLINCOMPLETE")

        assert result[0]["reason"] == "no_income_statement"
