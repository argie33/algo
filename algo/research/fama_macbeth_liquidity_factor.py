#!/usr/bin/env python3
"""
Fama-MacBeth cross-sectional regression harness for Amihud (2002) illiquidity.

Built 2026-08-26 to close the gap in liquidity_amihud_gap_flagged_not_implemented_20260825: an
ad hoc one-off analysis (not checked in, not re-runnable) found Amihud illiquidity - |monthly
return| / average daily dollar volume - to be a real, distinct signal (t=3.34 vs forward
1-month return, 126 months 2016-2026; correlation with log(market_cap) only -0.18) but was never
formalized into a permanent script, unlike stock_scores' 6 pillars and the price-factor family
in fama_macbeth_price_factors.py. This script is that formalization, using the same
methodology already established there (monthly two-pass Fama-MacBeth, not a pooled panel - see
that module's docstring for why pooled panels overstate significance).

Deliberately a STANDALONE script, not an extension of fama_macbeth_price_factors.py or
fama_macbeth_value_factors.py - both were being actively edited by a concurrent session for
unrelated Size-factor-promotion work when this was built, and this repo's own memory has
multiple documented incidents of concurrent-session edits to shared files clobbering real work.
A new, independent file with its own daily-panel fetch has zero collision surface.

Size/liquidity control: the original ad hoc check used log(market_cap) (from value_metrics, a
single-row-per-symbol snapshot - not point-in-time reconstructable here). This script instead
controls for log(trailing monthly average dollar volume), computed from the same price_daily
panel Amihud itself is built from - a real, standard liquidity-family control, though not
identical to a market-cap check. Both checks answer the same question ("is this just
re-measuring size/liquidity under another name?") via different available proxies; report both
so a future pass can reconcile them against a proper point-in-time market_cap panel if one gets
built.

Usage:
    python -m algo.research.fama_macbeth_liquidity_factor [options]

    --start-date DATE       Earliest daily price to pull (default: 2016-01-01)
    --end-date DATE         Latest daily price to pull (default: today)
    --min-cross-section N   Minimum symbols in a month's cross-section to use it (default: 100)
    --min-days-per-month N  Minimum trading days within a month to compute that symbol's
                             monthly Amihud value (default: 10)
"""

import argparse
import logging
from datetime import datetime

import numpy as np
import pandas as pd

from utils.db.context import DatabaseContext

logger = logging.getLogger(__name__)


def fetch_daily_panel(start_date: str, end_date: str) -> pd.DataFrame:
    """Daily (symbol, date, price, volume) panel - the raw input Amihud illiquidity is built
    from. Full price_daily history, not technical_data_daily (only ~3 months deep)."""
    sql = """
        SELECT symbol, date, COALESCE(adj_close, close) AS px, volume
        FROM price_daily
        WHERE date >= %s AND date < %s
          AND COALESCE(adj_close, close) > 0 AND volume > 0
          AND COALESCE(data_unavailable, false) = false
        ORDER BY symbol, date
    """
    with DatabaseContext("read") as cur:
        cur.execute(sql, (start_date, end_date))
        rows = cur.fetchall()
    df = pd.DataFrame(rows, columns=["symbol", "date", "px", "volume"])
    df["px"] = df["px"].astype(float)
    df["volume"] = df["volume"].astype(float)
    df["date"] = pd.to_datetime(df["date"])
    return df


def fetch_month_end_returns(start_date: str, end_date: str) -> pd.DataFrame:
    """One row per (symbol, month) = the last trading day's price that month - used only to
    compute the FORWARD month's return each symbol's Amihud value is tested against."""
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
    df["px"] = df["px"].astype(float)
    df["month"] = pd.PeriodIndex(pd.to_datetime(df["month"]), freq="M")
    return df


def compute_monthly_amihud(daily: pd.DataFrame, min_days_per_month: int) -> pd.DataFrame:
    """Per (symbol, month): mean(|daily return| / dollar volume) over that month's trading
    days, plus log(avg dollar volume) as a liquidity-family size control."""
    daily = daily.sort_values(["symbol", "date"]).copy()
    daily["month"] = daily["date"].dt.to_period("M")
    daily["ret"] = daily.groupby("symbol")["px"].pct_change()
    daily["dollar_vol"] = daily["px"] * daily["volume"]
    illiq = (daily["ret"].abs() / daily["dollar_vol"]).replace([np.inf, -np.inf], np.nan)
    daily["illiq"] = illiq

    monthly = (
        daily.groupby(["symbol", "month"])
        .agg(amihud=("illiq", "mean"), avg_dollar_vol=("dollar_vol", "mean"), n_days=("illiq", "count"))
        .reset_index()
    )
    monthly = monthly[monthly["n_days"] >= min_days_per_month].copy()
    monthly["log_dollar_vol"] = np.log(monthly["avg_dollar_vol"].clip(lower=1.0))
    return monthly[["symbol", "month", "amihud", "log_dollar_vol"]]


def build_monthly_records(
    monthly_amihud: pd.DataFrame, month_end_returns: pd.DataFrame, min_cross_section: int
) -> list[tuple[pd.Period, pd.DataFrame]]:
    """One winsorized, z-scored cross-section per month: this month's Amihud/log-dollar-volume
    vs. NEXT month's realized return (no lookahead - features are known before the return that
    tests them)."""
    px_pivot = month_end_returns.pivot(index="month", columns="symbol", values="px").sort_index()
    ret_pivot = px_pivot.pct_change(fill_method=None)
    months = ret_pivot.index

    amihud_by_month = {
        m: g.set_index("symbol")[["amihud", "log_dollar_vol"]] for m, g in monthly_amihud.groupby("month")
    }

    records = []
    for i in range(len(months) - 1):
        m = months[i]
        fwd_month = months[i + 1]
        if m not in amihud_by_month:
            continue

        frame = amihud_by_month[m].join(ret_pivot.loc[fwd_month].rename("fwd_ret"), how="inner")
        frame = frame.replace([np.inf, -np.inf], np.nan).dropna()
        # Drop pathological forward returns (data errors, not real single-month moves) -
        # same guard fama_macbeth_price_factors.py uses.
        frame = frame[(frame["fwd_ret"] > -0.95) & (frame["fwd_ret"] < 5.0)]
        if len(frame) < min_cross_section:
            continue

        for col in ["amihud", "log_dollar_vol"]:
            lo, hi = frame[col].quantile([0.01, 0.99])
            frame[col] = frame[col].clip(lo, hi)
            std = frame[col].std()
            frame[col] = (frame[col] - frame[col].mean()) / std if std > 0 else 0.0

        records.append((m, frame))
    return records


def _fama_macbeth(records: list[tuple[pd.Period, pd.DataFrame]], cols: list[str]) -> dict[str, tuple[float, float]]:
    """One cross-sectional OLS per month on `cols` (plus intercept), coefficient time series
    averaged with its own standard error - same two-pass method as fama_macbeth_price_factors.py."""
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


def run(start_date: str, end_date: str, min_cross_section: int, min_days_per_month: int) -> None:
    logger.info(f"Pulling daily price/volume panel {start_date}..{end_date}")
    daily = fetch_daily_panel(start_date, end_date)
    logger.info(f"{len(daily)} daily rows fetched, {daily['symbol'].nunique()} symbols")

    monthly_amihud = compute_monthly_amihud(daily, min_days_per_month)
    logger.info(f"{len(monthly_amihud)} symbol-months with a valid Amihud value")

    month_end_returns = fetch_month_end_returns(start_date, end_date)
    records = build_monthly_records(monthly_amihud, month_end_returns, min_cross_section)
    if not records:
        raise RuntimeError("No usable cross-sectional months - check date range / min_cross_section")

    sizes = [len(f) for _, f in records]
    print(f"Usable cross-sectional months: {len(records)}  ({records[0][0]} to {records[-1][0]})")
    print(f"Median cross-section size: {int(np.median(sizes))}\n")

    pooled = pd.concat([f for _, f in records])
    size_corr = pooled["amihud"].corr(pooled["log_dollar_vol"])
    print(f"Pooled correlation(amihud, log_dollar_vol) across all months: {size_corr:+.3f}")
    print("(distinct-signal check - not the same as the original log(market_cap) check, since")
    print(" market_cap isn't point-in-time reconstructable from price_daily alone; see module docstring)\n")

    print("=== Multivariate Fama-MacBeth (amihud, controlling for log_dollar_vol) ===")
    print(f"{'factor':16s} {'mean_coef':>10s} {'t_stat':>8s} {'n_months':>9s}")
    multi = _fama_macbeth(records, ["amihud", "log_dollar_vol"])
    for name, (mean, t) in multi.items():
        print(f"{name:16s} {mean:10.5f} {t:8.2f} {len(records):9d}")

    print("\n=== Univariate Fama-MacBeth (amihud alone) ===")
    uni = _fama_macbeth(records, ["amihud"])
    mean, t = uni["amihud"]
    print(f"{'amihud':16s} {mean:10.5f} {t:8.2f}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--start-date", default="2016-01-01")
    parser.add_argument("--end-date", default=datetime.now(tz=None).date().isoformat())
    parser.add_argument("--min-cross-section", type=int, default=100)
    parser.add_argument("--min-days-per-month", type=int, default=10)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run(args.start_date, args.end_date, args.min_cross_section, args.min_days_per_month)


if __name__ == "__main__":
    main()
