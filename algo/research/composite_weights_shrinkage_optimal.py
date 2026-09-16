#!/usr/bin/env python3
"""
Grinold-Kahn optimal multi-factor combining for the composite_score pillar weights, with
Ledoit-Wolf + James-Stein shrinkage - the industry-standard answer (Grinold & Kahn, *Active
Portfolio Management*, the standard institutional multi-factor combination reference; this is
the alpha-combination analogue of what Barra/Axioma do for risk models) to the question the
2026-09-11 "uniform equal-weight, nothing clears |t|>=2" decision in
loaders/stock_scores/pillar_weights.py punted on.

Built 2026-09-15 (/goal session: "what does the industry do... someone has figured out the best
right way to do this for the composite").

WHY EQUAL-WEIGHT WAS THE WRONG TOOL FOR THE QUESTION IT WAS ANSWERING: the existing
fama_macbeth_composite_weights.py decision rule judges each pillar's coefficient INDEPENDENTLY
against a hard |t|>=2 significance threshold, and falls back to equal weight for whichever
pillars don't clear it. That is a per-pillar hypothesis test, not a combination method - it
throws away the pillar-pillar covariance structure entirely (two correlated-but-individually-
noisy pillars can combine into a real joint signal that neither clears alone) and treats "not
significant" as "exactly zero incremental information," which is not what a noisy point
estimate means. A plain multivariate OLS coefficient (what that script's _fama_macbeth already
computes) IS mathematically Sigma^-1 . cov(X, y) - so the raw ingredients already exist; what's
missing is (a) not discarding the off-diagonal covariance information via independent per-pillar
gating, and (b) shrinking continuously toward the equal-weight prior by ESTIMATION CONFIDENCE
rather than binarizing on a threshold.

METHOD:
  1. Build the same pillar-proxy panel build_pillar_proxy_records() already builds (verified-live
     pillar formulas, no new data pipeline) - complete-case regime only, matching this repo's own
     "complete-case is the trustworthy regime, imputed is the diagnostic" standard.
  2. FIT period 2017-2021 / HOLDOUT period 2022-2026 (same split as
     barra_style_neutralized_composite_20260907.py - holdout genuinely never touched while
     iterating on method, per the WEIGHT-REVISION GOVERNANCE POLICY in pillar_weights.py).
  3. On FIT only: per-pillar monthly IC (cross-sectional Spearman rank correlation of pillar
     z-score vs. next-month forward return) -> mean IC vector `ic`.
  4. On FIT only: Ledoit-Wolf shrunk covariance matrix of the 5 pillar z-scores (pooled) -> Sigma.
     Ledoit-Wolf (not the raw sample covariance) specifically because a raw small-sample
     correlation matrix is itself noisy - inverting it directly (as a naive Sigma^-1 . ic
     computation would) is unstable and over-weights whichever pillar pair happens to look most
     correlated in this particular sample; shrinking Sigma toward a diagonal target before
     inverting is the standard fix (Ledoit & Wolf 2004).
  5. Raw Grinold-Kahn weights: w_raw = Sigma^-1 . ic (this is the real formula - the "combine by
     IC, adjusted for cross-factor correlation" analogue of Barra's factor-covariance machinery,
     not a hand-built interaction term like the retired VALUE_RISK_INTERACTION).
  6. James-Stein-style shrinkage of w_raw toward the equal-weight prior (1/5 each), shrinkage
     intensity per-pillar set by that pillar's own IC t-stat confidence (bootstrap block
     resampling of the monthly IC series, not the raw z-score panel, so the shrinkage intensity
     reflects genuine month-to-month IC estimation uncertainty) - continuous, not the existing
     binary |t|>=2 keep/reject gate.
  7. Validate BOTH w_raw and w_shrunk against the TRUE holdout (2022-2026, never touched during
     steps 3-6) via composite-level Spearman IC, compared against the current live equal-weight
     composite on the exact same holdout months. Also report FIT-period IC for the same three
     weight vectors so overfitting (large fit/holdout IC gap) is visible, not hidden.

This script does NOT modify BASE_PILLAR_WEIGHTS - it reports what the method recommends so a
human can review the fit-vs-holdout evidence before any production change, per this file's own
governance policy (never same-session act-and-ship on a single run).

Usage:
    python -m algo.research.composite_weights_shrinkage_optimal [options]
"""

import argparse
import logging
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.covariance import LedoitWolf

from algo.research.fama_macbeth_composite_weights import PILLAR_COLS, build_pillar_proxy_records
from algo.research.fama_macbeth_price_factors import print_survivorship_bias_caveat
from loaders.load_stock_scores import BASE_PILLAR_WEIGHTS

logger = logging.getLogger(__name__)

N_BOOTSTRAP = 2000
RNG_SEED = 0


def _monthly_ic_series(
    records: list[tuple[pd.Timestamp, pd.DataFrame]], col: str
) -> np.ndarray[Any, np.dtype[np.float64]]:
    """Per-month cross-sectional Spearman IC of one pillar column vs. fwd_ret."""
    ics = []
    for _month, frame in records:
        ic, _p = stats.spearmanr(frame[col].values, frame["fwd_ret"].values)
        if np.isfinite(ic):
            ics.append(ic)
    return np.array(ics)


def _bootstrap_ic_se(
    ic_series: np.ndarray[Any, np.dtype[np.float64]], n_boot: int = N_BOOTSTRAP, seed: int = RNG_SEED
) -> float:
    """Block-free i.i.d. bootstrap SE of the mean monthly IC - adequate here since the shrinkage
    step only needs a confidence WEIGHT per pillar, not a publishable t-stat (that's what the
    existing fama_macbeth_composite_weights.py FM t-stats are for)."""
    rng = np.random.default_rng(seed)
    n = len(ic_series)
    boot_means = np.array([rng.choice(ic_series, size=n, replace=True).mean() for _ in range(n_boot)])
    return float(boot_means.std(ddof=1))


def compute_grinold_kahn_weights(
    records_fit: list[tuple[pd.Timestamp, pd.DataFrame]],
) -> tuple[dict[str, float], dict[str, float], dict[str, tuple[float, float]]]:
    """Returns (w_raw, w_shrunk, ic_diagnostics) where ic_diagnostics[col] = (mean_ic, se_ic)."""
    pooled_fit = pd.concat([f for _, f in records_fit], ignore_index=True)
    x = pooled_fit[PILLAR_COLS].values

    lw = LedoitWolf().fit(x)
    sigma = lw.covariance_
    logger.info(f"Ledoit-Wolf shrinkage intensity: {lw.shrinkage_:.4f} (0=no shrinkage, 1=fully diagonal)")

    ic_diag: dict[str, tuple[float, float]] = {}
    ic_vec = np.zeros(len(PILLAR_COLS))
    for i, col in enumerate(PILLAR_COLS):
        series = _monthly_ic_series(records_fit, col)
        mean_ic = float(series.mean())
        se_ic = _bootstrap_ic_se(series)
        ic_diag[col] = (mean_ic, se_ic)
        ic_vec[i] = mean_ic

    w_raw_arr = np.linalg.solve(sigma, ic_vec)
    w_raw = dict(zip(PILLAR_COLS, w_raw_arr.tolist(), strict=True))

    # James-Stein-style continuous shrinkage toward equal-weight, confidence = |mean_ic| / se_ic
    # (a z-score-shaped confidence, but used as a smooth blend weight, not a threshold gate).
    equal = 1.0 / len(PILLAR_COLS)
    w_shrunk_arr = np.zeros(len(PILLAR_COLS))
    for i, col in enumerate(PILLAR_COLS):
        mean_ic, se_ic = ic_diag[col]
        confidence = min(1.0, abs(mean_ic) / se_ic / 3.0) if se_ic > 0 else 0.0
        w_shrunk_arr[i] = confidence * w_raw_arr[i] + (1.0 - confidence) * equal * np.sign(w_raw_arr[i] or 1.0)

    # Renormalize both to sum to 1.0 over their signed values so they're comparable composite
    # weight vectors against BASE_PILLAR_WEIGHTS (which also sums to 1.0) - preserves sign/
    # relative magnitude, only rescales the overall level.
    w_raw_arr = w_raw_arr / w_raw_arr.sum()
    w_shrunk_arr = w_shrunk_arr / w_shrunk_arr.sum()
    w_raw = dict(zip(PILLAR_COLS, w_raw_arr.tolist(), strict=True))
    w_shrunk = dict(zip(PILLAR_COLS, w_shrunk_arr.tolist(), strict=True))
    return w_raw, w_shrunk, ic_diag


def _composite_ic(records: list[tuple[pd.Timestamp, pd.DataFrame]], weights: dict[str, float]) -> tuple[float, float]:
    """Pooled monthly-mean Spearman IC of a weighted composite score across `records`, plus its
    month-to-month std (for an eyeball stability comparison, not a formal t-stat - the FM script
    already owns t-stat reporting for this data)."""
    ics = []
    for _month, frame in records:
        composite = sum(frame[c].values * w for c, w in weights.items())
        ic, _p = stats.spearmanr(composite, frame["fwd_ret"].values)
        if np.isfinite(ic):
            ics.append(ic)
    arr = np.array(ics)
    return float(arr.mean()), float(arr.std(ddof=1))


def run(start_date: str, end_date: str, min_cross_section: int) -> None:
    print_survivorship_bias_caveat()
    _records_partial, records_complete, _records_raw = build_pillar_proxy_records(
        start_date, end_date, min_cross_section
    )
    if not records_complete:
        raise RuntimeError("No complete-case months - cannot compute a trustworthy covariance/IC estimate")

    fit = [(m, f) for m, f in records_complete if m.year <= 2021]
    holdout = [(m, f) for m, f in records_complete if m.year >= 2022]
    if not fit or not holdout:
        raise RuntimeError(f"Fit/holdout split produced an empty side (fit={len(fit)}, holdout={len(holdout)})")

    print(f"\n########## FIT 2017-2021 ({len(fit)} months) - method fit here, never re-touched below ##########")
    w_raw, w_shrunk, ic_diag = compute_grinold_kahn_weights(fit)

    print(
        f"\n{'pillar':18s} {'mean_IC':>9s} {'boot_SE':>9s} {'IC/SE':>7s} {'w_raw':>8s} {'w_shrunk':>9s} {'w_equal(live)':>14s}"
    )
    live_key_map = {
        "growth_proxy": "growth",
        "value_proxy": "value",
        "quality_proxy": "quality",
        "stability_proxy": "risk",
        "momentum_proxy": "momentum",
    }
    for col in PILLAR_COLS:
        mean_ic, se_ic = ic_diag[col]
        ratio = mean_ic / se_ic if se_ic > 0 else float("nan")
        live_w = BASE_PILLAR_WEIGHTS[live_key_map[col]]
        print(
            f"{col:18s} {mean_ic:9.4f} {se_ic:9.4f} {ratio:7.2f} {w_raw[col]:8.3f} {w_shrunk[col]:9.3f} {live_w:14.3f}"
        )

    fit_ic_raw, fit_sd_raw = _composite_ic(fit, w_raw)
    fit_ic_shrunk, fit_sd_shrunk = _composite_ic(fit, w_shrunk)
    fit_ic_equal, fit_sd_equal = _composite_ic(fit, base_pillar_weights_as_proxy_keys())

    print(f"\n########## TRUE HOLDOUT 2022-2026 ({len(holdout)} months) - NEVER touched above ##########")
    ho_ic_raw, ho_sd_raw = _composite_ic(holdout, w_raw)
    ho_ic_shrunk, ho_sd_shrunk = _composite_ic(holdout, w_shrunk)
    ho_ic_equal, ho_sd_equal = _composite_ic(holdout, base_pillar_weights_as_proxy_keys())

    print(
        f"\n{'weighting':22s} {'fit_IC':>9s} {'fit_sd':>8s} {'holdout_IC':>11s} {'holdout_sd':>11s} {'fit->holdout gap':>17s}"
    )
    for name, (fi, fs, hi, hs) in {
        "grinold_kahn_raw": (fit_ic_raw, fit_sd_raw, ho_ic_raw, ho_sd_raw),
        "grinold_kahn_shrunk": (fit_ic_shrunk, fit_sd_shrunk, ho_ic_shrunk, ho_sd_shrunk),
        "live_equal_weight": (fit_ic_equal, fit_sd_equal, ho_ic_equal, ho_sd_equal),
    }.items():
        print(f"{name:22s} {fi:9.4f} {fs:8.4f} {hi:11.4f} {hs:11.4f} {fi - hi:17.4f}")

    print(
        "\nInterpretation: holdout_IC is the only number that matters for a production decision - "
        "fit_IC is expected to look better than holdout for ANY method (that's what 'fit' means) "
        "and a large positive fit->holdout gap is the overfitting signal this comparison exists "
        "to surface. grinold_kahn_shrunk beating live_equal_weight on HOLDOUT IC, with a gap no "
        "worse than live_equal_weight's own gap, is the bar for treating shrinkage as evidence "
        "over the current flat weights - not the fit-period number alone, and not this script's "
        "own single run without a second, later re-verification per this file's governance policy."
    )
    print("\nNo production weight was changed by this script. BASE_PILLAR_WEIGHTS is untouched.")


def base_pillar_weights_as_proxy_keys() -> dict[str, float]:
    return {
        "growth_proxy": BASE_PILLAR_WEIGHTS["growth"],
        "value_proxy": BASE_PILLAR_WEIGHTS["value"],
        "quality_proxy": BASE_PILLAR_WEIGHTS["quality"],
        "stability_proxy": BASE_PILLAR_WEIGHTS["risk"],
        "momentum_proxy": BASE_PILLAR_WEIGHTS["momentum"],
    }


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
