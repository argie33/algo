#!/usr/bin/env python3
"""
Fama-MacBeth validation for 3 new PRICE/VOLUME-only Momentum candidates never tested in this
repo before, plus a re-run of the already-built str_1m short-term-reversal factor
(algo/research/fama_macbeth_price_factors.py's FACTOR_COLS already includes str_1m - full-sample
t=-1.32 univariate/-0.83 multivariate, first-half t=-1.53/-1.50, second-half t=-0.42/+0.70 -
NULL, sign-flips in the second half, not re-implemented here, just recorded for the combined
verdict).

Candidates built fresh here (all point-in-time-safe from price_daily/company_profile, no
look-ahead):
1. 52-week-high proximity (George & Hwang 2004): close / trailing-252-trading-day rolling max
   close, computed from daily data (unlike technical_data_daily's ~3-month window, price_daily
   has full history - same reasoning as fama_macbeth_momentum_factors.py's own use of it).
2. Industry momentum (Moskowitz & Grinblatt 1999): leave-one-out average trailing 6-month
   return of a symbol's company_profile.sector peers, tested as a predictor of the SYMBOL's own
   forward return (not the peer group's).
3. Residual momentum (Blitz, Huij & Martens 2011): mom_12_1 with the market-beta component
   stripped - trailing 12-1 return minus (beta * SPY's own trailing 12-1 return), beta from a
   trailing 24-month window (same convention as fama_macbeth_price_factors.py's beta_window).

Same Fama-MacBeth methodology as every sibling script in this file family: one cross-sectional
OLS per month (const + candidates), coefficient time series averaged, t-stat from its own
month-count-limited standard error - not a pooled-panel correlation. Full-sample + a half-split
robustness check (same repo-wide bar: |t|>2 full sample, no sign flip across the split) built
in directly rather than requiring two separate CLI runs.

Usage:
    python -m algo.research.momentum_52wk_industry_residual_reversal_candidates [options]
"""

import argparse
import logging
from datetime import datetime

import numpy as np
import pandas as pd

from algo.research.fama_macbeth_price_factors import _fama_macbeth
from utils.db.context import DatabaseContext

logger = logging.getLogger(__name__)

CANDIDATE_COLS = ["high_52w_proximity", "industry_mom_6m", "residual_mom_12_1"]


def fetch_daily_prices(start_date: str, end_date: str) -> pd.DataFrame:
    sql = """
        SELECT symbol, date, COALESCE(adj_close, close) AS px
        FROM price_daily
        WHERE date >= %s AND date < %s
          AND COALESCE(adj_close, close) > 0
          AND COALESCE(data_unavailable, false) = false
        ORDER BY symbol, date
    """
    rows: list[tuple[str, object, float]] = []
    with DatabaseContext("read") as cur:
        cur.execute(sql, (start_date, end_date))
        while True:
            batch = cur.fetchmany(50000)
            if not batch:
                break
            rows.extend(batch)
    df = pd.DataFrame(rows, columns=["symbol", "date", "px"])
    df["px"] = df["px"].astype(float)
    df["date"] = pd.to_datetime(df["date"])
    return df


def fetch_sectors() -> pd.Series:
    sql = "SELECT symbol, sector FROM company_profile WHERE sector IS NOT NULL AND sector <> ''"
    with DatabaseContext("read") as cur:
        cur.execute(sql)
        rows = cur.fetchall()
    df = pd.DataFrame(rows, columns=["symbol", "sector"])
    return df.set_index("symbol")["sector"]


def build_month_end_panel(daily: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Returns (px, high_52w_proximity) - both month x symbol matrices. high_52w_proximity is
    computed on DAILY granularity (252 trading days) then sampled at month-end, matching
    George & Hwang's own daily-close construction rather than approximating from monthly data."""
    d = daily.sort_values(["symbol", "date"]).copy()
    g = d.groupby("symbol")["px"]
    roll_max_252 = g.transform(lambda s: s.rolling(252, min_periods=200).max())
    d["high_52w_proximity"] = d["px"] / roll_max_252

    d["month"] = d["date"].values.astype("datetime64[M]")
    month_end = d.sort_values("date").groupby(["symbol", "month"], as_index=False).last()

    px = month_end.pivot(index="month", columns="symbol", values="px").sort_index()
    prox = month_end.pivot(index="month", columns="symbol", values="high_52w_proximity").sort_index()
    return px, prox


def _trailing_cumret(px: pd.DataFrame, end_idx: int, n_months: int) -> pd.Series:
    if end_idx - n_months < 0:
        return pd.Series(np.nan, index=px.columns)
    with np.errstate(divide="ignore", invalid="ignore"):
        return px.iloc[end_idx] / px.iloc[end_idx - n_months] - 1.0


def build_records(
    px: pd.DataFrame, prox: pd.DataFrame, sectors: pd.Series, beta_window: int, min_cross_section: int
) -> list[tuple[pd.Timestamp, pd.DataFrame]]:
    ret = px.pct_change(fill_method=None)
    if "SPY" not in ret.columns:
        raise ValueError("SPY not present in price panel - required as the market factor")
    mkt = ret["SPY"]
    months = px.index
    sym_sector = sectors.reindex(px.columns)
    records: list[tuple[pd.Timestamp, pd.DataFrame]] = []

    for i in range(max(12, beta_window), len(months) - 1):
        mom_12_1 = _trailing_cumret(px, i - 1, 11)
        mom_6m = _trailing_cumret(px, i, 6)

        # Industry momentum: leave-one-out sector-average trailing 6m return.
        sector_frame = pd.DataFrame({"sector": sym_sector, "mom_6m": mom_6m})
        grp = sector_frame.groupby("sector")["mom_6m"]
        sector_sum = grp.transform("sum")
        sector_n = grp.transform("count")
        loo_avg = (sector_sum - sector_frame["mom_6m"]) / (sector_n - 1).replace(0, np.nan)
        industry_mom_6m = loo_avg.reindex(px.columns)

        # Residual momentum: mom_12_1 with the market-beta component stripped, beta from a
        # trailing `beta_window`-month window (mirrors fama_macbeth_price_factors.py exactly).
        winb = ret.iloc[i - beta_window + 1 : i + 1]
        mkt_win = mkt.iloc[i - beta_window + 1 : i + 1]
        mkt_var = mkt_win.var()
        beta = winb.apply(lambda col, m=mkt_win: col.cov(m)) / mkt_var if mkt_var and mkt_var > 0 else np.nan
        mkt_mom_12_1 = _trailing_cumret(px[["SPY"]], i - 1, 11)["SPY"]
        residual_mom_12_1 = mom_12_1 - beta * mkt_mom_12_1

        fwd_ret = ret.iloc[i + 1]

        frame = pd.DataFrame(
            {
                "high_52w_proximity": prox.iloc[i],
                "industry_mom_6m": industry_mom_6m,
                "residual_mom_12_1": residual_mom_12_1,
                "mom_12_1": mom_12_1,  # control, matches live composite's strongest input
                "fwd_ret": fwd_ret,
            }
        )
        frame = frame.drop(index=["SPY"], errors="ignore")
        frame = frame.replace([np.inf, -np.inf], np.nan).dropna()
        frame = frame[(frame["fwd_ret"] > -0.95) & (frame["fwd_ret"] < 5.0)]
        if len(frame) < min_cross_section:
            continue

        for col in [*CANDIDATE_COLS, "mom_12_1"]:
            lo, hi = frame[col].quantile([0.01, 0.99])
            frame[col] = frame[col].clip(lo, hi)
            std = frame[col].std()
            frame[col] = (frame[col] - frame[col].mean()) / std if std > 0 else 0.0

        records.append((months[i], frame))

    return records


def _print_block(label: str, records: list[tuple[pd.Timestamp, pd.DataFrame]]) -> None:
    print(f"\n=== {label} ({len(records)} months) ===")
    print(f"{'factor':22s} {'uni_t':>8s} {'multi_t':>8s} {'multi_ctrl_mom_t':>18s}")
    for c in CANDIDATE_COLS:
        uni = _fama_macbeth(records, [c])
        multi = _fama_macbeth(records, [c, "mom_12_1"])
        print(f"{c:22s} {uni[c][1]:8.2f} {multi[c][1]:8.2f} {multi['mom_12_1'][1]:18.2f}")


def run(start_date: str, end_date: str, min_cross_section: int, beta_window: int) -> None:
    logger.info(f"Fetching daily prices {start_date}..{end_date}")
    daily = fetch_daily_prices(start_date, end_date)
    logger.info(f"{len(daily)} daily rows")
    sectors = fetch_sectors()
    logger.info(f"{len(sectors)} symbols with a sector")

    px, prox = build_month_end_panel(daily)
    records = build_records(px, prox, sectors, beta_window, min_cross_section)
    if not records:
        raise RuntimeError("No usable cross-sectional months")

    sizes = [len(f) for _, f in records]
    print(f"Usable cross-sectional months: {len(records)}  ({records[0][0]} to {records[-1][0]})")
    print(f"Median cross-section size: {int(np.median(sizes))}")

    _print_block("FULL SAMPLE", records)
    split = len(records) // 2
    _print_block(f"FIRST HALF ({records[0][0]} to {records[split - 1][0]})", records[:split])
    _print_block(f"SECOND HALF ({records[split][0]} to {records[-1][0]})", records[split:])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--start-date", default="2014-01-01")
    parser.add_argument("--end-date", default=datetime.now(tz=None).date().isoformat())
    parser.add_argument("--min-cross-section", type=int, default=100)
    parser.add_argument("--beta-window", type=int, default=24)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run(args.start_date, args.end_date, args.min_cross_section, args.beta_window)


if __name__ == "__main__":
    main()
