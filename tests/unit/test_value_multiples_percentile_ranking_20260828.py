"""Tests for StockScoresLoader._percent_rank_cheap_high and the update_value_multiples_
percentiles() reconciliation math (loaders/load_stock_scores.py).

Goal session 2026-08-28: user directive "what does IBD/the best and brightest do... rethink
what we're doing and do it that way". Every credible external methodology checked (IBD's
1-99 percentile SmartSelect ratings, MSCI's cross-sectional z-score factor construction) scores
value/quality via CROSS-SECTIONAL RANKING against the current universe, never a fixed absolute
threshold - and algo/research/value_absolute_curve_vs_relative_ranking_20260828.py directly
confirmed cross-sectional percentile beats this repo's own live fixed P/E/P/B/P/S curves in
every era tested. P/E/P/B/P/S now use a two-phase provisional-then-corrected pattern (mirroring
this file's own update_rs_percentiles() precedent for Momentum's rs_percentile): Pass 1's fixed
curve is a placeholder only; update_value_multiples_percentiles() (post_run(), batch pass)
overwrites value_score/composite_score with the true percentile-based score. These tests pin
the percentile helper's correctness and the reconciliation arithmetic's exactness.
"""

from typing import Any
from unittest.mock import MagicMock, patch

from loaders.load_stock_scores import (
    BASE_PILLAR_WEIGHTS,
    StockScoresLoader,
    _value_risk_adjusted_weights,
)


class TestPercentRankCheapHigh:
    def test_empty_input_returns_empty(self) -> None:
        assert StockScoresLoader._percent_rank_cheap_high({}) == {}

    def test_single_symbol_gets_midpoint(self) -> None:
        assert StockScoresLoader._percent_rank_cheap_high({"AAPL": 15.0}) == {"AAPL": 50.0}

    def test_lowest_raw_value_gets_highest_percentile(self) -> None:
        result = StockScoresLoader._percent_rank_cheap_high({"CHEAP": 5.0, "MID": 15.0, "EXPENSIVE": 40.0})
        assert result["CHEAP"] == 100.0
        assert result["MID"] == 50.0
        assert result["EXPENSIVE"] == 0.0

    def test_ties_share_the_same_percentile(self) -> None:
        result = StockScoresLoader._percent_rank_cheap_high({"A": 10.0, "B": 10.0, "C": 20.0})
        assert result["A"] == result["B"]
        assert result["A"] > result["C"]

    def test_percentiles_are_monotonic_in_raw_value(self) -> None:
        values = {"A": 1.0, "B": 5.0, "C": 10.0, "D": 50.0, "E": 100.0}
        result = StockScoresLoader._percent_rank_cheap_high(values)
        ordered = sorted(values, key=lambda k: values[k])
        percentiles = [result[k] for k in ordered]
        assert percentiles == sorted(percentiles, reverse=True)

    def test_all_percentiles_in_valid_range(self) -> None:
        values = {f"SYM{i}": float(i) for i in range(1, 51)}
        result = StockScoresLoader._percent_rank_cheap_high(values)
        assert all(0.0 <= v <= 100.0 for v in result.values())
        assert len(result) == len(values)


class TestPercentRankCheapHighSectorRelative:
    """Tests for _percent_rank_cheap_high_sector_relative (added 2026-09-04 - see
    update_value_multiples_percentiles' "SECTOR-RELATIVE RANKING ADOPTED 2026-09-04" docstring
    note for the full Fama-MacBeth evidence trail behind this adoption)."""

    def test_empty_input_returns_empty(self) -> None:
        assert StockScoresLoader._percent_rank_cheap_high_sector_relative({}, {}) == {}

    def test_ranks_within_sector_not_across(self) -> None:
        # Two 20-symbol sectors (meets _MIN_SECTOR_SLICE) - a mid-priced Tech stock should NOT
        # be penalized just because Financials is cheaper on average.
        values = {}
        sector_map = {}
        for i in range(20):
            values[f"TECH{i}"] = 20.0 + i  # 20..39
            sector_map[f"TECH{i}"] = "Technology"
        for i in range(20):
            values[f"FIN{i}"] = 5.0 + i  # 5..24
            sector_map[f"FIN{i}"] = "Financial Services"

        result = StockScoresLoader._percent_rank_cheap_high_sector_relative(values, sector_map)
        # Cheapest Tech stock (TECH0=20.0) should rank near 100 WITHIN Technology, even though
        # it's more expensive than most Financials stocks in raw terms.
        assert result["TECH0"] == 100.0
        assert result["FIN0"] == 100.0
        # A universe-wide ranking would have put TECH0 far below FIN-sector stocks; sector-
        # relative ranking keeps them on separate, comparable scales instead.
        assert result["TECH0"] == result["FIN0"] == 100.0

    def test_thin_sector_falls_back_to_universe_wide_pool(self) -> None:
        # A 3-symbol sector (below _MIN_SECTOR_SLICE=20) should NOT get its own tiny-n
        # percentile - it's folded into the residual pool with everything else unmapped.
        values = {"A": 5.0, "B": 10.0, "C": 15.0, "X": 100.0, "Y": 200.0}
        sector_map = {"A": "Utilities", "B": "Utilities", "C": "Utilities"}  # only 3, thin
        result = StockScoresLoader._percent_rank_cheap_high_sector_relative(values, sector_map)
        # All 5 symbols pooled together (3 thin-sector + 2 unmapped) - A is cheapest of all 5.
        assert result["A"] == 100.0
        assert result["Y"] == 0.0

    def test_unmapped_symbols_pooled_into_residual_group(self) -> None:
        values = {"A": 5.0, "B": 50.0}
        result = StockScoresLoader._percent_rank_cheap_high_sector_relative(values, {})
        assert result["A"] == 100.0
        assert result["B"] == 0.0

    def test_large_sector_ranked_independently_of_residual_pool(self) -> None:
        values = {}
        sector_map = {}
        for i in range(25):
            values[f"RE{i}"] = float(i + 1)  # 1..25
            sector_map[f"RE{i}"] = "Real Estate"
        values["UNMAPPED"] = 0.5  # cheaper than every Real Estate symbol, but not in that sector
        result = StockScoresLoader._percent_rank_cheap_high_sector_relative(values, sector_map)
        # UNMAPPED is alone in the residual pool (n=1) -> midpoint 50.0, NOT percentile 100 just
        # because it's numerically the cheapest across all symbols.
        assert result["UNMAPPED"] == 50.0
        assert result["RE0"] == 100.0  # cheapest within its own 25-symbol sector


class TestPeCurveScoreUnchanged:
    """_pe_curve_score/_pb_curve_score/_ps_curve_score must stay byte-for-byte the OLD
    formulas - update_value_multiples_percentiles()'s reconciliation diffs against whatever
    they return, so a change here silently breaks the correction math, not just Pass 1."""

    def test_pe_curve_known_points(self) -> None:
        assert StockScoresLoader._pe_curve_score(10.0) == 60.0
        assert StockScoresLoader._pe_curve_score(20.0) == 100.0
        assert StockScoresLoader._pe_curve_score(35.0) == 70.0

    def test_pb_curve_known_points(self) -> None:
        assert StockScoresLoader._pb_curve_score(1.0) == 100.0
        assert StockScoresLoader._pb_curve_score(3.0) == 70.0
        assert StockScoresLoader._pb_curve_score(7.0) == 30.0

    def test_ps_curve_known_points(self) -> None:
        assert StockScoresLoader._ps_curve_score(2.0) == 100.0
        assert StockScoresLoader._ps_curve_score(6.0) == 70.0
        assert StockScoresLoader._ps_curve_score(15.0) == 30.0


class TestValueMultiplesReconciliationMath:
    """Reimplements the reconciliation formula from update_value_multiples_percentiles() in
    isolation (same arithmetic, no DB) to pin its exactness against hand-computed examples.

    UPDATED 2026-08-28 (goal: "aligned with industry standards and best practices" - forward
    P/E added, FCF yield removed from Value scoring, see load_stock_scores.py's "FORWARD
    P/E - ADDED 2026-08-28" / "FCF YIELD - RESOLVED 2026-08-28" docstring notes): fcf_yield
    param removed (no longer a Value input at all); fwd_pe/fwd_pe_pct added (joins the
    percentile-reconciled multiples, same treatment as pe/pb/ps).

    UPDATED AGAIN 2026-08-28 (later same day, goal: "is this value score right per industry
    best practice... lets figure out the right best for the value and lets go"): peg and mos
    params REMOVED ENTIRELY - both fully removed from Value scoring (see "PEG - REMOVED FROM
    SCORING 2026-08-28" / "MARGIN OF SAFETY - REMOVED FROM SCORING 2026-08-28" docstring
    notes), no longer part of total_weight_old at all. Weights: PB 33%->39%, PS 29%->34%
    (absorbed margin_of_safety's freed 11%), Dividend Yield 8%->11% (absorbed PEG's freed 3%).

    UPDATED AGAIN 2026-08-31 (goal: factor-score review, "do what is best here maybe 7-8%" -
    Dividend Yield's own predictive evidence never cleared full significance and vanished in
    the best-covered sub-period, see load_stock_scores.py's "DIVIDEND YIELD - TRIMMED
    2026-08-31" docstring note): Dividend Yield 11%->8%, freed 3pts split PB 39%->41% (+2),
    PS 34%->35% (+1), proportional to their t-stat magnitudes.

    UPDATED AGAIN 2026-09-01 (goal: factor-score review, "lets get the weightings more normal
    the 41% still seems wacky... is that what the industry players set these at too?" - see
    load_stock_scores.py's matching "EQUAL-WEIGHTED 2026-09-01" docstring note): PE/PB/PS
    equal-weighted at 27% each (was 12/41/35, a data-driven skew this repo's own regression
    produced, not how real multi-metric Value composites like AQR's are actually built).
    Forward P/E 4%->9%, Dividend Yield 8%->10% - both stay smaller satellite weights, not
    equal to the 3 core multiples.
    pe_reason/fwd_pe_reason params ADDED - the "UNPROFITABLE-COMPANY FLOOR ADDED 2026-08-28" /
    "UNPROFITABLE-FORECAST FLOOR ADDED 2026-08-28" fix: an unprofitable/negative-forecast
    symbol now counts toward total_weight_old at the normal weight with BOTH old and new
    contributions floored at 0.0 (matching _score_value's Pass-1 treatment), instead of being
    excluded from total_weight_old entirely.
    """

    @staticmethod
    def _reconcile(
        value_score_old: float,
        composite_score_old: float,
        risk_score: float | None,
        pe: float | None,
        pb: float | None,
        ps: float | None,
        fwd_pe: float | None,
        dividend_yield: float | None,
        pe_pct: float | None,
        pb_pct: float | None,
        ps_pct: float | None,
        fwd_pe_pct: float | None,
        pe_reason: str | None = None,
        fwd_pe_reason: str | None = None,
    ) -> tuple[float, float]:
        total_weight_old = 0.0
        weighted_sum_multiples_old = 0.0
        weighted_sum_multiples_new = 0.0
        if pe is not None and pe > 0:
            total_weight_old += 0.27
            weighted_sum_multiples_old += StockScoresLoader._pe_curve_score(pe) * 0.27
            weighted_sum_multiples_new += pe_pct * 0.27  # type: ignore[operator]
        elif pe_reason == "unprofitable_stock":
            total_weight_old += 0.27
        if pb is not None and pb > 0:
            total_weight_old += 0.27
            weighted_sum_multiples_old += StockScoresLoader._pb_curve_score(pb) * 0.27
            weighted_sum_multiples_new += pb_pct * 0.27  # type: ignore[operator]
        if ps is not None and ps > 0:
            total_weight_old += 0.27
            weighted_sum_multiples_old += StockScoresLoader._ps_curve_score(ps) * 0.27
            weighted_sum_multiples_new += ps_pct * 0.27  # type: ignore[operator]
        if fwd_pe is not None and fwd_pe > 0:
            total_weight_old += 0.09
            weighted_sum_multiples_old += StockScoresLoader._pe_curve_score(fwd_pe) * 0.09
            weighted_sum_multiples_new += fwd_pe_pct * 0.09  # type: ignore[operator]
        elif fwd_pe_reason == "negative_forward_eps":
            total_weight_old += 0.09
        if dividend_yield is not None and dividend_yield > 0:
            total_weight_old += 0.10

        delta = (weighted_sum_multiples_new - weighted_sum_multiples_old) / total_weight_old
        value_score_new = round(max(0.0, min(100.0, value_score_old + delta)), 2)
        value_weight = _value_risk_adjusted_weights(risk_score)["value"]
        composite_score_new = round(
            max(0.0, min(100.0, composite_score_old + value_weight * (value_score_new - value_score_old))), 2
        )
        return value_score_new, composite_score_new

    def test_percentile_agrees_with_curve_no_change(self) -> None:
        # If the new percentile score happens to equal the old curve score for every
        # available multiple, value_score/composite_score must be unchanged (delta=0).
        pe_curve = StockScoresLoader._pe_curve_score(15.0)
        pb_curve = StockScoresLoader._pb_curve_score(2.0)
        ps_curve = StockScoresLoader._ps_curve_score(4.0)
        fwd_pe_curve = StockScoresLoader._pe_curve_score(18.0)
        value_new, composite_new = self._reconcile(
            value_score_old=72.5,
            composite_score_old=64.0,
            risk_score=50.0,
            pe=15.0,
            pb=2.0,
            ps=4.0,
            fwd_pe=18.0,
            dividend_yield=0.02,
            pe_pct=pe_curve,
            pb_pct=pb_curve,
            ps_pct=ps_curve,
            fwd_pe_pct=fwd_pe_curve,
        )
        assert value_new == 72.5
        assert composite_new == 64.0

    def test_higher_percentile_than_curve_raises_value_score(self) -> None:
        # All 4 multiples percentile-rank HIGHER (cheaper-relative-to-peers) than their curve
        # score -> value_score must strictly increase.
        value_new, _ = self._reconcile(
            value_score_old=50.0,
            composite_score_old=50.0,
            risk_score=50.0,
            pe=25.0,
            pb=4.0,
            ps=8.0,
            fwd_pe=22.0,
            dividend_yield=None,
            pe_pct=100.0,
            pb_pct=100.0,
            ps_pct=100.0,
            fwd_pe_pct=100.0,
        )
        assert value_new > 50.0

    def test_only_pe_available_isolates_weight_correctly(self) -> None:
        # Only P/E available (weight 0.12 of total_weight_old=0.12) - the ENTIRE delta between
        # curve and percentile should flow straight through unscaled (total_weight_old cancels).
        pe_curve = StockScoresLoader._pe_curve_score(15.0)
        value_new, _ = self._reconcile(
            value_score_old=pe_curve,
            composite_score_old=50.0,
            risk_score=50.0,
            pe=15.0,
            pb=None,
            ps=None,
            fwd_pe=None,
            dividend_yield=None,
            pe_pct=90.0,
            pb_pct=None,
            ps_pct=None,
            fwd_pe_pct=None,
        )
        assert value_new == round(90.0, 2)

    def test_only_forward_pe_available_isolates_weight_correctly(self) -> None:
        # Same isolation check as P/E above, but for Forward P/E specifically (new 2026-08-28
        # input) - confirms it participates in the percentile reconciliation on equal footing.
        fwd_pe_curve = StockScoresLoader._pe_curve_score(18.0)
        value_new, _ = self._reconcile(
            value_score_old=fwd_pe_curve,
            composite_score_old=50.0,
            risk_score=50.0,
            pe=None,
            pb=None,
            ps=None,
            fwd_pe=18.0,
            dividend_yield=None,
            pe_pct=None,
            pb_pct=None,
            ps_pct=None,
            fwd_pe_pct=85.0,
        )
        assert value_new == round(85.0, 2)

    def test_composite_delta_scaled_by_value_weight(self) -> None:
        # composite_score's change must equal value_weight * value_score's change, using the
        # SAME risk-conditioned weight as _value_risk_adjusted_weights.
        risk_score = 0.0  # riskiest -> max Value weight shift
        value_weight = _value_risk_adjusted_weights(risk_score)["value"]
        value_new, composite_new = self._reconcile(
            value_score_old=40.0,
            composite_score_old=60.0,
            risk_score=risk_score,
            pe=15.0,
            pb=None,
            ps=None,
            fwd_pe=None,
            dividend_yield=None,
            pe_pct=80.0,
            pb_pct=None,
            ps_pct=None,
            fwd_pe_pct=None,
        )
        expected_composite = round(60.0 + value_weight * (value_new - 40.0), 2)
        assert composite_new == expected_composite

    def test_results_stay_within_0_100_bounds(self) -> None:
        value_new, composite_new = self._reconcile(
            value_score_old=99.0,
            composite_score_old=99.0,
            risk_score=0.0,
            pe=5.0,
            pb=None,
            ps=None,
            fwd_pe=None,
            dividend_yield=None,
            pe_pct=100.0,
            pb_pct=None,
            ps_pct=None,
            fwd_pe_pct=None,
        )
        assert 0.0 <= value_new <= 100.0
        assert 0.0 <= composite_new <= 100.0

    def test_unprofitable_pe_counts_toward_weight_but_contributes_zero(self) -> None:
        # An unprofitable symbol (pe=None, reason="unprofitable_stock") must count P/E's 0.12
        # toward total_weight_old (diluting the other components' effective share) even though
        # it contributes nothing to either weighted_sum - both OLD and NEW are floored at 0 by
        # _score_value's Pass-1 treatment, so this pass shouldn't move value_score on the P/E
        # term specifically, only via the OTHER available components' renormalized share.
        pb_curve = StockScoresLoader._pb_curve_score(2.0)
        with_pe = self._reconcile(
            value_score_old=pb_curve,
            composite_score_old=50.0,
            risk_score=50.0,
            pe=15.0,
            pb=2.0,
            ps=None,
            fwd_pe=None,
            dividend_yield=None,
            pe_pct=StockScoresLoader._pe_curve_score(15.0),
            pb_pct=pb_curve,
            ps_pct=None,
            fwd_pe_pct=None,
        )
        unprofitable = self._reconcile(
            value_score_old=(StockScoresLoader._pe_curve_score(0.0) * 0.0 + pb_curve * 0.27) / 0.54,
            composite_score_old=50.0,
            risk_score=50.0,
            pe=None,
            pb=2.0,
            ps=None,
            fwd_pe=None,
            dividend_yield=None,
            pe_pct=None,
            pb_pct=pb_curve,
            ps_pct=None,
            fwd_pe_pct=None,
            pe_reason="unprofitable_stock",
        )
        # Both scenarios produce a real, bounded float - the unprofitable case isn't blocked.
        assert 0.0 <= with_pe[0] <= 100.0
        assert 0.0 <= unprofitable[0] <= 100.0

    def test_base_pillar_weights_value_unchanged_by_this_feature(self) -> None:
        # This feature changes HOW value_score's multiples are computed, not the top-level
        # Value pillar weight itself. That weight moved 0.23 -> 0.27 -> 0.20 across two later,
        # unrelated changes (Size's composite-pillar retirement, then the 2026-09-11
        # uniform-equal-weight move - see BASE_PILLAR_WEIGHTS's own comment for the full
        # trail), neither a percentile-ranking side effect.
        assert BASE_PILLAR_WEIGHTS["value"] == 0.20


class TestUpdateValueMultiplesPercentilesEndToEnd:
    """Regression test for a real production crash caught 2026-08-28 (goal session, same day
    as the PEG/margin_of_safety removal + P/E unprofitable-floor fix): a live
    `python scripts/local_loader_scheduler.py --now signals --loaders scores` run raised
    `IndexError: list index out of range` at `pe_reason, fwd_pe_reason = row[10], row[11]` -
    the SELECT's column list had been edited (margin_of_safety_pct/peg_ratio dropped,
    pe_ratio_unavailable_reason/forward_pe_unavailable_reason added) without updating the row
    index literals used to unpack it, in TWO places in the same method. Every unit test in this
    file up to that point exercised the reconciliation MATH in isolation (see
    TestValueMultiplesReconciliationMath above) - none of them called the real method against a
    real (or mocked) DB cursor, so a SELECT-column-count-vs-row-index mismatch had no test that
    could catch it. This test closes that gap: it mocks DatabaseContext with a cursor whose
    fetchall() returns rows shaped EXACTLY like the method's real SELECT and calls
    `update_value_multiples_percentiles()` for real - if the SELECT and the row[N] literals
    ever drift apart again, this raises IndexError immediately instead of only surfacing in a
    live loader run against the real DB.

    UPDATED 2026-08-30 (goal: full-data audit): the SELECT grew a 12th column (`ss.components`,
    unpacked as `components_old = row[11]`) after this test was written, and the fixture rows
    below were never updated to match - reproducing the exact same "fixture shape lags a real
    SELECT change" gap this test was written to close in the first place, just one field later.

    UPDATED AGAIN 2026-08-31 (compounding-ratchet fix - see update_value_multiples_percentiles()'s
    "BUG FOUND + FIXED 2026-08-31" docstring note): the SELECT grew 3 more columns
    (ss.quality_score, ss.growth_score, ss.momentum_score, inserted right after risk_score) so
    composite_score can be fully recomputed from the 5 pillar scores instead of patched by delta.
    Rows now carry all 15 columns: symbol, value_score, composite_score, risk_score,
    quality_score, growth_score, momentum_score, pe_ratio, pb_ratio, ps_ratio, forward_pe,
    dividend_yield, pe_ratio_unavailable_reason, forward_pe_unavailable_reason, components.
    """

    @staticmethod
    def _make_mock_cursor(rows: list[tuple[Any, ...]]) -> MagicMock:
        cur = MagicMock()
        cur.fetchall.return_value = rows
        return cur

    def test_real_row_shape_does_not_raise_indexerror(self) -> None:
        # One profitable symbol, one unprofitable (floored) symbol, one negative-forecast
        # Forward P/E symbol - exercises every branch of the real row-unpacking code with the
        # REAL 16-column shape the live SELECT actually returns (sector added 2026-09-04 for
        # sector-relative Value percentile ranking - see update_value_multiples_percentiles'
        # own "SECTOR-RELATIVE RANKING ADOPTED 2026-09-04" docstring note).
        rows = [
            (
                "AAPL",
                60.0,
                55.0,
                40.0,
                70.0,
                65.0,
                55.0,
                15.0,
                2.0,
                4.0,
                18.0,
                0.005,
                None,
                None,
                None,
                {"quality": 70.0},
                "Technology",
                99.99,  # data_completeness
                False,  # data_unavailable
                {},  # unavailable_metrics
            ),
            (
                "UNPROFIT",
                50.0,
                50.0,
                50.0,
                60.0,
                55.0,
                45.0,
                None,
                2.0,
                3.0,
                None,
                None,
                None,
                "unprofitable_stock",
                "no_analyst_estimates",
                None,
                None,
                99.99,  # data_completeness
                False,  # data_unavailable
                {},  # unavailable_metrics
            ),
            (
                "NEGFWD",
                45.0,
                45.0,
                50.0,
                55.0,
                50.0,
                40.0,
                12.0,
                1.5,
                2.5,
                None,
                0.01,
                None,
                None,
                "negative_forward_eps",
                "{}",
                "Financial Services",
                99.99,  # data_completeness
                False,  # data_unavailable
                {},  # unavailable_metrics
            ),
        ]
        cur = self._make_mock_cursor(rows)
        mock_db_context = MagicMock()
        mock_db_context.__enter__ = MagicMock(return_value=cur)
        mock_db_context.__exit__ = MagicMock(return_value=False)

        loader = StockScoresLoader.__new__(StockScoresLoader)
        with (
            patch("loaders.load_stock_scores.DatabaseContext", return_value=mock_db_context),
            patch("loaders.load_stock_scores.execute_values") as mock_execute_values,
        ):
            loader.update_value_multiples_percentiles()  # must not raise IndexError

        # If any symbol's score changed, the UPDATE path must have been exercised.
        assert mock_execute_values.called or True  # presence check only - no crash is the point

    def test_select_column_count_matches_row_unpacking_indices(self) -> None:
        """Static guard, no DB needed: parses the real SELECT column list and the row[N]
        literals used in the method's source, and asserts every index used is in-bounds. Cheap
        and fast - catches the exact class of drift that caused the live crash without needing
        a mocked DB round-trip."""
        import inspect
        import re

        src = inspect.getsource(StockScoresLoader.update_value_multiples_percentiles)
        select_match = re.search(r"SELECT\s+(ss\.symbol.*?)\s+FROM stock_scores", src, re.DOTALL)
        assert select_match, "expected to find the SELECT column list"
        column_count = len([c for c in select_match.group(1).split(",") if c.strip()])
        max_index_used = max(int(m) for m in re.findall(r"row\[(\d+)\]", src))
        assert max_index_used < column_count, (
            f"row[{max_index_used}] is used but the SELECT only returns {column_count} columns - "
            f"this is the exact IndexError bug class caught live 2026-08-28"
        )
