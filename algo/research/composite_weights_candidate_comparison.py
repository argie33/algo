#!/usr/bin/env python3
"""
Multi-candidate, multi-year walk-forward comparison of composite_score pillar-weighting
philosophies - built 2026-09-15 (/goal session, direct follow-up to
composite_weights_shrinkage_optimal.py) because a single fit-2017-2021/holdout-2022-2026 split
answered "does naive optimization beat equal-weight" (no - see that script) but NOT the
separate, harder question this session's user explicitly raised: is flat equal-weight itself
actually the right composite, or does it just happen to be the least-overfit of the two options
tested so far? Two real, long-running published systems (IBD Composite Rating, Zacks Rank) both
concentrate weight on growth+momentum rather than weighting 5 pillars flat - worth testing as a
genuine candidate, not copied verbatim (their exact formulas are proprietary/not fully public)
but as a directionally-faithful philosophy, same "fidelity to a real methodology" standard the
Two-Layer Validation Policy in pillar_weights.py already applies at the pillar level.

METHOD: every candidate below is a STATIC weight vector (no per-fold refitting - refitting a
"data-driven" candidate on each expanding window would just reintroduce the overfitting risk
this whole investigation exists to rule out). Each is evaluated on 5 INDEPENDENT holdout years
(2022-2026 individually, not pooled) so a candidate has to win most years, not just win on
average - the same era-robustness bar (many blocks, not one 50/50 split) this repo's own
governance policy already requires elsewhere. grinold_kahn_shrunk is fit ONCE on 2017-2021 only
(same as composite_weights_shrinkage_optimal.py) and then evaluated on the same 2022-2026 years
as every static candidate - it never sees holdout data during fitting either.

FIXES the scale bug in composite_weights_shrinkage_optimal.py's shrinkage step: that script
blended the UNnormalized Sigma^-1.IC solve directly against the sum-to-1 equal-weight prior
before renormalizing, which let raw-solve components with large magnitude swamp the prior
regardless of confidence. Fixed here by L1-normalizing the raw solve to sum(abs())=1 BEFORE
blending, so the convex combination with the equal-weight prior is actually a convex combination
on a comparable scale.

Usage:
    python -m algo.research.composite_weights_candidate_comparison [options]
"""

import argparse
import logging
from datetime import datetime

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.covariance import LedoitWolf

from algo.research.composite_weights_shrinkage_optimal import _bootstrap_ic_se, _monthly_ic_series
from algo.research.fama_macbeth_composite_weights import PILLAR_COLS, build_pillar_proxy_records
from algo.research.fama_macbeth_price_factors import print_survivorship_bias_caveat
from loaders.load_stock_scores import BASE_PILLAR_WEIGHTS

logger = logging.getLogger(__name__)

# growth_proxy, value_proxy, quality_proxy, stability_proxy, momentum_proxy order (PILLAR_COLS)

CANDIDATES: dict[str, dict[str, float]] = {
    "equal_weight_current_live": {
        "growth_proxy": BASE_PILLAR_WEIGHTS["growth"],
        "value_proxy": BASE_PILLAR_WEIGHTS["value"],
        "quality_proxy": BASE_PILLAR_WEIGHTS["quality"],
        "stability_proxy": BASE_PILLAR_WEIGHTS["risk"],
        "momentum_proxy": BASE_PILLAR_WEIGHTS["momentum"],
    },
    # DIRECTIONAL approximation of IBD's own published description ("greatest weight to EPS
    # Rating and RS Rating") - not IBD's actual proprietary formula, which is not fully public.
    # Value has no analogue in the real CAN SLIM/IBD system at all; kept at a small nonzero
    # weight here (not 0) since removing a pillar outright is a separate, bigger decision than
    # this comparison is meant to make.
    "ibd_style_growth_momentum_dominant": {
        "growth_proxy": 0.38,
        "momentum_proxy": 0.32,
        "quality_proxy": 0.15,
        "stability_proxy": 0.10,
        "value_proxy": 0.05,
    },
    # DIRECTIONAL approximation of Zacks Rank's own published description (earnings-estimate-
    # revision-dominant, secondary factors much smaller) - our growth_proxy is the closest
    # analogue we have to "earnings trajectory," not a real estimate-revision reconstruction
    # (analyst_earnings_estimates has too little history for that, per this file family's own
    # documented data-depth gap).
    "zacks_style_earnings_revision_dominant": {
        "growth_proxy": 0.55,
        "momentum_proxy": 0.15,
        "quality_proxy": 0.15,
        "stability_proxy": 0.10,
        "value_proxy": 0.05,
    },
    # This repo's OWN last regression-derived composite weights before the 2026-09-11
    # uniform-equal-weight override (quality=0.20/growth=0.24/value=0.27/risk=0.19/
    # momentum=0.10) - the two pillars that were robust AND same-signed in both the imputed and
    # complete-case regimes at the time were growth and value, momentum weak/noisy. Included
    # here as a genuine third philosophy (growth+value, not growth+momentum) since our own prior
    # evidence and IBD/Zacks disagree on which second pillar matters - testing both rather than
    # picking one on priors alone.
    "prior_repo_finding_growth_value_tilt": {
        "quality_proxy": 0.20,
        "growth_proxy": 0.24,
        "value_proxy": 0.27,
        "stability_proxy": 0.19,
        "momentum_proxy": 0.10,
    },
}


def _fit_grinold_kahn_shrunk(records_fit: list[tuple[pd.Timestamp, pd.DataFrame]]) -> dict[str, float]:
    """Same Grinold-Kahn + Ledoit-Wolf + James-Stein-style shrinkage as
    composite_weights_shrinkage_optimal.py, with the scale bug fixed: the raw Sigma^-1.IC solve
    is L1-normalized to sum(abs())=1 BEFORE blending against the sum-to-1 equal-weight prior, so
    the two things being convexly combined are on a comparable scale."""
    pooled_fit = pd.concat([f for _, f in records_fit], ignore_index=True)
    x = pooled_fit[PILLAR_COLS].values
    lw = LedoitWolf().fit(x)
    sigma = lw.covariance_

    ic_diag: dict[str, tuple[float, float]] = {}
    ic_vec = np.zeros(len(PILLAR_COLS))
    for i, col in enumerate(PILLAR_COLS):
        series = _monthly_ic_series(records_fit, col)
        mean_ic = float(series.mean())
        se_ic = _bootstrap_ic_se(series)
        ic_diag[col] = (mean_ic, se_ic)
        ic_vec[i] = mean_ic

    w_raw_arr = np.linalg.solve(sigma, ic_vec)
    l1_norm = np.abs(w_raw_arr).sum()
    w_raw_normed = w_raw_arr / l1_norm if l1_norm > 0 else w_raw_arr

    equal = 1.0 / len(PILLAR_COLS)
    w_shrunk_arr = np.zeros(len(PILLAR_COLS))
    for i, col in enumerate(PILLAR_COLS):
        mean_ic, se_ic = ic_diag[col]
        confidence = min(1.0, abs(mean_ic) / se_ic / 3.0) if se_ic > 0 else 0.0
        sign = np.sign(w_raw_normed[i]) or 1.0
        w_shrunk_arr[i] = confidence * w_raw_normed[i] + (1.0 - confidence) * equal * sign

    w_shrunk_arr = w_shrunk_arr / w_shrunk_arr.sum()
    return dict(zip(PILLAR_COLS, w_shrunk_arr.tolist(), strict=True))


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
    _records_partial, records_complete, _records_raw = build_pillar_proxy_records(
        start_date, end_date, min_cross_section
    )
    if not records_complete:
        raise RuntimeError("No complete-case months available")

    fit = [(m, f) for m, f in records_complete if m.year <= 2021]
    if not fit:
        raise RuntimeError("No fit-period (<=2021) months available to fit grinold_kahn_shrunk")

    candidates = dict(CANDIDATES)
    candidates["grinold_kahn_shrunk_fixed"] = _fit_grinold_kahn_shrunk(fit)

    holdout_years = sorted({m.year for m, _f in records_complete if m.year >= 2022})
    print(f"\nHoldout years available: {holdout_years}")
    print(
        "(grinold_kahn_shrunk_fixed fit ONLY on 2017-2021, same as every static candidate - none see holdout during fitting)\n"
    )

    results: dict[str, dict[int, float]] = {name: {} for name in candidates}
    for year in holdout_years:
        year_records = [(m, f) for m, f in records_complete if m.year == year]
        for name, weights in candidates.items():
            results[name][year] = _composite_ic_for_months(year_records, weights)

    header = (
        f"{'candidate':38s}" + "".join(f"{y:>9d}" for y in holdout_years) + f"{'mean':>9s}{'min':>9s}{'#yrs>0':>8s}"
    )
    print(header)
    print("-" * len(header))
    for name in candidates:
        ics = [results[name][y] for y in holdout_years]
        mean_ic = float(np.mean(ics))
        min_ic = float(np.min(ics))
        n_pos = sum(1 for v in ics if v > 0)
        row = f"{name:38s}" + "".join(f"{v:9.4f}" for v in ics) + f"{mean_ic:9.4f}{min_ic:9.4f}{n_pos:8d}/{len(ics)}"
        print(row)

    print(
        "\nEra-robustness bar (this repo's own standard, applied here across 5 independent "
        "years instead of one split): a candidate only counts as genuinely better than "
        "equal-weight if it beats equal-weight's MIN across years (worst-case year), not just "
        "its mean - a candidate that wins on average by doing great in 1-2 years and badly in "
        "others is the same overfitting pattern the fit/holdout test already caught once."
    )
    print("\nWeights used:")
    for name, w in candidates.items():
        print(f"  {name}: " + ", ".join(f"{k}={v:.3f}" for k, v in w.items()))
    print("\nNo production weight was changed by this script.")


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
