"""Regression tests for the dashboard's live circuit-breaker "any_triggered" indicator.

_get_data_status's Phase 2 block (lambda/api/routes/algo_handlers/market.py) used to
hardcode portfolio_drawdown_pct >= 20.0 while the real configured halt_drawdown_pct
read by algo/risk/circuit_breaker.py at halt time was -10 (halt at 10% down). A live
drawdown of 12-19% would already have halted real trading while this dashboard
indicator kept showing "OK" - a false all-clear at exactly the moment it matters
most. Thresholds must come from algo_config, the same source the real circuit
breaker reads.

'lambda' is a Python keyword, so the module under test is loaded via importlib
rather than a normal `from lambda...` import.
"""

import importlib

market_module = importlib.import_module("lambda.api.routes.algo_handlers.market")


def test_drawdown_at_real_configured_threshold_triggers():
    """A 10% drawdown must trigger when halt_drawdown_pct is configured as -10, not 20."""
    triggered = market_module._is_any_circuit_breaker_triggered(
        {
            "portfolio_drawdown_pct": 12.0,
            "daily_loss_pct": 0.0,
            "weekly_loss_pct": 0.0,
            "open_risk_pct": 1.0,
            "vix_level": 15.0,
        },
        drawdown_threshold=10.0,
        daily_loss_threshold=2.0,
        weekly_loss_threshold=5.0,
        open_risk_threshold=4.0,
        vix_threshold=35.0,
    )
    assert triggered is True


def test_all_metrics_below_threshold_not_triggered():
    triggered = market_module._is_any_circuit_breaker_triggered(
        {
            "portfolio_drawdown_pct": 5.0,
            "daily_loss_pct": 0.2,
            "weekly_loss_pct": 0.3,
            "open_risk_pct": 2.0,
            "vix_level": 18.0,
        },
        drawdown_threshold=10.0,
        daily_loss_threshold=2.0,
        weekly_loss_threshold=5.0,
        open_risk_threshold=4.0,
        vix_threshold=35.0,
    )
    assert triggered is False


def test_missing_metrics_do_not_trigger_or_crash():
    triggered = market_module._is_any_circuit_breaker_triggered(
        {
            "portfolio_drawdown_pct": None,
            "daily_loss_pct": None,
            "weekly_loss_pct": None,
            "open_risk_pct": None,
            "vix_level": None,
        },
        drawdown_threshold=10.0,
        daily_loss_threshold=2.0,
        weekly_loss_threshold=5.0,
        open_risk_threshold=4.0,
        vix_threshold=35.0,
    )
    assert triggered is False


def test_missing_algo_config_reports_unknown_not_clear():
    """If algo_config lacks a required threshold key, Phase 2 must report None
    (rendered as "status unknown" by dashboard/panels/health.py), never a
    silent "all clear" built from a guessed default.
    """
    cur = importlib.import_module("unittest.mock").MagicMock()
    # First query (algo_config) returns only 4 of the 5 required keys.
    cur.fetchall.return_value = [
        ("halt_drawdown_pct", "-10"),
        ("max_daily_loss_pct", "2.0"),
        ("max_weekly_loss_pct", "5.0"),
        ("vix_max_threshold", "35.0"),
    ]

    execution_health: dict = {}
    market_module._collect_phase2_circuit_breakers(cur, execution_health)
    assert execution_health["phase_2_circuit_breakers"] is None
