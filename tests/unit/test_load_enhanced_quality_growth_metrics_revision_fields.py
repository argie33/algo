"""Regression test for load_enhanced_quality_growth_metrics.py's estimate-revision fields.

Covers _compute_estimate_revision_metrics(): before this fix, estimate_revision_direction,
revision_activity_30d, estimate_momentum_60d/90d, and revision_trend_score were hardcoded to
None every run (0/5682 populated universe-wide, live-verified 2026-08-04) even though
yf.Ticker(symbol).eps_trend/.eps_revisions supply exactly this data for the '0q' period.
"""

from unittest.mock import MagicMock, patch

import pandas as pd

from loaders.load_enhanced_quality_growth_metrics import EnhancedQualityGrowthMetricsLoader


def _loader() -> EnhancedQualityGrowthMetricsLoader:
    return EnhancedQualityGrowthMetricsLoader.__new__(EnhancedQualityGrowthMetricsLoader)


def _eps_trend_df(current=1.97898, ago_60=2.00767, ago_90=2.00701) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "current": [current],
            "7daysAgo": [2.01686],
            "30daysAgo": [2.00836],
            "60daysAgo": [ago_60],
            "90daysAgo": [ago_90],
        },
        index=["0q"],
    )


def _eps_revisions_df(up_30d=2, down_30d=0) -> pd.DataFrame:
    return pd.DataFrame(
        {"upLast7days": [1], "upLast30days": [up_30d], "downLast30days": [down_30d], "downLast7Days": [0]},
        index=["0q"],
    )


class TestComputeEstimateRevisionMetrics:
    def test_populates_all_five_fields_from_live_shaped_data(self):
        loader = _loader()
        mock_ticker = MagicMock()
        mock_ticker.eps_trend = _eps_trend_df()
        mock_ticker.eps_revisions = _eps_revisions_df()
        metrics: dict = {}

        with patch("yfinance.Ticker", return_value=mock_ticker):
            loader._compute_estimate_revision_metrics("AAPL", metrics)

        assert metrics["estimate_momentum_60d"] is not None
        assert metrics["estimate_momentum_90d"] is not None
        assert metrics["revision_trend_score"] is not None
        assert metrics["revision_activity_30d"] == 2.0
        assert metrics["estimate_revision_direction"] == 2.0

    def test_missing_0q_row_leaves_fields_unset(self):
        loader = _loader()
        mock_ticker = MagicMock()
        mock_ticker.eps_trend = pd.DataFrame({"current": [1.0]}, index=["+1q"])
        mock_ticker.eps_revisions = pd.DataFrame({"upLast30days": [1]}, index=["+1q"])
        metrics: dict = {}

        with patch("yfinance.Ticker", return_value=mock_ticker):
            loader._compute_estimate_revision_metrics("ZZZZ", metrics)

        assert "estimate_momentum_60d" not in metrics
        assert "estimate_momentum_90d" not in metrics
        assert "revision_activity_30d" not in metrics
        assert "estimate_revision_direction" not in metrics

    def test_empty_dataframes_leave_fields_unset(self):
        loader = _loader()
        mock_ticker = MagicMock()
        mock_ticker.eps_trend = pd.DataFrame()
        mock_ticker.eps_revisions = pd.DataFrame()
        metrics: dict = {}

        with patch("yfinance.Ticker", return_value=mock_ticker):
            loader._compute_estimate_revision_metrics("ZZZZ", metrics)

        assert metrics == {}

    def test_near_zero_prior_estimate_does_not_overflow_numeric_column(self):
        # A near-zero 60/90-days-ago EPS estimate would otherwise blow the percentage-change
        # calc past this table's NUMERIC(10,4) column limit (max magnitude 999,999.9999) -
        # same overflow class already guarded against for the sibling trend fields.
        loader = _loader()
        mock_ticker = MagicMock()
        mock_ticker.eps_trend = _eps_trend_df(current=1.0, ago_60=0.0000001, ago_90=2.0)
        mock_ticker.eps_revisions = _eps_revisions_df()
        metrics: dict = {}

        with patch("yfinance.Ticker", return_value=mock_ticker):
            loader._compute_estimate_revision_metrics("AAPL", metrics)

        assert "estimate_momentum_60d" not in metrics
        assert metrics["estimate_momentum_90d"] is not None

    def test_yfinance_exception_leaves_metrics_untouched(self):
        loader = _loader()
        metrics: dict = {}

        with patch("yfinance.Ticker", side_effect=RuntimeError("rate limited")):
            loader._compute_estimate_revision_metrics("AAPL", metrics)

        assert metrics == {}

    def test_eps_trend_and_eps_revisions_fetches_are_timeout_protected(self):
        """Regression test: eps_trend/eps_revisions must go through
        _yfinance_call_with_timeout, same as the sibling earnings_dates call.

        Live-reproduced 2026-08-16: these two fetches were calling retry_with_backoff
        directly on `ticker.eps_trend`/`ticker.eps_revisions` with no timeout wrapper - a
        real hang there (yfinance/curl_cffi hangs are known to never raise, so
        retry_with_backoff alone can't catch them) stalled the loader for 30+ minutes
        until local_loader_scheduler's external stall-killer intervened. A docstring here
        already claimed timeout protection "for the same reason" as earnings_dates, but
        the code never actually applied it.
        """
        loader = _loader()
        mock_ticker = MagicMock()
        mock_ticker.eps_trend = _eps_trend_df()
        mock_ticker.eps_revisions = _eps_revisions_df()
        metrics: dict = {}

        with (
            patch("yfinance.Ticker", return_value=mock_ticker),
            patch(
                "loaders.load_enhanced_quality_growth_metrics._yfinance_call_with_timeout",
                side_effect=lambda fn, context, *a, **kw: fn(),
            ) as mock_timeout_wrapper,
        ):
            loader._compute_estimate_revision_metrics("AAPL", metrics)

        assert mock_timeout_wrapper.call_count == 2
        assert metrics["estimate_momentum_60d"] is not None
