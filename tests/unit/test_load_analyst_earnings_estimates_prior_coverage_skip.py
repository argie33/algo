"""Regression test (2026-08-19, "no SEC data" audit - analyst-loader parity follow-up):
load_analyst_earnings_estimates.py never got the "skip the marker write for a symbol with
prior real coverage" guard its sibling loaders (load_analyst_upgrade_downgrade.py,
load_analyst_sentiment_analysis.py) already have from their 2026-08-18 fix. A transient
today-only yfinance hiccup wrote a fresh data_unavailable marker dated today() - since this
is a snapshot-per-day table keyed on (symbol, date), that marker becomes the "latest row per
symbol" the moment it's written, masking real historical forward-EPS coverage for that one
day. Live-confirmed low but nonzero impact (9 symbols with real history currently masked).
"""

from datetime import date
from unittest.mock import MagicMock, patch

from loaders.load_analyst_earnings_estimates import AnalystEarningsEstimatesLoader
from utils.infrastructure.timezone import EASTERN_TZ


def _fake_db_context():
    cur = MagicMock()
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=cur)
    ctx.__exit__ = MagicMock(return_value=False)
    return ctx, cur


class TestFetchIncrementalPriorCoverageSkip:
    def test_transient_failure_for_already_covered_symbol_skips_the_marker(self):
        loader = AnalystEarningsEstimatesLoader.__new__(AnalystEarningsEstimatesLoader)
        ctx, _cur = _fake_db_context()
        with (
            patch(
                "loaders.load_analyst_earnings_estimates.fetch_forward_eps",
                return_value=None,
            ),
            patch.object(loader, "_has_prior_real_coverage", return_value=True),
            patch("loaders.load_analyst_earnings_estimates.DatabaseContext", return_value=ctx),
        ):
            result = loader.fetch_incremental("NVDA", since=date(2026, 8, 11))
        assert result == []

    def test_prior_coverage_skip_retracts_pre_existing_stale_marker(self):
        """BUG FOUND 2026-08-21 (follow-up to the 2026-08-19 fix above): "skip the marker
        write" never retracts a marker already written BEFORE that fix landed - live-
        confirmed 7 symbols (ATOM, KPLT, PZG, RGS, SKYT, THCH, XAIR) stuck on a marker
        dated 2026-08-19 as their permanent "latest row", masking real historical
        forward-EPS coverage underneath (e.g. ATOM had real forward_eps through
        2026-08-09). Any marker coexisting with confirmed real coverage is always wrong -
        retract it here too."""
        loader = AnalystEarningsEstimatesLoader.__new__(AnalystEarningsEstimatesLoader)
        ctx, cur = _fake_db_context()
        with (
            patch(
                "loaders.load_analyst_earnings_estimates.fetch_forward_eps",
                return_value=None,
            ),
            patch.object(loader, "_has_prior_real_coverage", return_value=True),
            patch("loaders.load_analyst_earnings_estimates.DatabaseContext", return_value=ctx),
        ):
            result = loader.fetch_incremental("ATOM", since=date(2026, 8, 19))
        assert result == []
        query, params = cur.execute.call_args[0]
        assert "DELETE FROM analyst_earnings_estimates" in query
        assert "data_unavailable = true" in query
        assert params == ("ATOM",)

    def test_never_covered_symbol_still_gets_the_marker(self):
        # Control: a symbol with no real history on record must still get the honest
        # no_analyst_estimates marker - this is the genuine "no coverage" case.
        loader = AnalystEarningsEstimatesLoader.__new__(AnalystEarningsEstimatesLoader)
        with (
            patch(
                "loaders.load_analyst_earnings_estimates.fetch_forward_eps",
                return_value=None,
            ),
            patch.object(loader, "_has_prior_real_coverage", return_value=False),
        ):
            result = loader.fetch_incremental("ZZZZ", since=date(2026, 8, 11))
        assert len(result) == 1
        assert result[0]["data_unavailable"] is True
        assert result[0]["reason"] == "no_analyst_estimates"

    def test_real_fetch_returns_the_estimate_row(self):
        loader = AnalystEarningsEstimatesLoader.__new__(AnalystEarningsEstimatesLoader)
        with (
            patch(
                "loaders.load_analyst_earnings_estimates.fetch_forward_eps",
                return_value=12.8,
            ),
            patch(
                "loaders.load_analyst_earnings_estimates.fetch_forward_growth_estimates",
                return_value={
                    "forward_eps_growth_current_fy": 0.18,
                    "forward_eps_growth_next_fy": 0.08,
                    "forward_revenue_growth_next_fy": 0.10,
                    "eps_estimate_revision_90d_pct": -1.5,
                },
            ),
        ):
            result = loader.fetch_incremental("NVDA", since=date(2026, 8, 11))
        assert len(result) == 1
        assert result[0]["forward_eps"] == 12.8
        assert result[0]["data_unavailable"] is False
        assert result[0]["forward_eps_growth_current_fy"] == 0.18
        assert result[0]["forward_eps_growth_next_fy"] == 0.08
        assert result[0]["forward_revenue_growth_next_fy"] == 0.10
        assert result[0]["eps_estimate_revision_90d_pct"] == -1.5

    def test_growth_estimates_fetch_failure_does_not_break_the_row(self):
        """fetch_forward_growth_estimates returning None (no coverage on any of its 3
        endpoints) must not prevent the row from being written - forward_eps is the only
        required field, the growth/revision fields are best-effort."""
        loader = AnalystEarningsEstimatesLoader.__new__(AnalystEarningsEstimatesLoader)
        with (
            patch(
                "loaders.load_analyst_earnings_estimates.fetch_forward_eps",
                return_value=12.8,
            ),
            patch(
                "loaders.load_analyst_earnings_estimates.fetch_forward_growth_estimates",
                return_value=None,
            ),
        ):
            result = loader.fetch_incremental("NVDA", since=date(2026, 8, 11))
        assert len(result) == 1
        assert result[0]["forward_eps"] == 12.8
        assert result[0]["forward_eps_growth_current_fy"] is None
        assert result[0]["eps_estimate_revision_90d_pct"] is None

    def test_table_and_key_config_matches_live_schema(self):
        assert AnalystEarningsEstimatesLoader.table_name == "analyst_earnings_estimates"
        assert AnalystEarningsEstimatesLoader.primary_key == ("symbol", "date")
