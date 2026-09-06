"""Regression test for the 2026-08-28 dividend_yield per-share TTM fallback (TIER 4).

dividend_data.dividend_yield_pct is 0/91569 populated universe-wide (live-confirmed) - no
writer in this repo has ever set it, so the existing TIER 2 fallback (which requires
dividend_yield_pct IS NOT NULL) can never match anything, for any symbol. annual_cash_flow's
dividends_paid (TIER 3) is also unpopulated for many real payers (live-confirmed on SPG, RS,
CNK - all real, well-known dividend stocks with real dividend_per_share on file and nothing in
annual_cash_flow). dividend_data.dividend_per_share itself IS populated and was unused by any
fallback tier before this fix. TIER 4 sums trailing ~370 days of per-share payments and divides
by current_price - the standard trailing dividend yield calculation.
"""

from unittest.mock import patch

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _make_loader():
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


class _FakeSecValRow:
    """Minimal stand-in for a psycopg2 DictRow: supports sec_val_row[2] (data_unavailable flag,
    positional) and dict(sec_val_row) (mapping protocol) simultaneously."""

    def __init__(self, mapping):
        self._mapping = mapping

    def __getitem__(self, key):
        if key == 2:
            return False
        return self._mapping[key]

    def keys(self):
        return self._mapping.keys()


class _RoutingCursor:
    """Returns a real trailing-dividends sum for the new TIER 4 query, "no data" for
    everything else (dividend_data TIER 2, annual_cash_flow TIER 3, forward_pe, etc.)."""

    def __init__(self, ttm_dividends):
        self._ttm_dividends = ttm_dividends
        self.last_query = None

    def execute(self, query, params=None):
        self.last_query = query

    def fetchone(self):
        if self.last_query and "SUM(dividend_per_share)" in self.last_query:
            return (self._ttm_dividends,)
        return None

    def fetchall(self):
        return []


class TestDividendYieldPerShareTtmFallback:
    def test_computes_trailing_yield_from_dividend_per_share_when_other_tiers_empty(self):
        loader = _make_loader()
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = _RoutingCursor(ttm_dividends=8.20)
            metrics = loader._build_value_metrics(
                "SPG",
                _FakeSecValRow({"pe_ratio": 27.0, "dividend_yield": None, "market_cap": None, "current_price": 164.0}),
            )

        assert metrics["dividend_yield"] == 8.20 / 164.0
        assert metrics["dividend_yield_unavailable_reason"] is None

    def test_no_fallback_without_current_price(self):
        # Without current_price the trailing-yield formula has no denominator - must fall
        # through to the existing non-payer/missing-data classification, not crash.
        loader = _make_loader()

        class _NoDataCursor:
            def execute(self, query, params=None):
                pass

            def fetchone(self):
                return None

            def fetchall(self):
                return []

        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = _NoDataCursor()
            metrics = loader._build_value_metrics(
                "ENVA",
                _FakeSecValRow({"pe_ratio": 15.0, "dividend_yield": None, "market_cap": None, "current_price": None}),
            )

        assert metrics["dividend_yield"] == 0.0
        assert metrics["dividend_yield_unavailable_reason"] == "non_dividend_paying_stock"

    def test_out_of_bounds_yield_left_null(self):
        # A nonsensical trailing sum (e.g. stock-split artifact) must not produce a >100% yield.
        #
        # FIXED 2026-09-05 (goal session: "SEC/XBRL missing data to zero" audit): this used to
        # assert the fall-through to has_dividend_history's generic classification - but a real,
        # positive TTM dividend sum that's simply too large to be a genuine yield is the same
        # "real value, deliberately rejected as implausible" case TIER 3's own
        # dividend_yield_implausible_from_cash_flow flag already gets "implausible_ratio" for,
        # just via a different tier. Live-confirmed CVKD: real $16.50/share quarterly payments
        # against a $1.22 price implies a ~2705% yield - real data, correctly rejected, must not
        # be mislabeled as a plain missing-data/non-payer case.
        loader = _make_loader()
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = _RoutingCursor(ttm_dividends=500.0)
            metrics = loader._build_value_metrics(
                "SPG",
                _FakeSecValRow({"pe_ratio": 27.0, "dividend_yield": None, "market_cap": None, "current_price": 164.0}),
            )

        assert metrics["dividend_yield"] is None
        assert metrics["dividend_yield_unavailable_reason"] == "implausible_ratio"

    def test_lapsed_dividend_beyond_ttm_window_gets_specific_reason(self):
        """FIXED 2026-09-05 (goal session: "SEC/XBRL missing data to zero" follow-up). A real
        payment inside the 2-year has_dividend_history window but outside the 370-day TTM
        window used to fall through to the generic "missing_sec_data" - genuine recent data,
        just too stale to compute a confident current yield from, same "Legitimate / not
        applicable" class as a confirmed non-payer. Live-confirmed NHP: 46 real dividend_data
        rows on file, most recent ~568 days before this fix - within the 2-year window, outside
        the 370-day one.
        """

        class _LapsedDividendCursor:
            def __init__(self):
                self.last_query = None

            def execute(self, query, params=None):
                self.last_query = query

            def fetchone(self):
                if self.last_query and "SUM(dividend_per_share)" in self.last_query:
                    return (None,)  # TTM (370-day) window: nothing real
                if self.last_query and "INTERVAL '2 years'" in self.last_query:
                    return (1,)  # 2-year window: a real payment exists
                return None

            def fetchall(self):
                return []

        loader = _make_loader()
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = _LapsedDividendCursor()
            metrics = loader._build_value_metrics(
                "NHP",
                _FakeSecValRow({"pe_ratio": 15.0, "dividend_yield": None, "market_cap": None, "current_price": 16.20}),
            )

        assert metrics["dividend_yield"] is None
        assert metrics["dividend_yield_unavailable_reason"] == "dividend_lapsed_beyond_ttm_window"
