"""Canonical MSCI-style market-cap Tilt Index formula, shared by every API endpoint that
displays a *_tilted_weight for stock_scores' pillar/composite scores.

MOVED HERE 2026-09-17 from loaders/stock_scores/market_cap_tilt.py (which computed this once
in a batch pass and stored the result in 6 stock_scores columns, migration 1294) - user
directive: tilted weight is a display-only derived value, not a real "score", and storing it
as its own column read like a duplicate/parallel copy of the real pillar scores. Migration
1308 drops those columns; this module is now the ONLY implementation of the formula, imported
directly by every consuming API handler so they can't silently drift the way the two dashboard
endpoints did before migration 1294 existed (see that migration's own header for the original
"one path got the fix, the other didn't" bug this centralization is still meant to prevent -
centralizing the FORMULA in one importable function serves the same purpose migration 1294's
stored column did, without persisting a derived value as if it were its own score).

FORMULA: MSCI's own real, published Tilt Index construction (Momentum Indexes Methodology,
August 2021, section 2.2.2; confirmed equation-level identical for Quality in the Quality
Indexes Methodology, May 2022, section 2.2.3/Appendix V - "The MSCI Quality Tilt Index follows
the same weighting scheme as the MSCI Quality Index"):
    Z = cross-sectional z-score of the score within the eligible population, winsorized to
        [-3, +3]
    Tilt Score = 1 + Z            if Z >= 0
    Tilt Score = (1 - Z)^-1       if Z < 0
    Tilt Weight = market_cap * Tilt Score, renormalized so weights sum to 100 (percentage
        points) across the eligible population computed over.

Asymmetric on purpose (MSCI's own construction) - keeps the multiplier strictly positive
across the full winsorized range (0.25x at Z=-3 to 4x at Z=+3) with no separate floor
constant needed.

NOT a change to composite_score/pillar scores themselves, which stay pure factor-merit and
continue driving live Phase 7/8 trading decisions unchanged - these are DISPLAY-only.
"""

from __future__ import annotations

TILT_ZSCORE_WINSORIZE_BOUND = 3.0


def tilt_score_from_zscore(z: float) -> float:
    """MSCI's published Tilt Index Score formula (see module docstring)."""
    z = max(-TILT_ZSCORE_WINSORIZE_BOUND, min(TILT_ZSCORE_WINSORIZE_BOUND, z))
    return 1 + z if z > 0 else 1 / (1 - z)


def compute_tilted_weights(
    score_by_symbol: dict[str, float], market_cap_by_symbol: dict[str, float]
) -> dict[str, float]:
    """Compute MSCI Tilt Index weights (percentage points, summing to 100.0) for every symbol
    in `score_by_symbol` that also has a positive market cap in `market_cap_by_symbol`.

    `score_by_symbol`/`market_cap_by_symbol` should cover the SAME eligible population a
    caller would otherwise use for any other cross-sectional stock_scores ranking (see
    algo/signals/investable_universe.py's investable_universe_conditions) - the z-score (and
    therefore every symbol's resulting weight) is a function of that population's mean/stdev,
    so a caller that passes a different-shaped population than another caller will compute
    different numbers for the same symbol, same "must not silently drift between consumers"
    concern migration 1294 was originally built to prevent.

    A symbol missing a score, or missing/non-positive market cap, is simply absent from the
    returned dict (never a fabricated 0.0 or fallback) - same "skip what's unavailable, never
    fake it" convention as every pillar scoring pass in this codebase. NOT AN ERROR: a
    population too small to standardize against (under 2 scores, zero variance, or no symbol
    with a usable market cap at all) has no work to do - there is no real per-symbol weight to
    compute, so this returns an empty dict rather than raising, matching
    loaders/helpers/factor_normalization.py's _zscore_group same-size convention.
    """
    values = list(score_by_symbol.values())
    if len(values) < 2:
        return {}  # not an error - no work to do, see docstring
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    stdev = variance**0.5
    if stdev <= 0:
        return {}  # not an error - no work to do, see docstring

    raw_weights: dict[str, float] = {}
    for symbol, score in score_by_symbol.items():
        market_cap = market_cap_by_symbol.get(symbol)
        if market_cap is None or market_cap <= 0:
            continue
        z = (score - mean) / stdev
        raw_weights[symbol] = market_cap * tilt_score_from_zscore(z)

    total_weight = sum(raw_weights.values())
    if total_weight <= 0:
        return {}  # not an error - no work to do, see docstring
    return {symbol: (w / total_weight) * 100.0 for symbol, w in raw_weights.items()}
