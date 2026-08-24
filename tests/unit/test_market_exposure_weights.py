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
    """2026-08-23 pillar redesign (see algo/risk/market_exposure.py module docstring):
    the flat 19-factor weight table was replaced by 3 coarse pillar weights (Trend &
    Momentum / Independent Risk Layers / Breadth & Sentiment) per DeMiguel/Garlappi/
    Uppal's finding that naive/coarse weighting beats precision-tuned weighting
    out-of-sample. Individual sub-signals within a pillar are blended by
    MarketExposure._blend_scores(), which renormalizes over whatever's available and
    has no fixed-sum invariant of its own - only the top-level pillar allocation is a
    real invariant worth a hard fail-fast check.
    """

    def test_current_weights_sum_to_100(self):
        MarketExposure()  # must not raise

    def test_weights_are_the_documented_3_pillars(self):
        weights = [
            MarketExposure.W_PILLAR_TREND,
            MarketExposure.W_PILLAR_RISK,
            MarketExposure.W_PILLAR_CONFIRM,
        ]
        assert len(weights) == 3
        assert sum(weights) == pytest.approx(100.0)

    def test_drifted_weight_sum_raises(self, monkeypatch):
        monkeypatch.setattr(MarketExposure, "W_PILLAR_CONFIRM", MarketExposure.W_PILLAR_CONFIRM + 1)
        with pytest.raises(ValueError, match="must sum to exactly 100"):
            MarketExposure()

    def test_drifted_weight_sum_below_100_raises(self, monkeypatch):
        monkeypatch.setattr(MarketExposure, "W_PILLAR_TREND", MarketExposure.W_PILLAR_TREND - 5)
        with pytest.raises(ValueError, match="must sum to exactly 100"):
            MarketExposure()


class TestMarketExposureBlendScores:
    """MarketExposure._blend_scores() renormalizes a pillar's sub-signal weights over
    whatever's actually available - the mechanism that replaced the prior design's
    avail_max renormalization at the flat-19-factor level.
    """

    def test_full_weight_blend_is_plain_weighted_average(self):
        result = MarketExposure._blend_scores([(80.0, 0.55), (60.0, 0.35), (40.0, 0.10)])
        assert result == pytest.approx(80.0 * 0.55 + 60.0 * 0.35 + 40.0 * 0.10)

    def test_renormalizes_when_an_optional_input_is_missing(self):
        # market_technicals (0.10 weight) unavailable -> renormalize over the remaining
        # 0.55/0.35 (summing to 0.90) rather than leaving 10% of the pillar unspent.
        result = MarketExposure._blend_scores([(80.0, 0.55), (60.0, 0.35)])
        expected = (80.0 * 0.55 + 60.0 * 0.35) / 0.90
        assert result == pytest.approx(expected)

    def test_raises_when_no_weight_available(self):
        with pytest.raises(ValueError, match="No weight available"):
            MarketExposure._blend_scores([])
