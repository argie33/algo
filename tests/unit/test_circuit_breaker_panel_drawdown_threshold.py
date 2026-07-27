"""Regression test: the Circuit Breaker panel API (_get_circuit_breakers) must read
all its halt thresholds from algo_config, not hardcoded literals.

Bug: CB1 hardcoded threshold_dd = 20.0, independent of the real configured
halt_drawdown_pct algo/risk/circuit_breaker.py reads from algo_config at halt time
(-10, i.e. halt at 10% down). A live 12-19% drawdown would already have halted real
trading while this panel still reported "triggered": False for the same condition.
Same bug class already fixed in market.py's _get_data_status (commit 2a5a41c78) and
loaders/compute_circuit_breakers.py (commit bca23264d).

CB2 (daily_loss), CB3 (consecutive_losses), CB4 (vix), CB5 (weekly_loss), and CB7
(total_risk) had the identical hardcoded-literal bug - just not observable until an
operator actually tuned one of those algo_config values away from its seeded default,
since the hardcoded literals happened to match the defaults. Fixed alongside CB1 to
read live from the same multi-key algo_config query.

'lambda' is a Python keyword, so the module under test is loaded via importlib
rather than a normal `from lambda...` import.
"""

import importlib
from datetime import date, datetime
from unittest.mock import MagicMock

dashboard_module = importlib.import_module("lambda.api.routes.algo_handlers.dashboard")

_CB_DEFAULTS = {
    "halt_drawdown_pct": "-10",
    "max_daily_loss_pct": "2.0",
    "max_consecutive_losses": "3",
    "vix_max_threshold": "35.0",
    "max_weekly_loss_pct": "5.0",
    "max_total_risk_pct": "4.0",
}


def _make_cursor(
    drawdown_pct: float = 5.0,
    daily_loss_pct: float = 0.0,
    weekly_loss_pct: float = 0.0,
    open_risk_pct: float = 1.0,
    consecutive_losses: int = 0,
    vix_level: float = 15.0,
    config_overrides: dict[str, str] | None = None,
):
    cur = MagicMock()
    cb_cfg = {**_CB_DEFAULTS, **(config_overrides or {})}

    def execute_side_effect(query, params=None):
        if isinstance(query, str):
            cur._last_query = query.lower()

    cur.execute.side_effect = execute_side_effect

    def fetchone_side_effect():
        q = cur._last_query
        if "select 1 from" in q:
            return (1,)
        if "from circuit_breaker_status" in q:
            return {
                "portfolio_drawdown_pct": drawdown_pct,
                "daily_loss_pct": daily_loss_pct,
                "weekly_loss_pct": weekly_loss_pct,
                "open_risk_pct": open_risk_pct,
                "consecutive_losses": consecutive_losses,
                "vix_level": vix_level,
                "market_stage": 2,
                "check_date": date.today(),
            }
        return None

    def fetchall_side_effect():
        q = cur._last_query
        if "from algo_config" in q:
            # Mirrors the multi-key threshold fetch in _get_circuit_breakers.
            return list(cb_cfg.items())
        if "from price_daily" in q:
            # CB8 (intraday market health) needs 2 SPY closes; flat (no move) so it
            # never triggers and doesn't interfere with other breakers' assertions.
            return [(100.0,), (100.0,)]
        return []

    cur.fetchone.side_effect = fetchone_side_effect
    cur.fetchall.side_effect = fetchall_side_effect
    return cur


def test_circuit_breaker_panel_uses_configured_drawdown_threshold_not_20pct():
    """A 12% drawdown must show triggered=True when halt_drawdown_pct is -10, not 20."""
    from unittest.mock import patch

    cur = _make_cursor(drawdown_pct=12.0, config_overrides={"halt_drawdown_pct": "-10"})

    with patch("algo.infrastructure.MarketCalendar.is_trading_day", return_value=True):
        result = dashboard_module._get_circuit_breakers(cur)

    body = result.get("data", result)
    drawdown_breaker = next(b for b in body["breakers"] if b["id"] == "drawdown")
    assert float(drawdown_breaker["threshold"]) == 10.0
    assert drawdown_breaker["triggered"] is True


def test_circuit_breaker_panel_uses_configured_daily_loss_threshold_not_hardcoded_2pct():
    """A 1.2% daily loss must show triggered=True when max_daily_loss_pct is tightened to 1.0,
    even though the old hardcoded literal (2.0) would have reported "not triggered"."""
    from unittest.mock import patch

    cur = _make_cursor(daily_loss_pct=1.2, config_overrides={"max_daily_loss_pct": "1.0"})

    with patch("algo.infrastructure.MarketCalendar.is_trading_day", return_value=True):
        result = dashboard_module._get_circuit_breakers(cur)

    body = result.get("data", result)
    daily_loss_breaker = next(b for b in body["breakers"] if b["id"] == "daily_loss")
    assert float(daily_loss_breaker["threshold"]) == 1.0
    assert daily_loss_breaker["triggered"] is True


def test_circuit_breaker_panel_missing_config_key_fails_closed_with_error():
    """If algo_config is missing a required circuit breaker key, the panel must return
    an error response (not silently fall back to a hardcoded default)."""
    cur = _make_cursor()
    cur._last_query = ""

    def fetchall_missing_max_total_risk():
        q = cur._last_query
        if "from algo_config" in q:
            return [(k, v) for k, v in _CB_DEFAULTS.items() if k != "max_total_risk_pct"]
        if "from price_daily" in q:
            return [(100.0,), (100.0,)]
        return []

    cur.fetchall.side_effect = fetchall_missing_max_total_risk

    result = dashboard_module._get_circuit_breakers(cur)
    body = result.get("data", result)
    # Missing config key must fail closed via the error path (never silently substitute
    # a hardcoded default for the missing threshold, and never return a computed breaker list).
    assert "breakers" not in body
    assert body.get("statusCode", 400) >= 400
