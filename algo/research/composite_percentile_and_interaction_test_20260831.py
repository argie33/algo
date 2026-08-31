#!/usr/bin/env python3
"""
Composite-score research, 2026-08-31 session, Question A + Question B follow-ups to the
same-day rebuild of `algo/research/fama_macbeth_composite_weights.py`.

Reuses that script's `build_pillar_proxy_records()` (one DB fetch + panel build, not
re-derived here) to answer two separate questions raised directly by the user pushing back
on "is pillar-weighted-linear-combination even the right way to build the composite":

QUESTION A - cross-pillar interactions. Rebuild of
`algo/research/cross_pillar_interaction_sweep_20260828.py`, which is stale the same way the
composite-weights script was (still has size_proxy as a 6th pillar, retired 2026-08-28; old
growth_proxy/value_proxy/stability_proxy formulas). Uses the SAME complete-case (strict
dropna, no imputation) records as fama_macbeth_composite_weights.py's own COMPLETE-CASE
regime - the regime that script's own "AGREEMENT CHECK" discipline treats as the trustworthy
one, same precedent the original 2026-08-28 sweep established. For each of the 10 pillar
pairs (5 pillars now, not 6): main effects + interaction term, Fama-MacBeth, full-sample +
half-split, "robust" = |t|>2 in BOTH halves AND same sign (identical bar to the 2026-08-28
sweep). value_proxy x stability_proxy is already live in production
(_value_risk_adjusted_weights in loaders/load_stock_scores.py) - re-verified here with
corrected formulas, not assumed still true.

QUESTION B - percentile-rank vs fixed z-score/curve scale consistency. Production scores
Value's P/E/P/B/P/S via a cross-sectional PERCENTILE rank each run
(update_value_multiples_percentiles()) but Quality/Growth/Momentum/Risk via fixed absolute
curves - a real scale-mixing risk industry practice (MSCI/Russell/S&P factor indices)
avoids by percentile-ranking every factor before combining. Tests this empirically: takes
the IDENTICAL underlying pillar-proxy panel (records_raw from
build_pillar_proxy_records - the pillar proxy BEFORE any top-level per-month
normalization) and builds two variants of the top-level normalization:
  (1) Z-SCORE + 0-impute (exactly matches fama_macbeth_composite_weights.py's own
      records_partial / its already-reported live_linear_fixed_pct OOS Spearman=0.0830 -
      recomputed here from records_raw as a sanity check that this script's re-derivation
      matches the original, not because the number itself was in doubt).
  (2) PERCENTILE rank (0-1) within each month + 0.5-impute (the neutral/median value on a
      [0,1] percentile scale, the direct analogue of z-score's 0-impute on a
      mean-zero scale - NOT the same imputation value, deliberately, since 0 has no
      "no information" meaning on a percentile scale).
Both go through the identical walk-forward OOS harness (train on strictly prior years, test
on each held-out year, same BASE_PILLAR_WEIGHTS applied as fixed percentages either way) so
the ONLY thing that differs between the two Spearman/Pearson numbers is the per-month
normalization step - a clean, apples-to-apples test of "does percentile-ranking everything
(matching Value's real live methodology and industry practice) improve real predictive
power, or is the current mixed approach fine."

Usage:
    python -m algo.research.composite_percentile_and_interaction_test_20260831 [options]
"""

import argparse
import itertools
import logging
from collections.abc import Callable
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

from algo.research.fama_macbeth_composite_weights import (
    PILLAR_COLS,
    PILLAR_TO_LIVE_KEY,
    build_pillar_proxy_records,
)
from algo.research.fama_macbeth_price_factors import _fama_macbeth
from loaders.load_stock_scores import BASE_PILLAR_WEIGHTS

logger = logging.getLogger(__name__)

MIN_T = 2.0


def _zwinsor(s: pd.Series) -> pd.Series:
    s = s.replace([np.inf, -np.inf], np.nan)
    lo, hi = s.quantile([0.01, 0.99])
    s = s.clip(lo, hi)
    std = s.std()
    return (s - s.mean()) / std if std and std > 0 else s * 0.0


def _percentile_rank(s: pd.Series) -> pd.Series:
    """Cross-sectional percentile rank within one month, [0, 1], matching
    update_value_multiples_percentiles()'s real live methodology for Value's PE/PB/PS -
    extended here to every pillar proxy for the head-to-head comparison."""
    return s.rank(pct=True, method="average")


def run_interaction_sweep(records_complete: list[tuple[pd.Timestamp, pd.DataFrame]]) -> None:
    print("\n########## QUESTION A: cross-pillar interaction sweep (COMPLETE-CASE) ##########")
    sizes = [len(f) for _, f in records_complete]
    print(f"Usable complete-case cross-sectional months: {len(records_complete)}")
    print(f"Median cross-section size: {int(np.median(sizes))}\n")

    split = len(records_complete) // 2
    eras = {"FULL": records_complete, "ERA1": records_complete[:split], "ERA2": records_complete[split:]}

    results: list[dict[str, Any]] = []
    for a, b in itertools.combinations(PILLAR_COLS, 2):
        inter_col = f"{a}_x_{b}"
        for _month, frame in records_complete:
            frame[inter_col] = frame[a] * frame[b]

        row: dict[str, Any] = {"pair": f"{a} x {b}"}
        for era_label, recs in eras.items():
            fm = _fama_macbeth(recs, [a, b, inter_col])
            row[f"t_{era_label}"] = fm[inter_col][1]
            row[f"coef_{era_label}"] = fm[inter_col][0]
        results.append(row)

    print(f"{'pair':35s} {'coef_FULL':>10s} {'t_FULL':>7s} {'t_ERA1':>7s} {'t_ERA2':>7s} {'robust?':>8s}")
    robust_pairs: list[str] = []
    for row in sorted(results, key=lambda r: -abs(r["t_FULL"])):
        robust = (
            abs(row["t_ERA1"]) >= MIN_T and abs(row["t_ERA2"]) >= MIN_T and (row["t_ERA1"] > 0) == (row["t_ERA2"] > 0)
        )
        if robust:
            robust_pairs.append(row["pair"])
        flag = "YES" if robust else ""
        print(
            f"{row['pair']:35s} {row['coef_FULL']:10.5f} {row['t_FULL']:7.2f} "
            f"{row['t_ERA1']:7.2f} {row['t_ERA2']:7.2f} {flag:>8s}"
        )

    print(f"\nRobust pairs (|t|>={MIN_T:g} in BOTH half-split eras, same sign): {robust_pairs or 'none'}")
    vxr = "value_proxy x stability_proxy"
    vxr_row = next((r for r in results if r["pair"] == vxr), None)
    if vxr_row:
        already_robust = vxr in robust_pairs
        print(
            f"\nAlready-live interaction ({vxr}, -> _value_risk_adjusted_weights in production): "
            f"{'STILL ROBUST with corrected formulas' if already_robust else 'NO LONGER CLEARS THE ROBUST BAR with corrected formulas - re-verify before trusting the live implementation'}"
        )


def run_percentile_comparison(records_raw: list[tuple[pd.Timestamp, pd.DataFrame]], min_cross_section: int) -> None:
    print("\n########## QUESTION B: percentile-rank vs z-score normalization (walk-forward OOS) ##########")

    def _normalize(
        records: list[tuple[pd.Timestamp, pd.DataFrame]],
        fn: Callable[[pd.Series], pd.Series],
        impute_value: float,
    ) -> list[tuple[pd.Timestamp, pd.DataFrame]]:
        out: list[tuple[pd.Timestamp, pd.DataFrame]] = []
        for month, frame in records:
            f = frame.copy()
            for col in PILLAR_COLS:
                f[col] = fn(f[col]).fillna(impute_value)
            out.append((month, f))
        return out

    records_zscore = _normalize(records_raw, _zwinsor, 0.0)
    records_pct = _normalize(records_raw, _percentile_rank, 0.5)

    panel_rows_z, panel_rows_pct = [], []
    for (month, fz), (_month2, fp) in zip(records_zscore, records_pct, strict=True):
        fz = fz.copy()
        fz["month"] = month
        panel_rows_z.append(fz)
        fp = fp.copy()
        fp["month"] = month
        panel_rows_pct.append(fp)
    panel_z = pd.concat(panel_rows_z, ignore_index=True)
    panel_pct = pd.concat(panel_rows_pct, ignore_index=True)
    panel_z["year"] = pd.to_datetime(panel_z["month"]).dt.year
    panel_pct["year"] = pd.to_datetime(panel_pct["month"]).dt.year

    years = sorted(panel_z["year"].unique())
    first_test_idx = max(1, int(len(years) * 0.6))
    test_years = years[first_test_idx:]
    split_year = test_years[len(test_years) // 2] if len(test_years) > 1 else None

    live_weight_map = {c: BASE_PILLAR_WEIGHTS[k] for c, k in PILLAR_TO_LIVE_KEY.items()}

    def _walk_forward_pred(panel: pd.DataFrame) -> tuple[list[float], list[float], list[int]]:
        preds, actual, yr = [], [], []
        for test_year in test_years:
            test = panel[panel["year"] == test_year]
            if len(test) < min_cross_section:
                continue
            pred = sum(test[c] * w for c, w in live_weight_map.items())
            preds.extend(pred.tolist())
            actual.extend(test["fwd_ret"].tolist())
            yr.extend([test_year] * len(test))
        return preds, actual, yr

    z_pred, z_actual, z_year = _walk_forward_pred(panel_z)
    pct_pred, pct_actual, pct_year = _walk_forward_pred(panel_pct)

    if not z_pred or not pct_pred:
        print("No usable walk-forward test years - min_cross_section too high?")
        return

    def _report_variant(label: str, preds: list[float], actual: list[float], years_arr: list[int]) -> None:
        s = pd.Series(preds)
        a = pd.Series(actual)
        spear = s.corr(a, method="spearman")
        pears = s.corr(a, method="pearson")
        print(f"{label:30s} {spear:10.4f} {pears:10.4f}  (n={len(preds)}, years={sorted(set(years_arr))})")
        if split_year is not None:
            years_np = np.array(years_arr)
            mask1 = years_np < split_year
            mask2 = ~mask1
            for half_label, mask in (("  ERA1", mask1), ("  ERA2", mask2)):
                if mask.sum() < 30:
                    continue
                s_h, a_h = s[mask], a[mask]
                print(
                    f"{half_label:30s} {s_h.corr(a_h, method='spearman'):10.4f} "
                    f"{s_h.corr(a_h, method='pearson'):10.4f}  (n={int(mask.sum())})"
                )

    print(f"\n{'method':30s} {'Spearman':>10s} {'Pearson':>10s}")
    _report_variant("live_linear_zscore", z_pred, z_actual, z_year)
    _report_variant("live_linear_percentile", pct_pred, pct_actual, pct_year)

    z_spear = pd.Series(z_pred).corr(pd.Series(z_actual), method="spearman")
    pct_spear = pd.Series(pct_pred).corr(pd.Series(pct_actual), method="spearman")
    diff = pct_spear - z_spear
    print(
        f"\nPercentile - Z-score Spearman diff: {diff:+.4f} "
        f"({'percentile wins' if diff > 0.002 else 'z-score wins' if diff < -0.002 else 'essentially tied'})"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--start-date", default="2015-06-01")
    parser.add_argument("--end-date", default=datetime.now(tz=None).date().isoformat())
    parser.add_argument("--min-cross-section", type=int, default=100)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    logger.info("Building pillar-proxy panel (single fetch, reused for both questions)")
    _records_partial, records_complete, records_raw = build_pillar_proxy_records(
        args.start_date, args.end_date, args.min_cross_section
    )

    run_interaction_sweep(records_complete)
    run_percentile_comparison(records_raw, args.min_cross_section)


if __name__ == "__main__":
    main()
