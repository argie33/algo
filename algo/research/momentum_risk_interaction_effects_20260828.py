#!/usr/bin/env python3
"""
Fama-MacBeth interaction-term test for Momentum/Risk pillar candidates.

Built 2026-08-28 (goal: momentum/risk factor logic review). Every existing Fama-MacBeth
harness in this repo (fama_macbeth_momentum_factors.py, fama_macbeth_price_factors.py) tests
factors ADDITIVELY - each gets its own coefficient, summed. _score_momentum/_score_risk in
loaders/load_stock_scores.py mirror that: a flat weighted-sum of independently-scored inputs,
with no term for "what X means depends on Y." This script tests whether that's actually leaving
real signal on the table, for the two most concrete interaction candidates already flagged in
this repo's own history:

1. mom_12_1 x str_1m (short-term reversal conditional on long-term momentum): the
   _score_momentum docstring in load_stock_scores.py cites a double-sort finding that 1-month
   reversal is concentrated in LOW mom_12_1 names (-0.31 spread) while HIGH mom_12_1 names show
   continuation instead (+0.39 spread) - i.e. the same 1-month return predicts opposite things
   depending on 12-1 momentum. That's exactly what a linear interaction term is for. Never
   formally regression-tested before - the prior finding was a single double-sort, not
   confirmed via interaction coefficient + full-sample robustness.

2. mom_12_1 x vol_60d (the Barroso & Santa-Clara 2015, "Momentum Has Its Moments" effect):
   academic literature finds momentum's forward-return edge is weaker/riskier following
   high-volatility regimes. Momentum and Risk (Volatility 60d, 45% of that pillar) are this
   repo's two most price/vol-derived pillars and have never been tested against each other -
   directly in scope for a combined momentum+risk review.

Method: builds one combined daily-granularity panel (mom_12_1, str_1m, vol_60d, rsi_14, fwd_ret)
sampled at month-end, same winsorize/z-score/min-cross-section conventions as this repo's other
FM harnesses, then runs three specs per candidate: (a) additive-only (matches current scoring
architecture), (b) additive + interaction term, (c) interaction coefficient's own t-stat -
signal is only worth acting on if the interaction term itself clears significance ADDED ON TOP
of the additive terms, not just if the additive terms alone are significant (that would just
re-confirm what's already scored).
"""

import argparse
import logging
from datetime import datetime

import numpy as np
import pandas as pd

from utils.db.context import DatabaseContext

logger = logging.getLogger(__name__)


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


def compute_daily_indicators(daily: pd.DataFrame) -> pd.DataFrame:
    """RSI(14) and 60-trading-day annualized volatility, matching _score_momentum/_score_risk's
    own live inputs (rsi_14, volatility_60d)."""
    daily = daily.sort_values(["symbol", "date"])
    g = daily.groupby("symbol")["px"]

    delta = g.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.groupby(daily["symbol"]).transform(lambda s: s.ewm(alpha=1 / 14, adjust=False).mean())
    avg_loss = loss.groupby(daily["symbol"]).transform(lambda s: s.ewm(alpha=1 / 14, adjust=False).mean())
    rs = avg_gain / avg_loss.replace(0, np.nan)
    daily["rsi_14"] = 100 - (100 / (1 + rs))
    daily.loc[avg_loss == 0, "rsi_14"] = 100.0

    daily_ret = g.pct_change()
    daily["vol_60d"] = daily_ret.groupby(daily["symbol"]).transform(lambda s: s.rolling(60).std() * np.sqrt(252))

    return daily


def build_month_end_panel(daily_with_indicators: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    d = daily_with_indicators.copy()
    d["month"] = d["date"].values.astype("datetime64[M]")
    d = d.sort_values("date").groupby(["symbol", "month"], as_index=False).last()

    px = d.pivot(index="month", columns="symbol", values="px").sort_index()
    indicators = {
        col: d.pivot(index="month", columns="symbol", values=col).sort_index() for col in ["rsi_14", "vol_60d"]
    }
    return px, indicators


def _trailing_cumret(px: pd.DataFrame, end_idx: int, n_months: int) -> pd.Series:
    if end_idx - n_months < 0:
        return pd.Series(np.nan, index=px.columns)
    return px.iloc[end_idx] / px.iloc[end_idx - n_months] - 1.0


def build_records(
    px: pd.DataFrame, indicators: dict[str, pd.DataFrame], min_cross_section: int
) -> list[tuple[pd.Timestamp, pd.DataFrame]]:
    ret = px.pct_change(fill_method=None)
    months = px.index
    records: list[tuple[pd.Timestamp, pd.DataFrame]] = []

    for i in range(13, len(months) - 1):
        mom_12_1 = _trailing_cumret(px, i - 1, 11)
        str_1m = ret.iloc[i]
        fwd_ret = ret.iloc[i + 1]

        frame = pd.DataFrame(
            {
                "mom_12_1": mom_12_1,
                "str_1m": str_1m,
                "rsi_14": indicators["rsi_14"].iloc[i],
                "vol_60d": indicators["vol_60d"].iloc[i],
                "fwd_ret": fwd_ret,
            }
        )
        frame = frame.replace([np.inf, -np.inf], np.nan).dropna()
        frame = frame[(frame["fwd_ret"] > -0.95) & (frame["fwd_ret"] < 5.0)]
        if len(frame) < min_cross_section:
            continue

        for col in ["mom_12_1", "str_1m", "rsi_14", "vol_60d"]:
            lo, hi = frame[col].quantile([0.01, 0.99])
            frame[col] = frame[col].clip(lo, hi)
            std = frame[col].std()
            frame[col] = (frame[col] - frame[col].mean()) / std if std > 0 else 0.0

        frame["mom12_1_x_str1m"] = frame["mom_12_1"] * frame["str_1m"]
        frame["mom12_1_x_vol60d"] = frame["mom_12_1"] * frame["vol_60d"]

        records.append((months[i], frame))

    return records


def _fama_macbeth(records: list[tuple[pd.Timestamp, pd.DataFrame]], cols: list[str]) -> dict[str, tuple[float, float]]:
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


def _double_sort_table(records: list[tuple[pd.Timestamp, pd.DataFrame]], row_col: str, col_col: str) -> pd.DataFrame:
    """Mean forward return by (row_col tercile, col_col tercile), pooled across all months.
    Interpretability check alongside the interaction-coefficient regression above."""
    pooled = pd.concat([f[[row_col, col_col, "fwd_ret"]] for _m, f in records], ignore_index=True)
    pooled["row_t"] = pd.qcut(pooled[row_col], 3, labels=["low", "mid", "high"])
    pooled["col_t"] = pd.qcut(pooled[col_col], 3, labels=["low", "mid", "high"])
    return pooled.groupby(["row_t", "col_t"], observed=True)["fwd_ret"].mean().unstack() * 100


def run(start_date: str, end_date: str, min_cross_section: int) -> None:
    logger.info(f"Fetching daily prices {start_date}..{end_date}")
    daily = fetch_daily_prices(start_date, end_date)
    logger.info(f"{len(daily)} daily rows")

    daily = compute_daily_indicators(daily)
    px, indicators = build_month_end_panel(daily)
    records = build_records(px, indicators, min_cross_section)
    if not records:
        raise RuntimeError("No usable cross-sectional months")

    sizes = [len(f) for _, f in records]
    print(f"Usable cross-sectional months: {len(records)}  ({records[0][0]} to {records[-1][0]})")
    print(f"Median cross-section size: {int(np.median(sizes))}\n")

    print("=== Candidate 1: mom_12_1 x str_1m (reversal conditional on long-term momentum) ===")
    print("--- (a) additive only (current scoring architecture) ---")
    for name, (mean, t) in _fama_macbeth(records, ["mom_12_1", "str_1m"]).items():
        print(f"  {name:20s} {mean:10.5f}  t={t:6.2f}")
    print("--- (b) additive + interaction term ---")
    for name, (mean, t) in _fama_macbeth(records, ["mom_12_1", "str_1m", "mom12_1_x_str1m"]).items():
        print(f"  {name:20s} {mean:10.5f}  t={t:6.2f}")
    print("--- (c) double sort: mean fwd_ret% by (mom_12_1 tercile, str_1m tercile) ---")
    print(_double_sort_table(records, "mom_12_1", "str_1m").round(3))

    print("\n=== Candidate 2: mom_12_1 x vol_60d (Barroso & Santa-Clara momentum-crash effect) ===")
    print("--- (a) additive only (current scoring architecture) ---")
    for name, (mean, t) in _fama_macbeth(records, ["mom_12_1", "vol_60d"]).items():
        print(f"  {name:20s} {mean:10.5f}  t={t:6.2f}")
    print("--- (b) additive + interaction term ---")
    for name, (mean, t) in _fama_macbeth(records, ["mom_12_1", "vol_60d", "mom12_1_x_vol60d"]).items():
        print(f"  {name:20s} {mean:10.5f}  t={t:6.2f}")
    print("--- (c) double sort: mean fwd_ret% by (mom_12_1 tercile, vol_60d tercile) ---")
    print(_double_sort_table(records, "mom_12_1", "vol_60d").round(3))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--start-date", default="2015-06-01")
    parser.add_argument("--end-date", default=datetime.now(tz=None).date().isoformat())
    parser.add_argument("--min-cross-section", type=int, default=100)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run(args.start_date, args.end_date, args.min_cross_section)


if __name__ == "__main__":
    main()
