#!/usr/bin/env python3
"""Regression test for MarketExposure's factor-weight-sum invariant.

Guards against silent drift: if a future edit changes one W_* class constant without
updating the others, the composite score would no longer mean "0-100" with nothing in
the pipeline catching it. MarketExposure._validate_weights() runs at __init__ time to
fail fast on that.
"""

from datetime import date, datetime, timedelta
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

import pytest

from algo.risk.market_exposure import MarketExposure


class TestMarketExposureCacheStaleness:
    """try_load_cached's 2h TTL check must interpret the naive `updated_at` timestamp in
    the DB session's actual timezone (via SHOW timezone), not a hardcoded EASTERN_TZ -
    updated_at is written via SQL NOW() into a `timestamp without time zone` column, so it's
    in the session's local wall-clock (confirmed live: America/Chicago on this deployment,
    a full hour off Eastern during DST). Mislabeling it as Eastern silently added an hour to
    every computed cache age against a 2h threshold - a ~50% relative error.
    """

    def _mock_row(self, updated_at: datetime) -> tuple:
        return (
            50.0,  # raw_score
            50.0,  # exposure_pct
            "NEUTRAL",  # regime
            "[]",  # halt_reasons
            0,  # distribution_days
            "{}",  # factors
            date(2026, 7, 20),  # cached_date
            updated_at,  # updated_at
        )

    def test_uses_real_session_timezone_not_hardcoded_eastern(self):
        eval_date = date(2026, 7, 20)
        # Session timezone is America/Chicago (UTC-5 in July, 1h behind Eastern's UTC-4).
        # A cache row genuinely 1.5h old (real Chicago wall-clock) is under the 2h TTL and
        # must NOT be stale. The old bug mislabeled this Chicago-wall-clock value as Eastern,
        # which computes a UTC instant 1h EARLIER than the true one - inflating the derived
        # age by exactly 1h (1.5h true -> 2.5h computed), incorrectly tripping the 2h TTL.
        # 1.5h (not 1h) deliberately clears the +1h-inflated boundary so this test would have
        # failed under the pre-fix hardcoded-EASTERN_TZ code, not just coincidentally pass.
        # Built from the real current UTC instant expressed in Chicago wall-clock (not the
        # test host's own local time), so this is correct regardless of what timezone CI
        # happens to run in.
        now_chicago_naive = datetime.now(ZoneInfo("America/Chicago")).replace(tzinfo=None)
        ninety_min_ago_chicago = now_chicago_naive - timedelta(hours=1, minutes=30)
        mock_cur = Mock()
        mock_cur.fetchone.side_effect = [
            self._mock_row(ninety_min_ago_chicago),
            ("America/Chicago",),  # SHOW timezone
        ]
        with patch("algo.risk.market_exposure.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = mock_cur
            mock_db_ctx.return_value.__exit__.return_value = False
            result = MarketExposure().try_load_cached(eval_date)

        assert result is None or result.get("reason") != "cache_stale"

    def test_stale_cache_detected_correctly_against_real_session_timezone(self):
        eval_date = date(2026, 7, 20)
        # 2.5h old in the DB session's real wall-clock (Chicago) - genuinely stale under
        # the 2h TTL. The old hardcoded-Eastern bug added a further +1h to the computed
        # age (mislabeling a Chicago timestamp as Eastern, 1h behind), which would have
        # ALSO reported this as stale (same direction, larger margin) - so the meaningful
        # check is the inverse case above; this one guards the still-stale boundary.
        now_chicago_naive = datetime.now(ZoneInfo("America/Chicago")).replace(tzinfo=None)
        two_and_half_hours_ago = now_chicago_naive - timedelta(hours=2, minutes=30)
        mock_cur = Mock()
        mock_cur.fetchone.side_effect = [
            self._mock_row(two_and_half_hours_ago),
            ("America/Chicago",),
        ]
        with patch("algo.risk.market_exposure.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = mock_cur
            mock_db_ctx.return_value.__exit__.return_value = False
            result = MarketExposure().try_load_cached(eval_date)

        assert result is not None
        assert result.get("reason") == "cache_stale"


class TestMarketExposureWeightSum:
    def test_current_weights_sum_to_100(self):
        MarketExposure()  # must not raise

    def test_weights_are_the_documented_12_factors(self):
        weights = [
            MarketExposure.W_TREND_30WK,
            MarketExposure.W_SPY_MOMENTUM,
            MarketExposure.W_BREADTH_200,
            MarketExposure.W_SELLING_PRESSURE,
            MarketExposure.W_VIX,
            MarketExposure.W_CREDIT_SPREAD,
            MarketExposure.W_PUT_CALL,
            MarketExposure.W_NEW_HIGHS_LOWS,
            MarketExposure.W_AD_LINE,
            MarketExposure.W_BREADTH_50,
            MarketExposure.W_NAAIM,
            MarketExposure.W_AAII,
        ]
        assert len(weights) == 12
        assert sum(weights) == 100

    def test_drifted_weight_sum_raises(self, monkeypatch):
        monkeypatch.setattr(MarketExposure, "W_AAII", MarketExposure.W_AAII + 1)
        with pytest.raises(ValueError, match="must sum to exactly 100"):
            MarketExposure()

    def test_drifted_weight_sum_below_100_raises(self, monkeypatch):
        monkeypatch.setattr(MarketExposure, "W_TREND_30WK", MarketExposure.W_TREND_30WK - 5)
        with pytest.raises(ValueError, match="must sum to exactly 100"):
            MarketExposure()
