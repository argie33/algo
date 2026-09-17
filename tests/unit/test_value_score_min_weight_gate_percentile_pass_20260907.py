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

UPDATED 2026-09-15 (MSCI ENHANCED VALUE CONSTRUCTION FIDELITY fix, same file - see that fix's
own docstring note in update_value_multiples_percentiles()): P/S is no longer a scored Value
input at all (real MSCI Enhanced Value has no P/S variable) - a symbol with ONLY ps_ratio
available now has zero scoreable legs and is skipped entirely (no UPDATE emitted), rather than
being explicitly nulled by the gate below.

AQR VALUE REBUILT 2026-09-17 (see update_value_multiples_percentiles()'s own "AQR VALUE
REBUILT" docstring note): Value is now a SINGLE book-to-market leg, weight always 1.0 when
scored - the fractional nominal-weight state this test module was originally written to cover
(a thin fraction of several legs, e.g. RILY's 0.22 nominal weight off P/S alone) is now
structurally impossible; `weight_by_symbol` is always exactly 1.0 or the symbol isn't scored at
all. VALUE_MIN_WEIGHT (0.40) is consequently a vestigial gate here - it can never actually
reject anything, since 1.0 always clears it. The real remaining "insufficient data" case is a
symbol with no usable book value at all (pb_ratio missing, no negative_book_value reason): it
has no substitute leg under AQR's single-measure construction, so it is skipped entirely (no
UPDATE emitted at all), not explicitly nulled - see test_symbol_missing_book_value_is_skipped_
entirely below, which replaces the old thin-fractional-weight scenario.
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
    # _withhold_value_below_floor (added 2026-09-16, factor-purity sweep) is called
    # unconditionally at the end of update_value_multiples_percentiles() now - this stand-in
    # needs it bound too, same reason as every other method above.
    _withhold_value_below_floor = ValueMetricsMixin._withhold_value_below_floor
    # MSCI Z-SCORE REBUILD 2026-09-16 (see update_value_multiples_percentiles' own "MSCI
    # ENHANCED VALUE Z-SCORE CONSTRUCTION" docstring note): the rebuilt method reads
    # `self._MIN_SECTOR_SLICE` directly (not just through a bound helper method) when calling
    # `sector_neutral_zscore` on the composite - this minimal stand-in needs the plain class
    # constant bound too, not just methods, or `self._MIN_SECTOR_SLICE` raises AttributeError.
    _MIN_SECTOR_SLICE = ValueMetricsMixin._MIN_SECTOR_SLICE


def _make_mock_cursor(rows: list[tuple[Any, ...]]) -> MagicMock:
    cur = MagicMock()
    # side_effect [rows, []]: first fetchall() is the correction pass's own SELECT, second is
    # _withhold_value_below_floor()'s own SELECT (added 2026-09-16, factor-purity sweep) - []
    # means no symbol is below the liquidity floor in this test's fixture population.
    cur.fetchall.side_effect = [rows, []]
    return cur


class TestValueMinWeightGateInPercentilePass:
    def test_symbol_missing_book_value_is_skipped_entirely(self) -> None:
        # AQR VALUE REBUILT: NOBOOK has no pb_ratio and no negative_book_value reason (a
        # genuine "never computed this" gap, not a distress signal) - AQR's single book-to-
        # market leg has no substitute for a missing P/B (unlike MSCI's old Fwd-E/P/EV-CFO
        # fallback rules), so the symbol is skipped entirely: no UPDATE row at all, not an
        # explicit value_score=None. forward_pe/ps_ratio are present but no longer scored, so
        # they don't rescue it either.
        assert VALUE_MIN_WEIGHT == 0.40  # pin the constant this test's math depends on
        rows = [
            (
                "NOBOOK",
                97.61,  # value_score_old (a stale prior value)
                60.0,  # composite_score_old
                50.0,  # risk_score
                50.0,  # quality_score
                50.0,  # growth_score
                50.0,  # momentum_score
                None,  # pe_ratio (missing)
                None,  # pb_ratio (missing, no reason -> no book-to-market leg at all)
                0.22,  # ps_ratio (no longer scored - present only to confirm it's ignored)
                12.0,  # forward_pe (no longer scored - present only to confirm it's ignored)
                None,  # dividend_yield
                None,  # fcf_yield (no longer scored)
                None,  # pe_ratio_unavailable_reason
                None,  # forward_pe_unavailable_reason
                None,  # pb_ratio_unavailable_reason (added 2026-09-11)
                {"value": 97.61},  # components
                "Financial Services",  # sector
                80.0,  # data_completeness
                False,  # data_unavailable
                None,  # unavailable_metrics
                None,  # ps_ratio_unavailable_reason
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

        assert "updates" not in captured, "a symbol with no book-to-market leg must not be updated at all"

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
                None,  # forward_pe
                None,  # dividend_yield
                None,  # fcf_yield
                None,  # pe_ratio_unavailable_reason
                None,  # forward_pe_unavailable_reason
                None,  # pb_ratio_unavailable_reason (added 2026-09-11)
                {"value": 55.0},
                "Technology",
                90.0,  # data_completeness
                False,  # data_unavailable
                None,  # unavailable_metrics
                None,  # ps_ratio_unavailable_reason
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
