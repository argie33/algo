#!/usr/bin/env python3
"""
Systematic pairwise-interaction sweep across EVERY candidate ever proposed for Quality (21
columns), replacing hand-picked pairwise checks (e.g. quality_roa_interaction_feature_design.py,
which only tested candidate-vs-roa because that's the one conditioning variable a human had
already guessed) with SHAP interaction values extracted from the walk-forward tree model
quality_ml_feature_importance.py already validated.

WHY THIS EXISTS (2026-08-27, user pushback): "i fear we just looking at things in isolation...
looking at this ROA vs other things but we are missing biggest picture... best proper uses of ML
and figuring out relationships between the data". Correct criticism - testing candidate X against
ROA only tells you about that one pair. A gradient-boosted tree implicitly learns interactions
between EVERY pair of features it's given jointly; SHAP interaction values are the standard way
to extract "how much does the pair (i, j) matter together, beyond what i and j explain alone" for
ALL C(21,2)=210 pairs at once, not just the ones someone thought to test by hand.

Reuses quality_ml_feature_importance.py's exact panel-building and walk-forward split (same
expanding-window, strictly-out-of-sample discipline - a SHAP value computed on training data a
model has already memorized would be meaningless, same reason permutation importance there is
OOS-only). Interaction values are computed per OOS fold on a bounded random subsample (interaction
computation is O(n_samples * n_features^2 * n_trees), too slow to run on every OOS row across 6
folds x ~thousands of rows) and averaged in absolute value across folds - direction can flip
across a discontinuity a linear reading would miss, so |interaction| strength is what's being
ranked, not signed effect (a confirmed strong pair still needs a signed, half-split-robust
production formula built and validated separately, same as every other Quality decision here).

Usage:
    python -m algo.research.quality_shap_interaction_sweep
"""

import argparse
import logging
from datetime import datetime

import numpy as np
import pandas as pd
import shap
from sklearn.ensemble import HistGradientBoostingRegressor

from algo.research.quality_ml_feature_importance import ALL_CANDIDATE_COLS, build_panel

logger = logging.getLogger(__name__)

RNG_SEED = 0


def run(start_date: str, end_date: str, min_test_rows: int, sample_per_fold: int, top_n: int) -> None:
    panel = build_panel(start_date, end_date)
    panel["year"] = pd.to_datetime(panel["month"]).dt.year
    years = sorted(panel["year"].unique())

    first_test_idx = max(1, int(len(years) * 0.6))
    test_years = years[first_test_idx:]
    if not test_years:
        raise RuntimeError(f"Not enough distinct years ({len(years)}) for a walk-forward split")

    logger.info(f"Years in panel: {years[0]}-{years[-1]}. Walk-forward test years: {test_years}")

    n = len(ALL_CANDIDATE_COLS)
    interaction_sum = np.zeros((n, n))
    interaction_count = 0
    rng = np.random.default_rng(RNG_SEED)

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

        test_x = test[ALL_CANDIDATE_COLS]
        # NaN-preserving: HistGradientBoostingRegressor learned real split directions for
        # missingness during fit, same as quality_ml_feature_importance.py - shap's TreeExplainer
        # follows those learned directions natively, no imputation needed or wanted here.
        sample_idx = rng.choice(len(test_x), size=min(sample_per_fold, len(test_x)), replace=False)
        test_sample = test_x.iloc[sample_idx]

        explainer = shap.TreeExplainer(model)
        interaction_values = explainer.shap_interaction_values(test_sample)  # (n_samples, n, n)

        interaction_sum += np.abs(interaction_values).sum(axis=0)
        interaction_count += len(test_sample)
        logger.info(f"{test_year}: train_rows={len(train)} interaction_sample={len(test_sample)} done")

    if interaction_count == 0:
        raise RuntimeError("No walk-forward fold produced interaction values - min_test_rows too high?")

    mean_abs_interaction = interaction_sum / interaction_count

    # Diagonal = main-effect SHAP magnitude (not an interaction with itself) - report separately,
    # rank only the off-diagonal pairs.
    main_effect = pd.Series(np.diag(mean_abs_interaction), index=ALL_CANDIDATE_COLS).sort_values(ascending=False)

    pairs = []
    for i in range(n):
        for j in range(i + 1, n):
            # shap_interaction_values splits pairwise interaction magnitude evenly across the
            # [i,j] and [j,i] off-diagonal cells - sum both to get the pair's total.
            pairs.append(
                (ALL_CANDIDATE_COLS[i], ALL_CANDIDATE_COLS[j], mean_abs_interaction[i, j] + mean_abs_interaction[j, i])
            )
    pairs_df = pd.DataFrame(pairs, columns=["feature_a", "feature_b", "mean_abs_interaction"])
    pairs_df = pairs_df.sort_values("mean_abs_interaction", ascending=False)

    print(f"\n=== Main-effect SHAP magnitude (OOS, {interaction_count} sampled symbol-months) ===")
    print(f"{'candidate':22s} {'coverage':>9s} {'mean|SHAP|':>12s}")
    for name, val in main_effect.items():
        coverage = panel[name].notna().mean()
        print(f"{name:22s} {coverage:9.1%} {val:12.5f}")

    print(
        f"\n=== Top {top_n} pairwise interactions by mean|SHAP interaction value| (all {len(pairs_df)} pairs tested) ==="
    )
    print(f"{'feature_a':22s} {'feature_b':22s} {'coverage_a':>10s} {'coverage_b':>10s} {'mean_abs_interaction':>20s}")
    for _, row in pairs_df.head(top_n).iterrows():
        cov_a = panel[row["feature_a"]].notna().mean()
        cov_b = panel[row["feature_b"]].notna().mean()
        print(
            f"{row['feature_a']:22s} {row['feature_b']:22s} {cov_a:10.1%} {cov_b:10.1%} "
            f"{row['mean_abs_interaction']:20.5f}"
        )

    print(
        "\nNOTE: this ranks WHICH pairs interact, not whether the interaction is exploitable in a "
        "robust, deployable feature - any pair here still needs the same full-sample + half-split "
        "signed-effect validation as every other Quality decision (see "
        "quality_roa_conditioned_interaction_feature_validated_not_shipped_20260827 in MEMORY.md "
        "for what that looked like for the roa x {net_margin, gross_profitability} pairs, both of "
        "which should show up somewhere in this ranking as a cross-check)."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--start-date", default="2014-01-01")
    parser.add_argument("--end-date", default=datetime.now(tz=None).date().isoformat())
    parser.add_argument("--min-test-rows", type=int, default=500)
    parser.add_argument(
        "--sample-per-fold",
        type=int,
        default=800,
        help="Rows sampled per OOS fold for interaction computation (cost is O(n^2) in feature count)",
    )
    parser.add_argument("--top-n", type=int, default=25)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run(args.start_date, args.end_date, args.min_test_rows, args.sample_per_fold, args.top_n)


if __name__ == "__main__":
    main()
