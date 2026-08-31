#!/usr/bin/env python3
"""Regression test guarding against the frontend "Used in Score" weight badges
(webapp/frontend/src/components/StockScoreAccordion.jsx) drifting away from the actual
weight constants in loaders/load_stock_scores.py's _score_* functions.

Found live 2026-08-04: several tabs' displayed weight percentages were stale copies from
before the scoring code was tuned (e.g. Value's P/E badge said "20%" while the code used
0.45; Positioning's institutional-ownership badge said "35%" while the code used 0.55),
and momentum_1m - a real, 16%-weighted input, tied for the second-highest weight in the
whole momentum formula - had no display row in the Momentum tab at all despite the API
(lambda/api/routes/scores.py) already returning it. Users reading the scores page were
being told meaningfully wrong things about what actually drives each score.

Each weight is extracted directly from the live Python source (via inspect.getsource +
a regex anchored on the score-variable name each function multiplies by its weight
constant, e.g. `pe_score * 0.45`) rather than duplicated as a hardcoded literal, so this
test keeps tracking future weight tuning automatically - only the JSX side needs updating
when a weight changes, and this test is what catches it if someone forgets. Intentionally
scoped to the flat, single-level weighted-average components (value/risk's top-level
terms, momentum's dict-based 1m/3m/6m/12m weights and its rsi/macd terms) - Quality's base
score and its +/-10 point "enhancement" adjustment are a different shape (equal-weighted
average + bounded adjustment, not a flat weighted sum) and are deliberately out of scope.
Positioning was retired as a scored composite pillar entirely 2026-08-27 - see
TestPositioningScoreRemoved below.
"""

import inspect
import re

from loaders.load_stock_scores import BASE_PILLAR_WEIGHTS, GROWTH_SCORE_FIELDS, StockScoresLoader

with open("webapp/frontend/src/components/StockScoreAccordion.jsx", encoding="utf-8") as f:
    _JSX_SOURCE = f.read()


def _weight_for_score_var(source: str, score_var: str) -> float:
    """Find `<score_var> * 0.NN` (the weighted_sum accumulation line) in a function's source."""
    match = re.search(r"\b" + re.escape(score_var) + r"\s*\*\s*(0\.\d+)\b", source)
    assert match, f"expected to find `{score_var} * 0.NN` in source - has the code been restructured?"
    return float(match.group(1))


def _jsx_weight_for_key(key: str) -> str:
    # Quote-agnostic (['"]) and DOTALL: this only checks the weight *value*, not prettier's
    # layout choices. webapp/frontend/.prettierrc enforces singleQuote=false (double quotes)
    # and wraps an object across multiple lines once it exceeds printWidth=80 - a
    # single-quote, single-line-only regex broke the instant this file was actually run
    # through prettier, since format:check had been silently pointed at a nonexistent
    # directory (webapp/lambda, not webapp/frontend) and never really enforced style here
    # before 2026-08-20.
    match = re.search(r"key: [\"']" + re.escape(key) + r"[\"'].*?weight: [\"']([^\"']+)[\"']", _JSX_SOURCE, re.DOTALL)
    assert match, f"expected JSX schema to have a used:true weight badge for key '{key}'"
    return match.group(1)


def _assert_pct_matches(jsx_key: str, py_weight: float) -> None:
    expected_pct = round(py_weight * 100)
    jsx_weight = _jsx_weight_for_key(jsx_key)
    jsx_pct = int(re.match(r"(\d+)%", jsx_weight).group(1))
    assert jsx_pct == expected_pct, (
        f"{jsx_key}: JSX badge says {jsx_weight!r} but load_stock_scores.py weights it {py_weight} ({expected_pct}%)"
    )


class TestValueScoreWeightBadges:
    def test_weights_match_code(self):
        src = inspect.getsource(StockScoresLoader._score_value)
        # eve_score/evr_score (EV/EBITDA, EV/Revenue) removed 2026-08-25 - r=1.00/0.93
        # duplicates of ps_ratio/pe_ratio respectively, see _score_value's docstring RESOLVED
        # note. Confirmed 2026-08-28 (classification research) they belong to Value
        # conceptually but their non-PE/PS content is already covered by Quality's
        # debt_to_equity - stays unscored, not a re-add candidate.
        # size_score (market_cap) MOVED OUT 2026-08-26 - promoted to its own top-level "Size"
        # pillar (StockScoresLoader._score_size), no longer part of _score_value at all. See
        # TestSizeScoreWeightBadges below for its (trivial, single-input) coverage.
        # illiq_score (amihud_illiquidity) ADDED 2026-08-26, REMOVED same day (user directive)
        # - see _score_value's "AMIHUD ILLIQUIDITY" docstring note.
        # div_score (dividend_yield) briefly REPLACED by payout_score (net_payout_yield =
        # dividends + buybacks) 2026-08-26 on statistical grounds, then REVERTED back to
        # div_score/dividend_yield 2026-08-28 on explicit user directive - see
        # load_stock_scores.py's _score_value docstring for the full history.
        # FCF yield REMOVED 2026-08-28 (independently re-verified robustly wrong-signed, see
        # "FCF YIELD - RESOLVED 2026-08-28" docstring note). Forward P/E ADDED same pass
        # (fwd_pe_score, MSCI Value index core descriptor, user directive - see "FORWARD P/E -
        # ADDED 2026-08-28" docstring note). PB/PS weights bumped with FCF's freed weight.
        # PEG REMOVED FROM SCORING ENTIRELY 2026-08-28 (later same day, goal: "is this value
        # score right per industry best practice... lets figure out the right best for the
        # value and lets go") - a growth-ADJUSTED earnings multiple (PE / growth rate) is, by
        # design, a Value/Growth hybrid; no mainstream systematic Value methodology (MSCI
        # Enhanced Value/World Value, Russell, S&P Style, Barra, Fama-French/AQR) includes one,
        # and this repo's own 15-pair pillar-interaction sweep confirms Growth x Value isn't
        # era-robust either - see _score_value's "PEG - REMOVED FROM SCORING 2026-08-28"
        # docstring note. `_peg_to_score` was deleted (dead code, nothing calls it anymore).
        # Freed 3% went to Dividend Yield (8% -> 11%).
        # margin_of_safety (mos_score) REMOVED FROM SCORING 2026-08-28 (same day, earlier pass,
        # goal: "is margin of safety typically a metric used in the value factor score... or is
        # it typically used some other way") - industry-standard systematic Value factors
        # (MSCI/Russell/S&P/Fama-French/AQR) are built from accounting yield ratios, not DCF
        # intrinsic-value estimates; margin of safety is a Graham/Klarman per-stock deep-value
        # screening tool by convention, not a cross-sectional ranking input - see _score_value's
        # "MARGIN OF SAFETY - REMOVED FROM SCORING 2026-08-28" docstring note. Freed 11% went to
        # PB (+6, now 39%) and PS (+5, now 34%) above.
        # Both PEG and margin_of_safety, along with the already-unscored fcf_yield/ev_ebitda/
        # ev_revenue, were FULLY REMOVED FROM DISPLAY on this tab too (user directive: "if we
        # not scoring it we dont want to display it") - see TestUnscoredValueFieldsNotDisplayed
        # below. All five stay fully computed/stored/API-served; margin_of_safety and
        # intrinsic_value are the Deep Value Picks page's primary metrics instead.
        score_var_to_jsx_key = {
            "pe_score": "stock_pe",
            "pb_score": "stock_pb",
            "ps_score": "stock_ps",
            "fwd_pe_score": "stock_forward_pe",
            "div_score": "stock_dividend_yield",
        }
        for score_var, jsx_key in score_var_to_jsx_key.items():
            _assert_pct_matches(jsx_key, _weight_for_score_var(src, score_var))


class TestUnscoredValueFieldsNotDisplayed:
    def test_peg_and_margin_of_safety_not_scored(self):
        """Guards the 2026-08-28 removals - PEG and margin of safety (DCF discount to
        intrinsic value) should stay fully computed/stored but not weighted into value_score,
        matching industry practice: PEG is a Value/Growth hybrid no mainstream systematic
        methodology scores, and margin of safety is a deep-value screening tool, not a
        cross-sectional ranking input (see _score_value's docstring for the full evidence).
        Checks the backend side doesn't drift back."""
        src = inspect.getsource(StockScoresLoader._score_value)
        assert "mos_score" not in src, "margin of safety should no longer be a scored value_score component"
        assert "_peg_to_score" not in src, "PEG should no longer be a scored value_score component"
        assert not hasattr(StockScoresLoader, "_peg_to_score"), "_peg_to_score should be deleted, not just unused"

    def test_unscored_value_fields_have_no_display_row_at_all(self):
        """Guards the 2026-08-28 "if we not scoring it we dont want to display it" directive -
        unlike the prior convention (unscored fields stayed visible as informational rows),
        PEG/margin_of_safety/intrinsic_value/fcf_yield/ev_ebitda/ev_revenue should have NO row
        in VALUE_SCHEMA at all now, scored or not. Data itself is untouched - still computed/
        stored/API-served - this only guards the display layer."""
        schema_match = re.search(r"const VALUE_SCHEMA = \[([\s\S]*?)\n\];", _JSX_SOURCE)
        assert schema_match, "expected VALUE_SCHEMA to still exist"
        schema_src = schema_match.group(1)
        removed_keys = [
            "peg_ratio",
            "stock_margin_of_safety",
            "stock_intrinsic_value",
            "fcf_yield",
            "stock_ev_ebitda",
            "stock_ev_revenue",
        ]
        for key in removed_keys:
            assert f'key: "{key}"' not in schema_src and f"key: '{key}'" not in schema_src, (
                f"{key} should have no VALUE_SCHEMA row at all (not scored, so not displayed on this tab)"
            )


class TestGrowthScoreWeightBadges:
    # GROWTH_SCORE_FIELDS (loaders/load_stock_scores.py) key -> the JSX schema key that
    # displays it (StockScoreAccordion.jsx's GROWTH_SCHEMA). Kept explicit (not derived) so a
    # field renamed on one side without the other fails loudly here.
    _PY_FIELD_TO_JSX_KEY = {
        "revenue_growth_1y": "revenue_growth_1y_pct",
        "eps_growth_1y": "eps_growth_1y_pct",
        "revenue_growth_3y": "revenue_growth_3y_cagr",
        "eps_growth_3y": "eps_growth_3y_cagr",
        "revenue_growth_5y": "revenue_growth_5y_cagr",
        "eps_growth_5y": "eps_growth_5y_cagr",
        "net_income_growth_yoy": "net_income_growth_yoy",
        "sustainable_growth_rate": "sustainable_growth_rate",
        "quarterly_growth_momentum": "quarterly_growth_momentum",
        "earnings_growth_4q_avg": "earnings_growth_4q_avg",
        "fcf_growth_yoy": "fcf_growth_yoy",
    }

    def test_growth_score_fields_match_jsx_key_map(self):
        """GROWTH_SCORE_FIELDS and this test's own key map must agree - guards against either
        side adding/removing a candidate without updating the other."""
        assert set(GROWTH_SCORE_FIELDS) == set(self._PY_FIELD_TO_JSX_KEY)

    def test_growth_score_is_multi_input_equal_weighted_and_not_inverted(self):
        """RESTORED TO MULTI-INPUT 2026-08-28 (user directive, /goal session: "get the rest of
        the growth inputs back in there the ones that are in the react" + explicit pushback
        that revenue_growth_1y's inversion "shouldn't be inverted"). Supersedes the prior
        2026-08-27/08-28 single-input-shrinking history this test used to guard (11-input blend
        -> book_value_growth alone -> revenue_growth_1y alone) - see _score_growth's own
        docstring for that evidence-vs-override trail. _score_growth iterates the shared
        GROWTH_SCORE_FIELDS constant (checked directly, elsewhere in this class) rather than
        naming each field as its own literal, so this checks the iteration itself is present
        and that no per-field sign-flip (`-metrics[` / `-metrics.get(`) has crept back in -
        the user's directive was general, not scoped to revenue_growth_1y alone."""
        src = inspect.getsource(StockScoresLoader._score_growth)
        assert "GROWTH_SCORE_FIELDS" in src, "expected _score_growth to iterate the shared GROWTH_SCORE_FIELDS list"
        assert not re.search(r"-metrics\.get\(|-metrics\[", src), (
            "no growth candidate should be sign-flipped - user directive was growth should not be inverted"
        )
        # weighted_sum-style per-field `* 0.NN` literals shouldn't reappear - this is an
        # equal-weighted average (sum(component_scores) / len(component_scores)), not a
        # hand-tuned weighted blend.
        assert "weighted_sum" not in src

    def test_growth_schema_badges_are_equal_weight_not_sole_input(self):
        """Every GROWTH_SCORE_FIELDS candidate must have a real (non-"sole input") weight badge
        in GROWTH_SCHEMA, all equal (1 / len(GROWTH_SCORE_FIELDS), rounded) - "sole input" on a
        multi-input blend is exactly the misleading state this restore fixes."""
        schema_match = re.search(r"const GROWTH_SCHEMA = \[([\s\S]*?)\n\];", _JSX_SOURCE)
        assert schema_match, "expected GROWTH_SCHEMA to still exist"
        assert "sole input" not in schema_match.group(1)
        expected_weight = round(100 / len(GROWTH_SCORE_FIELDS)) / 100
        for jsx_key in self._PY_FIELD_TO_JSX_KEY.values():
            _assert_pct_matches(jsx_key, expected_weight)
        assert 'label: "Revenue Growth (1Y' in _JSX_SOURCE
        assert "inverted" not in schema_match.group(1).lower()


class TestSizeScoreRemoved:
    def test_size_is_not_a_scored_pillar(self):
        """Size (market cap) was briefly promoted to a 7th top-level pillar 2026-08-26, removed
        from scoring entirely the same day (a UX/product objection, not a dispute of the
        evidence), RE-PROMOTED 2026-08-27 on new era-robust half-split evidence, then RETIRED
        ENTIRELY 2026-08-28 (direct user directive "just get rid of size", triggered by its
        imputed-regime evidence not surviving a strict complete-case retest even after fixing
        the data-coverage bugs that retest required first) - see loaders/load_stock_scores.py's
        BASE_PILLAR_WEIGHTS for the full trail. Guards against the JSX schema drifting back to
        advertising market_cap as a scored (weight-badged) input - it's still displayed
        informationally via the Size (informational) card, just not scored."""
        assert not hasattr(StockScoresLoader, "_score_size")
        assert not hasattr(StockScoresLoader, "_size_curve_score")
        assert not hasattr(StockScoresLoader, "update_size_percentiles")
        assert "size" not in BASE_PILLAR_WEIGHTS
        with open("webapp/frontend/src/components/StockScoreAccordion.jsx", encoding="utf-8") as f:
            jsx_source = f.read()
        assert 'scoreKey: "size_score"' not in jsx_source
        # market_cap (informational display) is expected to remain - only the weight-badged
        # SIZE_SCHEMA entry should have no `weight:` key left.
        schema_match = re.search(r"const SIZE_SCHEMA = \[([\s\S]*?)\n\];", jsx_source)
        assert schema_match, "expected SIZE_SCHEMA to still exist (informational display)"
        assert "weight:" not in schema_match.group(1)


class TestPositioningScoreRemoved:
    def test_positioning_is_not_a_scored_pillar(self):
        """Positioning was retired as a top-level composite pillar 2026-08-27 (evidence-driven
        - A/D rating null across every methodology tried including a full 2000-2026 re-test;
        institutional ownership/short interest untestable for lack of real historical depth;
        the pillar-level composite proxy itself never significant and sign-flips across
        half-splits). See loaders/load_stock_scores.py's BASE_PILLAR_WEIGHTS for the full
        trail. Guards against the JSX schema drifting back to advertising A/D rating/
        institutional ownership/short interest as scored (weight-badged) inputs - they're
        still displayed informationally via positioning_inputs, just not scored."""
        assert not hasattr(StockScoresLoader, "_score_positioning")
        assert "positioning" not in BASE_PILLAR_WEIGHTS
        with open("webapp/frontend/src/components/StockScoreAccordion.jsx", encoding="utf-8") as f:
            jsx_source = f.read()
        assert 'scoreKey: "positioning_score"' not in jsx_source
        # positioning_inputs (informational display) is expected to remain - only the
        # weight-badged POSITIONING_SCHEMA entries (ad_rating/institutional_ownership_pct/
        # short_interest_pct/short_interest_pct_change) should have no `weight:` key left.
        schema_match = re.search(r"const POSITIONING_SCHEMA = \[([\s\S]*?)\n\];", jsx_source)
        assert schema_match, "expected POSITIONING_SCHEMA to still exist (informational display)"
        assert "weight:" not in schema_match.group(1)


class TestRiskScoreWeightBadges:
    def test_volatility_beta_and_max_drawdown_weights_match_code(self):
        """REWORKED 2026-08-30 (later same day, user directive: full delegation to figure out
        the best combination - see _score_risk's own docstring for the per-input reasoning).
        Volatility 60D 45% + Volatility 252D 20% + Beta 20% + Max Drawdown 1Y 15%.
        Volatility 30D dropped (most redundant of the three windows). Debt-to-Assets stays
        out - see test_debt_to_assets_not_scored below."""
        src = inspect.getsource(StockScoresLoader._score_risk)
        score_var_to_jsx_key = {
            "v60_score": "volatility_60d",
            "v252_score": "volatility_12m",  # API key "volatility_12m" actually carries volatility_252d
            "beta_score": "beta",
            "dd_score": "max_drawdown_1y",
        }
        for score_var, jsx_key in score_var_to_jsx_key.items():
            _assert_pct_matches(jsx_key, _weight_for_score_var(src, score_var))

    def test_downside_volatility_and_volatility_30d_not_scored(self):
        """downside_volatility and volatility_30d are not part of the current 4-input
        formula - should stay fully computed/stored but no longer weighted into risk_score."""
        src = inspect.getsource(StockScoresLoader._score_risk)
        assert "dvol60_score" not in src, "downside_volatility_60d should no longer be a scored risk_score component"
        assert "v30_score" not in src, "volatility_30d should no longer be a scored risk_score component"

    def test_debt_to_assets_not_scored(self):
        """Guards the 2026-08-30 "remove the debt to assets from the safety score" directive
        (given the same day it was briefly restored) - debt_to_assets should stay fully
        available via Quality's own quality_inputs/quality_score but no longer be merged into
        or weighted into risk_score, and RISK_SCHEMA should have no display row for it."""
        src = inspect.getsource(StockScoresLoader._score_risk)
        assert "dta_score" not in src, "debt_to_assets should no longer be a scored risk_score component"
        compute_src = inspect.getsource(StockScoresLoader._compute_stock_score)
        assert 'risk_metrics["debt_to_assets"]' not in compute_src, (
            "debt_to_assets should no longer be merged into risk_metrics before scoring"
        )
        schema_match = re.search(r"const RISK_SCHEMA = \[([\s\S]*?)\n\];", _JSX_SOURCE)
        assert schema_match, "expected RISK_SCHEMA to still exist"
        assert 'key: "debt_to_assets"' not in schema_match.group(1), (
            "debt_to_assets should have no RISK_SCHEMA row (not scored, so not displayed on this tab)"
        )


class TestMomentumScoreWeightBadges:
    def test_price_return_weights_match_code(self):
        src = inspect.getsource(StockScoresLoader._score_momentum)
        dict_match = re.search(r"weights = \{([\s\S]*?)\}", src)
        assert dict_match, "expected a `weights = {...}` dict literal in _score_momentum"
        dict_weights = {k: float(v) for k, v in re.findall(r'"(\w+)":\s*(0\.\d+)', dict_match.group(1))}

        # momentum_1m removed 2026-08-25 (goal: full scoring-architecture audit) - dropped
        # per the standard academic 12-1 momentum construction (Jegadeesh 1990 short-term
        # reversal); see _score_momentum's docstring for the empirical confirmation.
        field_to_jsx_key = {
            "momentum_3m": "momentum_3m",
        }
        for field, jsx_key in field_to_jsx_key.items():
            _assert_pct_matches(jsx_key, dict_weights[field])

        # momentum_6m/raw momentum_12m REPLACED same day by a derived 12-1 skip-month
        # construction (mom_12_1_score, not a `weights` dict entry - a standalone
        # `* 0.NN` line like eve_score/evr_score were) - see _score_momentum's docstring
        # RESOLVED note.
        _assert_pct_matches("momentum_12_1", _weight_for_score_var(src, "mom_12_1_score"))

    def test_rsi_and_macd_weights_match_code(self):
        """CONSOLIDATED 2026-08-28 (goal: momentum/risk factor-interaction review): RSI(14)
        and MACD-sign used to be two independently `rsi_score * 0.21` / `macd_score * 0.16`
        terms - but they're correlated (r=0.70 in the 2026-08-25 FM panel, r=0.58 live-
        reverified 2026-08-28) and their multivariate coefficients flip sign against each
        other, the same redundancy symptom already fixed for SMA-50/200 (averaged into one
        slot) and Risk's volatility windows (6 collapsed to 2). Now averaged into one
        `tech_trend_scores` slot at a combined 0.37 weight (21%+16%, unchanged) - see
        _score_momentum's CONSOLIDATED 2026-08-28 docstring note. `_weight_for_score_var`'s
        `<var> * 0.NN` pattern has nothing to match against an averaged-list slot (same
        reason SMA's weight was never checked this way either), so this checks the combined
        weight constant directly instead, and that both JSX rows advertise it."""
        src = inspect.getsource(StockScoresLoader._score_momentum)
        combined_match = re.search(r"tech_trend_scores\)\s*/\s*len\(tech_trend_scores\)\)\s*\*\s*(0\.\d+)", src)
        assert combined_match, "expected `(sum(tech_trend_scores) / len(tech_trend_scores)) * 0.NN` in source"
        combined_weight = float(combined_match.group(1))
        _assert_pct_matches("rsi", combined_weight)
        _assert_pct_matches("macd", combined_weight)


class TestCompositeWeightBadges:
    """StockScoreAccordion.jsx's PILLAR_COMPOSITE_WEIGHTS drives the "% of composite" badge
    added 2026-08-31 (goal: composite-score architecture review) next to every scored input's
    existing within-factor weight badge - each input's effective share of the full
    composite_score, not just its share of its own factor. Guards the same drift class as
    every other test in this file: a hardcoded frontend copy of BASE_PILLAR_WEIGHTS going
    stale after the next pillar reweight."""

    def test_pillar_composite_weights_match_backend(self):
        match = re.search(r"const PILLAR_COMPOSITE_WEIGHTS = \{([\s\S]*?)\n\};", _JSX_SOURCE)
        assert match, "expected a PILLAR_COMPOSITE_WEIGHTS object literal in StockScoreAccordion.jsx"
        jsx_weights = {k: float(v) for k, v in re.findall(r"(\w+):\s*(0\.\d+)", match.group(1))}
        assert jsx_weights == BASE_PILLAR_WEIGHTS, (
            f"StockScoreAccordion.jsx's PILLAR_COMPOSITE_WEIGHTS {jsx_weights} doesn't match "
            f"loaders/load_stock_scores.py's BASE_PILLAR_WEIGHTS {BASE_PILLAR_WEIGHTS}"
        )

    def test_pillar_composite_weights_is_exported(self):
        assert re.search(r"export \{[^}]*PILLAR_COMPOSITE_WEIGHTS[^}]*\};", _JSX_SOURCE), (
            "PILLAR_COMPOSITE_WEIGHTS should be exported so other files/tests can import "
            "the same single source of truth instead of hand-copying it"
        )

    def test_positioning_and_size_have_no_composite_weight(self):
        """Positioning and Size are retired composite pillars (informational-only tabs) -
        their InputsCard invocations must not pass a pillarWeight prop, or they'd wrongly
        imply these tabs still feed composite_score."""
        positioning_call = re.search(r'<InputsCard\s+title="Positioning \(informational\)"[\s\S]*?/>', _JSX_SOURCE)
        size_call = re.search(r'<InputsCard\s+title="Size \(informational\)"[\s\S]*?/>', _JSX_SOURCE)
        assert positioning_call and "pillarWeight" not in positioning_call.group(0)
        assert size_call and "pillarWeight" not in size_call.group(0)

    def test_all_five_composite_pillars_wire_a_pillar_weight(self):
        for key in ("quality", "growth", "value", "risk", "momentum"):
            assert re.search(r"pillarWeight=\{PILLAR_COMPOSITE_WEIGHTS\." + key + r"\}", _JSX_SOURCE), (
                f"expected InputsCard for '{key}' to wire pillarWeight={{PILLAR_COMPOSITE_WEIGHTS.{key}}}"
            )
