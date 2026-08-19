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
from unittest.mock import patch

from loaders.load_analyst_earnings_estimates import AnalystEarningsEstimatesLoader
from utils.infrastructure.timezone import EASTERN_TZ


class TestFetchIncrementalPriorCoverageSkip:
    def test_transient_failure_for_already_covered_symbol_skips_the_marker(self):
        loader = AnalystEarningsEstimatesLoader.__new__(AnalystEarningsEstimatesLoader)
        with (
            patch(
                "loaders.load_analyst_earnings_estimates.fetch_forward_eps",
                return_value=None,
            ),
            patch.object(loader, "_has_prior_real_coverage", return_value=True),
        ):
            result = loader.fetch_incremental("NVDA", since=date(2026, 8, 11))
        assert result == []

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
        with patch(
            "loaders.load_analyst_earnings_estimates.fetch_forward_eps",
            return_value=12.8,
        ):
            result = loader.fetch_incremental("NVDA", since=date(2026, 8, 11))
        assert len(result) == 1
        assert result[0]["forward_eps"] == 12.8
        assert result[0]["data_unavailable"] is False

    def test_table_and_key_config_matches_live_schema(self):
        assert AnalystEarningsEstimatesLoader.table_name == "analyst_earnings_estimates"
        assert AnalystEarningsEstimatesLoader.primary_key == ("symbol", "date")
