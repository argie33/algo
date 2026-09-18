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
from loaders.stock_scores.value_metrics import ValueMetricsMixin

with open("webapp/frontend/src/components/StockScoreAccordion.jsx", encoding="utf-8") as f:
    _JSX_SOURCE = f.read()


def _weight_for_score_var(source: str, score_var: str) -> float:
    """Find `<score_var> * 0.NN` or `<score_var> * 1.0` (a full-weight single-component pillar,
    e.g. momentum's AQR-pivot mom_12_1-only construction) - the weighted_sum accumulation line -
    in a function's source."""
    match = re.search(r"\b" + re.escape(score_var) + r"\s*\*\s*(0\.\d+|1\.0)\b", source)
    assert match, f"expected to find `{score_var} * 0.NN` or `* 1.0` in source - has the code been restructured?"
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
        """MSCI ENHANCED VALUE RESTORED 2026-09-17 (reverts the same-day AQR VALUE REBUILT
        pivot - see value_metrics.py's own MSCI-restoration comment). Pass 2's
        update_value_multiples_percentiles blends 3 MSCI legs at 1/3 each again (1/2 each for
        the 2-leg GICS-Financials-sector case) - no single leg carries the pillar's full weight.
        """
        src = inspect.getsource(ValueMetricsMixin.update_value_multiples_percentiles)
        assert "1.0 / 3.0" in src, (
            "expected update_value_multiples_percentiles's MSCI 3-leg blend (1/3 each), not a "
            "single full-weight AQR leg"
        )
        # stock_pb's JSX weight badge is "1/3" (a fraction, not a %) for the restored MSCI
        # construction - _jsx_weight_for_key just extracts the raw string, no % assumed.
        assert _jsx_weight_for_key("stock_pb") == "1/3", "stock_pb: JSX badge should say 1/3 (MSCI Book/Price leg)"

    def test_forward_pe_and_fcf_yield_scored_again(self):
        """MSCI ENHANCED VALUE RESTORED 2026-09-17: stock_forward_pe/fcf_yield (MSCI's real
        Earnings/Price and EV/CFO legs) are scored inputs again, same used:true/weight:"1/3"
        badge as stock_pb."""
        for key in ("stock_forward_pe", "fcf_yield"):
            match = re.search(r"key:\s*[\"']" + re.escape(key) + r"[\"'].*?\n\s*\},", _JSX_SOURCE, re.DOTALL)
            assert match, f"expected a {key} VALUE_SCHEMA entry"
            assert "used: true" in match.group(0), f"{key} must be used: true"
            assert 'weight: "1/3"' in match.group(0), f'{key} must be weight: "1/3"'


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
        PEG/margin_of_safety/intrinsic_value/ev_ebitda/ev_revenue should have NO row in
        VALUE_SCHEMA at all now, scored or not. Data itself is untouched - still computed/
        stored/API-served - this only guards the display layer.

        fcf_yield is NO LONGER in this removed-list as of the 2026-09-16 factor-purity sweep:
        it's back as the displayable proxy for Pass 2's real EV/CFO leg (value_metrics.py's
        cash_yield_raw_map falls back to it when operating_cash_flow/enterprise_value aren't
        both available) - a genuinely-scored input again, just under a different economic
        role than its old (removed) standalone price-basis leg. stock_pe is added instead -
        trailing P/E is folded into the single Earnings/Price leg (stock_forward_pe's row),
        never displayed as its own independent leg anymore."""
        schema_match = re.search(r"const VALUE_SCHEMA = \[([\s\S]*?)\n\];", _JSX_SOURCE)
        assert schema_match, "expected VALUE_SCHEMA to still exist"
        schema_src = schema_match.group(1)
        removed_keys = [
            "peg_ratio",
            "stock_margin_of_safety",
            "stock_intrinsic_value",
            "stock_ev_ebitda",
            "stock_ev_revenue",
            "stock_ps",
            "stock_dividend_yield",
            "stock_pe",
        ]
        for key in removed_keys:
            assert f'key: "{key}"' not in schema_src and f"key: '{key}'" not in schema_src, (
                f"{key} should have no VALUE_SCHEMA row at all (not scored, so not displayed on this tab)"
            )

    def test_ps_and_dividend_yield_not_scored(self):
        """Guards the 2026-09-16 factor-purity removal - P/S and Dividend Yield (plus the
        hand-set dividend magnitude-bonus curve and FCF-payout-sustainability gate that only
        existed to score dividend_yield) should stay fully computed/stored but never weighted
        into value_score again: MSCI Enhanced Value's real published methodology has no home
        for either, and Pass 2 (value_metrics.py) already dropped both on 2026-09-15. Checks
        the backend side doesn't drift back to computing this dead Pass-1 scaffolding."""
        src = inspect.getsource(StockScoresLoader._score_value)
        assert "ps_score" not in src, "P/S should no longer be a scored value_score component"
        assert "div_score" not in src, "Dividend yield should no longer be a scored value_score component"
        assert not hasattr(StockScoresLoader, "_dividend_sustainability_factor"), (
            "_dividend_sustainability_factor should be deleted, not just unused"
        )


class TestGrowthScoreWeightBadges:
    # GROWTH_SCORE_FIELDS (loaders/load_stock_scores.py) key -> the JSX schema key that
    # displays it (StockScoreAccordion.jsx's GROWTH_SCHEMA). Kept explicit (not derived) so a
    # field renamed on one side without the other fails loudly here.
    _PY_FIELD_TO_JSX_KEY = {
        "eps_growth_trend_5y": "eps_growth_trend_5y",
        "sps_growth_trend_5y": "sps_growth_trend_5y",
        "forward_eps_growth_current_fy": "forward_eps_growth_current_fy",
        "sustainable_growth_rate": "sustainable_growth_rate",
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

    def test_growth_schema_has_no_unscored_rows(self):
        """Guards the 2026-08-31 "if they not scored then dont track" directive - GROWTH_SCHEMA
        must contain exactly GROWTH_SCORE_FIELDS' rows, no extra unscored/reference-only rows
        (fcf_growth_yoy/eps_growth_stability/net_income_growth_yoy/eps_estimate_revision_90d_pct
        were removed from display, not just unweighted - same "if we not scoring it we dont want
        to display it" rule already applied to Value, see TestUnscoredValueFieldsNotDisplayed
        above). Data itself is untouched - still computed/stored/API-served - this only guards
        the display layer. Every other pillar's *_SCHEMA is already 100% scored; this keeps
        Growth consistent with that, not a Growth-specific rule."""
        schema_match = re.search(r"const GROWTH_SCHEMA = \[([\s\S]*?)\n\];", _JSX_SOURCE)
        assert schema_match, "expected GROWTH_SCHEMA to still exist"
        schema_src = schema_match.group(1)
        row_count = len(re.findall(r"key: [\"']", schema_src))
        used_count = len(re.findall(r"used: true", schema_src))
        assert row_count == used_count == len(GROWTH_SCORE_FIELDS), (
            f"GROWTH_SCHEMA has {row_count} rows ({used_count} scored) but GROWTH_SCORE_FIELDS "
            f"has {len(GROWTH_SCORE_FIELDS)} - every row must be scored, none unscored/tracked"
        )
        removed_keys = [
            "fcf_growth_yoy",
            "eps_growth_stability",
            "net_income_growth_yoy",
            "eps_estimate_revision_90d_pct",
        ]
        for key in removed_keys:
            assert f'key: "{key}"' not in schema_src and f"key: '{key}'" not in schema_src, (
                f"{key} should have no GROWTH_SCHEMA row at all (not scored, so not displayed)"
            )


class TestSizeScoreRemoved:
    def test_size_is_not_a_scored_pillar(self):
        """Size (market cap) was briefly promoted to a 7th top-level pillar 2026-08-26, removed
        from scoring entirely the same day (a UX/product objection, not a dispute of the
        evidence), RE-PROMOTED 2026-08-27 on new era-robust half-split evidence, then RETIRED
        ENTIRELY 2026-08-28 (direct user directive "just get rid of size", triggered by its
        imputed-regime evidence not surviving a strict complete-case retest even after fixing
        the data-coverage bugs that retest required first) - see loaders/load_stock_scores.py's
        BASE_PILLAR_WEIGHTS for the full trail. Its last informational-only display remnant
        (the "Size (informational)" card / SIZE_SCHEMA) was itself removed 2026-08-31 (commit
        3cf5bf937, user directive) - market_cap is no longer surfaced in the JSX at all.
        Guards against the JSX schema drifting back to advertising market_cap as a scored
        (weight-badged) input, or the informational card reappearing without a `used`/`weight`
        key that would wrongly imply Size still feeds composite_score."""
        assert not hasattr(StockScoresLoader, "_score_size")
        assert not hasattr(StockScoresLoader, "_size_curve_score")
        assert not hasattr(StockScoresLoader, "update_size_percentiles")
        assert "size" not in BASE_PILLAR_WEIGHTS
        with open("webapp/frontend/src/components/StockScoreAccordion.jsx", encoding="utf-8") as f:
            jsx_source = f.read()
        assert 'scoreKey: "size_score"' not in jsx_source
        # SIZE_SCHEMA and its informational card were removed entirely 2026-08-31 - if either
        # reappears, it must not be weight-badged (would wrongly imply Size scores again).
        schema_match = re.search(r"const SIZE_SCHEMA = \[([\s\S]*?)\n\];", jsx_source)
        if schema_match:
            assert "weight:" not in schema_match.group(1)
        size_card_match = re.search(r'<InputsCard\s+title="Size \(informational\)"[\s\S]*?/>', jsx_source)
        if size_card_match:
            assert "pillarWeight" not in size_card_match.group(0)


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
    def test_beta_bab_weight_matches_code(self):
        """AQR PIVOT 2026-09-17 (see risk_scoring.py's own module docstring): beta_bab
        (Frazzini & Pedersen 2014's Betting-Against-Beta shrinkage estimator) is now the
        pillar's SOLE scored input, `RISK_COMPONENT_WEIGHT` = 1.0 (100%) - a shared named
        constant rather than a per-line literal, so this checks the JSX badge against that
        constant directly instead of `_weight_for_score_var`'s literal-`0.NN` regex."""
        from loaders.stock_scores.risk_scoring import RISK_COMPONENT_WEIGHT

        _assert_pct_matches("beta_bab", RISK_COMPONENT_WEIGHT)

    def test_volatility_beta_and_max_drawdown_no_longer_scored(self):
        """volatility_60d/cmra_12m/raw beta/max_drawdown_1y are informational-only now
        (used:false) - beta_bab is the pillar's only scored input, see this class's own
        docstring above."""
        for key in ("volatility_60d", "cmra_12m", "beta", "max_drawdown_1y"):
            match = re.search(r"key:\s*[\"']" + re.escape(key) + r"[\"'].*?\n\s*\},", _JSX_SOURCE, re.DOTALL)
            assert match, f"expected a {key} RISK_SCHEMA entry"
            assert "used: false" in match.group(0), f"{key} must be used: false"
            assert "weight: null" in match.group(0), f"{key} must be weight: null"

    def test_liquidity_no_longer_scored(self):
        """Liquidity is fetched/displayed informationally only - no longer a weight-badged
        Risk input (see _score_risk's own docstring for the removal rationale)."""
        src = inspect.getsource(StockScoresLoader._score_risk)
        assert "liq_score" not in src, "avg_dollar_volume_20d should no longer be a scored risk_score component"

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
    def test_mom_12_1_and_mom_6m_weights_match_code(self):
        """RISK-ADJUSTED MOMENTUM RESTORED 2026-09-17 (reverts the same-day AQR MOMENTUM PIVOT
        - see momentum_scoring.py's own module docstring): momentum_score is risk-adjusted
        momentum_6m (50%) + risk-adjusted mom_12_1 (50%), matching MSCI's real Momentum Index
        methodology."""
        src = inspect.getsource(StockScoresLoader._score_momentum)
        # momentum_6m's weight lives in the `weights = {"momentum_6m": 0.NN}` dict (applied via
        # `score * w`, not a literal `score * 0.NN`), so _weight_for_score_var's literal-search
        # regex doesn't apply here - matched directly instead.
        weights_match = re.search(r'"momentum_6m":\s*(0\.\d+)', src)
        assert weights_match, 'expected a `weights = {"momentum_6m": 0.NN}` entry in _score_momentum'
        _assert_pct_matches("momentum_6m", float(weights_match.group(1)))
        _assert_pct_matches("momentum_12_1", _weight_for_score_var(src, "mom_12_1_score"))

    def test_technical_indicators_no_longer_scored_or_displayed(self):
        """RSI(14)/MACD/SMA-50/SMA-200/momentum_3m are not part of momentum_score - unaffected
        by the 2026-09-17 MSCI restoration (see momentum_scoring.py's own docstring for the full
        evidence trail). Guards that the rows were actually removed from MOMENTUM_SCHEMA, not
        just left stale (same "no display row for a no-longer-scored field" convention
        RISK_SCHEMA's test_debt_to_assets_not_scored already checks for debt_to_assets).
        momentum_6m IS scored again (see test_mom_12_1_and_mom_6m_weights_match_code above), so
        it's excluded from this removed-field list."""
        src = inspect.getsource(StockScoresLoader._score_momentum)
        assert "tech_trend_scores" not in src, "RSI/MACD should no longer be scored momentum_score components"
        assert "sma_scores" not in src, "SMA positioning should no longer be a scored momentum_score component"
        schema_match = re.search(r"const MOMENTUM_SCHEMA = \[([\s\S]*?)\n\];", _JSX_SOURCE)
        assert schema_match, "expected MOMENTUM_SCHEMA to still exist"
        schema_body = schema_match.group(1)
        for removed_key in ("momentum_3m", "rsi", "macd", "price_vs_sma_50", "price_vs_sma_200"):
            assert f'key: "{removed_key}"' not in schema_body, (
                f"{removed_key} should have no MOMENTUM_SCHEMA row (not scored, so not displayed on this tab)"
            )
        assert 'key: "momentum_12_1"' in schema_body, "momentum_12_1 should have a MOMENTUM_SCHEMA row (scored)"
        assert 'key: "momentum_6m"' in schema_body, "momentum_6m should have a MOMENTUM_SCHEMA row (scored again)"


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
        """Positioning and Size are retired composite pillars, informational-only. Growth was
        retired then RESTORED the same day (2026-09-17 - see BASE_PILLAR_WEIGHTS' own "ABOVE
        DECISION SUPERSEDED" note in pillar_weights.py) and now DOES wire a pillarWeight - see
        test_all_five_composite_pillars_wire_a_pillar_weight below. Positioning/Size's
        InputsCards must not pass a pillarWeight prop (would wrongly imply they feed
        composite_score). Size's own informational card was removed entirely 2026-08-31
        (commit 3cf5bf937, user directive) - if it ever reappears, it must not be weight-badged
        either."""
        positioning_call = re.search(r'<InputsCard\s+title="Positioning \(informational\)"[\s\S]*?/>', _JSX_SOURCE)
        size_call = re.search(r'<InputsCard\s+title="Size \(informational\)"[\s\S]*?/>', _JSX_SOURCE)
        assert positioning_call and "pillarWeight" not in positioning_call.group(0)
        if size_call:
            assert "pillarWeight" not in size_call.group(0)

    def test_all_five_composite_pillars_wire_a_pillar_weight(self):
        for key in ("quality", "value", "risk", "momentum", "growth"):
            assert re.search(r"pillarWeight=\{PILLAR_COMPOSITE_WEIGHTS\." + key + r"\}", _JSX_SOURCE), (
                f"expected InputsCard for '{key}' to wire pillarWeight={{PILLAR_COMPOSITE_WEIGHTS.{key}}}"
            )
