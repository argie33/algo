#!/usr/bin/env python3
"""
Fama-MacBeth cross-sectional regression harness for the Positioning pillar's A/D rating.

Built 2026-08-25 (goal: re-audit ALL stock_scores inputs without bias toward what already
shipped). A/D rating (35% weight, user-directed - see _score_positioning's docstring in
loaders/load_stock_scores.py) is a pure price/volume indicator (Chaikin Money Flow over a
20-day window, computed by loaders/technical_indicators.py::compute_ad_rating), so unlike
institutional_ownership_pct and short_interest_pct - both confirmed to have no real historical
depth in this database (institutional_holdings_13f: 1 row/symbol; short_interest_finra: only
2 months of real coverage, both checked directly 2026-08-25) - it's fully point-in-time-safe
and testable straight from price_daily's OHLCV columns.

Formula reconstructed exactly from compute_ad_rating (see that function's docstring for the
CMF methodology): Money Flow Multiplier = ((close-low)-(high-close))/(high-low) per day,
volume-weighted-averaged over 20 days into CMF in [-1,1], mapped to 50+50*cmf, then a +/-10
divergence nudge when the 20-day price return and CMF disagree in sign.

Usage:
    python -m algo.research.fama_macbeth_positioning_factors [options]
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

POSITIONING_FACTOR_COLS = ["ad_rating"]


def fetch_daily_ohlcv(start_date: str, end_date: str) -> pd.DataFrame:
    sql = """
        SELECT symbol, date, high, low, COALESCE(adj_close, close) AS close, volume
        FROM price_daily
        WHERE date >= %s AND date < %s
          AND COALESCE(adj_close, close) > 0
          AND high IS NOT NULL AND low IS NOT NULL AND volume IS NOT NULL
          AND COALESCE(data_unavailable, false) = false
        ORDER BY symbol, date
    """
    rows: list[tuple[str, object, float, float, float, float]] = []
    with DatabaseContext("read") as cur:
        cur.execute(sql, (start_date, end_date))
        while True:
            batch = cur.fetchmany(50000)
            if not batch:
                break
            rows.extend(batch)
    df = pd.DataFrame(rows, columns=["symbol", "date", "high", "low", "close", "volume"])
    for c in ["high", "low", "close", "volume"]:
        df[c] = df[c].astype(float)
    df["date"] = pd.to_datetime(df["date"])
    return df


def compute_ad_rating_series(daily: pd.DataFrame, window: int = 20) -> pd.Series:
    """Vectorized rolling reconstruction of compute_ad_rating, one value per (symbol, date)."""
    daily = daily.sort_values(["symbol", "date"]).copy()
    hl_diff = (daily["high"] - daily["low"]).replace(0, np.nan)
    mfm = ((daily["close"] - daily["low"]) - (daily["high"] - daily["close"])) / hl_diff
    mfv = mfm.fillna(0) * daily["volume"]

    g = daily.groupby("symbol")
    roll_mfv = mfv.groupby(daily["symbol"]).transform(lambda s: s.rolling(window).sum())
    roll_vol = daily["volume"].groupby(daily["symbol"]).transform(lambda s: s.rolling(window).sum())
    cmf = (roll_mfv / roll_vol).clip(-1.0, 1.0)
    base = 50.0 + 50.0 * cmf

    first_close = g["close"].transform(lambda s: s.shift(window - 1))
    price_return = (daily["close"] - first_close) / first_close

    nudge = pd.Series(0.0, index=daily.index)
    nudge[(price_return > 0) & (cmf < 0)] = -10.0
    nudge[(price_return < 0) & (cmf > 0)] = 10.0

    ad_rating = (base + nudge).clip(0.0, 100.0)
    ad_rating.index = pd.MultiIndex.from_arrays([daily["symbol"], daily["date"]])
    return ad_rating


def run(start_date: str, end_date: str, min_cross_section: int, horizon_months: int = 1) -> None:
    logger.info(f"Fetching daily OHLCV {start_date}..{end_date}")
    daily = fetch_daily_ohlcv(start_date, end_date)
    logger.info(f"{len(daily)} daily rows")

    ad_rating = compute_ad_rating_series(daily)
    daily = daily.set_index(["symbol", "date"])
    daily["ad_rating"] = ad_rating
    daily = daily.reset_index()

    daily["month"] = daily["date"].values.astype("datetime64[M]")
    monthly = daily.sort_values("date").groupby(["symbol", "month"], as_index=False).last()

    px = monthly.pivot(index="month", columns="symbol", values="close").sort_index()
    ad = monthly.pivot(index="month", columns="symbol", values="ad_rating").sort_index()
    months = px.index

    records: list[tuple[pd.Timestamp, pd.DataFrame]] = []
    for i in range(len(months) - horizon_months):
        fwd_ret = px.iloc[i + horizon_months] / px.iloc[i] - 1.0
        frame = pd.DataFrame({"ad_rating": ad.iloc[i], "fwd_ret": fwd_ret})
        frame = frame.replace([np.inf, -np.inf], np.nan).dropna()
        frame = frame[(frame["fwd_ret"] > -0.95) & (frame["fwd_ret"] < 5.0)]
        if len(frame) < min_cross_section:
            continue
        lo, hi = frame["ad_rating"].quantile([0.01, 0.99])
        frame["ad_rating"] = frame["ad_rating"].clip(lo, hi)
        std = frame["ad_rating"].std()
        frame["ad_rating"] = (frame["ad_rating"] - frame["ad_rating"].mean()) / std if std > 0 else 0.0
        records.append((months[i], frame))

    if not records:
        raise RuntimeError("No usable cross-sectional months")

    sizes = [len(f) for _, f in records]
    print(f"Usable cross-sectional months: {len(records)}  ({records[0][0]} to {records[-1][0]})")
    print(f"Median cross-section size: {int(np.median(sizes))}\n")

    print("=== Fama-MacBeth: A/D rating (Chaikin Money Flow) vs forward return ===")
    multi = _fama_macbeth(records, POSITIONING_FACTOR_COLS)
    for name, (mean, t) in multi.items():
        print(f"{name:12s} mean_coef={mean:10.5f}  t_stat={t:8.2f}  n_months={len(records)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--start-date", default="2015-06-01")
    parser.add_argument("--end-date", default=datetime.now(tz=None).date().isoformat())
    parser.add_argument("--min-cross-section", type=int, default=100)
    parser.add_argument("--horizon-months", type=int, default=1)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run(args.start_date, args.end_date, args.min_cross_section, args.horizon_months)


if __name__ == "__main__":
    main()
