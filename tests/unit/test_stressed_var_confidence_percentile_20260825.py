"""Regression test: ValueAtRisk.stressed_var()'s worst-12-month-window percentile used to be
hardcoded to 1.0 regardless of the `confidence` argument, instead of deriving from it like
historical_var()/cvar() do (`(1-confidence)*100`). Harmless under the only real call site
(generate_daily_risk_report() always calls with no args, and (1-0.99)*100 == 1.0 by
coincidence), but a real landmine for any future caller passing a non-default confidence -
the returned "confidence_level" field would echo back whatever was passed while the actual
math silently ignored it. Fixed 2026-08-25 (money-% goal-session audit).
"""

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import numpy as np

from algo.risk.var import ValueAtRisk


def _snapshot_rows() -> list[tuple[date, float]]:
    """500 days of synthetic portfolio values with a deliberately fat-tailed 252-day
    window (days 100-352) so the 1st and 5th percentile of that window's returns are
    numerically distinguishable, and every other window is comparatively calm - this
    forces both stressed_var() calls below to select the SAME worst window, isolating
    the percentile-threshold behavior as the only variable between them.
    """
    rng = np.random.default_rng(20260825)
    n = 500
    returns = rng.normal(loc=0.0003, scale=0.004, size=n)
    returns[100:352] = rng.normal(loc=-0.001, scale=0.02, size=252)

    values = [100_000.0]
    for r in returns:
        values.append(values[-1] * (1.0 + r))

    start = date(2020, 1, 1)
    return [(start + timedelta(days=i), v) for i, v in enumerate(values)]


def _run_stressed_var(confidence: float) -> dict:
    rows = _snapshot_rows()
    mock_cur = MagicMock()
    mock_cur.fetchall.return_value = rows
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_cur

    calc = ValueAtRisk({})
    with patch("algo.risk.var.DatabaseContext", return_value=mock_ctx):
        return calc.stressed_var(confidence=confidence)


def test_stressed_var_honors_confidence_parameter() -> None:
    result_99 = _run_stressed_var(0.99)
    result_95 = _run_stressed_var(0.95)

    assert result_99["confidence_level"] == 0.99
    assert result_95["confidence_level"] == 0.95

    # 99% confidence (1st percentile) looks further into the tail than 95% (5th
    # percentile) of the SAME worst window, so it must report an equal-or-larger loss.
    # A prior bug hardcoded the percentile to 1.0 regardless of `confidence`, which
    # would make these two calls return IDENTICAL stressed_var_pct - the real bug this
    # test guards against.
    assert result_99["stressed_var_pct"] != result_95["stressed_var_pct"]
    assert result_99["stressed_var_pct"] >= result_95["stressed_var_pct"]


def test_stressed_var_matches_independently_computed_percentile() -> None:
    """Hand-verify against numpy directly: the worst 252-day window's (1-confidence)*100
    percentile of returns, computed independently here, must match what stressed_var()
    reports (converted from a % of current portfolio value back to a raw return)."""
    rows = _snapshot_rows()
    values = [v for _, v in rows]
    returns = np.array([(values[i] - values[i - 1]) / values[i - 1] for i in range(1, len(values))])

    worst_thresh = None
    for start_idx in range(len(returns) - 252):
        window = returns[start_idx : start_idx + 252]
        thresh = np.percentile(window, 5.0)
        if worst_thresh is None or abs(thresh) > abs(worst_thresh):
            worst_thresh = thresh

    result = _run_stressed_var(0.95)
    expected_pct = round(abs(worst_thresh) * 100, 3)
    assert abs(result["stressed_var_pct"] - expected_pct) < 0.01
