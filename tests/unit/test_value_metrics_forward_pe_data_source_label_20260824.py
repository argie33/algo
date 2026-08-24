"""Regression test (2026-08-24, real-money-readiness goal session): value_metrics rows with
a populated forward_pe were unconditionally tagged data_source="sec_audited", even though
forward_pe is computed from analyst_earnings_estimates - a real yfinance-sourced consensus
estimate, since SEC filings never carry forward-looking analyst estimates. This silently
under-reported real yfinance dependency on lambda/api/routes/scores.py's data-source coverage
dashboard (live-confirmed 2,658 rows mislabeled). Fixed by reusing this codebase's existing
"sec_audited_except_X_yfinance" composite-label convention (already used for
load_sec_valuations.py's dual-class-shares case).
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
    """Returns a real positive forward_eps for the analyst_earnings_estimates query,
    "no data" for everything else - same isolation pattern as
    test_forward_pe_negative_analyst_estimate_reason_20260822.py."""

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


class _NoDataCursor:
    def execute(self, query, params=None):
        pass

    def fetchone(self):
        return None

    def fetchall(self):
        return []


class TestValueMetricsForwardPeDataSourceLabel:
    def test_populated_forward_pe_gets_composite_yfinance_label(self):
        loader = _make_loader()
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = _RoutingCursor(forward_eps=2.0)
            metrics = loader._build_value_metrics(
                "AAPL",
                _FakeSecValRow(
                    {"pe_ratio": 30.0, "pb_ratio": 40.0, "current_price": 200.0, "market_cap": 3_000_000_000_000.0}
                ),
            )

        assert metrics["forward_pe"] is not None
        assert metrics["data_source"] == "sec_audited_except_forward_pe_yfinance", (
            "a populated forward_pe means real yfinance-sourced analyst-estimate data is in "
            "this row - data_source must not silently claim pure sec_audited"
        )

    def test_missing_forward_pe_keeps_plain_sec_audited_label(self):
        loader = _make_loader()
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = _NoDataCursor()
            metrics = loader._build_value_metrics(
                "ENVA",
                _FakeSecValRow({"pe_ratio": 15.0, "current_price": 40.0, "market_cap": 1_000_000_000.0}),
            )

        assert metrics["forward_pe"] is None
        assert metrics["data_source"] == "sec_audited"
