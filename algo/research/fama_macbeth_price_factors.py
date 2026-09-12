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
    --min-cross-section N   Minimum symbols in a month's cross-section to use it (default: 100)
    --beta-window N         Trailing months for beta regression (default: 24)
    --vol-window N          Trailing months for vol/downside-vol/max-drawdown (default: 12)
"""

import argparse
import logging
from datetime import datetime

import numpy as np
import pandas as pd

from utils.db.context import DatabaseContext

logger = logging.getLogger(__name__)

FACTOR_COLS = ["mom_12_1", "mom_6m", "mom_3m", "str_1m", "vol", "downside_vol", "beta", "max_dd"]


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


def _fama_macbeth(records: list[tuple[pd.Timestamp, pd.DataFrame]], cols: list[str]) -> dict[str, tuple[float, float]]:
    """Run one cross-sectional OLS per month on `cols` (plus intercept), average the
    coefficient time series, and return {name: (mean_coef, t_stat)}."""
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
        se = arr.std(ddof=1) / np.sqrt(len(arr))
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


def run(start_date: str, end_date: str, min_cross_section: int, beta_window: int, vol_window: int) -> None:
    print_survivorship_bias_caveat()
    logger.info(f"Pulling month-end price panel {start_date}..{end_date}")
    df = fetch_month_end_prices(start_date, end_date)
    logger.info(f"{len(df)} symbol-month rows fetched")

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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--start-date", default="2014-01-01")
    parser.add_argument("--end-date", default=datetime.now(tz=None).date().isoformat())
    parser.add_argument("--min-cross-section", type=int, default=100)
    parser.add_argument("--beta-window", type=int, default=24)
    parser.add_argument("--vol-window", type=int, default=12)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run(args.start_date, args.end_date, args.min_cross_section, args.beta_window, args.vol_window)


if __name__ == "__main__":
    main()
