"""Regression test (goal session 2026-09-06, "implausible values" sweep continuation): forward_pe
= current_price / forward_eps had a plausibility FLOOR (MIN_PLAUSIBLE_FORWARD_PE_RATIO, fixed
2026-08-31 - see test_value_metrics_forward_pe_implausibly_low_excluded_20260831.py) but no
CEILING at all - unlike its siblings pe_ratio/pb_ratio/ps_ratio (load_sec_valuations.py), which
all bound both ends (MIN_PLAUSIBLE_*_RATIO and a shared <= 10000 ceiling). A tiny-but-real
forward_eps estimate (analyst consensus for a near-breakeven company) inflates forward_pe the
same way a tiny book/sales value inflates pb_ratio/ps_ratio, and nothing rejected it. Fixed by
adding MAX_PLAUSIBLE_FORWARD_PE_RATIO (10000, matching the sibling ratios' own ceiling).
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


class TestForwardPeImplausiblyHighExcluded:
    def test_tiny_forward_eps_above_ceiling_excluded(self):
        loader = _make_loader()
        # current_price=100, forward_eps=0.005 -> forward_pe=20,000, above the 10,000 ceiling.
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = _RoutingCursor(forward_eps=0.005)
            metrics = loader._build_value_metrics(
                "TINYEPS",
                _FakeSecValRow({"pe_ratio": 0.01, "current_price": 100.0, "market_cap": 1_380_357.0}),
            )
        assert metrics["forward_pe"] is None
        assert metrics["forward_pe_unavailable_reason"] == "implausible_ratio"

    def test_forward_pe_at_exact_ceiling_still_included(self):
        loader = _make_loader()
        # current_price=100, forward_eps=0.01 -> forward_pe=10,000 exactly.
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = _RoutingCursor(forward_eps=0.01)
            metrics = loader._build_value_metrics(
                "EDGECO2",
                _FakeSecValRow({"pe_ratio": 10.0, "current_price": 100.0, "market_cap": 1_000_000_000.0}),
            )
        assert metrics["forward_pe"] == 10000.0

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
