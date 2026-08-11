"""Regression tests for loaders/compute_circuit_breakers.py's threshold sourcing and
comparison precision.

Bug 1 (threshold hardcoding): CB1 hardcoded portfolio_drawdown_pct >= 20.0, independent
of the real configured halt_drawdown_pct (-10, i.e. halt at 10% down) that
algo/risk/circuit_breaker.py reads at halt time. Thresholds now come live from
algo_config, the same source the real halt gate uses.

Bug 2 (round-before-compare): _compute_open_risk (and drawdown/daily_loss/weekly_loss/
vix/spy_change/win_rate) used to round() the computed value BEFORE storing it in the
metrics dict used for the any_triggered/triggered_count comparison. A raw value of
3.9966% rounds to 4.00%, which then compares as triggered (>= 4.0) even though the real
circuit_breaker.py compares the raw, unrounded 3.9966% (not triggered). This was caught
live: the exact same portfolio state produced "any_triggered=True" from this loader and
"all clear" from Phase 2's real check in the same orchestrator run. Values are no longer
rounded before the trigger comparison.
"""

import importlib
from unittest.mock import MagicMock

module = importlib.import_module("loaders.compute_circuit_breakers")


def _mock_cursor(config_rows):
    cur = MagicMock()
    cur.fetchall.return_value = config_rows
    return cur


def test_open_risk_threshold_reads_from_algo_config_not_hardcoded():
    """halt_drawdown_pct=-10 in config must produce a 10.0 threshold, not the old 20.0."""
    cur = _mock_cursor(
        [
            {"key": "halt_drawdown_pct", "value": "-10"},
            {"key": "max_daily_loss_pct", "value": "2.0"},
            {"key": "max_weekly_loss_pct", "value": "5.0"},
            {"key": "max_total_risk_pct", "value": "4.0"},
            {"key": "vix_max_threshold", "value": "35.0"},
            {"key": "max_consecutive_losses", "value": "3"},
            {"key": "min_win_rate_pct", "value": "40"},
        ]
    )
    breakers = module._build_circuit_breakers(cur)
    cb1 = next(cb for cb in breakers if cb.name == "CB1")
    assert cb1.threshold == 10.0


def test_raw_unrounded_value_below_threshold_does_not_trigger():
    """A raw 3.9966% must NOT trigger a >=4.0 threshold, even though round(3.9966, 2) == 4.0.

    This is the exact live case: real open risk was 2872.7824 / 71885.26 * 100 =
    3.9966...%, which the buggy rounded-then-compared version flagged as triggered.
    """
    cur = _mock_cursor(
        [
            {"key": "halt_drawdown_pct", "value": "-10"},
            {"key": "max_daily_loss_pct", "value": "2.0"},
            {"key": "max_weekly_loss_pct", "value": "5.0"},
            {"key": "max_total_risk_pct", "value": "4.0"},
            {"key": "vix_max_threshold", "value": "35.0"},
            {"key": "max_consecutive_losses", "value": "3"},
            {"key": "min_win_rate_pct", "value": "40"},
        ]
    )
    breakers = module._build_circuit_breakers(cur)

    metrics = {
        "portfolio_drawdown_pct": 5.18,
        "daily_loss_pct": 0.0,
        "weekly_loss_pct": 0.2,
        "consecutive_losses": 1,
        "open_risk_pct": 3.996344174035123,
        "vix_level": 18.6,
        "market_stage": 2,
        "spy_prior_day_change_pct": 0.1,
        "win_rate_last_30_pct": 48.0,
    }
    assert module._check_any_triggered(metrics, breakers) is False
    assert module._count_triggered(metrics, breakers) == 0


def test_value_genuinely_at_or_over_threshold_still_triggers():
    cur = _mock_cursor(
        [
            {"key": "halt_drawdown_pct", "value": "-10"},
            {"key": "max_daily_loss_pct", "value": "2.0"},
            {"key": "max_weekly_loss_pct", "value": "5.0"},
            {"key": "max_total_risk_pct", "value": "4.0"},
            {"key": "vix_max_threshold", "value": "35.0"},
            {"key": "max_consecutive_losses", "value": "3"},
            {"key": "min_win_rate_pct", "value": "40"},
        ]
    )
    breakers = module._build_circuit_breakers(cur)

    metrics = {
        "portfolio_drawdown_pct": 12.0,
        "daily_loss_pct": 0.0,
        "weekly_loss_pct": 0.2,
        "consecutive_losses": 1,
        "open_risk_pct": 1.0,
        "vix_level": 18.6,
        "market_stage": 2,
        "spy_prior_day_change_pct": 0.1,
        "win_rate_last_30_pct": 48.0,
    }
    assert module._check_any_triggered(metrics, breakers) is True


def test_missing_config_key_raises():
    cur = _mock_cursor(
        [
            {"key": "halt_drawdown_pct", "value": "-10"},
            {"key": "max_daily_loss_pct", "value": "2.0"},
        ]
    )
    try:
        module._build_circuit_breakers(cur)
        raise AssertionError("expected ValueError for missing config keys")
    except ValueError as e:
        assert "missing required circuit breaker keys" in str(e)
