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

from loaders.load_stock_scores import BASE_PILLAR_WEIGHTS, StockScoresLoader

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
        # fpe_score/stock_forward_pe removed 2026-08-25 (goal: full scoring-architecture
        # audit) - forward_pe dropped entirely from _score_value (analyst_earnings_estimates
        # has zero historical depth, so this input could never be validated).
        # eve_score/evr_score (EV/EBITDA, EV/Revenue) removed same day, same-pass follow-up -
        # r=1.00/0.93 duplicates of ps_ratio/pe_ratio respectively, see _score_value's
        # docstring RESOLVED note.
        # size_score (market_cap) MOVED OUT 2026-08-26 - promoted to its own top-level "Size"
        # pillar (StockScoresLoader._score_size), no longer part of _score_value at all. See
        # TestSizeScoreWeightBadges below for its (trivial, single-input) coverage. The
        # remaining 7 inputs here were rescaled x1.25 to restore the 100% they held before
        # Size's 20% carve-out (later rescaled again x0.92 the same day - see next note).
        # illiq_score (amihud_illiquidity) ADDED 2026-08-26, REMOVED same day (user directive)
        # - see _score_value's "AMIHUD ILLIQUIDITY" docstring note. The 7 inputs below are
        # back at their pre-Amihud weights.
        score_var_to_jsx_key = {
            "pe_score": "stock_pe",
            "pb_score": "stock_pb",
            "ps_score": "stock_ps",
            "fcf_score": "fcf_yield",
            "div_score": "stock_dividend_yield",
        }
        for score_var, jsx_key in score_var_to_jsx_key.items():
            _assert_pct_matches(jsx_key, _weight_for_score_var(src, score_var))
        # PEG is scored via a helper call, not a `*_score` local - checked directly.
        peg_weight = _weight_for_score_var(src, 'self._peg_to_score(metrics["peg_ratio"])')
        _assert_pct_matches("peg_ratio", peg_weight)


class TestGrowthScoreWeightBadges:
    def test_weights_match_code(self):
        # RESTORED 2026-08-26 (user directive, goal: undo the 2026-08-25 4-input reduction) -
        # back to the pre-08-25 14-input set; see _score_growth's docstring. No class existed
        # here for Growth before this, which is exactly how the 08-25 cut to 4 inputs (and a
        # later same-day revert of the Quality trend fields - see that docstring) was able to
        # drift from what the JSX schema claimed without any test catching it.
        #
        # om_trend/nm_trend/roe_trend REMOVED from this dict 2026-08-27 (goal: resolve the
        # Growth-vs-Quality placement question, see growth_missing_metrics_swept_20260827) -
        # relocated to Quality's composite (load_value_quality_growth_metrics.py), which this
        # test class doesn't cover (Quality's sub-component shape is deliberately out of scope
        # here per this file's own module docstring). Growth is now an 11-input set.
        src = inspect.getsource(StockScoresLoader._score_growth)
        score_var_to_jsx_key = {
            "eps_1y": "eps_growth_1y_pct",
            "rev_1y": "revenue_growth_1y_pct",
            "eps_3y": "eps_growth_3y_cagr",
            "rev_3y": "revenue_growth_3y_cagr",
            "eps_5y": "eps_growth_5y_cagr",
            "rev_5y": "revenue_growth_5y_cagr",
            "ni_growth": "net_income_growth_yoy",
            "oi_growth": "operating_income_growth_yoy",
            "sgr": "sustainable_growth_rate",
            "fcf_growth": "fcf_growth_yoy",
            "ocf_growth": "ocf_growth_yoy",
            "asset_growth": "asset_growth_yoy",
        }
        for score_var, jsx_key in score_var_to_jsx_key.items():
            _assert_pct_matches(jsx_key, _weight_for_score_var(src, score_var))


class TestSizeScoreRemoved:
    def test_market_cap_is_not_a_scored_input(self):
        """Size (market cap) was briefly promoted to a 7th top-level pillar 2026-08-26, then
        removed from scoring entirely the same day (user directive) - see
        loaders/load_stock_scores.py's BASE_PILLAR_WEIGHTS docstring. Guards against the JSX
        schema drifting back to advertising market_cap as a scored factor."""
        assert not hasattr(StockScoresLoader, "_score_size")
        with open("webapp/frontend/src/components/StockScoreAccordion.jsx", encoding="utf-8") as f:
            jsx_source = f.read()
        assert '"market_cap"' not in jsx_source
        assert "size_score" not in jsx_source


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
    def test_volatility_and_beta_weights_match_code(self):
        # volatility_12m/30d and downside_volatility_252d/30d removed 2026-08-25 (goal: full
        # scoring-architecture audit) - all six volatility inputs correlated 0.52-0.92 with
        # each other (measured directly), so consolidated to one symmetric + one downside
        # window (60d) and redistributed the freed weight to beta/max_drawdown.
        src = inspect.getsource(StockScoresLoader._score_risk)
        score_var_to_jsx_key = {
            "v60_score": "volatility_60d",
            "beta_score": "beta",
            "dvol60_score": "downside_volatility_60d",
            "dd_score": "max_drawdown_1y",
        }
        for score_var, jsx_key in score_var_to_jsx_key.items():
            _assert_pct_matches(jsx_key, _weight_for_score_var(src, score_var))


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
        src = inspect.getsource(StockScoresLoader._score_momentum)
        _assert_pct_matches("rsi", _weight_for_score_var(src, "rsi_score"))
        _assert_pct_matches("macd", _weight_for_score_var(src, "macd_score"))
