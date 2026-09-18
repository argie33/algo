"""Sector-neutral winsorized z-score normalization, shared across pillars.

Rewrite context (2026-09-07, "best and brightest" scoring-methodology directive): published
multi-factor methodology (MSCI Barra USE4/Factor Indexes, AQR's Quality Minus Junk, Fama-French
profitability construction) converges on ONE transform for every raw fundamental ratio -
winsorize, then z-score, computed within each symbol's own sector as the peer group - rather
than hand-tuned absolute breakpoint curves that vary by industry/sector. This module is that
one transform, extracted so Quality (and any future pillar) can share it instead of each
re-deriving its own winsorize/rank/group logic.

Deliberately plain-Python dict-in/dict-out (symbol -> value), matching the existing convention
in loaders/stock_scores/value_metrics.py's `_percent_rank_cheap_high_sector_relative`/
`_winsorize_group_values` (which this module's winsorization bound and residual-pooling
behavior mirror) rather than introducing a pandas dependency into loaders/helpers.
"""

import math


def _winsorize_group(values: dict[str, float]) -> dict[str, float]:
    """Clip a single group's raw values to its own [5th, 95th] percentile.

    FIXED 2026-09-17 (factor-purity MSCI-fidelity audit): this was [1st, 99th] - not MSCI's
    real bound. MSCI's published methodology (e.g. MSCI Enhanced Value Index Methodology
    Appendix II, Section 2.2.1's explicit worked example) winsorizes raw z-scores at the
    [5th, 95th] percentile before the final z-score step, not [1st, 99th]. No pillar in this
    codebase had a documented reason to deviate from that bound - this was an unexamined
    holdover, not a deliberate choice.

    Below 5 points an empirical quantile isn't a trustworthy clip boundary - values pass
    through unchanged (same "too few peers to trust" precedent as the sector-size floor in
    `sector_neutral_zscore`).
    """
    n = len(values)
    if n < 5:
        return dict(values)

    sorted_vals = sorted(values.values())

    def _percentile(pct: float) -> float:
        rank = pct / 100.0 * (n - 1)
        lo = int(rank)
        hi = min(lo + 1, n - 1)
        frac = rank - lo
        return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * frac

    low, high = _percentile(5.0), _percentile(95.0)
    return {symbol: min(max(val, low), high) for symbol, val in values.items()}


def _zscore_group(values: dict[str, float], market_caps: dict[str, float] | None = None) -> dict[str, float]:
    """Z-score a single (already-winsorized) group. A group of 1 has no variance to
    standardize against - returns 0.0 (the neutral/mean score), matching the "no peer to rank
    against" convention `_percent_rank_cheap_high`'s single-symbol case already uses elsewhere
    in this codebase.

    MARKET-CAP-WEIGHTED MEAN/STDEV (added 2026-09-17, factor-purity MSCI-fidelity audit): MSCI's
    real z-score formula (MSCI Enhanced Value Index Methodology, Appendix II - "the mean and
    standard deviation are calculated using the free-float market-cap-weighted values of all
    securities in the parent index") weights the mean/stdev by each constituent's market cap,
    not equal-weighted across symbols - a large-cap outlier's ratio pulls the reference
    distribution more than a micro-cap's, mirroring how MSCI's real cap-weighted parent index
    is itself constructed. `market_caps` is optional and additive-only: omitted (None), or a
    symbol missing from it, falls back to equal-weighting (weight=1.0) for that symbol - so
    every existing caller that doesn't pass market cap data keeps its exact prior behavior,
    and a caller can adopt cap-weighting incrementally per pillar. A symbol with a non-positive
    or missing market cap falls back to weight=1.0 (mean influence) - a symbol with no market
    cap is not silently dropped from the reference population, matching this codebase's "fix
    don't exclude" precedent (see sector_neutral_zscore's own FPI docstring) for the same kind
    of gap.
    """
    if len(values) < 2:
        return dict.fromkeys(values, 0.0)
    weights = {symbol: (market_caps or {}).get(symbol) or 1.0 for symbol in values}
    weights = {symbol: (w if w > 0 else 1.0) for symbol, w in weights.items()}
    total_weight = sum(weights.values())
    mean = sum(val * weights[symbol] for symbol, val in values.items()) / total_weight
    variance = sum(weights[symbol] * (val - mean) ** 2 for symbol, val in values.items()) / total_weight
    stdev = math.sqrt(variance)
    if stdev <= 0:
        return dict.fromkeys(values, 0.0)
    return {symbol: (val - mean) / stdev for symbol, val in values.items()}


def sector_neutral_zscore(
    values: dict[str, float],
    sectors: dict[str, str],
    min_sector_size: int = 15,
    is_foreign_private_issuer: dict[str, bool] | None = None,
    market_caps: dict[str, float] | None = None,
) -> dict[str, float]:
    """Winsorize to [5th, 95th] percentile WITHIN each sector, then z-score WITHIN each sector
    (market-cap-weighted mean/stdev if `market_caps` is supplied - see `_zscore_group`'s own
    docstring; optional and backward-compatible, same as `universe_wide_zscore`).

    This is the peer-group step published methodology calls for (MSCI Barra: "a sector-relative
    score is derived from the combined score by standardizing within each sector"; AQR QMJ:
    rank-then-z applied per metric) - the reference population changes per sector, the
    transformation math does not, unlike a hand-tuned curve whose SHAPE varies by industry.

    A symbol with no `sectors` entry, or whose sector has fewer than `min_sector_size` members
    among `values`, is pooled into one residual group and z-scored against that pool instead -
    never dropped, mirroring `_percent_rank_cheap_high_sector_relative`'s own residual-pool
    fallback (same repo, same "too few peers to trust a sector-only score" reasoning).

    FPI PEER-GROUP SPLIT (added 2026-09-14, goal-session "fix z-scoring issues" directive,
    direct follow-up to that session's live-verified finding: Foreign Private Issuers are
    ~19.8% of the universe by base rate but were 32-52% of our own top-25 lists across every
    cap band for Momentum/Value - vs 0-8% for Quality, whose FPI inputs are already gated by
    separate missing-quarterly-filing/unsupported-currency data checks). Before this fix, an
    FPI with no `is_foreign_private_issuer` signal passed to this function was pooled into the
    SAME sector group as its US GICS peers - a Korean bank's ROE/margin ratios standardized
    against Wells Fargo/JPM's, a Japanese industrial's against Caterpillar's. Real institutional
    multi-factor products (MSCI USA Momentum/Quality/Value, S&P/Nasdaq factor indices) never
    face this because their eligible universe excludes FPIs entirely at construction time -
    that's a fact about how THEIR index is built, not license to exclude FPIs from OUR scoring
    (they're real, legitimately-tradeable companies). The actual defect being fixed here is
    narrower and more defensible: an FPI's fundamentals ratios reflect real, structural
    differences from US GAAP filers (country/currency risk discount baked into valuation
    multiples, IFRS-vs-GAAP recognition differences, EM liquidity/governance discounts) that
    have nothing to do with the metric itself being genuinely better or worse - comparing an
    FPI only against OTHER FPIs (rather than dropping the distinction, which would put them
    back in the contaminated sector pool, or excluding them, which the standing "fix don't
    exclude" directive forbids) removes that structural mismatch while keeping every FPI fully
    scored. FPIs are pooled into ONE global group across all sectors (not split further into
    per-sector-and-FPI cells) because most sectors don't have anywhere near
    `min_sector_size` FPI members individually - same "too few peers to trust a narrower cell"
    reasoning this function already applies to the domestic per-sector/residual split, just
    applied one level earlier so a thin per-sector FPI count doesn't fall back into contaminated
    domestic peer groups instead of its own honest residual pool.
    """
    fpi = is_foreign_private_issuer or {}
    groups: dict[str, list[str]] = {}
    residual: dict[str, float] = {}
    fpi_pool: dict[str, float] = {}
    for symbol, val in values.items():
        if fpi.get(symbol):
            fpi_pool[symbol] = val
            continue
        sector = sectors.get(symbol)
        if sector is None:
            residual[symbol] = val
        else:
            groups.setdefault(sector, []).append(symbol)

    result: dict[str, float] = {}
    for symbols in groups.values():
        if len(symbols) < min_sector_size:
            for symbol in symbols:
                residual[symbol] = values[symbol]
            continue
        sector_values = {symbol: values[symbol] for symbol in symbols}
        result.update(_zscore_group(_winsorize_group(sector_values), market_caps))

    if fpi_pool:
        result.update(_zscore_group(_winsorize_group(fpi_pool), market_caps))
    if residual:
        result.update(_zscore_group(_winsorize_group(residual), market_caps))
    return result


def universe_wide_zscore(values: dict[str, float], market_caps: dict[str, float] | None = None) -> dict[str, float]:
    """Winsorize to [5th, 95th] percentile across the WHOLE population, then z-score against
    that same single population - the correct transform for a factor whose real index
    construction standardizes momentum/quality/etc. against the full eligible universe, not
    per-sector peer groups (unlike `sector_neutral_zscore` above, which IS what MSCI Barra-style
    Quality/Value ratios call for). Market-cap-weighted mean/stdev if `market_caps` is supplied -
    see `_zscore_group`'s own docstring; optional, backward-compatible for callers not yet
    passing cap data.

    ADDED 2026-09-15 (fix for momentum_pillar_sector_relative_conflated_construction_vs_
    diversification_cap_20260915): `sector_neutral_zscore` was applied to momentum's mom_12_1
    component on the theory that MTUM's real MSCI USA Momentum (SR) index "z-scores momentum
    WITHIN each GICS sector" - live-verified wrong (both against fresh MTUM daily holdings
    cap-neutral rank correlation, 0.235 sector-relative vs 0.558 universe-wide using this
    function, and against the index provider's own published methodology language: "the index
    maintains sector diversification... on a market cap-weighted basis" - a PORTFOLIO-
    CONSTRUCTION-level diversification CAP on total sector exposure, not a STOCK-SCORING-level
    per-sector z-score). Same conflation already caught and fixed for Risk/USMV
    (risk_pillar_sector_neutral_vs_real_minvol_construction_20260915) - a real, recurring
    methodology-translation error in this codebase, not a one-off.
    """
    return _zscore_group(_winsorize_group(values), market_caps)


def zscore_to_percentile_scale(zscores: dict[str, float]) -> dict[str, float]:
    """Map a z-score onto the [0, 100] scale existing composite/threshold logic expects, via the
    standard normal CDF (Phi(z) * 100) - smooth and monotonic, unlike a hard percentile-rank tie
    (two symbols with different but close z-scores get different scores here; they'd tie under a
    pure rank). Uses `math.erf` for the CDF (no scipy dependency): Phi(z) = 0.5*(1+erf(z/sqrt(2))).
    """
    import math

    return {symbol: 50.0 * (1.0 + math.erf(z / math.sqrt(2.0))) for symbol, z in zscores.items()}
