#!/usr/bin/env python3
"""
Tests a composite construction genuinely INSPIRED BY (not a literal claimed replica of - IBD
does not publish its exact combination formula) IBD's own publicly documented/independently
reverse-engineered rating system, built 2026-09-15 (/goal session, direct user directive: "we
want to do it like the industry guys like ibd... the idea is to come up with something similar
to what these guys already figured out" - not a literal copy, a philosophy transplant, tested
honestly on our own true holdout rather than assumed to work because IBD is popular).

TWO SPECIFIC, VERIFIABLE FACTS this script adopts (verified via WebSearch 2026-09-15, not
guessed - see conversation record):

1. IBD's own published explainer confirms the Composite Rating gives DOUBLE WEIGHT to EPS
   Rating and RS (Relative Strength) Rating relative to its other components (SMR, Industry
   Group RS, Accumulation/Distribution, 52-week-high proximity) - the exact combination formula
   beyond "double weight" is proprietary and NOT published, so this script cannot and does not
   claim to reproduce it exactly. Mapped onto our 5 pillars (Growth<->EPS Rating,
   Momentum<->RS Rating get double weight; Quality/Risk/Value, the closest analogues of
   SMR/A-D/other secondary components, get single weight): a 2:2:1:1:1 ratio ->
   growth=2/7=0.2857, momentum=2/7=0.2857, quality=risk=value=1/7=0.1429 each.

2. IBD's RS Rating formula is independently reverse-engineered and CONSISTENT across multiple
   independent sources (github.com/skyte/relative-strength, DataDrivenInvestor - not an official
   IBD press release, but convergent across unrelated reproductions, treated as reliable):
   StrengthFactor = 0.4*ROC(63 trading days) + 0.2*ROC(126d) + 0.2*ROC(189d) + 0.2*ROC(252d),
   i.e. a RECENCY-WEIGHTED blend of trailing cumulative returns at 1/2/3/4-quarter horizons
   (each ROC is cumulative-from-today, so the most recent quarter is counted in all four terms -
   effectively much more heavily weighted than the nominal 40% suggests), then PERCENTILE-RANKED
   1-99 - not z-scored. This is a materially different momentum construction than this repo's
   current momentum_proxy (flat 50/50 mom_12_1/mom_6m, z-scored) in three ways: quarterly
   decomposition instead of two overlapping windows, heavy recency weighting instead of flat,
   and percentile rank instead of z-score. Approximated here at MONTHLY panel resolution (this
   whole research family's panels are month-end, not daily) as 3/6/9/12-month trailing cumulative
   returns - a disclosed granularity approximation of the real 63/126/189/252-TRADING-DAY windows.

WHAT THIS SCRIPT DOES NOT CLAIM: this is not "IBD's actual formula" - IBD's real Composite
Rating combination and Zacks Rank's real earnings-estimate-revision weighting are both
proprietary and not fully public (confirmed via direct search of IBD's and Zacks' own published
explainers, both of which state this openly). This is "the two specific, verifiable design
choices IBD is documented to make, transplanted into our own architecture and honestly
validated" - not a claim of exact replication. A genuine Zacks-style earnings-revision-dominant
factor is NOT attempted here at all: analyst_earnings_estimates has ~1 month of real snapshot
history in this DB, not a point-in-time-reconstructable panel (same data-depth gap already
documented in fama_macbeth_composite_weights.py's own GROWTH_PROXY_COLS docstring) - faking it
with a growth-proxy substitute, as an earlier same-session pass did, is exactly the kind of
unfaithful construction this rebuild is meant to avoid.

METHOD: reuses build_pillar_proxy_records()'s RAW (pre-standardization) growth/value/quality/
stability proxies and fwd_ret unchanged - only momentum is rebuilt, and only the standardization
step (percentile vs z-score) and pillar weights are varied, so every comparison isolates one
specific, named design choice rather than conflating several at once. Same true-holdout
discipline as every other script in this family: candidates are static, holdout years
(2022-2026) are evaluated independently (not pooled), and the bar is beating equal-weight's
worst-case year, not its average.

Usage:
    python -m algo.research.composite_ibd_style_construction [options]
"""

import argparse
import logging
from datetime import datetime

import numpy as np
import pandas as pd
from scipy import stats

from algo.research.fama_macbeth_composite_weights import build_pillar_proxy_records
from algo.research.fama_macbeth_momentum_factors import (
    _trailing_cumret,
    build_month_end_panel,
    compute_daily_indicators,
    fetch_daily_prices,
)
from algo.research.fama_macbeth_price_factors import print_survivorship_bias_caveat
from loaders.load_stock_scores import BASE_PILLAR_WEIGHTS

logger = logging.getLogger(__name__)

RAW_PROXY_COLS = ["growth_proxy", "value_proxy", "quality_proxy", "stability_proxy"]  # momentum rebuilt separately


def build_ibd_rs_momentum(start_date: str, end_date: str) -> pd.DataFrame:
    """Returns a long DataFrame [month, symbol, ibd_rs_raw] - the recency-weighted quarterly
    momentum blend, at monthly panel resolution (3/6/9/12-month trailing cumulative returns
    approximating IBD's real 63/126/189/252-trading-day windows)."""
    logger.info("Fetching daily prices for IBD-style RS reconstruction")
    daily = fetch_daily_prices(start_date, end_date)
    daily_ind = compute_daily_indicators(daily)
    px, _indicators = build_month_end_panel(daily_ind)

    months = px.index
    rows = []
    for i in range(12, len(months)):
        mom_3 = _trailing_cumret(px, i, 3)
        mom_6 = _trailing_cumret(px, i, 6)
        mom_9 = _trailing_cumret(px, i, 9)
        mom_12 = _trailing_cumret(px, i, 12)
        ibd_rs_raw = 0.4 * mom_3 + 0.2 * mom_6 + 0.2 * mom_9 + 0.2 * mom_12
        frame = ibd_rs_raw.rename("ibd_rs_raw").reset_index()
        frame.columns = ["symbol", "ibd_rs_raw"]
        frame["month"] = months[i]
        rows.append(frame)
    return pd.concat(rows, ignore_index=True)


def _percentile_rank(s: pd.Series) -> pd.Series:
    """1-99 style percentile rank within the cross-section, IBD's actual disclosed scale
    convention - not a z-score."""
    return s.rank(pct=True) * 98.0 + 1.0


def _zwinsor_local(s: pd.Series) -> pd.Series:
    lo, hi = s.quantile(0.01), s.quantile(0.99)
    return s.clip(lo, hi).pipe(lambda x: (x - x.mean()) / x.std(ddof=0) if x.std(ddof=0) > 0 else x * 0.0)


def build_candidate_panels(
    start_date: str, end_date: str, min_cross_section: int
) -> tuple[list[tuple[pd.Timestamp, pd.DataFrame]], list[tuple[pd.Timestamp, pd.DataFrame]]]:
    """Returns (records_percentile, records_zscore) - same underlying raw data, two
    standardization conventions, so the percentile-vs-zscore question is isolated from the
    weight-tilt question."""
    _rp, _rc, records_raw = build_pillar_proxy_records(start_date, end_date, min_cross_section)
    ibd_rs_long = build_ibd_rs_momentum(start_date, end_date)
    ibd_rs_by_month = {m: g.set_index("symbol")["ibd_rs_raw"] for m, g in ibd_rs_long.groupby("month")}

    records_percentile = []
    records_zscore = []
    for month, raw in records_raw:
        month_ts = pd.Timestamp(month).replace(day=1)
        ibd_rs = ibd_rs_by_month.get(month_ts)
        if ibd_rs is None:
            continue
        frame = raw.join(ibd_rs.rename("ibd_rs_raw"), how="inner")
        frame = frame.dropna(subset=[*RAW_PROXY_COLS, "ibd_rs_raw", "fwd_ret"])
        if len(frame) < min_cross_section:
            continue

        pct_frame = frame.copy()
        for col in [*RAW_PROXY_COLS, "ibd_rs_raw"]:
            pct_frame[col] = _percentile_rank(frame[col])
        records_percentile.append((month, pct_frame))

        z_frame = frame.copy()
        for col in [*RAW_PROXY_COLS, "ibd_rs_raw"]:
            z_frame[col] = _zwinsor_local(frame[col])
        records_zscore.append((month, z_frame))

    return records_percentile, records_zscore


def _composite_ic_for_months(records: list[tuple[pd.Timestamp, pd.DataFrame]], weights: dict[str, float]) -> float:
    ics = []
    for _month, frame in records:
        composite = sum(frame[c].values * w for c, w in weights.items())
        ic, _p = stats.spearmanr(composite, frame["fwd_ret"].values)
        if np.isfinite(ic):
            ics.append(ic)
    return float(np.mean(ics)) if ics else float("nan")


def run(start_date: str, end_date: str, min_cross_section: int) -> None:
    print_survivorship_bias_caveat()
    records_percentile, records_zscore = build_candidate_panels(start_date, end_date, min_cross_section)
    if not records_percentile:
        raise RuntimeError("No usable months after joining IBD-RS momentum onto the pillar panel")

    equal_w = {
        "growth_proxy": BASE_PILLAR_WEIGHTS["growth"],
        "value_proxy": BASE_PILLAR_WEIGHTS["value"],
        "quality_proxy": BASE_PILLAR_WEIGHTS["quality"],
        "stability_proxy": BASE_PILLAR_WEIGHTS["risk"],
        "ibd_rs_raw": BASE_PILLAR_WEIGHTS["momentum"],
    }
    ibd_tilt_w = {
        "growth_proxy": 2 / 7,
        "ibd_rs_raw": 2 / 7,
        "quality_proxy": 1 / 7,
        "stability_proxy": 1 / 7,
        "value_proxy": 1 / 7,
    }

    holdout_years = sorted({m.year for m, _f in records_percentile if m.year >= 2022})
    print(f"\nHoldout years available: {holdout_years}")
    print(
        "Isolating TWO design choices independently: standardization (percentile vs z-score) x weighting (equal vs IBD 2:2:1:1:1 tilt)\n"
    )

    scenarios = {
        "equal_weight__zscore (current live equivalent)": (records_zscore, equal_w),
        "equal_weight__percentile (IBD scale, flat weight)": (records_percentile, equal_w),
        "ibd_tilt_2211__zscore (IBD weight, current scale)": (records_zscore, ibd_tilt_w),
        "ibd_tilt_2211__percentile (full IBD-inspired)": (records_percentile, ibd_tilt_w),
    }

    header = f"{'scenario':46s}" + "".join(f"{y:>9d}" for y in holdout_years) + f"{'mean':>9s}{'min':>9s}{'#yrs>0':>8s}"
    print(header)
    print("-" * len(header))
    for name, (records, weights) in scenarios.items():
        ics = []
        for year in holdout_years:
            year_records = [(m, f) for m, f in records if m.year == year]
            ics.append(_composite_ic_for_months(year_records, weights))
        mean_ic = float(np.mean(ics))
        min_ic = float(np.min(ics))
        n_pos = sum(1 for v in ics if v > 0)
        row = f"{name:46s}" + "".join(f"{v:9.4f}" for v in ics) + f"{mean_ic:9.4f}{min_ic:9.4f}{n_pos:8d}/{len(ics)}"
        print(row)

    print(
        "\nRead this as a 2x2: if percentile-scaling helps regardless of weight, and the IBD "
        "tilt helps regardless of scaling, they're independent, additive wins - both worth "
        "adopting. If one only helps in combination with the other, that's a real interaction, "
        "not two separate findings - worth knowing before shipping either alone."
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
