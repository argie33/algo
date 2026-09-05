"""Shared curve-score and percentile-rank helpers used across StockScoresLoader's pillars.

Extracted verbatim (no logic change) from loaders/load_stock_scores.py's staticmethods/
classmethod of the same names - see that file's thin wrapper methods, which just delegate here.
"""

import itertools
import math

# MIN_SECTOR_SLICE: a sector/GICS group needs at least this many symbols in the current run's
# universe before its own within-sector percentile is trusted; smaller groups fall back to the
# plain universe-wide percentile for just their members (fails open, mirrors
# `_get_symbol_sector`'s own fail-open convention in load_value_quality_growth_metrics.py).
# Live sector sizes in the scored universe are all far above this (smallest ~117 symbols, see
# StockScoresLoader's SECTOR-RELATIVE VALUE RANKING docstring note) - this floor exists for
# 'Unclassified' (company_profile.sector missing/NULL) and any genuinely thin group, not the
# normal case. Mirrors StockScoresLoader._MIN_SECTOR_SLICE exactly.
MIN_SECTOR_SLICE = 20


def _pct_to_score(pct_return: float) -> float | None:
    """Convert percentage return to 0-100 score.

    Returns None if momentum is weak (< ±3%), as this indicates
    insufficient conviction. Fail-fast: weak signal is missing data, not low score.
    -20% = 0, ±3% = None, +20% = 100.

    pct_return is a percentage NUMBER (e.g. 20.0 for +20%), not a fraction - matches
    load_risk_metrics_daily.py's ret_pct = (price_new - price_old) / price_old * 100,
    which is what momentum_1m/3m/6m/12m are computed as and stored as.
    """
    # Weak momentum zone: -3% to +3% lacks conviction. pct_return is a percentage NUMBER
    # (e.g. 3.0, not 0.03) - matches the scale momentum_1m/3m/6m/12m are stored in.
    if -3 <= pct_return <= 3:
        return None

    # Map momentum: -20% = 0, +20% = 100
    score = 50 + (pct_return / 0.4)
    return max(0, min(100, score))


def _rsi_to_score(rsi: float) -> float:
    """Map RSI(14) to a momentum-following 0-100 score (higher RSI = more bullish).

    This is deliberately NOT a mean-reversion mapping (which would penalize high RSI as
    "overbought"). For a momentum factor, sustained strength (RSI 50-85) should score well;
    only extreme overbought (>85) gets a mild pullback for reversal risk.
    """
    rsi = max(0.0, min(100.0, rsi))
    if rsi <= 30:
        return (rsi / 30) * 30
    if rsi <= 50:
        return 30 + ((rsi - 30) / 20) * 20
    if rsi <= 70:
        return 50 + ((rsi - 50) / 20) * 35
    if rsi <= 85:
        return 85 + ((rsi - 70) / 15) * 15
    return max(60.0, 100 - (rsi - 85) * 3)


def _pe_curve_score(pe: float) -> float:
    """PROVISIONAL fixed-threshold P/E score (see StockScoresLoader._score_value's PE block
    comment) - used as this symbol's Pass-1 placeholder only. Pass-2
    (update_value_multiples_percentiles()) fully recomputes value_score from percentile ranks
    rather than diffing against this function's output, so this formula is free to change
    without affecting reconciliation."""
    if pe <= 10:
        return 40 + pe * 2  # very cheap / possibly value trap
    if pe <= 20:
        return 60 + (pe - 10) * 4  # good range
    if pe <= 35:
        return 100 - (pe - 20) * 2  # growth premium zone -> 70 at pe=35
    return max(0.0, 70 - (pe - 35) * 1.4)  # expensive -> 0 at pe~85


def _pb_curve_score(pb: float) -> float:
    """PROVISIONAL fixed-threshold P/B score - see `_pe_curve_score`'s docstring for why this
    must stay unchanged independent of the live scoring path."""
    if pb <= 1.0:
        return 100.0
    if pb <= 3.0:
        return 100 - ((pb - 1.0) / 2.0) * 30  # 100->70 in [1,3]
    if pb <= 7.0:
        return 70 - ((pb - 3.0) / 4.0) * 40  # 70->30 in [3,7]
    return max(0.0, 30 - (pb - 7.0) * 3)


def _ps_curve_score(ps: float) -> float:
    """PROVISIONAL fixed-threshold P/S score - see `_pe_curve_score`'s docstring for why this
    must stay unchanged independent of the live scoring path."""
    if ps <= 2.0:
        return 100.0
    if ps <= 6.0:
        return 100 - ((ps - 2.0) / 4.0) * 30  # 100->70 in [2,6]
    if ps <= 15.0:
        return 70 - ((ps - 6.0) / 9.0) * 40  # 70->30 in [6,15]
    return max(0.0, 30 - (ps - 15.0) * 1.5)


def _vol_curve_score(vol: float) -> float:
    """Fixed-threshold volatility score for volatility_60d/252d, same threshold family as
    `_pe_curve_score`/`_pb_curve_score`/`_ps_curve_score`. `vol` must already be non-negative
    (callers clamp via max(0, ...))."""
    if vol <= 0.15:
        return 100.0
    if vol <= 0.30:
        return 100 - ((vol - 0.15) / 0.15) * 50
    if vol <= 0.60:
        return 50 - ((vol - 0.30) / 0.30) * 40
    return max(0.0, 10 - (vol - 0.60) * 20)


def _max_drawdown_curve_score(drawdown_pct: float) -> float:
    """Fixed-threshold max-drawdown score. `drawdown_pct` is a non-negative magnitude (e.g.
    34.63 for a 34.63% peak-to-trough decline) - callers pass
    `abs(min(0.0, max_drawdown_1y))`."""
    if drawdown_pct <= 10:
        return 100 - drawdown_pct * 2  # 100->80
    if drawdown_pct <= 25:
        return 80 - (drawdown_pct - 10) * 2  # 80->50
    if drawdown_pct <= 50:
        return 50 - (drawdown_pct - 25) * 1.2  # 50->20
    return max(0.0, 20 - (drawdown_pct - 50) * 0.4)


def _liquidity_curve_score(avg_dollar_volume_20d: float) -> float:
    """Tradability-risk score for 20-trading-day average dollar volume. See
    StockScoresLoader._score_risk's liquidity-component docstring for the full rationale and
    why the breakpoints are anchored to algo_config.min_adv_dollars ($500K) rather than an
    invented number. `avg_dollar_volume_20d` must already be positive (callers guard via `> 0`).

    Piecewise-linear on log10(dollar_volume), same style as `_vol_curve_score`/
    `_max_drawdown_curve_score`: $100K->0, $500K->35 (the trade-eligibility floor itself),
    $2M->65, $10M->90, $50M+->100 (saturates).
    """
    log_dv = math.log10(avg_dollar_volume_20d)
    breakpoints = [(5.0, 0.0), (5.7, 35.0), (6.3, 65.0), (7.0, 90.0), (7.7, 100.0)]
    if log_dv <= breakpoints[0][0]:
        return 0.0
    if log_dv >= breakpoints[-1][0]:
        return 100.0
    for (x0, y0), (x1, y1) in itertools.pairwise(breakpoints):
        if log_dv <= x1:
            return y0 + (log_dv - x0) / (x1 - x0) * (y1 - y0)
    return 100.0  # unreachable - satisfies mypy's exhaustiveness check


def _percent_rank_cheap_high(values: dict[str, float]) -> dict[str, float]:
    """symbol -> percentile in [0, 100], where the LOWEST raw value gets the HIGHEST percentile
    (100) - matches this pillar's "cheap is good" convention for P/E, P/B, P/S. Ties share the
    same percentile (RANK()-style, not average-rank - matches PostgreSQL's own PERCENT_RANK()
    tie behavior, the same window function `update_rs_percentiles()` already uses for
    rs_percentile). A universe of 1 symbol gets 50.0 (no peer to rank against); empty input
    returns {}.
    """
    n = len(values)
    if n == 0:
        # No candidates to rank - accurate representation of zero work, not data loss.
        return {}
    if n == 1:
        return dict.fromkeys(values, 50.0)
    sorted_items = sorted(values.items(), key=lambda kv: kv[1])
    result: dict[str, float] = {}
    i = 0
    while i < n:
        j = i
        while j < n and sorted_items[j][1] == sorted_items[i][1]:
            j += 1
        pct = 100.0 * (n - 1 - i) / (n - 1)
        for sym, _ in sorted_items[i:j]:
            result[sym] = pct
        i = j
    return result


def _percent_rank_cheap_high_sector_relative(
    values: dict[str, float], sector_map: dict[str, str], min_sector_slice: int = MIN_SECTOR_SLICE
) -> dict[str, float]:
    """Sector-relative counterpart to `_percent_rank_cheap_high` - same "lowest raw value ->
    highest percentile" convention, but each symbol is ranked ONLY against same-sector peers
    (`sector_map[symbol]`, GICS via company_profile.sector) instead of the full cross-sector
    universe. Symbols with no sector_map entry, or belonging to a sector with fewer than
    `min_sector_slice` members among `values`, are pooled into one residual group and ranked
    via the plain universe-wide `_percent_rank_cheap_high` instead - never dropped, never left
    unranked.

    ADDED 2026-09-04 (real-money-readiness review, "always do what is best" directive - see
    StockScoresLoader.update_value_multiples_percentiles(), for the full evidence trail and
    citations). Ties/single-sector/empty-input edge cases all delegate to
    `_percent_rank_cheap_high`'s own already-tested handling, per sector group.
    """
    groups: dict[str, list[str]] = {}
    residual: dict[str, float] = {}
    for symbol, val in values.items():
        sector = sector_map.get(symbol)
        if sector is None:
            residual[symbol] = val
        else:
            groups.setdefault(sector, []).append(symbol)

    result: dict[str, float] = {}
    for symbols in groups.values():
        if len(symbols) < min_sector_slice:
            for symbol in symbols:
                residual[symbol] = values[symbol]
            continue
        sector_values = {symbol: values[symbol] for symbol in symbols}
        result.update(_percent_rank_cheap_high(sector_values))

    if residual:
        result.update(_percent_rank_cheap_high(residual))
    return result


__all__ = [
    "MIN_SECTOR_SLICE",
    "_liquidity_curve_score",
    "_max_drawdown_curve_score",
    "_pb_curve_score",
    "_pct_to_score",
    "_pe_curve_score",
    "_percent_rank_cheap_high",
    "_percent_rank_cheap_high_sector_relative",
    "_ps_curve_score",
    "_rsi_to_score",
    "_vol_curve_score",
]
