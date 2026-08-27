#!/usr/bin/env python3
"""
Walk-forward machine-learning cross-check of the Quality pillar's candidate inputs.

Built 2026-08-26 (user-requested: don't rely on Fama-MacBeth's linear-additive assumption
alone - "not sure of those other results, don't want to be closed-minded, use whatever is the
best right way"). This is a SECOND, INDEPENDENT lens on the same question
algo/research/fama_macbeth_quality_factors.py already answers with linear regression: does
each candidate input carry real, independent forward-return signal? A tree-based model can
surface non-linear effects and interactions between inputs that a linear FM regression
structurally cannot - if it disagrees with FM about what matters, that's worth chasing; if it
agrees, that's real cross-method confidence, not redundant work.

MODEL CHOICE: HistGradientBoostingRegressor, not a plain RandomForestRegressor as literally
requested. Reason: 12 of the 21 candidates tested here have partial coverage (38%-91% - see
each candidate list's own comment in fama_macbeth_quality_factors.py for why). A plain
RandomForest can't handle NaN and would need every missing value IMPUTED to some fabricated
number before fitting - exactly the "fabricated default hides a data quality issue" antipattern
GOVERNANCE.md's Data Quality section explicitly bans (same principle that keeps this whole
codebase from ever inventing a fallback score for missing data). HistGradientBoosting handles
NaN natively (missingness itself becomes a valid split direction, learned from data, not
assumed) - same gradient-boosted-tree family, same non-linear/interaction-capturing ability,
without fabricating a single value. This is the "best right way", not the literal ask, because
the literal ask would have required violating this codebase's own data-integrity rule to work.

METHODOLOGY (why this isn't just a fitting exercise): plain in-sample feature importance from
a model fit on the whole panel is close to worthless here - with ~150 non-independent months
(same annual fundamental repeats for ~12 consecutive months), a flexible model can trivially
memorize noise and call it "importance". Every result below is WALK-FORWARD OUT-OF-SAMPLE: the
model is retrained on an EXPANDING window ending at test_year-1, then evaluated ONLY on
test_year - it never sees the future it's being scored against. Feature importance is
PERMUTATION importance computed on each OOS test fold (not the in-sample impurity-based
importance every tree library defaults to, which is well-documented to be biased toward
high-cardinality/continuous features), averaged across folds.

Usage:
    python -m algo.research.quality_ml_feature_importance [options]
"""

import argparse
import logging
from datetime import datetime

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.inspection import permutation_importance

from algo.research.fama_macbeth_growth_factors import merge_asof_monthly
from algo.research.fama_macbeth_price_factors import fetch_month_end_prices
from algo.research.fama_macbeth_quality_factors import (
    ALTMAN_CANDIDATE_COLS,
    CASH_QUALITY_CANDIDATE_COLS,
    EXTENDED_CANDIDATE_COLS,
    NEW_CANDIDATE_COLS,
    QUALITY_FACTOR_COLS,
    ROIC_CANDIDATE_COLS,
    build_quality_panel,
    fetch_annual_quality_fundamentals,
)

logger = logging.getLogger(__name__)

# Every candidate ever proposed for Quality, tested together in one model - unlike the FM
# harness, which had to isolate sparse-coverage candidates (altman_z_score, roic_pct) into
# their own passes to avoid one 0%-coverage column poisoning a shared dropna(). A tree model
# with native NaN support doesn't have that problem, so this is the first time all 21
# candidates have been evaluated jointly against each other and against forward returns.
ALL_CANDIDATE_COLS = list(
    dict.fromkeys(
        [
            *QUALITY_FACTOR_COLS,
            *EXTENDED_CANDIDATE_COLS,
            *ALTMAN_CANDIDATE_COLS,
            *ROIC_CANDIDATE_COLS,
            *NEW_CANDIDATE_COLS,
            *CASH_QUALITY_CANDIDATE_COLS,
        ]
    )
)


def build_panel(start_date: str, end_date: str) -> pd.DataFrame:
    logger.info("Fetching annual quality fundamentals (point-in-time reconstruction)")
    fund = fetch_annual_quality_fundamentals()
    quality_panel = build_quality_panel(fund)

    logger.info(f"Pulling month-end price panel {start_date}..{end_date}")
    price_df = fetch_month_end_prices(start_date, end_date)
    px = price_df.pivot(index="month", columns="symbol", values="px").sort_index()
    months = px.index

    monthly = merge_asof_monthly(months, quality_panel, cols=ALL_CANDIDATE_COLS)

    rows = []
    for i in range(len(months) - 1):
        month = months[i]
        qframe = monthly.get(month)
        if qframe is None or qframe.empty:
            continue
        fwd_ret = px.iloc[i + 1] / px.iloc[i] - 1.0
        frame = qframe.join(fwd_ret.rename("fwd_ret"), how="inner")
        frame = frame.replace([np.inf, -np.inf], np.nan)
        frame = frame[(frame["fwd_ret"] > -0.95) & (frame["fwd_ret"] < 5.0)]
        # A row needs at least one real candidate value to be worth a prediction - an
        # all-missing row contributes nothing a global mean fallback wouldn't already give.
        if frame[ALL_CANDIDATE_COLS].notna().any(axis=1).sum() == 0:
            continue
        frame = frame[frame[ALL_CANDIDATE_COLS].notna().any(axis=1)]
        frame["month"] = month
        rows.append(frame.reset_index())

    if not rows:
        raise RuntimeError("No usable cross-sectional months")
    return pd.concat(rows, ignore_index=True)


def run(start_date: str, end_date: str, min_test_rows: int) -> None:
    panel = build_panel(start_date, end_date)
    panel["year"] = pd.to_datetime(panel["month"]).dt.year
    years = sorted(panel["year"].unique())

    # Expanding-window walk-forward: first ~60% of years seed the initial training set (needs
    # enough history for a tree model to find anything at all), then every subsequent year is
    # a genuinely out-of-sample test fold, retrained each time on everything strictly before it.
    first_test_idx = max(1, int(len(years) * 0.6))
    test_years = years[first_test_idx:]
    if not test_years:
        raise RuntimeError(f"Not enough distinct years ({len(years)}) for a walk-forward split")

    logger.info(f"Years in panel: {years[0]}-{years[-1]}. Walk-forward test years: {test_years}")

    oos_pred = []
    oos_actual = []
    importances: list[pd.Series] = []

    for test_year in test_years:
        train = panel[panel["year"] < test_year]
        test = panel[panel["year"] == test_year]
        if len(test) < min_test_rows or train.empty:
            logger.info(f"Skipping {test_year}: train={len(train)} test={len(test)} (below min_test_rows)")
            continue

        model = HistGradientBoostingRegressor(
            max_iter=200,
            max_depth=4,
            learning_rate=0.05,
            l2_regularization=1.0,
            random_state=0,
        )
        model.fit(train[ALL_CANDIDATE_COLS], train["fwd_ret"])

        preds = model.predict(test[ALL_CANDIDATE_COLS])
        oos_pred.extend(preds.tolist())
        oos_actual.extend(test["fwd_ret"].tolist())

        # Permutation importance on the OOS fold itself (not the training data) - measures how
        # much each feature actually helps predict returns the model has never seen, the
        # out-of-sample-honest analogue of the in-sample impurity importance every tree library
        # defaults to.
        perm = permutation_importance(
            model, test[ALL_CANDIDATE_COLS], test["fwd_ret"], n_repeats=5, random_state=0, scoring="r2"
        )
        importances.append(pd.Series(perm.importances_mean, index=ALL_CANDIDATE_COLS))
        logger.info(f"{test_year}: train_rows={len(train)} test_rows={len(test)} done")

    if not oos_pred:
        raise RuntimeError("No walk-forward fold produced predictions - min_test_rows too high?")

    oos_pred_s = pd.Series(oos_pred)
    oos_actual_s = pd.Series(oos_actual)
    spearman = oos_pred_s.corr(oos_actual_s, method="spearman")
    pearson = oos_pred_s.corr(oos_actual_s, method="pearson")

    print(f"\n=== Walk-forward out-of-sample fit: {len(test_years)} test years, {len(oos_pred)} symbol-months ===")
    print(f"OOS Spearman rank correlation (predicted vs actual fwd 1m return): {spearman:.4f}")
    print(f"OOS Pearson correlation:                                          {pearson:.4f}")
    print(
        "(A random/no-signal model scores ~0 on both. This is the honest 'does the model "
        "predict anything on data it never trained on' number - not an in-sample fit stat.)"
    )

    avg_importance = pd.concat(importances, axis=1).mean(axis=1).sort_values(ascending=False)
    print("\n=== Permutation feature importance, averaged across all OOS folds (higher = more relied on) ===")
    print(f"{'factor':22s} {'avg_importance':>14s}  coverage")
    for name, val in avg_importance.items():
        coverage = panel[name].notna().mean()
        print(f"{name:22s} {val:14.5f}  {coverage:.1%}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--start-date", default="2014-01-01")
    parser.add_argument("--end-date", default=datetime.now(tz=None).date().isoformat())
    parser.add_argument("--min-test-rows", type=int, default=500)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run(args.start_date, args.end_date, args.min_test_rows)


if __name__ == "__main__":
    main()
