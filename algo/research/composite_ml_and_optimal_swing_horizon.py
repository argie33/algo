#!/usr/bin/env python3
"""
Completes the corrected-horizon picture started in composite_swing_horizon_validation.py -
built 2026-09-15 (/goal session, direct user demand: "have we tried hard enough with all the
inputs... have we exhausted if there are any better ML options" before accepting equal-weight).

Two comparisons this repo had already built and run ONCE each (fama_macbeth_composite_weights.py's
own walk-forward ML comparison; composite_weights_shrinkage_optimal.py's Grinold-Kahn optimal
weighting) - but BOTH were run at the ~1-month horizon inherited from the wider fama_macbeth_*
family, the same wrong-horizon mistake composite_swing_horizon_validation.py already caught and
fixed for the equal-weight/IBD-tilt comparison. Neither has been re-verified at the real
20-trading-day swing horizon (matches max_hold_days config default) until now. This script
answers, on the SAME corrected horizon and SAME true holdout discipline as
composite_swing_horizon_validation.py:

  1. Does ANY machine learning model (Ridge/Lasso at several regularization strengths,
     gradient-boosted trees) beat the simple linear equal-weight composite, walk-forward,
     expanding-window (train on all years before the test year, never on the test year itself)?
  2. Does the Grinold-Kahn/Ledoit-Wolf-shrunk "optimal" weighting (fit ONLY on 2017-2021,
     recomputed against 20-trading-day ICs this time, not 1-month) beat equal-weight on the
     TRUE 2022-2026 holdout at this corrected horizon?

Both answered honestly, with the same era-robustness bar as every other script this session:
beating equal-weight's own worst year, not just its average.

Usage:
    python -m algo.research.composite_ml_and_optimal_swing_horizon [options]
"""

import argparse
import logging
from collections import defaultdict
from datetime import datetime

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.covariance import LedoitWolf
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Lasso, Ridge

from algo.research.composite_swing_horizon_validation import compute_20td_forward_returns
from algo.research.fama_macbeth_composite_weights import PILLAR_COLS, build_pillar_proxy_records
from algo.research.fama_macbeth_price_factors import print_survivorship_bias_caveat
from loaders.load_stock_scores import BASE_PILLAR_WEIGHTS

logger = logging.getLogger(__name__)


def _zwinsor_local(s: pd.Series) -> pd.Series:
    lo, hi = s.quantile(0.01), s.quantile(0.99)
    clipped = s.clip(lo, hi)
    std = clipped.std(ddof=0)
    return (clipped - clipped.mean()) / std if std > 0 else clipped * 0.0


def build_corrected_panel(
    start_date: str, end_date: str, min_cross_section: int
) -> list[tuple[pd.Timestamp, pd.DataFrame]]:
    _rp, _rc, records_raw = build_pillar_proxy_records(start_date, end_date, min_cross_section)
    month_ends = [m for m, _f in records_raw]
    fwd20 = compute_20td_forward_returns(start_date, end_date, month_ends)
    fwd20_by_month = {m: g.set_index("symbol")["fwd_ret_20td"] for m, g in fwd20.groupby("month")}

    records = []
    for month, raw in records_raw:
        fwd = fwd20_by_month.get(month)
        if fwd is None:
            continue
        frame = raw.drop(columns=["fwd_ret"]).join(fwd.rename("fwd_ret"), how="inner")
        frame = frame.dropna(subset=[*PILLAR_COLS, "fwd_ret"])
        if len(frame) < min_cross_section:
            continue
        for col in PILLAR_COLS:
            frame[col] = _zwinsor_local(frame[col])
        records.append((month, frame))
    return records


def run_ml_comparison(records: list[tuple[pd.Timestamp, pd.DataFrame]]) -> None:
    equal_w = {
        "growth_proxy": BASE_PILLAR_WEIGHTS["growth"],
        "value_proxy": BASE_PILLAR_WEIGHTS["value"],
        "quality_proxy": BASE_PILLAR_WEIGHTS["quality"],
        "stability_proxy": BASE_PILLAR_WEIGHTS["risk"],
        "momentum_proxy": BASE_PILLAR_WEIGHTS["momentum"],
    }
    test_years = sorted({m.year for m, _f in records if m.year >= 2022})
    ridge_alphas = [0.1, 1.0, 10.0]
    lasso_alphas = [0.001, 0.01, 0.1]

    model_year_ic: dict[str, dict[int, list[float]]] = defaultdict(lambda: defaultdict(list))

    for test_year in test_years:
        train = pd.concat([f for m, f in records if m.year < test_year], ignore_index=True)
        test_records = [(m, f) for m, f in records if m.year == test_year]
        if train.empty or not test_records:
            continue
        x_train, y_train = train[PILLAR_COLS], train["fwd_ret"]

        tree = HistGradientBoostingRegressor(
            max_iter=200, max_depth=4, learning_rate=0.05, l2_regularization=1.0, random_state=0
        )
        tree.fit(x_train, y_train)

        ridge_models = {a: Ridge(alpha=a).fit(x_train, y_train) for a in ridge_alphas}
        lasso_models = {a: Lasso(alpha=a, max_iter=5000).fit(x_train, y_train) for a in lasso_alphas}

        for _month, frame in test_records:
            x_test = frame[PILLAR_COLS]
            y_test = frame["fwd_ret"].values

            live_pred = sum(frame[c].values * w for c, w in equal_w.items())
            ic, _ = stats.spearmanr(live_pred, y_test)
            if np.isfinite(ic):
                model_year_ic["equal_weight_linear"][test_year].append(ic)

            tree_pred = tree.predict(x_test)
            ic, _ = stats.spearmanr(tree_pred, y_test)
            if np.isfinite(ic):
                model_year_ic["ml_tree(d4,l2=1)"][test_year].append(ic)

            for a, m in ridge_models.items():
                ic, _ = stats.spearmanr(m.predict(x_test), y_test)
                if np.isfinite(ic):
                    model_year_ic[f"ridge_a{a:g}"][test_year].append(ic)

            for a, m in lasso_models.items():
                ic, _ = stats.spearmanr(m.predict(x_test), y_test)
                if np.isfinite(ic):
                    model_year_ic[f"lasso_a{a:g}"][test_year].append(ic)

    print("\n########## WALK-FORWARD ML COMPARISON (20-trading-day horizon, expanding window) ##########")
    print(f"Test years: {test_years}\n")
    header = f"{'model':22s}" + "".join(f"{y:>9d}" for y in test_years) + f"{'mean':>9s}{'min':>9s}{'#yrs>0':>8s}"
    print(header)
    print("-" * len(header))
    for name, year_ics in model_year_ic.items():
        yearly_means = [float(np.mean(year_ics[y])) if year_ics.get(y) else float("nan") for y in test_years]
        mean_ic = float(np.nanmean(yearly_means))
        min_ic = float(np.nanmin(yearly_means))
        n_pos = sum(1 for v in yearly_means if v > 0)
        row = (
            f"{name:22s}"
            + "".join(f"{v:9.4f}" for v in yearly_means)
            + f"{mean_ic:9.4f}{min_ic:9.4f}{n_pos:8d}/{len(test_years)}"
        )
        print(row)


def run_optimal_weight_comparison(records: list[tuple[pd.Timestamp, pd.DataFrame]]) -> None:
    fit = [(m, f) for m, f in records if m.year <= 2021]
    holdout = [(m, f) for m, f in records if m.year >= 2022]
    if not fit or not holdout:
        print("\nSkipping optimal-weight comparison - insufficient fit or holdout months")
        return

    pooled_fit = pd.concat([f for _, f in fit], ignore_index=True)
    x = pooled_fit[PILLAR_COLS].values
    lw = LedoitWolf().fit(x)
    sigma = lw.covariance_

    ic_vec = np.zeros(len(PILLAR_COLS))
    for i, col in enumerate(PILLAR_COLS):
        ics = []
        for _m, frame in fit:
            ic, _ = stats.spearmanr(frame[col].values, frame["fwd_ret"].values)
            if np.isfinite(ic):
                ics.append(ic)
        ic_vec[i] = np.mean(ics)

    w_raw_arr = np.linalg.solve(sigma, ic_vec)
    l1 = np.abs(w_raw_arr).sum()
    w_optimal = dict(zip(PILLAR_COLS, (w_raw_arr / l1 if l1 > 0 else w_raw_arr).tolist(), strict=True))

    equal_w = {
        "growth_proxy": BASE_PILLAR_WEIGHTS["growth"],
        "value_proxy": BASE_PILLAR_WEIGHTS["value"],
        "quality_proxy": BASE_PILLAR_WEIGHTS["quality"],
        "stability_proxy": BASE_PILLAR_WEIGHTS["risk"],
        "momentum_proxy": BASE_PILLAR_WEIGHTS["momentum"],
    }

    holdout_years = sorted({m.year for m, _f in holdout})
    print("\n########## GRINOLD-KAHN OPTIMAL WEIGHTING (20-trading-day horizon, fit 2017-2021 only) ##########")
    print("Fit-derived weights (L1-normalized Sigma^-1 . IC, NOT re-touched on holdout):")
    for col, w in w_optimal.items():
        print(f"  {col}: {w:.3f}")

    header = (
        f"{'weighting':22s}" + "".join(f"{y:>9d}" for y in holdout_years) + f"{'mean':>9s}{'min':>9s}{'#yrs>0':>8s}"
    )
    print(header)
    print("-" * len(header))
    for name, weights in [("equal_weight", equal_w), ("grinold_kahn_optimal", w_optimal)]:
        ics = []
        for year in holdout_years:
            year_records = [(m, f) for m, f in holdout if m.year == year]
            month_ics = []
            for _m, frame in year_records:
                composite = sum(frame[c].values * w for c, w in weights.items())
                ic, _ = stats.spearmanr(composite, frame["fwd_ret"].values)
                if np.isfinite(ic):
                    month_ics.append(ic)
            ics.append(float(np.mean(month_ics)) if month_ics else float("nan"))
        mean_ic = float(np.nanmean(ics))
        min_ic = float(np.nanmin(ics))
        n_pos = sum(1 for v in ics if v > 0)
        row = f"{name:22s}" + "".join(f"{v:9.4f}" for v in ics) + f"{mean_ic:9.4f}{min_ic:9.4f}{n_pos:8d}/{len(ics)}"
        print(row)


def run(start_date: str, end_date: str, min_cross_section: int) -> None:
    print_survivorship_bias_caveat()
    records = build_corrected_panel(start_date, end_date, min_cross_section)
    if not records:
        raise RuntimeError("No usable months after building the corrected 20-trading-day panel")

    run_ml_comparison(records)
    run_optimal_weight_comparison(records)

    print(
        "\nEra-robustness bar (same as every other script this session): a model/weighting only "
        "counts as genuinely better than equal-weight if it beats equal-weight's own worst year, "
        "not just its mean. No production weight or scoring formula was changed by this script."
    )


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
