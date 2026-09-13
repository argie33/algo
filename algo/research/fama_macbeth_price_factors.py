#!/usr/bin/env python3
"""
Fama-MacBeth cross-sectional regression harness for price-derived factors.

Built 2026-08-25 (goal: figure out the right stock_scores inputs/weightings). Runs a proper
monthly Fama-MacBeth two-pass regression - one cross-sectional OLS per month, then the
coefficient time series is averaged with its own standard error - rather than the pooled-panel
Spearman correlations used elsewhere in this codebase's factor audits (see
loaders/load_stock_scores.py's pillar docstrings). The distinction matters: a pooled panel
treats every symbol-month as an independent observation, so it understates the correlation
between observations in the same month (shared market-wide shocks) and overstates statistical
significance - a p=1e-70 pooled result can correspond to a t-stat under 2 once averaged
properly across (many fewer) independent months. Fama-MacBeth's t-stats are month-count-limited,
not observation-count-limited, which is the more honest test for "does this factor predict the
cross-section of forward returns."

Scope: price-derived factors only (momentum, volatility, beta, drawdown) - these are the only
factor family point-in-time-reconstructable from price_daily alone, which has real daily
coverage for 3,000+ symbols back to 2016 and 10,982 by 2025-2026. Fundamental factors (growth,
value, quality, positioning sub-fields) are NOT run here: value_metrics/growth_metrics/
quality_metrics/stability_metrics/momentum_metrics are all single-row-per-symbol snapshots (no
history - confirmed via `SELECT COUNT(*), COUNT(DISTINCT symbol)` returning a 1.0 ratio on
every one of them), so a monthly panel for those pillars would first need point-in-time
reconstruction from annual_income_statement/annual_balance_sheet, the way the 2026-08-25
asset-growth-sign-flip backtest did ad hoc (see git commit 92cd092ce). That's a real, larger
follow-up - flagged, not built here.

Known data caveat: ~35-38% of price_daily rows (even 2020+) have a NULL adj_close; this script
falls back to COALESCE(adj_close, close), which means symbols with a NULL adj_close around a
split/dividend event will show an unadjusted return spike for that month. Not corrected for -
acceptable for a research/factor-weighting pass, not for anything computing real position P&L.

Usage:
    python -m algo.research.fama_macbeth_price_factors [options]

    --start-date DATE       Earliest month-end price to pull (default: 2014-01-01, gives a
                             24-month warmup before the first usable regression month)
    --end-date DATE         Latest month-end price to pull (default: today)
    --min-cross-section N   Minimum symbols in a month's cross-section to use it (default: 100
                             whole-universe, auto-scaled down for a small --industries group)
    --beta-window N         Trailing months for beta regression (default: 24)
    --vol-window N          Trailing months for vol/downside-vol/max-drawdown (default: 12)
"""

import argparse
import logging
from datetime import datetime
from typing import Any, NamedTuple

import numpy as np
import pandas as pd

from loaders.helpers.vqg_shared import (
    DEPOSITORY_BANK_INDUSTRIES,
    INSURANCE_UNDERWRITER_INDUSTRIES,
    REIT_INDUSTRIES,
)
from utils.db.context import DatabaseContext

logger = logging.getLogger(__name__)

FACTOR_COLS = ["mom_12_1", "mom_6m", "mom_3m", "str_1m", "vol", "downside_vol", "beta", "max_dd"]

# See fama_macbeth_quality_factors.py's own INDUSTRY_GROUPS for why this exists.
INDUSTRY_GROUPS = {
    "banks": DEPOSITORY_BANK_INDUSTRIES,
    "insurers": INSURANCE_UNDERWRITER_INDUSTRIES,
    "reits": REIT_INDUSTRIES,
}

# Whole-GICS-sector groups (company_profile.sector), a coarser grouping than the industry-level
# INDUSTRY_GROUPS above - added 2026-09-13 (/goal session Item 3) to test Materials' newly-
# measured leaderboard overweight (2.79x in top-50, see
# leaderboard_concentration_post_universe_fix_20260913 in memory) the same non-circular way
# banks/insurers/reits were already tested, instead of assuming either "deserved" or "artifact".
# No existing per-industry list fits Materials (it spans chemicals/mining/metals/construction
# materials industries with no single narrow SIC-style bucket), so this filters by the broad
# sector column directly rather than adding a synthetic industries frozenset to vqg_shared.py.
SECTOR_GROUPS = {
    "materials": "Materials",
}


def fetch_month_end_prices(start_date: str, end_date: str) -> pd.DataFrame:
    """Pull one row per (symbol, month) = the last trading day's price that month.

    Uses COALESCE(adj_close, close) - see module docstring caveat on NULL adj_close coverage.
    """
    sql = """
        WITH month_ends AS (
            SELECT symbol, date, COALESCE(adj_close, close) AS px,
                   ROW_NUMBER() OVER (
                       PARTITION BY symbol, date_trunc('month', date) ORDER BY date DESC
                   ) AS rn
            FROM price_daily
            WHERE date >= %s AND date < %s
              AND COALESCE(adj_close, close) > 0
              AND COALESCE(data_unavailable, false) = false
        )
        SELECT symbol, date_trunc('month', date)::date AS month, px
        FROM month_ends WHERE rn = 1
        ORDER BY symbol, month
    """
    with DatabaseContext("read") as cur:
        cur.execute(sql, (start_date, end_date))
        rows = cur.fetchall()
    df = pd.DataFrame(rows, columns=["symbol", "month", "px"])
    df["px"] = df["px"].astype(float)  # psycopg2 returns NUMERIC as decimal.Decimal
    return df


def _trailing_cumret(px: pd.DataFrame, end_idx: int, n_months: int) -> pd.Series:
    """Cumulative return over n_months ending at end_idx (inclusive)."""
    if end_idx - n_months < 0:
        return pd.Series(np.nan, index=px.columns)
    start = px.iloc[end_idx - n_months]
    end = px.iloc[end_idx]
    with np.errstate(divide="ignore", invalid="ignore"):
        return end / start - 1.0


def build_monthly_cross_sections(
    px: pd.DataFrame, ret: pd.DataFrame, beta_window: int, vol_window: int, min_cross_section: int
) -> list[tuple[pd.Timestamp, pd.DataFrame]]:
    """Build one winsorized, z-scored cross-sectional factor+forward-return frame per month."""
    if "SPY" not in ret.columns:
        raise ValueError("SPY not present in price panel - required as the market factor for beta")
    mkt = ret["SPY"]
    months = ret.index
    records: list[tuple[pd.Timestamp, pd.DataFrame]] = []

    for i in range(len(months)):
        if i < beta_window or i >= len(months) - 1:
            continue

        mom_12_1 = _trailing_cumret(px, i - 1, 11)  # skip most-recent month (Jegadeesh 1990)
        mom_6m = _trailing_cumret(px, i, 6)
        mom_3m = _trailing_cumret(px, i, 3)
        str_1m = ret.iloc[i]

        win = ret.iloc[i - vol_window + 1 : i + 1]
        vol = win.std() * np.sqrt(12)
        downside_vol = win.where(win < 0).std() * np.sqrt(12)

        winb = ret.iloc[i - beta_window + 1 : i + 1]
        mkt_win = mkt.iloc[i - beta_window + 1 : i + 1]
        mkt_var = mkt_win.var()
        beta = winb.apply(lambda col, m=mkt_win: col.cov(m)) / mkt_var if mkt_var and mkt_var > 0 else np.nan

        win_px = px.iloc[i - vol_window + 1 : i + 1]
        roll_max = win_px.cummax()
        max_dd = (win_px / roll_max - 1.0).min()

        fwd_ret = ret.iloc[i + 1]

        frame = pd.DataFrame(
            {
                "mom_12_1": mom_12_1,
                "mom_6m": mom_6m,
                "mom_3m": mom_3m,
                "str_1m": str_1m,
                "vol": vol,
                "downside_vol": downside_vol,
                "beta": beta,
                "max_dd": max_dd,
                "fwd_ret": fwd_ret,
            }
        )
        frame = frame.drop(index=["SPY"], errors="ignore")
        frame = frame.replace([np.inf, -np.inf], np.nan).dropna()
        # Drop pathological forward returns (data errors, not real single-month moves).
        frame = frame[(frame["fwd_ret"] > -0.95) & (frame["fwd_ret"] < 5.0)]
        if len(frame) < min_cross_section:
            continue

        for col in FACTOR_COLS:
            lo, hi = frame[col].quantile([0.01, 0.99])
            frame[col] = frame[col].clip(lo, hi)
            std = frame[col].std()
            frame[col] = (frame[col] - frame[col].mean()) / std if std > 0 else 0.0

        records.append((months[i], frame))

    return records


def newey_west_se(x: np.ndarray[Any, Any], lags: int) -> float:
    """Newey-West HAC (Bartlett kernel) standard error of the sample mean of a time series.

    Extracted 2026-09-13 (goal: "check the accuracy of all our inputs" session) from
    `momentum_residual_univariate_isolation_check.py`'s own `_newey_west_tstat` (that file's
    private, one-off copy predates this shared home - not touched here beyond adding this
    shared version; existing call site is unaffected). `lags=0` is close to but not identical
    to the plain `std(ddof=1)/sqrt(n)` formula `_fama_macbeth` uses when `hac_lags=None` (this
    uses a population-variance convention, ddof=0, vs. that formula's sample-variance ddof=1 -
    the two converge as n grows but differ slightly for small n), so `hac_lags=None` (unchanged
    default behavior) rather than `hac_lags=0` is what preserves every existing call site's
    exact historical output.
    """
    n = len(x)
    mean = x.mean()
    demeaned = x - mean
    gamma0 = float(np.sum(demeaned * demeaned)) / n
    var = gamma0
    for lag in range(1, lags + 1):
        w = 1.0 - lag / (lags + 1)
        gamma_l = float(np.sum(demeaned[lag:] * demeaned[: n - lag])) / n
        var += 2.0 * w * gamma_l
    return float(np.sqrt(max(var, 0.0) / n))


def _fama_macbeth(
    records: list[tuple[pd.Timestamp, pd.DataFrame]], cols: list[str], hac_lags: int | None = None
) -> dict[str, tuple[float, float]]:
    """Run one cross-sectional OLS per month on `cols` (plus intercept), average the
    coefficient time series, and return {name: (mean_coef, t_stat)}.

    `hac_lags` (added 2026-09-13, goal: "check the accuracy of all our inputs" session):
    optional Newey-West HAC lag count for the t-stat's standard error, instead of the plain
    `std(ddof=1)/sqrt(n)` this function has always used. Defaults to None (unchanged behavior -
    every existing call site and every conclusion already drawn from this function's t-stats
    stays exactly as computed) because the naive SE assumes the monthly coefficient series has
    no serial correlation, which is optimistic in two known ways real callers hit: (1) any
    horizon_months>1 caller (e.g. fama_macbeth_growth_factors.py's `run(horizon_months=N)`)
    uses OVERLAPPING forward-return windows by construction - consecutive months share
    horizon_months-1 months of the same realized return, which is textbook Newey-West territory
    (the standard rule of thumb is lags=horizon_months-1); (2) even at horizon_months=1,
    persistent factor premia (a value/quality/momentum regime that runs hot or cold for several
    months in a row, not just one) can autocorrelate the coefficient series itself -
    `momentum_residual_univariate_isolation_check.py` already found this worth checking
    (Newey-West 3-lag) for one momentum-family isolation check; this makes that same check
    available to every other factor-validation script in this family instead of it being a
    one-off. Pass an explicit lag count (commonly horizon_months-1, or a small fixed count like
    3 as a general robustness cross-check) on any NEW analysis where serial correlation is a
    live concern - this does not retroactively change any already-documented conclusion.
    """
    coef_hist: dict[str, list[float]] = {c: [] for c in ["const", *cols]}
    for _month, frame in records:
        x = np.column_stack([np.ones(len(frame))] + [frame[c].values for c in cols])
        y = frame["fwd_ret"].values
        coefs, *_ = np.linalg.lstsq(x, y, rcond=None)
        for j, name in enumerate(["const", *cols]):
            coef_hist[name].append(coefs[j])

    results = {}
    for name, series in coef_hist.items():
        arr = np.array(series)
        mean = arr.mean()
        se = newey_west_se(arr, hac_lags) if hac_lags is not None else arr.std(ddof=1) / np.sqrt(len(arr))
        results[name] = (mean, mean / se if se > 0 else float("nan"))
    return results


def benjamini_hochberg_fdr(t_stats: dict[str, float], n_months: int, q: float = 0.10) -> dict[str, bool]:
    """Benjamini-Hochberg FDR correction across a family of candidates tested in the same pass.

    `t_stats` maps candidate name -> Fama-MacBeth t-stat (the second element of each
    `_fama_macbeth` result tuple). `n_months` is the number of monthly cross-sections each
    t-stat was computed over (used as the t-distribution's degrees of freedom, n_months - 1)
    so t-stats from windows of different lengths are put on a common p-value scale before
    comparison. Returns {name: bool} - True means the candidate survives correction at FDR
    `q` (the expected fraction of false discoveries among everything declared "significant",
    not a per-candidate alpha).

    Use this instead of a bare |t|>=2 cutoff whenever more than one candidate is screened in
    the same pass. Per multiple_hypothesis_testing_no_fdr_correction_20260912 in memory: this
    repo's fama_macbeth_*.py family has tested ~65 candidate factors total, each historically
    judged individually against |t|>=2 (~p<0.05) with zero multiple-comparisons correction -
    testing that many candidates at p<0.05 would produce ~3 "significant" hits by chance alone
    even if none of them were real factors. This does not retroactively change conclusions
    already documented in this file's history; apply it to every NEW multi-candidate screen
    going forward (see the WEIGHT-REVISION GOVERNANCE POLICY in loaders/stock_scores/
    pillar_weights.py).
    """
    from scipy import stats as scipy_stats

    names = list(t_stats.keys())
    df = max(n_months - 1, 1)
    pvals = np.array([2 * scipy_stats.t.sf(abs(t_stats[n]), df) if not np.isnan(t_stats[n]) else 1.0 for n in names])
    m = len(pvals)
    order = np.argsort(pvals)
    sorted_p = pvals[order]
    thresholds = q * (np.arange(1, m + 1) / m)
    below = np.where(sorted_p <= thresholds)[0]
    cutoff_p = sorted_p[below.max()] if len(below) else -1.0
    return {name: bool(cutoff_p >= 0 and pvals[i] <= cutoff_p) for i, name in enumerate(names)}


def variance_inflation_factors(records: list[tuple[pd.Timestamp, pd.DataFrame]], cols: list[str]) -> dict[str, float]:
    """Average per-month VIF for each factor in `cols` (regress each factor on the others
    within each month's cross-section, average 1/(1-R^2) across months).

    Built 2026-09-13 - direct response to vol/max_dd/beta producing era-split results that
    flipped BOTH which era was strong and the sign of the effect between two independently
    written test scripts (see risk_momentum_price_factor_validity_fresh_run_postcleanup_20260913
    vs algo-3b's contradicting run, in memory). A single 50/50 split can't distinguish "real,
    unstable-over-time factor" from "collinear factor whose multivariate coefficient is
    underdetermined" - VIF answers the second question directly. Loosely: VIF>5 means a
    factor's multivariate sign/magnitude should not be trusted on its own; VIF>10 is severe.
    Check this BEFORE shipping any weight change based on a multivariate coefficient's sign.
    """
    per_month: dict[str, list[float]] = {c: [] for c in cols}
    for _month, frame in records:
        for target in cols:
            others = [c for c in cols if c != target]
            x = np.column_stack([np.ones(len(frame))] + [frame[c].values for c in others])
            y = frame[target].values
            coefs, *_ = np.linalg.lstsq(x, y, rcond=None)
            pred = x @ coefs
            ss_res = np.sum((y - pred) ** 2)
            ss_tot = np.sum((y - y.mean()) ** 2)
            r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0
            per_month[target].append(1.0 / (1.0 - r2) if r2 < 0.999 else float("inf"))
    return {c: float(np.mean(v)) for c, v in per_month.items()}


class EraRobustness(NamedTuple):
    t_stats: list[float]
    sign_agrees_across_blocks: bool
    blocks_clearing_1_5: int
    n_blocks: int


def multi_split_era_robustness(
    records: list[tuple[pd.Timestamp, pd.DataFrame]], cols: list[str], n_splits: int = 4
) -> dict[str, EraRobustness]:
    """Split the sample chronologically into `n_splits` contiguous, roughly-equal blocks - not
    just one 50/50 split - and run a univariate Fama-MacBeth per factor within each block.

    Built 2026-09-13, same motivation as `variance_inflation_factors` above. A single
    split_date answers "is this factor stronger in the first half or second half" - one draw,
    entirely dependent on exactly where the split falls, which is how two honest sessions can
    get opposite-era-strength answers on the same (clean, post-price_daily-cleanup) data. This
    reports the full block-by-block distribution instead: how many of the n_splits blocks agree
    in sign, and how many independently clear a block-level bar of |t|>=1.5 (loosened from the
    usual 2.0 since each block has ~1/n_splits the months of a single-split half). A factor
    whose sign flips across blocks, or clears the bar in only one, is exactly the
    noise/instability signature this exists to catch - do not make a weight decision off a
    single split_date result for any factor without also checking this.
    """
    n = len(records)
    edges = [round(i * n / n_splits) for i in range(n_splits + 1)]
    blocks = [records[edges[i] : edges[i + 1]] for i in range(n_splits)]

    out: dict[str, EraRobustness] = {}
    for c in cols:
        t_stats: list[float] = []
        signs: list[int] = []
        for block in blocks:
            if len(block) < 3:
                t_stats.append(float("nan"))
                signs.append(0)
                continue
            _mean, t = _fama_macbeth(block, [c])[c]
            t_stats.append(t)
            signs.append(int(np.sign(t)) if not np.isnan(t) else 0)
        valid = [t for t in t_stats if not np.isnan(t)]
        nonzero_signs = {s for s in signs if s != 0}
        out[c] = EraRobustness(
            t_stats=t_stats,
            sign_agrees_across_blocks=len(nonzero_signs) <= 1 and bool(nonzero_signs),
            blocks_clearing_1_5=sum(1 for t in valid if abs(t) >= 1.5),
            n_blocks=n_splits,
        )
    return out


SURVIVORSHIP_BIAS_CAVEAT = (
    "SURVIVORSHIP BIAS WARNING: this panel excludes every company that failed/delisted for "
    "cause during the sample window (confirmed 2026-09-12 - zero price_daily rows for Lehman, "
    "Bear Stearns, Enron, SVB, Signature Bank, First Republic, WorldCom, WAMU under any ticker; "
    "see survivorship_bias_concretely_reverified_zero_rows_named_failures_20260912 in memory). "
    "Every t-stat/IC below answers 'does this factor help pick among companies that survived,' "
    "NEVER 'does this factor protect against picking one that was about to fail.' Do not treat "
    "a significant result here as evidence a factor manages tail/crisis risk. No fix currently "
    "applied - real fix is a delisted-symbol price backfill (data vendor decision, not started)."
)


def print_survivorship_bias_caveat() -> None:
    """Print SURVIVORSHIP_BIAS_CAVEAT as a banner. Call this at the start of every
    fama_macbeth_*.py `run()` (and any other backtest/factor-test script here) so the
    limitation is visible in every actual invocation's output, not just in a memory file
    nobody reads before running the script."""
    print(f"\n{'=' * 78}\n{SURVIVORSHIP_BIAS_CAVEAT}\n{'=' * 78}\n")


def fetch_symbols_for_industries(industries: frozenset[str]) -> set[str]:
    """Symbols whose company_profile.industry (SIC-derived) is in `industries`.

    Added 2026-09-12 (see forward_return_validation_methodology_circular_for_price_derived_pillars_20260912
    in memory) - the "real next step" flagged there: an industry filter for
    fama_macbeth_quality_factors.py/fama_macbeth_value_factors.py, tested first against
    DEPOSITORY_BANK_INDUSTRIES (loaders/helpers/vqg_shared.py) to get a genuine point-in-time-panel
    answer for banks specifically, rather than the circular snapshot-vs-trailing-return proxy used
    in prior sessions' bank/insurance memory entries.
    """
    sql = "SELECT symbol FROM company_profile WHERE industry = ANY(%s)"
    with DatabaseContext("read") as cur:
        cur.execute(sql, (list(industries),))
        return {row[0] for row in cur.fetchall()}


def fetch_symbols_for_sector(sector: str) -> set[str]:
    """Symbols whose company_profile.sector matches `sector` exactly - see SECTOR_GROUPS'
    own comment for why a whole-sector filter is needed alongside the narrower
    fetch_symbols_for_industries() above."""
    with DatabaseContext("read") as cur:
        cur.execute("SELECT symbol FROM company_profile WHERE sector = %s", (sector,))
        return {row[0] for row in cur.fetchall()}


def run(
    start_date: str,
    end_date: str,
    min_cross_section: int | None,
    beta_window: int,
    vol_window: int,
    industry_group: str | None = None,
) -> None:
    print_survivorship_bias_caveat()
    logger.info(f"Pulling month-end price panel {start_date}..{end_date}")
    df = fetch_month_end_prices(start_date, end_date)
    logger.info(f"{len(df)} symbol-month rows fetched")

    symbols: set[str] | None = None
    if industry_group is not None:
        if industry_group in SECTOR_GROUPS:
            symbols = fetch_symbols_for_sector(SECTOR_GROUPS[industry_group]) | {"SPY"}
        else:
            symbols = fetch_symbols_for_industries(INDUSTRY_GROUPS[industry_group]) | {"SPY"}
        logger.info(f"--industries {industry_group}: {len(symbols) - 1} symbols in company_profile (+SPY)")
        df = df[df["symbol"].isin(symbols)]
        logger.info(f"{len(df)} symbol-month rows after industry filter")

    if min_cross_section is None:
        # Small industry groups (e.g. insurers, ~95 symbols) never clear the whole-universe
        # default of 100/month even at full membership - auto-scale down instead of a silent
        # zero-usable-months RuntimeError (live-hit 2026-09-12 running --industries insurers).
        # Only applies when the caller didn't pass an explicit --min-cross-section.
        min_cross_section = 100 if symbols is None else max(10, int(0.5 * (len(symbols) - 1)))
        logger.info(f"--min-cross-section not set, using {min_cross_section}")

    px = df.pivot(index="month", columns="symbol", values="px").sort_index()
    ret = px.pct_change(fill_method=None)

    records = build_monthly_cross_sections(px, ret, beta_window, vol_window, min_cross_section)
    if not records:
        raise RuntimeError("No usable cross-sectional months - check date range / min_cross_section")

    sizes = [len(f) for _, f in records]
    print(f"Usable cross-sectional months: {len(records)}  ({records[0][0]} to {records[-1][0]})")
    print(f"Median cross-section size: {int(np.median(sizes))}\n")

    print("=== Multivariate Fama-MacBeth (controls for all factors jointly) ===")
    print(f"{'factor':14s} {'mean_coef':>10s} {'t_stat':>8s} {'n_months':>9s}")
    multi = _fama_macbeth(records, FACTOR_COLS)
    for name, (mean, t) in multi.items():
        print(f"{name:14s} {mean:10.5f} {t:8.2f} {len(records):9d}")

    print("\n=== Univariate Fama-MacBeth (each factor alone) ===")
    uni_mean, uni_t = {}, {}
    for c in FACTOR_COLS:
        uni = _fama_macbeth(records, [c])
        uni_mean[c], uni_t[c] = uni[c]
    fdr = benjamini_hochberg_fdr(uni_t, len(records))
    print(f"{'factor':14s} {'mean_coef':>10s} {'t_stat':>8s} {'FDR q<=0.10':>12s}")
    for c in FACTOR_COLS:
        verdict = "PASS" if fdr[c] else "fail"
        print(f"{c:14s} {uni_mean[c]:10.5f} {uni_t[c]:8.2f} {verdict:>12s}")

    print("\n=== Multicollinearity check (VIF - check before trusting any multivariate sign) ===")
    vif = variance_inflation_factors(records, FACTOR_COLS)
    for c in FACTOR_COLS:
        flag = (
            "  <- HIGH: multivariate coef for this factor is unstable, don't trust its sign alone" if vif[c] > 5 else ""
        )
        print(f"{c:14s} VIF={vif[c]:6.2f}{flag}")

    n_splits = 4
    print(f"\n=== Multi-split era robustness ({n_splits}-block chronological split, not a single 50/50) ===")
    robustness = multi_split_era_robustness(records, FACTOR_COLS, n_splits=n_splits)
    for c in FACTOR_COLS:
        r = robustness[c]
        t_str = "  ".join(f"{t:6.2f}" if not np.isnan(t) else "   nan" for t in r.t_stats)
        robust = r.sign_agrees_across_blocks and r.blocks_clearing_1_5 >= n_splits - 1
        verdict = "ROBUST" if robust else "unstable/inconclusive"
        print(
            f"{c:14s} block t-stats: [{t_str}]  sign_agrees={r.sign_agrees_across_blocks}  "
            f"clears|t|>=1.5 in {r.blocks_clearing_1_5}/{r.n_blocks}  -> {verdict}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--start-date", default="2014-01-01")
    parser.add_argument("--end-date", default=datetime.now(tz=None).date().isoformat())
    parser.add_argument(
        "--min-cross-section",
        type=int,
        default=None,
        help="Minimum symbols in a month's cross-section to use it (default: 100 whole-universe, "
        "auto-scaled down for a small --industries group).",
    )
    parser.add_argument("--beta-window", type=int, default=24)
    parser.add_argument("--vol-window", type=int, default=12)
    parser.add_argument(
        "--industries",
        choices=sorted(set(INDUSTRY_GROUPS) | set(SECTOR_GROUPS)),
        default=None,
        help="Restrict the panel to one industry/sector group (see INDUSTRY_GROUPS/SECTOR_GROUPS) "
        "instead of the whole universe.",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run(
        args.start_date,
        args.end_date,
        args.min_cross_section,
        args.beta_window,
        args.vol_window,
        args.industries,
    )


if __name__ == "__main__":
    main()
