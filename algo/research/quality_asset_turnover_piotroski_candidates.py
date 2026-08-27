#!/usr/bin/env python3
"""
Tests two Quality candidates flagged as gaps 2026-08-27 (user-supplied literature checklist,
cross-referenced against every candidate this pillar has ever tested - see
quality_shap_interaction_sweep.py's docstring for the broader audit this continues):

- asset_turnover: Revenue / Total Assets - the classic DuPont efficiency component. Never
  tested; not in QUALITY_FACTOR_COLS/EXTENDED_CANDIDATE_COLS/NEW_CANDIDATE_COLS/anything else
  in fama_macbeth_quality_factors.py.
- piotroski_f_score: the standard 9-signal binary composite (Piotroski 2000, JAR) - never built
  as its own gestalt here, even though EVERY one of its 9 underlying signals is individually
  derivable from fetch_annual_quality_fundamentals()'s existing panel (no new SQL/data source
  needed). Tested as a single 0-9 integer factor, the same way the original paper and most
  replications treat it (a monotonic composite score, not 9 separate regressors).

NOT buildable from current data (checked, not attempted): cash conversion cycle needs
accounts_payable, which does not exist in annual_balance_sheet (checked via information_schema -
only accounts_receivable and inventory are present, no payables side) - DSO+DIO could be
computed but DPO cannot, so a genuine 3-leg cash conversion cycle is a real, currently-unfillable
data gap, not attempted here as a 2-leg approximation (would silently misrepresent the metric).

Usage:
    python -m algo.research.quality_asset_turnover_piotroski_candidates
"""

import argparse
import logging
from datetime import datetime

import numpy as np
import pandas as pd

from algo.research.fama_macbeth_growth_factors import merge_asof_monthly
from algo.research.fama_macbeth_price_factors import _fama_macbeth, fetch_month_end_prices
from algo.research.fama_macbeth_quality_factors import fetch_annual_quality_fundamentals

logger = logging.getLogger(__name__)

REPORTING_LAG_DAYS = 90
CANDIDATES = ["asset_turnover", "piotroski_f_score"]


def build_panel(fund: pd.DataFrame) -> pd.DataFrame:
    fund = fund.sort_values(["symbol", "fiscal_year"]).reset_index(drop=True)

    out = fund[["symbol", "fiscal_year"]].copy()

    roa = np.where(fund["total_assets"] > 0, fund["net_income"] / fund["total_assets"], np.nan)
    asset_turnover = np.where(fund["total_assets"] > 0, fund["revenue"] / fund["total_assets"], np.nan)
    gross_margin = np.where(fund["revenue"] > 0, (fund["revenue"] - fund["cost_of_revenue"]) / fund["revenue"], np.nan)
    leverage = np.where(fund["total_assets"] > 0, fund["long_term_debt"] / fund["total_assets"], np.nan)
    current_ratio = np.where(
        fund["current_liabilities"] > 0, fund["current_assets"] / fund["current_liabilities"], np.nan
    )

    out["asset_turnover"] = asset_turnover

    frame = pd.DataFrame(
        {
            "symbol": fund["symbol"],
            "roa": roa,
            "ocf": fund["operating_cash_flow"],
            "ni": fund["net_income"],
            "leverage": leverage,
            "current_ratio": current_ratio,
            "shares": fund["shares_outstanding_diluted"],
            "gross_margin": gross_margin,
            "asset_turnover": asset_turnover,
        }
    )
    fg = frame.groupby("symbol", group_keys=False)

    def _prior(col: str) -> pd.Series:
        return fg[col].shift(1)

    # Piotroski (2000) 9 binary signals - standard definitions, each 1 if the criterion holds,
    # 0 otherwise (NaN if the underlying inputs aren't both available that year, propagated to
    # a NaN total rather than silently scored as 0 - a missing signal is not the same as a
    # failed one).
    # BUG FIXED 2026-08-27 (live-caught, user-prompted re-check): `(frame["roa"] > 0).astype(
    # float)` does NOT propagate NaN - pandas/numpy comparison operators return False for a NaN
    # operand, not NaN, so a missing roa silently scored s1=0.0 ("criterion failed") instead of
    # "unknown". That made every one of the 9 signals technically "not NaN" always, so
    # `signals.notna().sum(axis=1) >= 7` below was vacuously true on every row regardless of
    # real data availability - confirmed live: piotroski_f_score showed 100.0% coverage at
    # every single checked month even though asset_turnover (one of its own 9 inputs) only had
    # 88-97% coverage over the same months, a logical impossibility. Fixed with `.where(...)` to
    # explicitly re-NaN any signal whose underlying input(s) were actually missing, so the
    # completeness gate below now does what its own comment always claimed it did.
    def _binary(condition: pd.Series, *required: pd.Series) -> pd.Series:
        result = condition.astype(float)
        for r in required:
            result = result.where(r.notna())
        return result

    s1 = _binary(frame["roa"] > 0, frame["roa"])
    s2 = _binary(frame["ocf"] > 0, frame["ocf"])
    s3 = _binary(frame["roa"] > _prior("roa"), frame["roa"], _prior("roa"))
    s4 = _binary(frame["ocf"] > frame["ni"], frame["ocf"], frame["ni"])
    s5 = _binary(frame["leverage"] < _prior("leverage"), frame["leverage"], _prior("leverage"))
    s6 = _binary(frame["current_ratio"] > _prior("current_ratio"), frame["current_ratio"], _prior("current_ratio"))
    s7 = _binary(frame["shares"] <= _prior("shares"), frame["shares"], _prior("shares"))
    s8 = _binary(frame["gross_margin"] > _prior("gross_margin"), frame["gross_margin"], _prior("gross_margin"))
    s9 = _binary(frame["asset_turnover"] > _prior("asset_turnover"), frame["asset_turnover"], _prior("asset_turnover"))

    signals = pd.concat([s1, s2, s3, s4, s5, s6, s7, s8, s9], axis=1)
    # Require at least 7 of 9 signals computable (the 5 YoY-delta signals need a prior year,
    # so year-1-on-record symbols are naturally excluded here, same as every _growth()/
    # _growth_rate() YoY field elsewhere in this file family) - a score built from only 2-3
    # available signals would be the same thin-sample extrapolation problem this codebase
    # already guards against elsewhere (see quality_score's own 40% completeness floor).
    enough = signals.notna().sum(axis=1) >= 7
    out["piotroski_f_score"] = np.where(enough, signals.sum(axis=1, skipna=True), np.nan)

    out["known_date"] = pd.to_datetime(out["fiscal_year"].astype(str) + "-12-31") + pd.Timedelta(
        days=REPORTING_LAG_DAYS
    )
    return out.dropna(subset=["known_date"])


def _zwinsor(s: pd.Series) -> pd.Series:
    s = s.replace([np.inf, -np.inf], np.nan)
    lo, hi = s.quantile([0.01, 0.99])
    s = s.clip(lo, hi)
    std = s.std()
    return (s - s.mean()) / std if std and std > 0 else s * 0.0


def build_records(start_date: str, end_date: str, min_cross_section: int) -> list[tuple[pd.Timestamp, pd.DataFrame]]:
    fund = fetch_annual_quality_fundamentals()
    panel = build_panel(fund)

    price_df = fetch_month_end_prices(start_date, end_date)
    px = price_df.pivot(index="month", columns="symbol", values="px").sort_index()
    months = px.index

    monthly = merge_asof_monthly(months, panel, cols=CANDIDATES)

    records = []
    for i in range(len(months) - 1):
        month = months[i]
        qframe = monthly.get(month)
        if qframe is None or qframe.empty:
            continue
        fwd_ret = px.iloc[i + 1] / px.iloc[i] - 1.0
        frame = qframe.join(fwd_ret.rename("fwd_ret"), how="inner")
        frame = frame.replace([np.inf, -np.inf], np.nan)
        frame = frame[(frame["fwd_ret"] > -0.95) & (frame["fwd_ret"] < 5.0)]
        for c in CANDIDATES:
            frame[c] = _zwinsor(frame[c])
        if len(frame.dropna(subset=CANDIDATES, how="all")) < min_cross_section:
            continue
        records.append((month, frame))
    return records


def run(start_date: str, end_date: str, min_cross_section: int, split_date: str) -> None:
    records = build_records(start_date, end_date, min_cross_section)
    if not records:
        raise RuntimeError("No usable cross-sectional months")

    print(f"Usable cross-sectional months: {len(records)}  ({records[0][0]} to {records[-1][0]})\n")

    split_ts = pd.Timestamp(split_date)
    first_half = [r for r in records if pd.Timestamp(r[0]) < split_ts]
    second_half = [r for r in records if pd.Timestamp(r[0]) >= split_ts]

    for label, recs in (
        ("FULL SAMPLE", records),
        (f"FIRST HALF (< {split_date})", first_half),
        (f"SECOND HALF (>= {split_date})", second_half),
    ):
        print(f"--- {label} ({len(recs)} months) ---")
        for c in CANDIDATES:
            usable = [(m, f.dropna(subset=[c])) for m, f in recs]
            usable = [(m, f) for m, f in usable if len(f) >= min_cross_section]
            if not usable:
                print(f"  {c:20s} (no usable months)")
                continue
            result = _fama_macbeth(usable, [c])
            mean, t = result[c]
            coverage = np.mean([len(f) for _, f in usable]) if usable else 0
            print(
                f"  {c:20s} mean_coef={mean:10.5f}  t_stat={t:7.2f}  n_months={len(usable):4d}  avg_n={coverage:7.0f}"
            )
        print()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--start-date", default="2014-01-01")
    parser.add_argument("--end-date", default=datetime.now(tz=None).date().isoformat())
    parser.add_argument("--min-cross-section", type=int, default=100)
    parser.add_argument("--split-date", default="2020-06-01")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run(args.start_date, args.end_date, args.min_cross_section, args.split_date)


if __name__ == "__main__":
    main()
