"""Regression test for a 2026-09-07 pre-live-trading audit fix to _score_candidates_inline()
(algo/orchestrator/phase7_signal_generation.py).

minervini_trend_score is a genuine 0-8 point sum of eight boolean trend criteria
(loaders/load_trend_analysis.py) - 0.0 is a real, valid "fails every trend criterion" result,
not a sentinel for missing data. The degraded-data fallback block used `minervini = minervini or
2.0`, which treats a genuine 0.0 as falsy and silently overwrites it with the "conservative
estimate" 2.0 whenever weinstein_stage (the OTHER half of the `is None` trigger condition) is
also missing - actively inflating trend_template_score/signal_quality_score for a stock with a
dead trend template, exactly the class of stock Phase 8's min_signal_quality_score floor exists
to filter out.

Fix: only substitute the conservative default when the value is genuinely None.
"""

from datetime import date
from unittest.mock import MagicMock, patch

from algo.orchestrator.phase7_signal_generation import _score_candidates_inline


def _mock_db_context(tech_row: tuple) -> MagicMock:
    cur = MagicMock()
    cur.fetchone.return_value = tech_row
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=cur)
    cm.__exit__ = MagicMock(return_value=False)
    return cm


class TestMinervinizFalsyZeroNotOverwritten:
    def test_genuine_zero_minervini_with_missing_weinstein_not_inflated(self) -> None:
        """weinstein missing (None) triggers the degraded-data fallback block, but minervini's
        genuine 0.0 (fails every trend criterion) must survive, not get bumped to 2.0."""
        candidates = [{"symbol": "DEAD", "signal_date": date(2026, 9, 7)}]
        # (rsi, macd, macd_signal, minervini, weinstein, pct_from_52w_high)
        tech_row = (50.0, 1.0, 0.5, 0.0, None, -5.0)

        with (
            patch(
                "algo.orchestrator.phase7_signal_generation.DatabaseContext",
                return_value=_mock_db_context(tech_row),
            ),
            patch(
                "algo.orchestrator.phase7_signal_generation._fetch_institutional_ownership_for_scoring",
                return_value=None,
            ),
            patch(
                "algo.orchestrator.phase7_signal_generation._fetch_vcp_strength_for_scoring",
                return_value=None,
            ),
        ):
            result = _score_candidates_inline(candidates)

        assert len(result) == 1
        # trend_template_score for minervini=0.0 must be strictly lower than what minervini=2.0
        # (the old buggy substitution) would have produced - computed once, hand-verified via
        # compute_signal_quality_components(minervini_score=0.0) vs (minervini_score=2.0) with
        # otherwise-identical inputs: 8 vs 13.
        assert result[0]["trend_template_score"] == 8

    def test_genuinely_missing_minervini_still_gets_conservative_default(self) -> None:
        """Sanity counterpart: when minervini is ACTUALLY None (not a real 0.0), the
        conservative-default substitution must still apply - the fix must not disable it
        entirely."""
        candidates = [{"symbol": "NODATA", "signal_date": date(2026, 9, 7)}]
        tech_row = (50.0, 1.0, 0.5, None, None, -5.0)

        with (
            patch(
                "algo.orchestrator.phase7_signal_generation.DatabaseContext",
                return_value=_mock_db_context(tech_row),
            ),
            patch(
                "algo.orchestrator.phase7_signal_generation._fetch_institutional_ownership_for_scoring",
                return_value=None,
            ),
            patch(
                "algo.orchestrator.phase7_signal_generation._fetch_vcp_strength_for_scoring",
                return_value=None,
            ),
        ):
            result = _score_candidates_inline(candidates)

        assert len(result) == 1
        assert result[0]["trend_template_score"] == 13
