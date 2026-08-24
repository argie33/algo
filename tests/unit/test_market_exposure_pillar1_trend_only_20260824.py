#!/usr/bin/env python3
"""Regression test for the 2026-08-24b Pillar 1 reweight to trend_30wk-only.

Backtest evidence (SPY 1993-2026, QQQ 1999-2026 - see market_exposure.py's module
docstring "PILLAR 1 SUB-WEIGHT EVIDENCE") showed the prior 55/35/10 trend_30wk/
spy_momentum/market_technicals blend underperformed trend_30wk alone on risk-adjusted
return on both assets. spy_momentum and market_technicals are still computed and
persisted (dashboard display, audit trail) but must contribute exactly zero to
pillar_trend_score - a future edit that silently re-introduces their weight would
regress the composite back to the unvalidated blend without anyone noticing.
"""

from algo.risk.market_exposure import MarketExposure


class TestPillar1TrendOnlyWeights:
    def test_subweight_constants_are_trend_only(self):
        assert MarketExposure.SUBW_TREND_30WK == 1.0
        assert MarketExposure.SUBW_SPY_MOMENTUM == 0.0
        assert MarketExposure.SUBW_MARKET_TECHNICALS == 0.0

    def test_pillar_trend_score_ignores_momentum_and_technicals(self):
        """pillar_trend_score must equal trend_30wk's own score regardless of what
        spy_momentum/market_technicals read - they're computed for display/audit only."""
        trend_score = 73.0
        for mom_score, mtech_score in [(0.0, 0.0), (100.0, 100.0), (50.0, 12.0), (0.0, 100.0)]:
            result = MarketExposure._blend_scores(
                [
                    (trend_score, MarketExposure.SUBW_TREND_30WK),
                    (mom_score, MarketExposure.SUBW_SPY_MOMENTUM),
                    (mtech_score, MarketExposure.SUBW_MARKET_TECHNICALS),
                ]
            )
            assert result == trend_score, (
                f"pillar_trend_score={result} should equal trend_30wk's own score "
                f"({trend_score}) regardless of momentum={mom_score}/technicals={mtech_score}"
            )

    def test_pillar_trend_score_matches_trend_only_when_optional_signals_missing(self):
        """market_technicals is optional and degrades gracefully - with it entirely
        absent from the blend list (not just zero-weighted), the score must still equal
        trend_30wk alone, matching the mtech-unavailable renormalization path."""
        trend_score = 41.5
        result = MarketExposure._blend_scores(
            [
                (trend_score, MarketExposure.SUBW_TREND_30WK),
                (99.0, MarketExposure.SUBW_SPY_MOMENTUM),
            ]
        )
        assert result == trend_score
