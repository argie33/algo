#!/usr/bin/env python3
"""Fama-MacBeth + era-robustness verification for Amihud (2002) illiquidity, using the EXACT
live production construction `RiskMetricsLoader._calculate_amihud_illiquidity` computes
(mean(|daily log return| / dollar volume) over a trailing window - see that method's own
docstring for the full citation).

Built 2026-09-17 (factor-purity sweep follow-up). risk_scoring.py's own module docstring
records a single ad hoc test from 2026-08-25 (t=3.34, positive, 126 months) that was never
run through this repo's own required verification bar for a NEW scored factor - multi-block
era-robustness and FDR correction (see the WEIGHT-REVISION GOVERNANCE POLICY in
loaders/stock_scores/pillar_weights.py: "mandatory disjoint holdout, FDR correction for
multi-candidate screens"). This script closes that gap before any live scoring weight is
assigned - a genuine re-verification, not a repeat of the same ad hoc number.

Amihud illiquidity is heavily right-skewed (a near-zero-volume day can be orders of magnitude
larger than a typical day) - log-transformed before winsorizing/z-scoring, the same treatment
this repo's own log_dvol candidate already applies to raw dollar volume in
fama_macbeth_price_factors.py's build_new_candidate_cross_sections.
"""

import argparse
import logging
from datetime import datetime

import numpy as np
import pandas as pd

from algo.research.fama_macbeth_price_factors import (
    _fama_macbeth,
    benjamini_hochberg_fdr,
    multi_split_era_robustness,
    print_survivorship_bias_caveat,
)
from utils.db.context import DatabaseContext

logger = logging.getLogger(__name__)

AMIHUD_WINDOW_DAYS = 21  # ~1 trading month, matching the trailing-window convention every
# other monthly-panel script in this family uses (fetch_trailing_dollar_volume's own 20-day
# window, rounded to a full trading month for a monthly-frequency panel).


def fetch_daily_prices_and_volume(start_date: str, end_date: str) -> pd.DataFrame:
    """One row per (symbol, date): close price and volume, real trading-day granularity."""
    sql = """
        SELECT symbol, date, COALESCE(adj_close, close) AS px, volume
        FROM price_daily
        WHERE date BETWEEN %s AND %s
          AND COALESCE(data_unavailable, false) = false
          AND COALESCE(adj_close, close) IS NOT NULL
          AND COALESCE(adj_close, close) > 0
          AND volume IS NOT NULL
        ORDER BY symbol, date
    """
    with DatabaseContext("read") as cur:
        cur.execute(sql, (start_date, end_date))
        rows = cur.fetchall()
    df = pd.DataFrame(rows, columns=["symbol", "date", "px", "volume"])
    df["date"] = pd.to_datetime(df["date"])
    df["px"] = df["px"].astype(float)
    df["volume"] = df["volume"].astype(float)
    return df


def build_amihud_cross_sections(daily: pd.DataFrame, min_cross_section: int) -> list[tuple[pd.Timestamp, pd.DataFrame]]:
    """Pivot to (date x symbol) price/volume matrices, compute trailing-21-day Amihud
    illiquidity at every real month-end trading date using the same
    mean(|log return| / dollar volume) construction as the live production code, then build
    one winsorized/z-scored (on log(amihud)) cross-section per usable month regressed against
    forward 1-month return."""
    px = daily.pivot(index="date", columns="symbol", values="px").sort_index()
    volume = daily.pivot(index="date", columns="symbol", values="volume").sort_index()
    log_ret = np.log(px / px.shift(1))
    dollar_volume = px * volume
    daily_illiquidity = log_ret.abs() / dollar_volume.replace(0, np.nan)

    month_key = pd.Series(px.index.to_period("M"), index=px.index)
    month_end_mask = (month_key != month_key.shift(-1)).fillna(True)
    month_end_dates = px.index[month_end_mask.to_numpy()]

    records: list[tuple[pd.Timestamp, pd.DataFrame]] = []
    for me_idx, me_date in enumerate(month_end_dates):
        pos = px.index.get_loc(me_date)
        if pos < AMIHUD_WINDOW_DAYS or me_idx >= len(month_end_dates) - 1:
            continue

        window = daily_illiquidity.iloc[pos - AMIHUD_WINDOW_DAYS + 1 : pos + 1]
        amihud = window.mean(skipna=True)
        # Real Amihud, not log yet - require at least half the window's days to have a valid
        # reading (same "don't extrapolate off a handful of days" principle every pillar in
        # this repo already applies), then log-transform for the heavily right-skewed scale.
        valid_days = window.notna().sum()
        amihud = amihud.where(valid_days >= AMIHUD_WINDOW_DAYS // 2)
        log_amihud = np.log(amihud.where(amihud > 0))

        next_me = month_end_dates[me_idx + 1]
        fwd_ret = px.loc[next_me] / px.loc[me_date] - 1.0

        frame = pd.DataFrame({"log_amihud": log_amihud, "fwd_ret": fwd_ret})
        frame = frame.replace([np.inf, -np.inf], np.nan).dropna()
        frame = frame[(frame["fwd_ret"] > -0.95) & (frame["fwd_ret"] < 5.0)]
        if len(frame) < min_cross_section:
            continue

        lo, hi = frame["log_amihud"].quantile([0.01, 0.99])
        frame["log_amihud"] = frame["log_amihud"].clip(lo, hi)
        std = frame["log_amihud"].std()
        frame["log_amihud"] = (frame["log_amihud"] - frame["log_amihud"].mean()) / std if std > 0 else 0.0

        records.append((me_date, frame))

    return records


def run(start_date: str, end_date: str, min_cross_section: int) -> None:
    print_survivorship_bias_caveat()
    logger.info(f"Fetching daily prices+volume {start_date}..{end_date}")
    daily = fetch_daily_prices_and_volume(start_date, end_date)
    logger.info(f"{len(daily)} (symbol, date) rows, {daily['symbol'].nunique()} symbols")

    records = build_amihud_cross_sections(daily, min_cross_section)
    if not records:
        raise RuntimeError("No usable cross-sectional months")

    sizes = [len(f) for _, f in records]
    print(f"Usable cross-sectional months: {len(records)}  ({records[0][0].date()} to {records[-1][0].date()})")
    print(f"Median cross-section size: {int(np.median(sizes))}\n")

    mean, t = _fama_macbeth(records, ["log_amihud"])["log_amihud"]
    fdr = benjamini_hochberg_fdr({"log_amihud": t}, len(records))
    print("=== Full-sample univariate Fama-MacBeth (log(Amihud illiquidity)) ===")
    print(f"mean_coef={mean:.6f}  t_stat={t:.2f}  FDR q<=0.10: {'PASS' if fdr['log_amihud'] else 'fail'}")

    print("\n=== Multi-split era robustness (4-block chronological split) ===")
    robustness = multi_split_era_robustness(records, ["log_amihud"], n_splits=4)["log_amihud"]
    print(f"per-block t-stats: {[round(x, 2) for x in robustness.t_stats]}")
    print(f"sign agrees across all valid blocks: {robustness.sign_agrees_across_blocks}")
    print(f"blocks clearing |t|>=1.5: {robustness.blocks_clearing_1_5}/{robustness.n_blocks}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--start-date", default="2017-01-01")
    parser.add_argument("--end-date", default=datetime.now(tz=None).date().isoformat())
    parser.add_argument("--min-cross-section", type=int, default=100)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run(args.start_date, args.end_date, args.min_cross_section)


if __name__ == "__main__":
    main()
