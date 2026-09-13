"""Regression test for the 2026-09-13 fix: `_fama_macbeth` gained an optional `hac_lags`
parameter (Newey-West HAC-corrected standard error) so overlapping-forward-return-window
callers (e.g. fama_macbeth_growth_factors.py's horizon_months>1 path) and any other
serial-correlation-sensitive analysis can get a properly corrected t-stat instead of only a
printed warning to "treat the magnitude with more skepticism".

Covers: (1) default (hac_lags=None) behavior is byte-for-byte unchanged from before this fix -
no existing conclusion silently changes; (2) an artificially strongly-autocorrelated
coefficient series produces a HAC t-stat that is smaller in magnitude than the naive one (HAC
should never UNDERSTATE the true uncertainty introduced by positive autocorrelation); (3) a
white-noise (zero-autocorrelation) series' naive and HAC t-stats are close to each other,
confirming HAC doesn't spuriously inflate/deflate significance when there is no serial
correlation to correct for.
"""

import numpy as np
import pandas as pd
import pytest

from algo.research.fama_macbeth_price_factors import _fama_macbeth, newey_west_se


def _records_from_coef_series(coefs: list[float]) -> list[tuple[pd.Timestamp, pd.DataFrame]]:
    """Build a minimal records list whose per-month univariate _fama_macbeth OLS coefficient
    on "x" is exactly the given value - two symbols per month is enough to pin down the OLS
    solution for a single regressor plus intercept."""
    records = []
    for i, c in enumerate(coefs):
        month = pd.Timestamp("2020-01-01") + pd.DateOffset(months=i)
        frame = pd.DataFrame({"x": [0.0, 1.0], "fwd_ret": [0.0, c]})
        records.append((month, frame))
    return records


class TestFamaMacBethHacLags:
    def test_default_hac_lags_none_matches_pre_fix_naive_formula(self) -> None:
        coefs = [0.01, -0.02, 0.03, 0.015, -0.01, 0.02, -0.005, 0.01, 0.0, 0.025]
        records = _records_from_coef_series(coefs)
        mean, t = _fama_macbeth(records, ["x"])["x"]
        arr = np.array(coefs)
        expected_mean = arr.mean()
        expected_se = arr.std(ddof=1) / np.sqrt(len(arr))
        assert mean == pytest.approx(expected_mean)
        assert t == pytest.approx(expected_mean / expected_se)

    def test_hac_shrinks_tstat_for_strongly_autocorrelated_series(self) -> None:
        """A strongly positively-autocorrelated coefficient series (an AR(1)-shaped run, not
        i.i.d.) understates true uncertainty under the naive formula - HAC should pull |t|
        down, not up, for this shape."""
        rng = np.random.default_rng(42)
        n = 60
        noise = rng.normal(0, 1.0, n)
        ar_series = np.zeros(n)
        for i in range(1, n):
            ar_series[i] = 0.85 * ar_series[i - 1] + noise[i]
        ar_series += 0.3  # nonzero mean so both t-stats are well-defined and comparable
        records = _records_from_coef_series(list(ar_series))
        _mean_naive, t_naive = _fama_macbeth(records, ["x"])["x"]
        _mean_hac, t_hac = _fama_macbeth(records, ["x"], hac_lags=5)["x"]
        assert abs(t_hac) < abs(t_naive)

    def test_hac_close_to_naive_for_white_noise_series(self) -> None:
        rng = np.random.default_rng(7)
        coefs = list(rng.normal(0.02, 1.0, 200))
        records = _records_from_coef_series(coefs)
        _mean_naive, t_naive = _fama_macbeth(records, ["x"])["x"]
        _mean_hac, t_hac = _fama_macbeth(records, ["x"], hac_lags=3)["x"]
        assert abs(t_hac - t_naive) / abs(t_naive) < 0.25

    def test_newey_west_se_positive_for_nonconstant_series(self) -> None:
        arr = np.array([0.01, -0.02, 0.03, 0.015, -0.01, 0.02, -0.005, 0.01, 0.0, 0.025])
        se = newey_west_se(arr, lags=3)
        assert se > 0
