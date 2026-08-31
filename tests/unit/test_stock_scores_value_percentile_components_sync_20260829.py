"""Regression test for the 2026-08-29 fix: update_value_multiples_percentiles() (the post_run
batch pass that replaces Value's Pass-1 provisional fixed-curve P/E/P/B/P/S scores with real
cross-sectional percentile ranks, then recomputes value_score/composite_score) updated those
two columns but never touched stock_scores.components - the Pass-1 JSON breakdown built in
_compute_stock_score's "Build components breakdown for dashboard display" block.

Live-audited 2026-08-29: 4690/4708 scored symbols (99.6%) had components->'value' disagreeing
with the real value_score column, by up to 94 points on a 0-100 scale - because this batch
pass changes value_score for nearly every symbol but the UPDATE statement only SET value_score,
composite_score, updated_at. Not currently read by the scores API (lambda/api/routes/scores.py
rebuilds its breakdown from the individual *_score columns directly), so this was a latent
data-integrity bug rather than a live user-facing one - fixed anyway since components is a real
field in the API response model (lambda/api/models/responses.py).

Fix: also fetch ss.components, patch its 'value' key to the newly-corrected value_score, and
write it back in the same UPDATE.
"""

import json
from unittest.mock import MagicMock, patch

from loaders.load_stock_scores import StockScoresLoader


def _loader() -> StockScoresLoader:
    return StockScoresLoader.__new__(StockScoresLoader)


def _cursor_cm(cursor: MagicMock) -> MagicMock:
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=cursor)
    cm.__exit__ = MagicMock(return_value=False)
    return cm


class TestValuePercentileComponentsSync:
    def test_components_value_key_updated_alongside_value_score(self):
        loader = _loader()

        # Deliberately expensive-looking multiples so the fixed-curve Pass-1 score and the
        # (single-symbol-universe, always-50.0 per _percent_rank_cheap_high's own documented
        # behavior) percentile score disagree - guaranteeing this symbol hits the update path.
        pe, pb, ps, fwd_pe, dividend_yield = 24.10, 5.98, 7.25, 17.04, 0.0037
        pe_curve = loader._pe_curve_score(pe)
        pb_curve = loader._pb_curve_score(pb)
        ps_curve = loader._ps_curve_score(ps)
        fwd_pe_curve = loader._pe_curve_score(fwd_pe)

        weighted_sum_old = pe_curve * 0.12 + pb_curve * 0.39 + ps_curve * 0.34 + fwd_pe_curve * 0.04
        total_weight_old = 0.12 + 0.39 + 0.34 + 0.04 + 0.11  # dividend_yield present too
        # value_score_old is whatever Pass-1 actually stored - pick something plausible and
        # self-consistent so the delta arithmetic below is realistic, not just "whatever old was".
        value_score_old = round(max(0.0, min(100.0, weighted_sum_old / (total_weight_old - 0.11))), 2)
        composite_score_old = 34.11
        risk_score = 40.55
        components_old = {
            "quality": 66.82,
            "growth": 31.01,
            "value": value_score_old,
            "risk": risk_score,
            "momentum": 23.45,
        }

        row = (
            "META",
            value_score_old,
            composite_score_old,
            risk_score,
            components_old["quality"],
            components_old["growth"],
            components_old["momentum"],
            pe,
            pb,
            ps,
            fwd_pe,
            dividend_yield,
            None,
            None,  # pe_reason, fwd_pe_reason
            components_old,
        )

        select_cursor = MagicMock()
        select_cursor.fetchall.return_value = [row]
        write_cursor = MagicMock()

        db_contexts = [_cursor_cm(select_cursor), _cursor_cm(write_cursor)]
        with (
            patch("loaders.load_stock_scores.DatabaseContext", side_effect=db_contexts),
            patch("loaders.load_stock_scores.execute_values") as mock_execute_values,
        ):
            loader.update_value_multiples_percentiles()

        assert mock_execute_values.called, (
            "expected a write when the percentile score differs from the fixed-curve score"
        )
        _, args, _kwargs = mock_execute_values.mock_calls[0]
        updates = args[2]  # execute_values(cur, sql, updates, template=...)
        assert len(updates) == 1
        symbol, value_score_new, composite_score_new, components_json = updates[0]

        assert symbol == "META"
        components_new = json.loads(components_json)

        # The core bug: components['value'] must track the corrected value_score, not the
        # stale Pass-1 provisional one.
        assert components_new["value"] == value_score_new
        assert value_score_new != components_old["value"], (
            "test setup didn't actually exercise a value_score change - strengthen the fixture"
        )
        # Every other pillar's breakdown must survive untouched.
        assert components_new["quality"] == components_old["quality"]
        assert components_new["growth"] == components_old["growth"]
        assert components_new["risk"] == components_old["risk"]
        assert components_new["momentum"] == components_old["momentum"]
