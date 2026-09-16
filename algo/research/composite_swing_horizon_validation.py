#!/usr/bin/env python3
"""
Re-validates composite pillar weighting/scaling/momentum-construction candidates against a
forward return horizon that actually matches this system's real swing-trading target, built
2026-09-15 (/goal session). Every composite-weight test run earlier this session
(composite_weights_shrinkage_optimal.py, composite_weights_candidate_comparison.py,
composite_ibd_style_construction.py, composite_gate_vs_blend_topdecile.py) inherited
build_pillar_proxy_records()'s fwd_ret = next CALENDAR MONTH's return (~21 trading days) from
the wider fama_macbeth_* research family, which built that convention for long-horizon factor
validation, not for this system specifically.

Live-verified this session (not assumed): `algo/infrastructure/config_schema.py` sets
max_hold_days default=20 (trading days), and industry-standard "swing trading" is independently
defined (verified via WebSearch) as roughly 2-20 trading days - a real, load-bearing target this
system's own config already encodes. ~21 calendar days is close to 20 trading days but not the
same thing (21 calendar days spans ~15 trading days after weekends/holidays) - this script fixes
that by computing the forward return over an EXACT 20-TRADING-DAY window from each month-end
snapshot date, using daily price_daily data, instead of reusing the monthly-panel's next-row
return.

SCOPE NOTE (user directive, 2026-09-15): this does NOT attempt to condition on the real
buy_sell_daily breakout signal - that table only has ~3 months of history, nowhere near enough
for a multi-year holdout, and the user has explicitly said to trust the signal system as-is and
focus exclusively on the composite score's own standalone quality. This script answers "does
this candidate rank quality better over the actual 20-trading-day swing horizon," not "does it
improve the full breakout-then-rank production pipeline" - a scoped, honest boundary.

Reuses build_pillar_proxy_records()'s raw (pre-standardization) growth/value/quality/stability
proxies unchanged - only the forward-return target and (for momentum) the construction are
corrected. Same true-holdout discipline as every other script this session: fit is never reused
for holdout evaluation, holdout years (2022-2026) are evaluated independently, era-robustness
bar is beating the worst year, not the average.

Usage:
    python -m algo.research.composite_swing_horizon_validation [options]
"""

import argparse
import logging
from datetime import datetime

import numpy as np
import pandas as pd
from scipy import stats

from algo.research.fama_macbeth_composite_weights import PILLAR_COLS, build_pillar_proxy_records
from algo.research.fama_macbeth_momentum_factors import fetch_daily_prices
from algo.research.fama_macbeth_price_factors import print_survivorship_bias_caveat
from loaders.load_stock_scores import BASE_PILLAR_WEIGHTS

logger = logging.getLogger(__name__)

SWING_HORIZON_TRADING_DAYS = 20  # matches algo/infrastructure/config_schema.py max_hold_days default


def compute_20td_forward_returns(start_date: str, end_date: str, month_ends: list[pd.Timestamp]) -> pd.DataFrame:
    """For each month-end snapshot date, returns a long DataFrame [month, symbol, fwd_ret_20td] -
    the return from the first trading day ON OR AFTER that month-end to the trading day
    SWING_HORIZON_TRADING_DAYS later, using real daily price_daily data (not the monthly panel's
    next-row return)."""
    logger.info("Fetching daily prices for 20-trading-day forward return reconstruction")
    daily = fetch_daily_prices(start_date, end_date)
    px = daily.pivot(index="date", columns="symbol", values="px").sort_index()
    px.index = pd.to_datetime(px.index)
    dates = px.index

    rows = []
    for month_end in month_ends:
        # build_pillar_proxy_records' "month" label is date_trunc('month', date) - the FIRST
        # calendar day of the month - even though the actual price/fundamentals snapshot it's
        # attached to is the LAST real trading day of that same month (see
        # fama_macbeth_price_factors.fetch_month_end_prices). Resolve the real last-trading-day
        # index first (last daily date strictly before the next month starts), THEN start the
        # forward window the trading day after that - anything else silently overlaps the
        # window with the very month the score was computed from (look-ahead, not prediction).
        next_month_start = pd.Timestamp(month_end) + pd.DateOffset(months=1)
        real_month_end_idx = dates.searchsorted(next_month_start, side="left") - 1
        idx = real_month_end_idx + 1
        if real_month_end_idx < 0 or idx >= len(dates) or idx + SWING_HORIZON_TRADING_DAYS >= len(dates):
            continue
        start_px = px.iloc[idx]
        end_px = px.iloc[idx + SWING_HORIZON_TRADING_DAYS]
        fwd_ret = (end_px / start_px - 1.0).rename("fwd_ret_20td").reset_index()
        fwd_ret.columns = ["symbol", "fwd_ret_20td"]
        fwd_ret["month"] = month_end
        rows.append(fwd_ret)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=["symbol", "fwd_ret_20td", "month"])


def _percentile_rank(s: pd.Series) -> pd.Series:
    return s.rank(pct=True) * 100.0


def _zwinsor_local(s: pd.Series) -> pd.Series:
    lo, hi = s.quantile(0.01), s.quantile(0.99)
    clipped = s.clip(lo, hi)
    std = clipped.std(ddof=0)
    return (clipped - clipped.mean()) / std if std > 0 else clipped * 0.0


def run(start_date: str, end_date: str, min_cross_section: int) -> None:
    print_survivorship_bias_caveat()
    _rp, _rc, records_raw = build_pillar_proxy_records(start_date, end_date, min_cross_section)
    month_ends = [m for m, _f in records_raw]
    fwd20 = compute_20td_forward_returns(start_date, end_date, month_ends)
    fwd20_by_month = {m: g.set_index("symbol")["fwd_ret_20td"] for m, g in fwd20.groupby("month")}

    records_percentile = []
    records_zscore = []
    for month, raw in records_raw:
        fwd = fwd20_by_month.get(month)
        if fwd is None:
            continue
        frame = raw.drop(columns=["fwd_ret"]).join(fwd.rename("fwd_ret"), how="inner")
        frame = frame.dropna(subset=[*PILLAR_COLS, "fwd_ret"])
        if len(frame) < min_cross_section:
            continue

        pct_frame = frame.copy()
        for col in PILLAR_COLS:
            pct_frame[col] = _percentile_rank(frame[col])
        records_percentile.append((month, pct_frame))

        z_frame = frame.copy()
        for col in PILLAR_COLS:
            z_frame[col] = _zwinsor_local(frame[col])
        records_zscore.append((month, z_frame))

    if not records_percentile:
        raise RuntimeError("No usable months after joining 20-trading-day forward returns")

    equal_w = {
        "growth_proxy": BASE_PILLAR_WEIGHTS["growth"],
        "value_proxy": BASE_PILLAR_WEIGHTS["value"],
        "quality_proxy": BASE_PILLAR_WEIGHTS["quality"],
        "stability_proxy": BASE_PILLAR_WEIGHTS["risk"],
        "momentum_proxy": BASE_PILLAR_WEIGHTS["momentum"],
    }
    ibd_tilt_w = {
        "growth_proxy": 2 / 7,
        "momentum_proxy": 2 / 7,
        "quality_proxy": 1 / 7,
        "stability_proxy": 1 / 7,
        "value_proxy": 1 / 7,
    }

    holdout_years = sorted({m.year for m, _f in records_percentile if m.year >= 2022})
    print(f"\nHoldout years: {holdout_years}")
    print(
        f"Forward return horizon: {SWING_HORIZON_TRADING_DAYS} trading days (matches max_hold_days config default), NOT the ~1-month convention every earlier script this session used\n"
    )

    scenarios = {
        "equal_weight__zscore": (records_zscore, equal_w),
        "equal_weight__percentile": (records_percentile, equal_w),
        "ibd_tilt_2211__zscore": (records_zscore, ibd_tilt_w),
        "ibd_tilt_2211__percentile": (records_percentile, ibd_tilt_w),
    }

    header = f"{'scenario':32s}" + "".join(f"{y:>9d}" for y in holdout_years) + f"{'mean':>9s}{'min':>9s}{'#yrs>0':>8s}"
    print(header)
    print("-" * len(header))
    for name, (records, weights) in scenarios.items():
        ics = []
        for year in holdout_years:
            year_records = [(m, f) for m, f in records if m.year == year]
            month_ics = []
            for _m, frame in year_records:
                composite = sum(frame[c].values * w for c, w in weights.items())
                ic, _p = stats.spearmanr(composite, frame["fwd_ret"].values)
                if np.isfinite(ic):
                    month_ics.append(ic)
            ics.append(float(np.mean(month_ics)) if month_ics else float("nan"))
        mean_ic = float(np.nanmean(ics))
        min_ic = float(np.nanmin(ics))
        n_pos = sum(1 for v in ics if v > 0)
        row = f"{name:32s}" + "".join(f"{v:9.4f}" for v in ics) + f"{mean_ic:9.4f}{min_ic:9.4f}{n_pos:8d}/{len(ics)}"
        print(row)

    print(
        "\nThis is the corrected-horizon version of composite_ibd_style_construction.py's same "
        "2x2 - compare these numbers against that script's ~1-month-horizon results directly to "
        "see whether the earlier conclusion (IBD tilt + percentile scaling both help) survives "
        "at the horizon that actually matters for this system."
    )
    print("\nNo production weight or scoring formula was changed by this script.")


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
