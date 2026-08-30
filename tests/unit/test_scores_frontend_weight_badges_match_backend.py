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
        """RESTORED 2026-08-30 (explicit user directive, after a full history dig found the
        08-28 redesign - percentile-ranking, Forward P/E addition, PEG/FCF-Yield/Margin-of-
        Safety removal - had little to no quoted user sign-off). Reverted to the 08-26/08-28
        7-input fixed-curve formula: P/E 12% + P/B 30% + P/S 27% + PEG 7% + FCF Yield 9% +
        Dividend Yield 8% + Margin of Safety 7%. Forward P/E is no longer scored.
        update_value_multiples_percentiles() (cross-sectional percentile-rank batch pass) is
        disabled, not deleted - see its call site's own comment in _compute_composite_score
        for why running it now would corrupt scores against these reverted weights."""
        src = inspect.getsource(StockScoresLoader._score_value)
        score_var_to_jsx_key = {
            "pe_score": "stock_pe",
            "pb_score": "stock_pb",
            "ps_score": "stock_ps",
            "div_score": "stock_dividend_yield",
            "fcf_score": "fcf_yield",
            "mos_score": "stock_margin_of_safety",
        }
        for score_var, jsx_key in score_var_to_jsx_key.items():
            _assert_pct_matches(jsx_key, _weight_for_score_var(src, score_var))
        # PEG uses `self._peg_to_score(...) * 0.07` inline, not a named `peg_score` variable -
        # different call shape than the other score vars above.
        peg_match = re.search(r"_peg_to_score\([^)]*\)\s*\*\s*(0\.\d+)", src)
        assert peg_match, "expected `self._peg_to_score(...) * 0.NN` in source"
        _assert_pct_matches("peg_ratio", float(peg_match.group(1)))

    def test_forward_pe_not_scored(self):
        """Forward P/E is not part of the reverted 08-26/08-28 formula - guards against it
        drifting back into value_score without an explicit decision."""
        src = inspect.getsource(StockScoresLoader._score_value)
        assert "fwd_pe_score" not in src, "forward_pe should not be a scored value_score component"

    def test_percentile_ranking_disabled(self):
        """update_value_multiples_percentiles() (called from post_run()) must not be active
        while _score_value uses the reverted fixed-curve weights - its delta correction is
        hardcoded to the pre-revert weights and would silently corrupt value_score/
        composite_score if it ran. The method itself stays defined (not deleted)."""
        assert hasattr(StockScoresLoader, "update_value_multiples_percentiles")
        src = inspect.getsource(StockScoresLoader.post_run)
        assert not re.search(r"^\s*self\.update_value_multiples_percentiles\(\)", src, re.MULTILINE), (
            "update_value_multiples_percentiles() call should be disabled (commented out), "
            "not active, while _score_value uses the reverted fixed-curve weights"
        )


class TestUnscoredValueFieldsDisplayed:
    def test_forward_pe_and_ev_multiples_have_no_display_row(self):
        """Forward P/E, EV/EBITDA, and EV/Revenue are not part of the reverted formula - should
        have no row in VALUE_SCHEMA (unscored fields aren't displayed on this tab, per the
        08-28 "if we not scoring it we dont want to display it" convention, which still
        applies)."""
        schema_match = re.search(r"const VALUE_SCHEMA = \[([\s\S]*?)\n\];", _JSX_SOURCE)
        assert schema_match, "expected VALUE_SCHEMA to still exist"
        schema_src = schema_match.group(1)
        removed_keys = ["stock_forward_pe", "stock_ev_ebitda", "stock_ev_revenue"]
        for key in removed_keys:
            assert f'key: "{key}"' not in schema_src and f"key: '{key}'" not in schema_src, (
                f"{key} should have no VALUE_SCHEMA row at all (not scored, so not displayed on this tab)"
            )

    def test_peg_fcf_yield_margin_of_safety_are_scored_and_displayed(self):
        """RESTORED 2026-08-30 - PEG, FCF Yield, and Margin of Safety are scored value_score
        components again and must have a real (non-informational) weight badge in
        VALUE_SCHEMA."""
        for key in ["peg_ratio", "fcf_yield", "stock_margin_of_safety"]:
            weight = _jsx_weight_for_key(key)
            assert re.match(r"\d+%", weight), f"{key} should have a real weight badge, got {weight!r}"


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
    def test_volatility_beta_and_dta_weights_match_code(self):
        """RESTORED 2026-08-30 (explicit user directive, after a full history dig found this
        pillar's entire 5 -> 12-13 -> 8 -> 4 -> 3 input evolution had zero quoted user sign-off
        on the formula content - only the Stability->Risk rename was ever user-directed).
        Reverted to the ORIGINAL formula (pre-2026-07-23): Volatility 252D 40% + Volatility
        60D 20% + Volatility 30D 15% + Beta 15% + Debt-to-Assets 10%."""
        src = inspect.getsource(StockScoresLoader._score_risk)
        score_var_to_jsx_key = {
            "v252_score": "volatility_12m",  # API key "volatility_12m" actually carries volatility_252d
            "v60_score": "volatility_60d",
            "v30_score": "volatility_30d",
            "beta_score": "beta",
            "dta_score": "debt_to_assets",
        }
        for score_var, jsx_key in score_var_to_jsx_key.items():
            _assert_pct_matches(jsx_key, _weight_for_score_var(src, score_var))

    def test_downside_volatility_and_max_drawdown_not_scored(self):
        """downside_volatility and max_drawdown_1y are not part of the original 5-input
        formula this pillar was reverted to - should stay fully computed/stored but no longer
        weighted into risk_score."""
        src = inspect.getsource(StockScoresLoader._score_risk)
        assert "dvol60_score" not in src, "downside_volatility_60d should no longer be a scored risk_score component"
        assert "dd_score" not in src, "max_drawdown_1y should no longer be a scored risk_score component"


class TestMomentumScoreWeightBadges:
    def test_price_return_weights_match_code(self):
        """RESTORED 2026-08-30 (explicit user directive, after a full history dig found this
        pillar's momentum_1m drop / 12-1 skip-month construction / RSI-MACD merge / ROC
        removal had zero quoted user sign-off). Reverted to the ORIGINAL 8-input formula:
        Momentum 1M 16% + 3M 16% + 6M 14% + 12M 9%."""
        src = inspect.getsource(StockScoresLoader._score_momentum)
        dict_match = re.search(r"weights = \{([\s\S]*?)\}", src)
        assert dict_match, "expected a `weights = {...}` dict literal in _score_momentum"
        dict_weights = {k: float(v) for k, v in re.findall(r'"(\w+)":\s*(0\.\d+)', dict_match.group(1))}

        field_to_jsx_key = {
            "momentum_1m": "momentum_1m",
            "momentum_3m": "momentum_3m",
            "momentum_6m": "momentum_6m",
            "momentum_12m": "momentum_12_3",  # API key "momentum_12_3" carries raw momentum_12m
        }
        for field, jsx_key in field_to_jsx_key.items():
            _assert_pct_matches(jsx_key, dict_weights[field])

    def test_mom_12_1_not_scored(self):
        """The derived 12-1 skip-month construction is not part of the original 8-input
        formula this pillar was reverted to - should no longer be a scored component."""
        src = inspect.getsource(StockScoresLoader._score_momentum)
        assert "mom_12_1_score" not in src, "mom_12_1 should no longer be a scored momentum_score component"

    def test_rsi_and_macd_weights_match_code(self):
        """RESTORED 2026-08-30 - RSI(14) and MACD-sign are independently weighted again
        (15%/10%), not averaged into one combined slot."""
        src = inspect.getsource(StockScoresLoader._score_momentum)
        _assert_pct_matches("rsi", _weight_for_score_var(src, "rsi_score"))
        _assert_pct_matches("macd", _weight_for_score_var(src, "macd_score"))

    def test_roc_composite_weight_matches_code(self):
        """RESTORED 2026-08-30 - the ROC composite (roc_20d/60d/120d/252d, averaged) is a
        scored input again."""
        src = inspect.getsource(StockScoresLoader._score_momentum)
        combined_match = re.search(r"roc_scores\)\s*/\s*len\(roc_scores\)\)\s*\*\s*(0\.\d+)", src)
        assert combined_match, "expected `(sum(roc_scores) / len(roc_scores)) * 0.NN` in source"
        combined_weight = float(combined_match.group(1))
        for jsx_key in ["roc_20d", "roc_60d", "roc_120d", "roc_252d"]:
            _assert_pct_matches(jsx_key, combined_weight)
