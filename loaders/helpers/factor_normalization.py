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

import statistics


def _winsorize_group(values: dict[str, float]) -> dict[str, float]:
    """Clip a single group's raw values to its own [1st, 99th] percentile.

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

    low, high = _percentile(1.0), _percentile(99.0)
    return {symbol: min(max(val, low), high) for symbol, val in values.items()}


def _zscore_group(values: dict[str, float]) -> dict[str, float]:
    """Z-score a single (already-winsorized) group. A group of 1 has no variance to
    standardize against - returns 0.0 (the neutral/mean score), matching the "no peer to rank
    against" convention `_percent_rank_cheap_high`'s single-symbol case already uses elsewhere
    in this codebase.
    """
    if len(values) < 2:
        return dict.fromkeys(values, 0.0)
    mean = statistics.fmean(values.values())
    stdev = statistics.pstdev(values.values())
    if stdev <= 0:
        return dict.fromkeys(values, 0.0)
    return {symbol: (val - mean) / stdev for symbol, val in values.items()}


def sector_neutral_zscore(
    values: dict[str, float], sectors: dict[str, str], min_sector_size: int = 15
) -> dict[str, float]:
    """Winsorize to [1st, 99th] percentile WITHIN each sector, then z-score WITHIN each sector.

    This is the peer-group step published methodology calls for (MSCI Barra: "a sector-relative
    score is derived from the combined score by standardizing within each sector"; AQR QMJ:
    rank-then-z applied per metric) - the reference population changes per sector, the
    transformation math does not, unlike a hand-tuned curve whose SHAPE varies by industry.

    A symbol with no `sectors` entry, or whose sector has fewer than `min_sector_size` members
    among `values`, is pooled into one residual group and z-scored against that pool instead -
    never dropped, mirroring `_percent_rank_cheap_high_sector_relative`'s own residual-pool
    fallback (same repo, same "too few peers to trust a sector-only score" reasoning).
    """
    groups: dict[str, list[str]] = {}
    residual: dict[str, float] = {}
    for symbol, val in values.items():
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
        result.update(_zscore_group(_winsorize_group(sector_values)))

    if residual:
        result.update(_zscore_group(_winsorize_group(residual)))
    return result


def zscore_to_percentile_scale(zscores: dict[str, float]) -> dict[str, float]:
    """Map a z-score onto the [0, 100] scale existing composite/threshold logic expects, via the
    standard normal CDF (Phi(z) * 100) - smooth and monotonic, unlike a hard percentile-rank tie
    (two symbols with different but close z-scores get different scores here; they'd tie under a
    pure rank). Uses `math.erf` for the CDF (no scipy dependency): Phi(z) = 0.5*(1+erf(z/sqrt(2))).
    """
    import math

    return {symbol: 50.0 * (1.0 + math.erf(z / math.sqrt(2.0))) for symbol, z in zscores.items()}
