#!/usr/bin/env python3
"""
Fama-MacBeth validation of 3 Risk-pillar candidates from the user's literature checklist that
were explicitly deprioritized as "lower-priority/exotic" earlier in this session's checklist
sweep (risk_idio_vol_downside_beta_operating_leverage_candidates.py's own directive skipped
these on scope grounds) - the user correctly called that deprioritization out as the same kind
of anchoring bias as everything else tested this session, so it's done here properly, not
skipped again.

Candidates (all built fresh from DAILY price_daily data, unlike the live Risk-4 controls which
are monthly - literature for all three is explicitly daily-return-based, and this repo's own
52-week-high/momentum candidates already established the "pull from price_daily for daily
granularity, sample at month-end" pattern this reuses):

1. Idiosyncratic skewness / MAX effect (Bali, Cakici & Whitelaw 2011; skewness construction also
   per Ang/Chen/Xing-style residualization): two variants computed from a trailing 252-trading-day
   window ending each month - (a) idio_skew: skewness of the market-residualized daily return
   over just the LAST 21 trading days of that window (the "trailing month" MAX-effect measurement
   period, using a longer window only to estimate a stable beta for residualizing), and (b)
   max_ret_21d: the simpler literature proxy, max raw daily return over the same last-21-day
   window (not residualized). Literature predicts BOTH negatively predict forward returns
   (investors overpay for lottery-like upside).
2. Coskewness (Harvey & Siddique 2000): standardized co-moment form
   coskew = mean[(r_i - mean(r_i)) * (r_m - mean(r_m))^2] / (std(r_i) * var(r_m)) over the full
   252-day window - equivalent in sign/interpretation to the regression-coefficient form, cheaper
   to compute at this scale. Literature predicts NEGATIVE coskewness earns a return premium (crash
   protection), i.e. this factor's sign should be negative in the FM regression.
3. CVaR / tail risk: mean of the worst 5% of daily returns over the same 252-day window - a
   direct left-tail severity measure distinct from symmetric volatility (live vol_60d) and from
   max_drawdown_1y (one specific worst episode, not the average severity of the whole left tail).

Same methodology as every sibling script in this file family: live-4 Risk controls
(vol/downside_vol/beta/max_dd) via fama_macbeth_price_factors.py's build_monthly_cross_sections
(monthly panel), new candidates merged in by month from a separately-fetched daily panel,
full-sample + half-split Fama-MacBeth (one cross-sectional OLS per month, coefficient series
averaged, month-count-limited t-stat).

Read-only research - does not touch any live scoring code.

Usage: python -m algo.research.risk_skewness_coskewness_cvar_candidates
"""

import argparse
import logging
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

from algo.research.fama_macbeth_price_factors import (
    FACTOR_COLS,
    _fama_macbeth,
    build_monthly_cross_sections,
    fetch_month_end_prices,
)
from utils.db.context import DatabaseContext

logger = logging.getLogger(__name__)

CANDIDATE_COLS = ["idio_skew", "max_ret_21d", "coskew", "cvar_5pct"]
DAILY_WINDOW = 252
SKEW_MAX_WINDOW = 21
MIN_DAILY_OBS = 200  # require most of a 252-day window to trust the estimate


def _zwinsor(s: pd.Series) -> pd.Series:
    lo, hi = s.quantile([0.01, 0.99])
    s = s.clip(lo, hi)
    std = s.std()
    return (s - s.mean()) / std if std and std > 0 else s * 0.0


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


def _skew(arr: np.ndarray[Any, Any]) -> Any:
    n = arr.shape[0]
    if n < 3:
        return np.nan
    mean = arr.mean(axis=0)
    diff = arr - mean
    var = (diff**2).mean(axis=0)
    std = np.sqrt(var)
    with np.errstate(invalid="ignore", divide="ignore"):
        m3 = (diff**3).mean(axis=0)
        return m3 / std**3


def run(start_date: str, end_date: str, min_cross_section: int, beta_window: int, vol_window: int) -> None:
    logger.info(f"Pulling monthly price panel {start_date}..{end_date} (live-4 controls)")
    px_m = fetch_month_end_prices(start_date, end_date).pivot(index="month", columns="symbol", values="px").sort_index()
    ret_m = px_m.pct_change(fill_method=None)
    months = ret_m.index

    logger.info("Building live-4-control monthly cross-sections")
    records = build_monthly_cross_sections(px_m, ret_m, beta_window, vol_window, min_cross_section)
    records_by_month = dict(records)

    logger.info(f"Fetching daily prices {start_date}..{end_date} (for skew/coskew/CVaR)")
    daily = fetch_daily_prices(start_date, end_date)
    logger.info(f"{len(daily)} daily rows")
    px_d = daily.pivot(index="date", columns="symbol", values="px").sort_index()
    ret_d = px_d.pct_change(fill_method=None)
    if "SPY" not in ret_d.columns:
        raise ValueError("SPY not present in daily price panel - required as the market factor")
    mkt_d = ret_d["SPY"]
    daily_dates = ret_d.index

    new_records: list[tuple[pd.Timestamp, pd.DataFrame]] = []
    for month in months:
        if month not in records_by_month:
            continue
        frame = records_by_month[month].copy()
        idx = frame.index

        # Position of this month-end within the DAILY index (last daily date <= month-end).
        # `month` comes from fetch_month_end_prices' pivot index, which is a plain
        # datetime.date (from Postgres date_trunc(...)::date, never pd.to_datetime'd) - cast to
        # Timestamp before searchsorted against daily_dates (a real DatetimeIndex).
        pos = daily_dates.searchsorted(pd.Timestamp(month), side="right") - 1
        if pos < DAILY_WINDOW:
            continue

        win = ret_d.iloc[pos - DAILY_WINDOW + 1 : pos + 1]
        mkt_win = mkt_d.iloc[pos - DAILY_WINDOW + 1 : pos + 1]
        obs_count = win.notna().sum()
        enough = obs_count >= MIN_DAILY_OBS

        # --- Beta over the full 252d window, for residualizing the last 21d only (idio_skew).
        mkt_var = mkt_win.var()
        beta = (
            win.apply(lambda col, m=mkt_win: col.cov(m)) / mkt_var
            if mkt_var and mkt_var > 0
            else pd.Series(np.nan, index=win.columns)
        )
        resid = win - pd.DataFrame(np.outer(mkt_win.values, beta.values), index=win.index, columns=win.columns)

        last21_resid = resid.iloc[-SKEW_MAX_WINDOW:]
        idio_skew = pd.Series(_skew(last21_resid.to_numpy()), index=win.columns)
        last21_raw = win.iloc[-SKEW_MAX_WINDOW:]
        max_ret_21d = last21_raw.max()

        # --- Coskewness (Harvey & Siddique 2000), standardized co-moment form, full 252d window.
        r_mean = win.mean()
        m_mean = mkt_win.mean()
        r_demeaned = win - r_mean
        m_demeaned_sq = (mkt_win - m_mean) ** 2
        numerator = r_demeaned.mul(m_demeaned_sq, axis=0).mean()
        r_std = win.std()
        m_var = mkt_win.var()
        with np.errstate(invalid="ignore", divide="ignore"):
            coskew = numerator / (r_std * m_var)

        # --- CVaR (worst 5% mean), full 252d window.
        q05 = win.quantile(0.05)
        cvar_5pct = win.where(win.le(q05, axis=1)).mean()

        for s, col in [
            (idio_skew, "idio_skew"),
            (max_ret_21d, "max_ret_21d"),
            (coskew, "coskew"),
            (cvar_5pct, "cvar_5pct"),
        ]:
            frame[col] = s.reindex(idx).where(enough.reindex(idx))

        frame = frame.replace([np.inf, -np.inf], np.nan)
        for col in CANDIDATE_COLS:
            avail = frame[col].notna()
            if avail.sum() >= min_cross_section:
                frame.loc[avail, col] = _zwinsor(frame.loc[avail, col])
            else:
                frame[col] = np.nan

        new_records.append((month, frame))

    print(f"Usable months: {len(new_records)} ({new_records[0][0]} to {new_records[-1][0]})")

    def _report(records_subset: list[tuple[pd.Timestamp, pd.DataFrame]], label: str) -> None:
        print(f"\n=== {label} ({records_subset[0][0]} to {records_subset[-1][0]}, {len(records_subset)}mo) ===")
        for candidate in CANDIDATE_COLS:
            sub = [(m, f.dropna(subset=[candidate])) for m, f in records_subset]
            sub = [(m, f) for m, f in sub if len(f) >= min_cross_section]
            if not sub:
                print(f"{candidate:20s} insufficient coverage")
                continue
            uni = _fama_macbeth(sub, [candidate])
            multi = _fama_macbeth(sub, [*FACTOR_COLS, candidate])
            _um, ut = uni[candidate]
            _mm, mt = multi[candidate]
            coverage = np.mean([len(f) for _, f in sub])
            print(
                f"{candidate:20s} univariate t={ut:6.2f}  multivariate(+live4) t={mt:6.2f}  "
                f"n_months={len(sub):3d}  avg_cross_section={coverage:.0f}"
            )

    _report(new_records, "FULL SAMPLE")
    split_idx = len(new_records) // 2
    _report(new_records[:split_idx], "FIRST HALF")
    _report(new_records[split_idx:], "SECOND HALF")


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
