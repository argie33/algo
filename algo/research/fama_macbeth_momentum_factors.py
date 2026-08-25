#!/usr/bin/env python3
"""
Fama-MacBeth cross-sectional regression harness for the full Momentum pillar.

Built 2026-08-25 (goal: re-audit ALL stock_scores inputs, not just the ones already touched
today, without bias toward what's already shipped). Unlike
algo/research/fama_macbeth_price_factors.py (which only tested momentum_3m/6m/12m plus a
proper skip-month construction), this reconstructs the ENTIRE live Momentum pillar - RSI(14),
MACD sign, and price-vs-SMA(50/200) are all pure price-derived indicators, so they're fully
point-in-time-safe straight from price_daily's daily granularity, same as the return-window
factors. No third-party claim to verify here - these are mechanical indicator definitions
(RSI: Wilder 1978; MACD: Appel, standard 12/26/9 EMA convention), not anomaly claims, so the
"credible source" bar is just "does this match the standard formula everyone uses," not
literature replication.

Indicator conventions (standard, match this repo's _score_momentum usage):
- RSI(14): Wilder's smoothing (EWM with alpha=1/14 on gains/losses), the near-universal
  charting-platform convention.
- MACD: EMA(12) - EMA(26); scored by SIGN only here, matching _score_momentum's own
  documented reasoning (MACD's raw magnitude isn't comparable across price levels).
- SMA(50)/SMA(200): simple moving average; price_vs_sma = price/sma - 1.

Usage:
    python -m algo.research.fama_macbeth_momentum_factors [options]
    (same --start-date/--end-date/--min-cross-section args as the other harnesses)
"""

import argparse
import logging
from datetime import datetime

import numpy as np
import pandas as pd

from algo.research.fama_macbeth_price_factors import _fama_macbeth
from utils.db.context import DatabaseContext

logger = logging.getLogger(__name__)

MOMENTUM_FACTOR_COLS = [
    "mom_12_1",
    "mom_3m",
    "mom_6m",
    "mom_12m",
    "rsi_14",
    "macd_sign",
    "price_vs_sma_50",
    "price_vs_sma_200",
]


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
    """Compute RSI(14), MACD sign, and price-vs-SMA(50/200) per symbol."""
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

    ema12 = g.transform(lambda s: s.ewm(span=12, adjust=False).mean())
    ema26 = g.transform(lambda s: s.ewm(span=26, adjust=False).mean())
    macd_line = ema12 - ema26
    daily["macd_sign"] = np.sign(macd_line)

    sma50 = g.transform(lambda s: s.rolling(50).mean())
    sma200 = g.transform(lambda s: s.rolling(200).mean())
    daily["price_vs_sma_50"] = daily["px"] / sma50 - 1.0
    daily["price_vs_sma_200"] = daily["px"] / sma200 - 1.0

    return daily


def build_month_end_panel(daily_with_indicators: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (px, indicator_frames) - px is a month x symbol close matrix; indicator_frames
    is month x symbol for each of rsi_14/macd_sign/price_vs_sma_50/price_vs_sma_200."""
    d = daily_with_indicators.copy()
    d["month"] = d["date"].values.astype("datetime64[M]")
    d = d.sort_values("date").groupby(["symbol", "month"], as_index=False).last()

    px = d.pivot(index="month", columns="symbol", values="px").sort_index()
    indicators = {
        col: d.pivot(index="month", columns="symbol", values=col).sort_index()
        for col in ["rsi_14", "macd_sign", "price_vs_sma_50", "price_vs_sma_200"]
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

    for i in range(12, len(months) - 1):
        mom_12_1 = _trailing_cumret(px, i - 1, 11)
        mom_3m = _trailing_cumret(px, i, 3)
        mom_6m = _trailing_cumret(px, i, 6)
        mom_12m = _trailing_cumret(px, i, 12)
        fwd_ret = ret.iloc[i + 1]

        frame = pd.DataFrame(
            {
                "mom_12_1": mom_12_1,
                "mom_3m": mom_3m,
                "mom_6m": mom_6m,
                "mom_12m": mom_12m,
                "rsi_14": indicators["rsi_14"].iloc[i],
                "macd_sign": indicators["macd_sign"].iloc[i],
                "price_vs_sma_50": indicators["price_vs_sma_50"].iloc[i],
                "price_vs_sma_200": indicators["price_vs_sma_200"].iloc[i],
                "fwd_ret": fwd_ret,
            }
        )
        frame = frame.replace([np.inf, -np.inf], np.nan).dropna()
        frame = frame[(frame["fwd_ret"] > -0.95) & (frame["fwd_ret"] < 5.0)]
        if len(frame) < min_cross_section:
            continue

        for col in MOMENTUM_FACTOR_COLS:
            if col == "macd_sign":
                continue  # already a clean +/-1 signal, don't z-score a binary
            lo, hi = frame[col].quantile([0.01, 0.99])
            frame[col] = frame[col].clip(lo, hi)
            std = frame[col].std()
            frame[col] = (frame[col] - frame[col].mean()) / std if std > 0 else 0.0

        records.append((months[i], frame))

    return records


def run(start_date: str, end_date: str, min_cross_section: int) -> None:
    logger.info(f"Fetching daily prices {start_date}..{end_date}")
    daily = fetch_daily_prices(start_date, end_date)
    logger.info(f"{len(daily)} daily rows")

    logger.info("Computing RSI/MACD/SMA indicators")
    daily = compute_daily_indicators(daily)

    px, indicators = build_month_end_panel(daily)
    records = build_records(px, indicators, min_cross_section)
    if not records:
        raise RuntimeError("No usable cross-sectional months")

    sizes = [len(f) for _, f in records]
    print(f"Usable cross-sectional months: {len(records)}  ({records[0][0]} to {records[-1][0]})")
    print(f"Median cross-section size: {int(np.median(sizes))}\n")

    print("=== Multivariate Fama-MacBeth (full live Momentum-pillar input set, jointly) ===")
    print(f"{'factor':18s} {'mean_coef':>10s} {'t_stat':>8s} {'n_months':>9s}")
    multi = _fama_macbeth(records, MOMENTUM_FACTOR_COLS)
    for name, (mean, t) in multi.items():
        print(f"{name:18s} {mean:10.5f} {t:8.2f} {len(records):9d}")

    print("\n=== Univariate Fama-MacBeth (each factor alone) ===")
    print(f"{'factor':18s} {'mean_coef':>10s} {'t_stat':>8s}")
    for c in MOMENTUM_FACTOR_COLS:
        uni = _fama_macbeth(records, [c])
        mean, t = uni[c]
        print(f"{c:18s} {mean:10.5f} {t:8.2f}")


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
