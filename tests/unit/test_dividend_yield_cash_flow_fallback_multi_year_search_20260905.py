"""Regression test (2026-09-05, goal: "implausible values" sweep): the annual_cash_flow
dividend_yield fallback (see test_dividend_yield_cash_flow_fallback.py for the original TIER 3
fix) only checked the single most recent within-2-year-window candidate (fetchone()/LIMIT 1) -
same missing-cross-year-fallback gap as fcf_margin/ps_ratio/pe_ratio/pb_ratio. A real but tiny/
artifact-scale dividends_paid figure in the most recent qualifying year could reject the whole
fallback even when an older (but still within-window) year has a genuinely representative
figure. Live-confirmed 13 of 21 currently-implausible symbols (MKZR, AHT, NLOP, etc.) have
multiple within-window candidates where this matters.
"""

from unittest.mock import patch

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _make_loader():
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


class _FakeSecValRow:
    def __init__(self, mapping):
        self._mapping = mapping

    def __getitem__(self, key):
        if key == 2:
            return False
        return self._mapping[key]

    def keys(self):
        return self._mapping.keys()


class _RoutingCursor:
    """Returns multiple within-window dividends_paid candidates for the annual_cash_flow
    query, most recent first (matches the real query's ORDER BY fiscal_year DESC)."""

    def __init__(self, dividends_paid_rows):
        self._dividends_paid_rows = dividends_paid_rows
        self.last_query = None

    def execute(self, query, params=None):
        self.last_query = query

    def fetchone(self):
        return None

    def fetchall(self):
        if self.last_query and "annual_cash_flow" in self.last_query:
            return [(v,) for v in self._dividends_paid_rows]
        return []


class TestDividendYieldCashFlowMultiYearSearch:
    def test_implausible_recent_year_falls_back_to_plausible_older_year(self):
        # Most recent within-window year: dividends_paid=$100 against a $10B market cap ->
        # candidate yield is negligible/implausible-low-magnitude in the other direction only if
        # bound is symmetric; here we simulate the >30% ceiling instead: recent year is $5B
        # (implausibly huge, > 30% of $10B market cap), older year is $300M (3%, plausible).
        loader = _make_loader()
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = _RoutingCursor(
                dividends_paid_rows=[5_000_000_000.0, 300_000_000.0]
            )
            metrics = loader._build_value_metrics(
                "SYM",
                _FakeSecValRow({"pe_ratio": 12.0, "dividend_yield": None, "market_cap": 10_000_000_000.0}),
            )

        assert metrics["dividend_yield"] == 0.03
        assert metrics["dividend_yield_unavailable_reason"] is None

    def test_no_plausible_candidate_in_window_stays_implausible(self):
        loader = _make_loader()
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = _RoutingCursor(
                dividends_paid_rows=[5_000_000_000.0, 6_000_000_000.0]
            )
            metrics = loader._build_value_metrics(
                "SYM",
                _FakeSecValRow({"pe_ratio": 12.0, "dividend_yield": None, "market_cap": 10_000_000_000.0}),
            )

        assert metrics["dividend_yield"] is None
        assert metrics["dividend_yield_unavailable_reason"] == "implausible_ratio"
