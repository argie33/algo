"""Regression test (2026-08-22, "No analyst coverage" bucket audit): forward_pe's
unavailable reason must distinguish "a real analyst forward-EPS estimate exists but
projects a loss" from "genuinely no analyst coverage at all".

Bug: load_value_quality_growth_metrics.py computed forward_pe only when forward_eps > 0
(correct - price / negative earnings isn't a valid multiple, same as pe_ratio's own
"unprofitable_stock" case) but then labeled EVERY forward_pe=None case
"no_analyst_estimates", even when a real, non-null forward_eps was on file (negative).
Live-confirmed 848 of 1,560 universe "no_analyst_estimates" forward_pe rows (54%) had a
real forward_eps, including well-known large-caps like MRNA/RBLX/RIVN/RKLB/WBD/BNTX -
all real biotech/EV/growth names genuinely projected to lose money next year, not
"nobody covers this stock". Fixed by adding a distinct "negative_forward_eps" reason,
categorized under "Legitimate / not applicable" in lambda/api/routes/scores.py (same
bucket as pe_ratio's "unprofitable_stock").
"""

import importlib
from unittest.mock import patch

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader

scores_mod = importlib.import_module("lambda.api.routes.scores")


def _make_loader() -> ValueQualityGrowthMetricsLoader:
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


class _FakeSecValRow:
    """Minimal stand-in for a psycopg2 DictRow (mapping protocol only - no positional
    access needed by this code path)."""

    def __init__(self, mapping):
        self._mapping = mapping

    def __getitem__(self, key):
        return self._mapping[key]

    def keys(self):
        return self._mapping.keys()


class _RoutingCursor:
    """Returns a real (negative) forward_eps for the analyst_earnings_estimates query,
    "no data" for everything else - isolates the forward_pe path the same way
    tests/unit/test_dividend_yield_cash_flow_fallback.py isolates the dividend path."""

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


class TestForwardPeNegativeAnalystEstimateReason:
    def test_negative_forward_eps_gets_its_own_reason_not_no_analyst_estimates(self):
        loader = _make_loader()
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = _RoutingCursor(forward_eps=-1.5)
            metrics = loader._build_value_metrics(
                "MRNA",
                _FakeSecValRow(
                    {"pe_ratio": None, "pb_ratio": 3.0, "current_price": 40.0, "market_cap": 15_000_000_000.0}
                ),
            )

        assert metrics["forward_pe"] is None
        assert metrics["forward_pe_unavailable_reason"] == "negative_forward_eps"

    def test_genuinely_missing_estimate_still_says_no_analyst_estimates(self):
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
                _FakeSecValRow({"pe_ratio": 15.0, "current_price": 40.0, "market_cap": 1_000_000_000.0}),
            )

        assert metrics["forward_pe"] is None
        assert metrics["forward_pe_unavailable_reason"] == "no_analyst_estimates"

    def test_negative_forward_eps_categorizes_as_legitimate_not_no_coverage(self):
        assert scores_mod._categorize_reason("negative_forward_eps") == "Legitimate / not applicable"
        assert scores_mod._categorize_reason("no_analyst_estimates") == "No analyst coverage"
