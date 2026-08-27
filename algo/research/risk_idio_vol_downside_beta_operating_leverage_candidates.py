#!/usr/bin/env python3
"""
Fama-MacBeth validation of 3 untested Risk-pillar candidates: idiosyncratic volatility,
downside beta, and operating leverage (degree of operating leverage).

Built 2026-08-27 (goal: literature-checklist sweep across all pillars, Risk's turn - unlike
Quality/Value/Growth, Risk has never gotten a systematic candidate-vs-literature pass). Reuses
fama_macbeth_price_factors.py's monthly panel construction (fetch_month_end_prices,
build_monthly_cross_sections, FACTOR_COLS, _fama_macbeth) for the live 4 controls
(vol/downside_vol/beta/max_dd - see loaders/load_stock_scores.py's _score_risk docstring for
why these 4 and what's already been tested/rejected here, e.g. downside_vol carries no
independent signal over vol, t=+1.39 wrong-signed controlled) and fama_macbeth_growth_factors.py's
fetch_annual_fundamentals/REPORTING_LAG_DAYS/merge_asof_monthly for the fundamentals-based
operating leverage candidate.

Read-only research - does not touch any live scoring code.

Usage: python -m algo.research.risk_idio_vol_downside_beta_operating_leverage_candidates
"""

import argparse
import logging
from datetime import datetime

import numpy as np
import pandas as pd

from algo.research.fama_macbeth_growth_factors import (
    REPORTING_LAG_DAYS,
    fetch_annual_fundamentals,
    merge_asof_monthly,
)
from algo.research.fama_macbeth_price_factors import (
    FACTOR_COLS,
    _fama_macbeth,
    build_monthly_cross_sections,
    fetch_month_end_prices,
)

logger = logging.getLogger(__name__)

DOWNSIDE_BETA_WINDOW = 36  # months - needs enough down-market months to be estimable
DOWNSIDE_BETA_MIN_DOWN_MONTHS = 8


def _zwinsor(s: pd.Series) -> pd.Series:
    lo, hi = s.quantile([0.01, 0.99])
    s = s.clip(lo, hi)
    std = s.std()
    return (s - s.mean()) / std if std and std > 0 else s * 0.0


def build_operating_leverage_panel() -> pd.DataFrame:
    fund = fetch_annual_fundamentals().sort_values(["symbol", "fiscal_year"]).reset_index(drop=True)
    g = fund.groupby("symbol", group_keys=False)
    rev_pct = g["revenue"].pct_change()
    oi_pct = g["operating_income"].pct_change()
    # Guard near-zero revenue-growth denominators (DOL blows up / sign is meaningless there) -
    # same "don't extrapolate from a degenerate ratio" convention this repo applies elsewhere
    # (e.g. quality_metrics's |ratio|>1000 bounds).
    valid = rev_pct.abs() > 0.01
    dol = pd.Series(np.nan, index=fund.index)
    dol[valid] = oi_pct[valid] / rev_pct[valid]
    out = fund[["symbol", "fiscal_year"]].copy()
    out["operating_leverage"] = dol
    out["known_date"] = pd.to_datetime(fund["fiscal_year"].astype(str) + "-12-31") + pd.Timedelta(
        days=REPORTING_LAG_DAYS
    )
    return out.dropna(subset=["operating_leverage", "known_date"])


def run(start_date: str, end_date: str, min_cross_section: int, beta_window: int, vol_window: int) -> None:
    logger.info(f"Pulling month-end price panel {start_date}..{end_date}")
    df = fetch_month_end_prices(start_date, end_date)
    px = df.pivot(index="month", columns="symbol", values="px").sort_index()
    ret = px.pct_change(fill_method=None)
    mkt = ret["SPY"]
    months = ret.index

    logger.info("Building live-4-control monthly cross-sections")
    records = build_monthly_cross_sections(px, ret, beta_window, vol_window, min_cross_section)
    records_by_month = dict(records)

    logger.info("Building operating_leverage panel (annual fundamentals, point-in-time)")
    ol_fund = build_operating_leverage_panel()
    ol_monthly = merge_asof_monthly(months, ol_fund, cols=["operating_leverage"])

    new_records: list[tuple[pd.Timestamp, pd.DataFrame]] = []
    for i, month in enumerate(months):
        if month not in records_by_month:
            continue
        frame = records_by_month[month].copy()
        idx = frame.index  # symbols surviving the live-4 build (already dropna'd on those 4 + fwd_ret)

        # --- Idiosyncratic volatility: residual stdev after removing a LOCAL (vol_window)
        # CAPM beta, distinct from the live 24mo beta used for the "beta" control. Ang, Hodrick,
        # Xing & Zhang (2006).
        win = ret.iloc[i - vol_window + 1 : i + 1]
        mkt_win = mkt.iloc[i - vol_window + 1 : i + 1]
        mkt_var = mkt_win.var()
        local_beta = (
            win.apply(lambda col, m=mkt_win: col.cov(m)) / mkt_var
            if mkt_var and mkt_var > 0
            else pd.Series(np.nan, index=win.columns)
        )
        resid = win - pd.DataFrame(np.outer(mkt_win.values, local_beta.values), index=win.index, columns=win.columns)
        idio_vol = resid.std() * np.sqrt(12)

        # --- Downside beta: covariance/variance restricted to down-market months only, over a
        # longer window (down months are a minority of any window). Ang, Chen & Xing (2006).
        if i >= DOWNSIDE_BETA_WINDOW:
            win_db = ret.iloc[i - DOWNSIDE_BETA_WINDOW + 1 : i + 1]
            mkt_db = mkt.iloc[i - DOWNSIDE_BETA_WINDOW + 1 : i + 1]
            down_mask = mkt_db < 0
            if down_mask.sum() >= DOWNSIDE_BETA_MIN_DOWN_MONTHS:
                mkt_down = mkt_db[down_mask]
                win_down = win_db[down_mask]
                mkt_down_var = mkt_down.var()
                downside_beta = (
                    win_down.apply(lambda col, m=mkt_down: col.cov(m)) / mkt_down_var
                    if mkt_down_var and mkt_down_var > 0
                    else pd.Series(np.nan, index=win_db.columns)
                )
            else:
                downside_beta = pd.Series(np.nan, index=win_db.columns)
        else:
            downside_beta = pd.Series(np.nan, index=ret.columns)

        frame["idio_vol"] = idio_vol.reindex(idx)
        frame["downside_beta"] = downside_beta.reindex(idx)
        if month in ol_monthly:
            frame["operating_leverage"] = ol_monthly[month]["operating_leverage"].reindex(idx)
        else:
            frame["operating_leverage"] = np.nan

        frame = frame.replace([np.inf, -np.inf], np.nan)
        for col in ["idio_vol", "downside_beta", "operating_leverage"]:
            avail = frame[col].notna()
            if avail.sum() >= min_cross_section:
                frame.loc[avail, col] = _zwinsor(frame.loc[avail, col])
            else:
                frame[col] = np.nan

        new_records.append((month, frame))

    print(f"Usable months: {len(new_records)} ({new_records[0][0]} to {new_records[-1][0]})")

    def _report(records_subset: list[tuple[pd.Timestamp, pd.DataFrame]], label: str) -> None:
        print(f"\n=== {label} ({records_subset[0][0]} to {records_subset[-1][0]}, {len(records_subset)}mo) ===")
        for candidate in ["idio_vol", "downside_beta", "operating_leverage"]:
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
