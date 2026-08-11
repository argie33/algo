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
scoped to the flat, single-level weighted-average components (value/positioning/
stability's top-level terms, momentum's dict-based 1m/3m/6m/12m weights and its
rsi/macd terms) - Quality's base score and its +/-10 point "enhancement" adjustment are a
different shape (equal-weighted average + bounded adjustment, not a flat weighted sum)
and are deliberately out of scope.
"""

import inspect
import re

from loaders.load_stock_scores import StockScoresLoader

with open("webapp/frontend/src/components/StockScoreAccordion.jsx", encoding="utf-8") as f:
    _JSX_SOURCE = f.read()


def _weight_for_score_var(source: str, score_var: str) -> float:
    """Find `<score_var> * 0.NN` (the weighted_sum accumulation line) in a function's source."""
    match = re.search(r"\b" + re.escape(score_var) + r"\s*\*\s*(0\.\d+)\b", source)
    assert match, f"expected to find `{score_var} * 0.NN` in source - has the code been restructured?"
    return float(match.group(1))


def _jsx_weight_for_key(key: str) -> str:
    match = re.search(r"key: '" + re.escape(key) + r"'.*?weight: '([^']+)'", _JSX_SOURCE)
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
        score_var_to_jsx_key = {
            "pe_score": "stock_pe",
            "pb_score": "stock_pb",
            "ps_score": "stock_ps",
            "fcf_score": "fcf_yield",
            "div_score": "stock_dividend_yield",
            "fpe_score": "stock_forward_pe",
            "eve_score": "stock_ev_ebitda",
            "evr_score": "stock_ev_revenue",
        }
        for score_var, jsx_key in score_var_to_jsx_key.items():
            _assert_pct_matches(jsx_key, _weight_for_score_var(src, score_var))
        # PEG is scored via a helper call, not a `*_score` local - checked directly.
        peg_weight = _weight_for_score_var(src, 'self._peg_to_score(metrics["peg_ratio"])')
        _assert_pct_matches("peg_ratio", peg_weight)


class TestPositioningScoreWeightBadges:
    def test_weights_match_code(self):
        src = inspect.getsource(StockScoresLoader._score_positioning)
        _assert_pct_matches("institutional_ownership_pct", _weight_for_score_var(src, "io"))
        _assert_pct_matches("insider_ownership_pct", _weight_for_score_var(src, "min(100, ins_score)"))
        _assert_pct_matches("short_interest_pct", _weight_for_score_var(src, "max(0, min(100, score))"))
        _assert_pct_matches("short_interest_trend", _weight_for_score_var(src, "trend_score"))
        _assert_pct_matches("ad_rating", _weight_for_score_var(src, 'metrics["ad_rating"]'))


class TestStabilityScoreWeightBadges:
    def test_volatility_and_beta_weights_match_code(self):
        src = inspect.getsource(StockScoresLoader._score_stability)
        score_var_to_jsx_key = {
            "vol_score": "volatility_12m",
            "v60_score": "volatility_60d",
            "v30_score": "volatility_30d",
            "beta_score": "beta",
            "dvol_score": "downside_volatility_252d",
            "dd_score": "max_drawdown_1y",
            "diversification_score": "revenue_concentration_hhi",
        }
        for score_var, jsx_key in score_var_to_jsx_key.items():
            _assert_pct_matches(jsx_key, _weight_for_score_var(src, score_var))


class TestMomentumScoreWeightBadges:
    def test_price_return_weights_match_code(self):
        src = inspect.getsource(StockScoresLoader._score_momentum)
        dict_match = re.search(r"weights = \{([\s\S]*?)\}", src)
        assert dict_match, "expected a `weights = {...}` dict literal in _score_momentum"
        dict_weights = {k: float(v) for k, v in re.findall(r'"(\w+)":\s*(0\.\d+)', dict_match.group(1))}

        field_to_jsx_key = {
            "momentum_1m": "momentum_1m",
            "momentum_3m": "momentum_3m",
            "momentum_6m": "momentum_6m",
            "momentum_12m": "momentum_12_3",
        }
        for field, jsx_key in field_to_jsx_key.items():
            _assert_pct_matches(jsx_key, dict_weights[field])

    def test_rsi_and_macd_weights_match_code(self):
        src = inspect.getsource(StockScoresLoader._score_momentum)
        _assert_pct_matches("rsi", _weight_for_score_var(src, "rsi_score"))
        _assert_pct_matches("macd", _weight_for_score_var(src, "macd_score"))
