#!/usr/bin/env python3
"""
Isolates residual_mom_12_1 (Blitz/Huij/Martens 2011 residual momentum) from mom_12_1 to resolve
an ambiguous result in momentum_52wk_industry_residual_reversal_candidates.py: multivariate
(controlled for mom_12_1) cleared |t|>2 (t=-2.04 full, -3.08 second-half) but raw univariate was
weak throughout (-0.34/-0.36/-0.13) - residual_mom_12_1 is a near-linear function of mom_12_1
(residual = mom_12_1 - beta*mkt_mom_12_1), so the multivariate result could be a collinearity
artifact rather than independent signal.

Mirrors loaders/load_stock_scores.py's _score_risk docstring precedent for max_drawdown_1y's own
resolved multivariate-vs-univariate ambiguity: univariate-only regression, Newey-West(3-lag)
HAC-adjusted SE (statsmodels not in this repo's pinned requirements - implemented manually via
the standard Bartlett-kernel formula, not a new dependency), plus half-split and tercile
sub-period splits.

Usage:
    python -m algo.research.momentum_residual_univariate_isolation_check
"""

import logging
from typing import Any

import numpy as np
import pandas as pd

from algo.research.fama_macbeth_price_factors import _fama_macbeth
from algo.research.momentum_52wk_industry_residual_reversal_candidates import (
    build_month_end_panel,
    build_records,
    fetch_daily_prices,
    fetch_sectors,
)

logger = logging.getLogger(__name__)


def _coef_series(records: list[tuple[pd.Timestamp, pd.DataFrame]], col: str) -> np.ndarray[Any, Any]:
    """Per-month univariate OLS coefficient (const + col only) - same construction _fama_macbeth
    uses internally, extracted here so we can apply a HAC correction to the resulting series."""
    coefs = []
    for _month, frame in records:
        x = np.column_stack([np.ones(len(frame)), frame[col].values])
        y = frame["fwd_ret"].values
        c, *_ = np.linalg.lstsq(x, y, rcond=None)
        coefs.append(c[1])
    return np.array(coefs)


def _newey_west_tstat(x: np.ndarray[Any, Any], lags: int = 3) -> tuple[float, float, float]:
    """Newey-West HAC-adjusted t-stat for the sample mean of a time series (Bartlett kernel).
    Returns (mean, naive_t, hac_t)."""
    n = len(x)
    mean = x.mean()
    demeaned = x - mean
    gamma0 = float(np.sum(demeaned * demeaned)) / n
    var = gamma0
    for lag in range(1, lags + 1):
        w = 1.0 - lag / (lags + 1)
        gamma_l = float(np.sum(demeaned[lag:] * demeaned[: n - lag])) / n
        var += 2.0 * w * gamma_l
    se_naive = x.std(ddof=1) / np.sqrt(n)
    se_hac = np.sqrt(max(var, 0.0) / n)
    naive_t = mean / se_naive if se_naive > 0 else float("nan")
    hac_t = mean / se_hac if se_hac > 0 else float("nan")
    return mean, naive_t, hac_t


def run() -> None:
    daily = fetch_daily_prices("2014-01-01", "2026-08-27")
    sectors = fetch_sectors()
    px, prox = build_month_end_panel(daily)
    records = build_records(px, prox, sectors, beta_window=24, min_cross_section=100)
    print(f"Usable months: {len(records)} ({records[0][0]} to {records[-1][0]})")

    col = "residual_mom_12_1"
    coefs = _coef_series(records, col)

    mean, naive_t, hac_t = _newey_west_tstat(coefs, lags=3)
    print(f"\n=== FULL SAMPLE univariate-only {col} ===")
    print(f"mean_coef={mean:.5f}  naive_t={naive_t:.2f}  newey_west(3lag)_t={hac_t:.2f}  n_months={len(coefs)}")

    # Cross-check against _fama_macbeth's own naive t-stat for the same univariate spec.
    uni_check = _fama_macbeth(records, [col])
    print(f"(cross-check via _fama_macbeth: t={uni_check[col][1]:.2f} - should match naive_t above)")

    split = len(records) // 2
    halves = [
        (f"FIRST HALF ({records[0][0]} to {records[split - 1][0]})", coefs[:split]),
        (f"SECOND HALF ({records[split][0]} to {records[-1][0]})", coefs[split:]),
    ]
    for label, sub in halves:
        m, nt, ht = _newey_west_tstat(sub, lags=3)
        print(f"\n=== {label} ===")
        print(f"mean_coef={m:.5f}  naive_t={nt:.2f}  newey_west(3lag)_t={ht:.2f}  n_months={len(sub)}")

    n = len(coefs)
    t1, t2 = n // 3, 2 * n // 3
    terciles = [
        (f"TERCILE 1 ({records[0][0]} to {records[t1 - 1][0]})", coefs[:t1]),
        (f"TERCILE 2 ({records[t1][0]} to {records[t2 - 1][0]})", coefs[t1:t2]),
        (f"TERCILE 3 ({records[t2][0]} to {records[-1][0]})", coefs[t2:]),
    ]
    print("\n=== TERCILES ===")
    for label, sub in terciles:
        m, nt, ht = _newey_west_tstat(sub, lags=3)
        print(f"{label}: mean_coef={m:.5f}  naive_t={nt:.2f}  newey_west(3lag)_t={ht:.2f}  n_months={len(sub)}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run()
