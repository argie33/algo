"""Regression test (2026-09-10, goal: "under 500" SEC/XBRL missing-data push,
missing_cash_flow_data bucket): every annual_cash_flow row can be flagged
data_unavailable=TRUE (stale-orphan fiscal year, incomplete filing, or a "no annual cashflow
data" entity-type classification) while quarterly_cash_flow has real, current data every
quarter. Live-confirmed XRTX (annual all `stale_fiscal_year_not_confirmed_by_full_sec_
refetch`), AIBZ/GLND (annual `incomplete_sec_filing_cashflow`), USDE/BXDC (annual
`no_annual_cashflow_data_in_sec_edgar_reit_or_special_entity`) - all have real quarterly
operating_cash_flow (often capex too) that fetch_incremental's annual-only query never saw,
so dcf_fcf/fcf_yield fell to "missing_cash_flow_data" despite real data existing.

`_fetch_ttm_cash_flow_row` builds a synthetic TTM row from the 4 most recent real quarters
(same "all 4 quarters must have a real value" discipline as the income-statement sibling,
_fetch_ttm_income_statement_row), reached via `_fetch_cash_flow_rows` only when the annual
tier is completely empty.
"""

from loaders.load_sec_valuations import SecValuationsLoader


def _make_loader() -> SecValuationsLoader:
    return SecValuationsLoader.__new__(SecValuationsLoader)


class _FakeCursor:
    def __init__(self, annual_rows=None, quarters=None):
        self._annual_rows = annual_rows or []
        self._quarters = quarters or []
        self._last_query = ""

    def execute(self, query, params=None):
        self._last_query = query

    def fetchall(self):
        if "FROM annual_cash_flow" in self._last_query:
            return self._annual_rows
        if "FROM quarterly_cash_flow" in self._last_query:
            return self._quarters
        return []


def _quarter(ocf, capex, dividends_paid=None, sbc=None, buyback=None):
    return (ocf, capex, dividends_paid, sbc, buyback)


class TestSecValuationsTtmQuarterlyCashFlowFallback:
    def test_four_real_quarters_recover_ocf_and_capex(self):
        loader = _make_loader()
        quarters = [_quarter(1_000_000.0, 100_000.0) for _ in range(4)]

        result = loader._fetch_cash_flow_rows(_FakeCursor(quarters=quarters), "XRTX")

        assert result == [(4_000_000.0, 400_000.0, None, None, None)]

    def test_annual_tier_wins_when_present(self):
        loader = _make_loader()
        annual = [(5_000_000.0, 500_000.0, None, None, None)]
        quarters = [_quarter(1_000_000.0, 100_000.0) for _ in range(4)]

        result = loader._fetch_cash_flow_rows(_FakeCursor(annual_rows=annual, quarters=quarters), "HASANNUAL")

        assert result == annual

    def test_fewer_than_four_quarters_returns_empty(self):
        loader = _make_loader()
        quarters = [_quarter(1_000_000.0, 100_000.0) for _ in range(2)]

        result = loader._fetch_cash_flow_rows(_FakeCursor(quarters=quarters), "TOOFRESH")

        assert result == []

    def test_four_quarters_with_null_ocf_returns_empty(self):
        loader = _make_loader()
        quarters = [_quarter(1_000_000.0, 100_000.0), _quarter(None, 100_000.0)] + [
            _quarter(1_000_000.0, 100_000.0) for _ in range(2)
        ]

        result = loader._fetch_cash_flow_rows(_FakeCursor(quarters=quarters), "PARTIALDATA")

        assert result == []

    def test_capex_null_in_one_quarter_leaves_ttm_capex_none_not_understated(self):
        # Same "all-or-nothing" discipline as annual is_capex_exempt handling - a partial
        # capex sum would understate FCF, not correctly represent "unknown".
        loader = _make_loader()
        quarters = [_quarter(1_000_000.0, 100_000.0), _quarter(1_000_000.0, None)] + [
            _quarter(1_000_000.0, 100_000.0) for _ in range(2)
        ]

        result = loader._fetch_cash_flow_rows(_FakeCursor(quarters=quarters), "AIBZ")

        assert result == [(4_000_000.0, None, None, None, None)]

    def test_dividends_sbc_buyback_summed_treating_missing_quarter_as_zero(self):
        loader = _make_loader()
        quarters = [
            _quarter(1_000_000.0, 100_000.0, dividends_paid=10_000.0, sbc=5_000.0, buyback=2_000.0),
            _quarter(1_000_000.0, 100_000.0, dividends_paid=None, sbc=5_000.0, buyback=None),
            _quarter(1_000_000.0, 100_000.0),
            _quarter(1_000_000.0, 100_000.0),
        ]

        result = loader._fetch_cash_flow_rows(_FakeCursor(quarters=quarters), "USDE")

        assert result == [(4_000_000.0, 400_000.0, 10_000.0, 10_000.0, 2_000.0)]
