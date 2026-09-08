"""Regression test for a 2026-09-07 fix (goal session: "look at our scores, you'll see tons of
stupid shit" leaderboard audit) to loaders/stock_scores/value_metrics.py's
update_value_multiples_percentiles().

_score_value's VALUE_MIN_WEIGHT (loaders/stock_scores/value_score.py) gates Pass 1 against
building a value_score off too thin a sample (< 40% of nominal PE/PB/PS/ForwardPE/Dividend
weight). But update_value_multiples_percentiles() FULLY RECOMPUTES value_score from scratch every
run and never re-applied that same gate - so a symbol that clears Pass 1 (e.g. off dividend_yield
alone) but loses components by the time this batch pass runs, or a symbol whose PE got excluded by
_pe_earnings_too_volatile/_pe_earnings_tax_benefit_inflated with no PB available, can end up with
total_weight as low as 0.27 (a single multiple) - and since `_percent_rank_cheap_high_sector_
relative` has no winsorization, that ONE metric's raw percentile becomes the entire value_score
verbatim.

Live-confirmed RILY (B. Riley Financial): PE excluded by _pe_earnings_too_volatile, PB missing,
only PS available (ratio 0.22) - value_score=97.61, #1 in the whole 5,047-symbol universe off a
single metric with no PE/PB cross-check.
"""

from typing import Any
from unittest.mock import MagicMock, patch

from loaders.stock_scores.value_score import VALUE_MIN_WEIGHT


class _Loader:
    """Minimal stand-in mixing in just the method under test, avoiding StockScoresLoader's
    full import graph (same pattern as this file's sibling percentile-ranking tests)."""

    from loaders.stock_scores.value_metrics import ValueMetricsMixin

    update_value_multiples_percentiles = ValueMetricsMixin.update_value_multiples_percentiles
    _components_with_corrected_value = staticmethod(ValueMetricsMixin._components_with_corrected_value)
    _percent_rank_cheap_high_sector_relative = staticmethod(ValueMetricsMixin._percent_rank_cheap_high_sector_relative)


def _make_mock_cursor(rows: list[tuple[Any, ...]]) -> MagicMock:
    cur = MagicMock()
    cur.fetchall.return_value = rows
    return cur


class TestValueMinWeightGateInPercentilePass:
    def test_single_metric_below_min_weight_is_nulled_not_scored(self) -> None:
        # THINPS: only ps_ratio available (0.27 weight) - below VALUE_MIN_WEIGHT (0.40). Old
        # (buggy) behavior: value_score_new = ps_pct alone (could hit 97+ on a single extreme
        # ratio). Fixed behavior: value_score must come back NULL, same "insufficient data,
        # don't fabricate a score" treatment Pass 1 already uses.
        assert VALUE_MIN_WEIGHT == 0.40  # pin the constant this test's math depends on
        rows = [
            (
                "THINPS",
                97.61,  # value_score_old (the live buggy value)
                60.0,  # composite_score_old
                50.0,  # risk_score
                50.0,  # quality_score
                50.0,  # growth_score
                50.0,  # momentum_score
                None,  # pe_ratio (excluded upstream, no reason -> contributes 0 weight)
                None,  # pb_ratio (missing)
                0.22,  # ps_ratio
                None,  # forward_pe
                None,  # dividend_yield
                None,  # pe_ratio_unavailable_reason
                None,  # forward_pe_unavailable_reason
                {"value": 97.61},  # components
                "Financial Services",  # sector
                80.0,  # data_completeness
                False,  # data_unavailable
                None,  # unavailable_metrics
            )
        ]
        cur = _make_mock_cursor(rows)
        mock_db_context = MagicMock()
        mock_db_context.__enter__ = MagicMock(return_value=cur)
        mock_db_context.__exit__ = MagicMock(return_value=False)

        loader = _Loader()
        captured: dict[str, Any] = {}

        def _fake_execute_values(_cur: Any, _sql: str, updates: Any, template: str) -> None:
            captured["updates"] = updates

        with (
            patch("loaders.stock_scores.value_metrics._owner") as mock_owner,
        ):
            mock_owner.return_value.DatabaseContext.return_value = mock_db_context
            mock_owner.return_value.execute_values.side_effect = _fake_execute_values
            loader.update_value_multiples_percentiles()

        assert "updates" in captured, "expected an UPDATE for THINPS (score changed from 97.61)"
        (
            symbol,
            value_score_new,
            _composite_new,
            _components_json,
            _completeness_new,
            _unavailable_new,
            _unavailable_metrics_json,
            _reason_new,
        ) = captured["updates"][0]
        assert symbol == "THINPS"
        assert value_score_new is None

    def test_two_core_multiples_at_min_weight_still_scores(self) -> None:
        # Sanity counterpart: PE + PB (0.27 + 0.27 = 0.54, clears VALUE_MIN_WEIGHT) must still
        # produce a real float, not be swept up by the new gate.
        rows = [
            (
                "TWOMETRIC",
                55.0,
                60.0,
                50.0,
                50.0,
                50.0,
                50.0,
                15.0,  # pe_ratio
                2.0,  # pb_ratio
                None,  # ps_ratio
                None,
                None,
                None,
                None,
                {"value": 55.0},
                "Technology",
                90.0,  # data_completeness
                False,  # data_unavailable
                None,  # unavailable_metrics
            )
        ]
        cur = _make_mock_cursor(rows)
        mock_db_context = MagicMock()
        mock_db_context.__enter__ = MagicMock(return_value=cur)
        mock_db_context.__exit__ = MagicMock(return_value=False)

        loader = _Loader()
        captured: dict[str, Any] = {}

        def _fake_execute_values(_cur: Any, _sql: str, updates: Any, template: str) -> None:
            captured["updates"] = updates

        with patch("loaders.stock_scores.value_metrics._owner") as mock_owner:
            mock_owner.return_value.DatabaseContext.return_value = mock_db_context
            mock_owner.return_value.execute_values.side_effect = _fake_execute_values
            loader.update_value_multiples_percentiles()

        if "updates" in captured:
            (
                _symbol,
                value_score_new,
                _composite_new,
                _components_json,
                _completeness_new,
                _unavailable_new,
                _unavailable_metrics_json,
                _reason_new,
            ) = captured["updates"][0]
            assert isinstance(value_score_new, float)
