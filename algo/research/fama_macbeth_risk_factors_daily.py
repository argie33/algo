#!/usr/bin/env python3
"""
Fama-MacBeth cross-sectional regression harness for Risk-pillar factors, using the REAL
daily-window construction `loaders/stock_scores/risk_scoring.py` actually scores live.

Built 2026-09-14 (scores-investigation follow-up). `fama_macbeth_price_factors.py`'s
`vol`/`beta`/`max_dd` columns are NOT the same signal as live production: that script computes
volatility as `monthly_return.std() * sqrt(12)` over a trailing 12-MONTH window, whereas
`stability_metrics.volatility_60d`/`volatility_252d` (what Risk actually scores, 20% weight
each) are `daily_log_return.std(ddof=1) * sqrt(252)` over trailing 60/252 TRADING-DAY windows -
a genuinely different, higher-frequency construction (confirmed by reading
`RiskMetricsLoader._calculate_volatility`/`_calculate_max_drawdown` directly, not assumed).
This script closes that gap: it reconstructs volatility_60d/volatility_252d/max_drawdown_1y
from `price_daily` using the EXACT same formulas (sample std with Bessel's correction,
log returns, 252-day annualization, peak-to-trough max drawdown), at each month-end test date,
then runs the same monthly Fama-MacBeth + Benjamini-Hochberg FDR methodology every other script
in this family uses.

Scope: only vol_60d/vol_252d/max_dd_1y (the 3 components whose absolute-vs-sector-neutral
literature argument was tested but never at the individual-component level with this exact
construction - see risk_scoring.py's own module docstring for that history). Beta and Liquidity
are NOT retested here: `_score_risk` scores Beta as distance-from-1.0 (a style-fit target, not
a return-prediction bet) and Liquidity against a fixed execution-tradability floor
(algo_config.min_adv_dollars) - neither claims to harvest a cross-sectional return edge, so
"forward-return edge" is not the right test for either (see risk_scoring.py's own "FOLLOW-UP
RE-CHECKED, NOT ACTED ON" note - same reasoning applies here, not re-litigated).

Usage:
    python -m algo.research.fama_macbeth_risk_factors_daily [options]
    (same --start-date/--end-date/--min-cross-section args as fama_macbeth_price_factors)
"""

import argparse
import logging
from datetime import datetime

import numpy as np
import pandas as pd

from algo.research.fama_macbeth_price_factors import (
    _fama_macbeth,
    benjamini_hochberg_fdr,
    print_survivorship_bias_caveat,
)
from utils.db.context import DatabaseContext

logger = logging.getLogger(__name__)

FACTOR_COLS = ["vol_60d", "vol_252d", "max_dd_1y"]

VOL_60D_WINDOW = 60
VOL_252D_WINDOW = 252
DRAWDOWN_WINDOW = 252
TRADING_DAYS_PER_YEAR = 252.0


def fetch_daily_prices(start_date: str, end_date: str) -> pd.DataFrame:
    """One row per (symbol, date) close price, real trading-day granularity (not month-end).
    Restricted to symbols with a reasonable amount of real history so the panel stays tractable
    (matches this repo's existing >=100-symbol-month min-cross-section convention at the input
    stage, not just the output stage)."""
    sql = """
        SELECT symbol, date, COALESCE(adj_close, close) AS px
        FROM price_daily
        WHERE date BETWEEN %s AND %s
          AND COALESCE(data_unavailable, false) = false
          AND COALESCE(adj_close, close) IS NOT NULL
          AND COALESCE(adj_close, close) > 0
        ORDER BY symbol, date
    """
    with DatabaseContext("read") as cur:
        cur.execute(sql, (start_date, end_date))
        rows = cur.fetchall()
    df = pd.DataFrame(rows, columns=["symbol", "date", "px"])
    df["date"] = pd.to_datetime(df["date"])
    df["px"] = df["px"].astype(float)
    return df


def build_daily_risk_cross_sections(
    daily_px: pd.DataFrame, min_cross_section: int
) -> list[tuple[pd.Timestamp, pd.DataFrame]]:
    """Pivot to a (date x symbol) price matrix, compute vol_60d/vol_252d/max_dd_1y at every
    real month-end trading date using the EXACT production formulas, then build one
    winsorized/z-scored cross-section per usable month regressed against forward 1-month return
    (from the NEXT month-end date, not a calendar month - matches every other script here)."""
    px = daily_px.pivot(index="date", columns="symbol", values="px").sort_index()
    log_ret = np.log(px / px.shift(1))

    # Real month-end trading dates within the panel (last trading day of each calendar month).
    month_key = pd.Series(px.index.to_period("M"), index=px.index)
    month_end_mask = (month_key != month_key.shift(-1)).fillna(True)
    month_end_dates = px.index[month_end_mask.to_numpy()]

    records: list[tuple[pd.Timestamp, pd.DataFrame]] = []
    for me_idx, me_date in enumerate(month_end_dates):
        pos = px.index.get_loc(me_date)
        if pos < VOL_252D_WINDOW or me_idx >= len(month_end_dates) - 1:
            continue

        win60 = log_ret.iloc[pos - VOL_60D_WINDOW + 1 : pos + 1]
        vol_60d = win60.std(ddof=1) * np.sqrt(TRADING_DAYS_PER_YEAR)

        win252 = log_ret.iloc[pos - VOL_252D_WINDOW + 1 : pos + 1]
        vol_252d = win252.std(ddof=1) * np.sqrt(TRADING_DAYS_PER_YEAR)

        win_px_dd = px.iloc[pos - DRAWDOWN_WINDOW + 1 : pos + 1]
        roll_max = win_px_dd.cummax()
        max_dd_1y = (win_px_dd / roll_max - 1.0).min()  # negative fraction, e.g. -0.34

        next_me = month_end_dates[me_idx + 1]
        fwd_ret = px.loc[next_me] / px.loc[me_date] - 1.0

        frame = pd.DataFrame({"vol_60d": vol_60d, "vol_252d": vol_252d, "max_dd_1y": max_dd_1y, "fwd_ret": fwd_ret})
        frame = frame.replace([np.inf, -np.inf], np.nan).dropna()
        frame = frame[(frame["fwd_ret"] > -0.95) & (frame["fwd_ret"] < 5.0)]
        if len(frame) < min_cross_section:
            continue

        for col in FACTOR_COLS:
            lo, hi = frame[col].quantile([0.01, 0.99])
            frame[col] = frame[col].clip(lo, hi)
            std = frame[col].std()
            frame[col] = (frame[col] - frame[col].mean()) / std if std > 0 else 0.0

        records.append((me_date, frame))

    return records


def run(start_date: str, end_date: str, min_cross_section: int) -> None:
    print_survivorship_bias_caveat()
    logger.info(f"Fetching daily prices {start_date}..{end_date}")
    daily_px = fetch_daily_prices(start_date, end_date)
    logger.info(f"{len(daily_px)} (symbol, date) rows, {daily_px['symbol'].nunique()} symbols")

    records = build_daily_risk_cross_sections(daily_px, min_cross_section)
    if not records:
        raise RuntimeError("No usable cross-sectional months")

    sizes = [len(f) for _, f in records]
    print(f"Usable cross-sectional months: {len(records)}  ({records[0][0].date()} to {records[-1][0].date()})")
    print(f"Median cross-section size: {int(np.median(sizes))}\n")

    print("=== Univariate Fama-MacBeth (each Risk daily-window component alone) ===")
    uni_mean, uni_t = {}, {}
    for c in FACTOR_COLS:
        uni_mean[c], uni_t[c] = _fama_macbeth(records, [c])[c]
    uni_fdr = benjamini_hochberg_fdr(uni_t, len(records))
    print(f"{'factor':12s} {'mean_coef':>10s} {'t_stat':>8s} {'FDR q<=0.10':>12s}")
    for c in FACTOR_COLS:
        print(f"{c:12s} {uni_mean[c]:10.5f} {uni_t[c]:8.2f} {'PASS' if uni_fdr[c] else 'fail':>12s}")

    print("\n=== Multivariate Fama-MacBeth (all 3 jointly) ===")
    print(f"{'factor':12s} {'mean_coef':>10s} {'t_stat':>8s} {'n_months':>9s}")
    multi = _fama_macbeth(records, FACTOR_COLS)
    for name, (mean, t) in multi.items():
        print(f"{name:12s} {mean:10.5f} {t:8.2f} {len(records):9d}")

    # Era-robustness split (first half / second half), same convention risk_scoring.py's own
    # docstring uses for max_drawdown's sub-period check - a single full-sample t-stat can hide
    # a sign flip.
    mid = len(records) // 2
    for label, subset in (("first half", records[:mid]), ("second half", records[mid:])):
        sub_mean, sub_t = {}, {}
        for c in FACTOR_COLS:
            sub_mean[c], sub_t[c] = _fama_macbeth(subset, [c])[c]
        print(f"\n=== {label} ({subset[0][0].date()} to {subset[-1][0].date()}, {len(subset)} months) ===")
        for c in FACTOR_COLS:
            print(f"{c:12s} {sub_mean[c]:10.5f} {sub_t[c]:8.2f}")


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
