"""Regression test for the 2026-08-31 fix: forward_pe = current_price / forward_eps had no
plausibility floor at all, unlike pe_ratio/pb_ratio/ps_ratio (load_sec_valuations.py's
MIN_PLAUSIBLE_PB_RATIO/MIN_PLAUSIBLE_PE_RATIO, added earlier this same session - see that
constant's docstring for the full VCIG evidence: a real, independently-confirmed-via-SEC-XBRL-
and-yfinance company whose tiny real share count inflates every per-share figure, winning
percentile 100 in load_stock_scores.py's _percent_rank_cheap_high and driving composite_score's
#1 rank). forward_eps carries the exact same risk via analyst estimates - MIN_PLAUSIBLE_
FORWARD_PE_RATIO (0.05) excludes it from the percentile universe the same way, rather than
letting a single extreme value dominate the ranking.
"""

from unittest.mock import patch

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _make_loader() -> ValueQualityGrowthMetricsLoader:
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


class _FakeSecValRow:
    def __init__(self, mapping):
        self._mapping = mapping

    def __getitem__(self, key):
        return self._mapping[key]

    def keys(self):
        return self._mapping.keys()


class _RoutingCursor:
    def __init__(self, forward_eps):
        self._forward_eps = forward_eps
        self.last_query = None

    def execute(self, query, params=None):
        self.last_query = query

    def fetchone(self):
        if self.last_query and "analyst_earnings_estimates" in self.last_query:
            return (self._forward_eps,)
        return None

    def fetchall(self):
        return []


class TestForwardPeImplausiblyLowExcluded:
    def test_vcig_shaped_forward_pe_below_floor_excluded(self):
        loader = _make_loader()
        # VCIG-shaped: a real forward EPS estimate implying ~$223/share (the same
        # tiny-share-count effect already confirmed for VCIG's real pe/pb ratios) against
        # a ~$2 price - forward_pe would compute to ~0.01, below the 0.05 floor.
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = _RoutingCursor(forward_eps=223.0)
            metrics = loader._build_value_metrics(
                "VCIG",
                _FakeSecValRow({"pe_ratio": 0.01, "current_price": 2.23, "market_cap": 1_380_357.0}),
            )
        assert metrics["forward_pe"] is None
        assert metrics["forward_pe_unavailable_reason"] == "implausibly_low_forward_pe"

    def test_normal_forward_pe_unaffected(self):
        loader = _make_loader()
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = _RoutingCursor(forward_eps=2.0)
            metrics = loader._build_value_metrics(
                "AAPL",
                _FakeSecValRow(
                    {"pe_ratio": 30.0, "pb_ratio": 40.0, "current_price": 200.0, "market_cap": 3_000_000_000_000.0}
                ),
            )
        assert metrics["forward_pe"] == 100.0

    def test_forward_pe_at_exact_floor_still_included(self):
        loader = _make_loader()
        # current_price=5.0, forward_eps=100.0 -> forward_pe=0.05 exactly.
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = _RoutingCursor(forward_eps=100.0)
            metrics = loader._build_value_metrics(
                "EDGECO",
                _FakeSecValRow({"pe_ratio": 10.0, "current_price": 5.0, "market_cap": 1_000_000_000.0}),
            )
        assert metrics["forward_pe"] == 0.05
