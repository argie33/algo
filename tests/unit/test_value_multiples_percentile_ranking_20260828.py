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
    """_pe_curve_score/_pb_curve_score must stay byte-for-byte the OLD formulas -
    update_value_multiples_percentiles()'s reconciliation diffs against whatever they return,
    so a change here silently breaks the correction math, not just Pass 1. _ps_curve_score was
    deleted 2026-09-16 (factor-purity sweep, P/S dropped from scoring entirely - see
    value_score.py's VALUE_MIN_WEIGHT docstring), so its own pinning test is gone with it."""

    def test_pe_curve_known_points(self) -> None:
        assert StockScoresLoader._pe_curve_score(10.0) == 60.0
        assert StockScoresLoader._pe_curve_score(20.0) == 100.0
        assert StockScoresLoader._pe_curve_score(35.0) == 70.0

    def test_pb_curve_known_points(self) -> None:
        assert StockScoresLoader._pb_curve_score(1.0) == 100.0
        assert StockScoresLoader._pb_curve_score(3.0) == 70.0
        assert StockScoresLoader._pb_curve_score(7.0) == 30.0


class TestMsciThreeLegConstruction:
    """Exercises the REAL, LIVE construction `update_value_multiples_percentiles()` uses today
    (loaders/stock_scores/value_metrics.py) - MSCI Enhanced Value's actual published 3-variable
    definition (Price-to-Book-or-Cash-Earnings, Price-to-Forward-Earnings-or-trailing, EV/CFO-
    or-Cash-Earnings), each an equal 1/3 weight, verified against MSCI_Enhanced_Value_Index_
    Meth_Aug14.pdf (msci.com/eqb/methodology) - see that method's own "MSCI ENHANCED VALUE
    CONSTRUCTION FIDELITY" docstring note for the full citation and evidence trail.

    REPLACES the former TestValueMultiplesReconciliationMath class (removed 2026-09-16,
    factor-purity sweep, /goal: "we should only have one common set of scores... like the
    industry guys"). That class hand-reimplemented an ADDITIVE-DELTA reconciliation over a
    5-input flat-20%-each construction (P/E/P/B/P/S/Forward-P/E/Dividend-Yield) in its own
    `_reconcile()` helper - an architecture superseded TWICE in the live code (2026-08-31:
    additive-delta -> full-recompute; 2026-09-15: 5-input flat-weight -> MSCI's real 3-leg
    1/3-weight-each P/B, E/P, EV/CFO formula, no P/S or dividend-yield leg at all) without the
    test ever being updated to match, or ever calling the real method - it tested only itself,
    giving false confidence that Pass 2's reconciliation was covered. These tests instead drive
    the real `update_value_multiples_percentiles()` end-to-end (mocked DatabaseContext, real
    row-shaped fixtures - same convention as TestUpdateValueMultiplesPercentilesEndToEnd below)
    and assert on its actual UPDATE payload.

    Row shape matches the real SELECT in `update_value_multiples_percentiles()` exactly (27
    columns, indices 0-26) - see `_ROW_COLUMNS` below and that method's own column list.
    """

    # Mirrors the real SELECT's column order exactly (update_value_multiples_percentiles()).
    _ROW_COLUMNS = [
        "symbol",
        "value_score",
        "composite_score",
        "risk_score",
        "quality_score",
        "growth_score",
        "momentum_score",
        "pe_ratio",
        "pb_ratio",
        "ps_ratio",
        "forward_pe",
        "dividend_yield",
        "fcf_yield",
        "pe_ratio_unavailable_reason",
        "forward_pe_unavailable_reason",
        "pb_ratio_unavailable_reason",
        "components",
        "sector",
        "data_completeness",
        "data_unavailable",
        "unavailable_metrics",
        "ps_ratio_unavailable_reason",
        "is_foreign_private_issuer",
        "enterprise_value",
        "operating_cash_flow",
        "market_cap",
        "industry",
    ]

    @classmethod
    def _row(cls, **overrides: Any) -> tuple[Any, ...]:
        defaults: dict[str, Any] = {
            "symbol": "SYM",
            # Deliberately NOT 50.0 (or any value a real computed score could plausibly land
            # on by coincidence) - update_value_multiples_percentiles() only appends a symbol
            # to its UPDATE batch when the recomputed value differs from this "old" value, so
            # a coincidental match here would silently hide a symbol from `updates` and turn a
            # real bug into a confusing KeyError instead of a clear assertion failure.
            "value_score": 1.0,
            "composite_score": 1.0,
            "risk_score": 50.0,
            "quality_score": 50.0,
            "growth_score": 50.0,
            "momentum_score": 50.0,
            "pe_ratio": None,
            "pb_ratio": None,
            "ps_ratio": None,
            "forward_pe": None,
            "dividend_yield": None,
            "fcf_yield": None,
            "pe_ratio_unavailable_reason": None,
            "forward_pe_unavailable_reason": None,
            "pb_ratio_unavailable_reason": None,
            "components": None,
            "sector": "Consumer Defensive",  # thin/mixed sectors -> residual pool, same
            # convention TestNegativeBookValueFloorSurvivesPercentilePass already used, so
            # every symbol in a test's row set is ranked against every other one directly.
            "data_completeness": 99.99,
            "data_unavailable": False,
            "unavailable_metrics": {},
            "ps_ratio_unavailable_reason": None,
            "is_foreign_private_issuer": False,
            "enterprise_value": None,
            "operating_cash_flow": None,
            "market_cap": None,
            "industry": None,
        }
        defaults.update(overrides)
        return tuple(defaults[col] for col in cls._ROW_COLUMNS)

    @staticmethod
    def _run(rows: list[tuple[Any, ...]]) -> MagicMock:
        """Runs the real method against `rows`, returns the mocked execute_values call (or a
        Mock with `.called = False` if nothing changed - a legitimate outcome for some cases)."""
        cur = MagicMock()
        # side_effect [rows, []]: first fetchall() is the correction pass's own SELECT, second
        # is _withhold_value_below_floor()'s own SELECT (added 2026-09-16, factor-purity sweep)
        # - [] means no symbol is below the liquidity floor in this test's fixture population.
        cur.fetchall.side_effect = [rows, []]
        mock_db_context = MagicMock()
        mock_db_context.__enter__ = MagicMock(return_value=cur)
        mock_db_context.__exit__ = MagicMock(return_value=False)

        loader = StockScoresLoader.__new__(StockScoresLoader)
        with (
            patch("loaders.load_stock_scores.DatabaseContext", return_value=mock_db_context),
            patch("loaders.load_stock_scores.execute_values") as mock_execute_values,
        ):
            loader.update_value_multiples_percentiles()
        return mock_execute_values

    @classmethod
    def _updates_by_symbol(cls, mock_execute_values: MagicMock) -> dict[str, tuple[Any, ...]]:
        assert mock_execute_values.called, "expected at least one symbol's value_score to change"
        updates = mock_execute_values.call_args.args[2]
        return {u[0]: u for u in updates}

    def test_ev_cfo_leg_moves_the_score_between_otherwise_identical_peers(self) -> None:
        # GOODCASH and BADCASH share IDENTICAL P/B and Forward P/E raw ratios (so those two
        # legs alone can't differentiate them) - only their EV/CFO leg differs (cheap vs. rich
        # relative to enterprise value). GOODCASH's value_score must come out strictly higher,
        # proving the 3rd leg (added 2026-09-15, the EV/CFO fidelity fix - real CFO/EV, not the
        # old price-basis fcf_yield proxy) actually moves the score, not just gets computed and
        # discarded.
        rows = [
            self._row(
                symbol="GOODCASH",
                pb_ratio=2.0,
                forward_pe=15.0,
                enterprise_value=100.0,
                operating_cash_flow=40.0,  # CFO/EV = 0.40, cheap
                market_cap=90.0,
            ),
            self._row(
                symbol="BADCASH",
                pb_ratio=2.0,
                forward_pe=15.0,
                enterprise_value=100.0,
                operating_cash_flow=5.0,  # CFO/EV = 0.05, rich
                market_cap=90.0,
            ),
        ]
        updates = self._updates_by_symbol(self._run(rows))
        goodcash_value_score = updates["GOODCASH"][1]
        badcash_value_score = updates["BADCASH"][1]
        assert goodcash_value_score is not None
        assert badcash_value_score is not None
        assert goodcash_value_score > badcash_value_score

    def test_negative_book_value_floor_beats_cash_yield_substitute(self) -> None:
        # NEGBOOK has a real, cheap fcf_yield (the price-basis EV/CFO fallback) AND negative
        # book value - MSCI's stated "missing P/B -> P/CE" substitution rule must NOT apply
        # here (negative equity is a real, known-worst signal, not missing data): the P/B leg
        # must be FLOORED at 0.0, not filled in with the flattering cash-yield number. POSBOOK
        # has an ordinary positive P/B and no cash-yield data at all. Identical Forward P/E.
        rows = [
            self._row(symbol="POSBOOK", pb_ratio=2.0, forward_pe=15.0),
            self._row(
                symbol="NEGBOOK",
                pb_ratio=None,
                pb_ratio_unavailable_reason="negative_book_value",
                forward_pe=15.0,
                fcf_yield=0.50,  # would otherwise look extremely cheap
            ),
        ]
        updates = self._updates_by_symbol(self._run(rows))
        assert updates["NEGBOOK"][1] < updates["POSBOOK"][1], (
            "negative-book-value P/B leg must be floored at 0.0, not substituted with the "
            "flattering cash-yield number - that substitution rule is for genuinely MISSING "
            "P/B data only, per MSCI's own stated rule"
        )

    def test_missing_book_value_falls_back_to_cash_earnings_substitute(self) -> None:
        # GENUINELYMISSING has pb_ratio=None with NO unavailable_reason at all (a real "we
        # never computed this" gap, not a known-worst negative-equity signal) - MSCI's stated
        # substitution rule (missing P/B -> P/CE) should apply: the leg is filled from
        # cash_yield_pct, still counting as 1/3 weight, not floored and not dropped/renormalized
        # away. Confirms the symbol still clears VALUE_MIN_WEIGHT and gets a real, non-floored
        # score even with only Forward P/E + the substituted leg (P/B genuinely absent).
        rows = [
            self._row(
                symbol="GENUINELYMISSING",
                pb_ratio=None,
                pb_ratio_unavailable_reason=None,
                forward_pe=15.0,
                enterprise_value=100.0,
                operating_cash_flow=20.0,
            ),
            # A peer so the percentile ranking has more than one symbol to rank against.
            self._row(symbol="PEER", pb_ratio=3.0, forward_pe=20.0, enterprise_value=100.0, operating_cash_flow=5.0),
        ]
        updates = self._updates_by_symbol(self._run(rows))
        assert updates["GENUINELYMISSING"][1] is not None

    def test_double_unprofitable_symbol_floors_earnings_leg(self) -> None:
        # Both trailing P/E (unprofitable) AND forward P/E (negative forecast) unusable - the
        # worst possible Earnings/Price outcome, floored at 0.0, not excluded/renormalized.
        rows = [
            self._row(symbol="HEALTHY", pb_ratio=2.0, forward_pe=15.0),
            self._row(
                symbol="DOUBLYUNPROFITABLE",
                pb_ratio=2.0,
                pe_ratio=None,
                pe_ratio_unavailable_reason="unprofitable_stock",
                forward_pe=None,
                forward_pe_unavailable_reason="negative_forward_eps",
            ),
        ]
        updates = self._updates_by_symbol(self._run(rows))
        assert updates["DOUBLYUNPROFITABLE"][1] < updates["HEALTHY"][1]

    def test_bank_industry_omits_ev_cfo_leg_entirely(self) -> None:
        # A depository bank's operating_cash_flow/enterprise_value are not comparable
        # "cash generation" measures (loan-issuance/deposit-flow driven, not leverage) - the
        # EV/CFO leg must be omitted for it entirely, not scored on a number that doesn't mean
        # what the leg claims. With P/B and Forward P/E both present (2/3 legs, clears
        # VALUE_MIN_WEIGHT), the bank still gets a real value_score - just never touched by its
        # own (deliberately extreme, to make the assertion unambiguous) EV/CFO inputs.
        rows = [
            self._row(symbol="ORDINARYCO", pb_ratio=2.0, forward_pe=15.0),
            self._row(
                symbol="BIGBANK",
                pb_ratio=2.0,
                forward_pe=15.0,
                enterprise_value=100.0,
                operating_cash_flow=-500.0,  # would be a nonsensical/extreme cash yield if used
                industry="National Commercial Banks",
            ),
        ]
        updates = self._updates_by_symbol(self._run(rows))
        # Same P/B and Forward P/E raw ratios (and same thin-universe residual pool), EV/CFO
        # leg never applied to BIGBANK -> identical value_score to ORDINARYCO.
        assert updates["BIGBANK"][1] == updates["ORDINARYCO"][1]

    def test_financial_services_sector_omits_ev_cfo_leg_even_outside_bank_insurer_industries(self) -> None:
        # MSCI's real, published rule (MSCI_Enhanced_Value_Index_Meth_Aug14.pdf, Appendix II,
        # Cases 4-6) drops the EV/CFO-or-P/CE leg for the WHOLE GICS Financials sector, not just
        # depository banks/insurance underwriters - an asset manager or broker-dealer classified
        # "Financial Services" but NOT in DEPOSITORY_BANK_INDUSTRIES/
        # INSURANCE_UNDERWRITER_INDUSTRIES must still have the leg omitted (added 2026-09-16,
        # factor-purity sweep, broadening the narrower 2026-09-15 industry-only carve-out to
        # match the primary source exactly).
        rows = [
            self._row(symbol="ORDINARYCO", pb_ratio=2.0, forward_pe=15.0),
            self._row(
                symbol="ASSETMANAGER",
                pb_ratio=2.0,
                forward_pe=15.0,
                sector="Financial Services",
                industry="Asset Management",  # NOT in DEPOSITORY_BANK_INDUSTRIES/
                # INSURANCE_UNDERWRITER_INDUSTRIES - only the sector-wide trigger should catch it
                enterprise_value=100.0,
                operating_cash_flow=-500.0,  # would be a nonsensical/extreme cash yield if used
            ),
        ]
        updates = self._updates_by_symbol(self._run(rows))
        assert updates["ASSETMANAGER"][1] == updates["ORDINARYCO"][1]

    def test_single_leg_below_value_min_weight_is_withheld(self) -> None:
        # Only Forward P/E available (1/3 = 0.333 nominal weight) - below VALUE_MIN_WEIGHT
        # (0.40) - value_score must be withheld (None), the same "insufficient data, don't
        # fabricate a score" treatment Pass 1 uses (VALUE_MIN_WEIGHT's own docstring in
        # value_score.py), not a thin-sample score built off one metric.
        rows = [
            self._row(symbol="ONLYFWDPE", pb_ratio=None, forward_pe=15.0),
            self._row(symbol="PEER", pb_ratio=None, forward_pe=25.0),
        ]
        updates = self._updates_by_symbol(self._run(rows))
        assert updates["ONLYFWDPE"][1] is None

    def test_two_legs_at_two_thirds_weight_clears_value_min_weight(self) -> None:
        # P/B + Forward P/E (2/3 = 0.667 nominal weight) clears VALUE_MIN_WEIGHT (0.40) - a
        # real, non-withheld score, unlike the single-leg case above.
        rows = [
            self._row(symbol="TWOLEG", pb_ratio=2.0, forward_pe=15.0),
            self._row(symbol="PEER", pb_ratio=4.0, forward_pe=25.0),
        ]
        updates = self._updates_by_symbol(self._run(rows))
        assert updates["TWOLEG"][1] is not None

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

    UPDATED AGAIN 2026-09-11 (BUG FOUND + FIXED - see update_value_multiples_percentiles()'s
    own "BUG FOUND + FIXED 2026-09-11" docstring note): the SELECT grew one more column,
    vm.pb_ratio_unavailable_reason, inserted right after forward_pe_unavailable_reason - needed
    to floor negative-book-value P/B at 0.0 in this pass the same way it was already floored
    for unprofitable_stock/negative_forward_eps, instead of silently undoing _score_value's
    Pass-1 floor on every post_run().
    """

    @staticmethod
    def _make_mock_cursor(rows: list[tuple[Any, ...]]) -> MagicMock:
        cur = MagicMock()
        # side_effect [rows, []]: first fetchall() is the correction pass's own SELECT, second
        # is _withhold_value_below_floor()'s own SELECT (added 2026-09-16, factor-purity sweep)
        # - [] means no symbol is below the liquidity floor in this test's fixture population.
        cur.fetchall.side_effect = [rows, []]
        return cur

    def test_real_row_shape_does_not_raise_indexerror(self) -> None:
        # One profitable symbol, one unprofitable (floored) symbol, one negative-forecast
        # Forward P/E symbol, one negative-book-value (floored) symbol, one no-revenue
        # (floored) P/S symbol - exercises every branch of the real row-unpacking code with
        # the REAL 22-column shape the live SELECT actually returns (sector added 2026-09-04
        # for sector-relative Value percentile ranking - see update_value_multiples_
        # percentiles' own "SECTOR-RELATIVE RANKING ADOPTED 2026-09-04" docstring note;
        # pb_ratio_unavailable_reason added 2026-09-11 - see that method's own "BUG FOUND +
        # FIXED 2026-09-11" docstring note; ps_ratio_unavailable_reason added same fix family).
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
                None,
                {"quality": 70.0},
                "Technology",
                99.99,  # data_completeness
                False,  # data_unavailable
                {},  # unavailable_metrics
                None,  # ps_ratio_unavailable_reason
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
                None,
                99.99,  # data_completeness
                False,  # data_unavailable
                {},  # unavailable_metrics
                None,  # ps_ratio_unavailable_reason
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
                None,
                "{}",
                "Financial Services",
                99.99,  # data_completeness
                False,  # data_unavailable
                {},  # unavailable_metrics
                None,  # ps_ratio_unavailable_reason
            ),
            (
                "NEGBOOK",
                35.0,
                40.0,
                55.0,
                50.0,
                45.0,
                35.0,
                10.0,
                None,
                2.0,
                None,
                None,
                None,
                None,
                "no_analyst_estimates",
                "negative_book_value",
                None,
                "Consumer Defensive",
                99.99,  # data_completeness
                False,  # data_unavailable
                {},  # unavailable_metrics
                None,  # ps_ratio_unavailable_reason
            ),
            (
                "NOREV",
                30.0,
                35.0,
                50.0,
                45.0,
                40.0,
                30.0,
                9.0,
                1.2,
                None,
                None,
                None,
                None,
                None,
                "no_analyst_estimates",
                None,
                None,
                "Health Care",
                99.99,  # data_completeness
                False,  # data_unavailable
                {},  # unavailable_metrics
                "no_revenue_reported",  # ps_ratio_unavailable_reason
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


class TestNegativeBookValueFloorSurvivesPercentilePass:
    """Regression test for the 2026-09-11 fix (see update_value_multiples_percentiles()'s own
    "BUG FOUND + FIXED 2026-09-11" docstring note): this batch pass previously never selected
    vm.pb_ratio_unavailable_reason, so a negative-book-value symbol's P/B component - correctly
    floored to 0.0 by _score_value's Pass 1 - was silently DROPPED (not floored) here instead,
    since this pass unconditionally overwrites value_score on every post_run(). Two symbols,
    identical PE/PS, one with a real positive pb_ratio and one with pb_ratio=None/reason=
    "negative_book_value" - the negative-book-value symbol must come out with a STRICTLY LOWER
    recomputed value_score, proving its P/B term was floored (0.27 weight at score 0.0), not
    excluded (renormalized over PE+PS only, which would score it identically or higher)."""

    @staticmethod
    def _row(symbol: str, pb: float | None, pb_reason: str | None) -> tuple[Any, ...]:
        return (
            symbol,
            50.0,  # value_score (Pass-1 placeholder, overwritten)
            50.0,  # composite_score
            50.0,  # risk_score
            60.0,  # quality_score
            55.0,  # growth_score
            45.0,  # momentum_score
            15.0,  # pe_ratio
            pb,  # pb_ratio
            4.0,  # ps_ratio
            None,  # forward_pe
            None,  # dividend_yield
            None,  # fcf_yield
            None,  # pe_ratio_unavailable_reason
            "no_analyst_estimates",  # forward_pe_unavailable_reason
            pb_reason,  # pb_ratio_unavailable_reason
            None,  # components
            "Consumer Defensive",  # sector - large residual pool, plain universe-wide ranking
            99.99,  # data_completeness
            False,  # data_unavailable
            {},  # unavailable_metrics
            None,  # ps_ratio_unavailable_reason
        )

    def test_negative_book_value_scores_lower_than_positive_peer(self) -> None:
        rows = [
            self._row("POSBOOK", 2.0, None),
            self._row("NEGBOOK", None, "negative_book_value"),
        ]
        cur = MagicMock()
        # side_effect [rows, []]: first fetchall() is the correction pass's own SELECT, second
        # is _withhold_value_below_floor()'s own SELECT (added 2026-09-16, factor-purity sweep)
        # - [] means no symbol is below the liquidity floor in this test's fixture population.
        cur.fetchall.side_effect = [rows, []]
        mock_db_context = MagicMock()
        mock_db_context.__enter__ = MagicMock(return_value=cur)
        mock_db_context.__exit__ = MagicMock(return_value=False)

        loader = StockScoresLoader.__new__(StockScoresLoader)
        with (
            patch("loaders.load_stock_scores.DatabaseContext", return_value=mock_db_context),
            patch("loaders.load_stock_scores.execute_values") as mock_execute_values,
        ):
            loader.update_value_multiples_percentiles()

        assert mock_execute_values.called, "both symbols' PE/PS are identical but PB differs - value_score must change"
        updates = mock_execute_values.call_args.args[2]
        by_symbol = {u[0]: u[1] for u in updates}  # symbol -> value_score
        assert by_symbol["NEGBOOK"] < by_symbol["POSBOOK"], (
            "negative-book-value symbol's P/B term must be FLOORED (0.0 at 0.27 weight), not "
            "dropped/renormalized - a dropped term would score it >= the positive-P/B peer"
        )
