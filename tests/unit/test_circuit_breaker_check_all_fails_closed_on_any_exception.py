#!/usr/bin/env python3
"""Regression test: CircuitBreaker.check_all() must fail closed (halted=True, never raise)
when ANY individual check raises, not just psycopg2.DatabaseError/OperationalError.

Found via adversarial stress-testing (deliberately injecting a plain ValueError from one
check): check_all()'s own comments claim "All check failures result in fail-closed halt" -
but its except clauses (both the per-check inner one and the whole-method outer one) only
caught (psycopg2.DatabaseError, psycopg2.OperationalError). A ValueError (e.g. a malformed
algo_config value, the exact kind _get_required_config's own callers can raise) propagated
straight out of check_all() uncaught. This only stayed safe in practice because both current
callers (phase2_circuit_breakers.py, utils/orchestrator_diagnostics.py) happen to also wrap
check_all() in their own broad `except Exception` - a landmine for any future caller that
reasonably trusts this function's own docstring instead of re-adding that same broad catch.
"""

from datetime import date
from unittest.mock import MagicMock

from algo.risk.circuit_breaker import CircuitBreaker

CONFIG = {
    "halt_drawdown_pct": -10.0,
    "max_daily_loss_pct": 2.0,
    "max_consecutive_losses": 3,
    "max_total_risk_pct": 4.0,
    "vix_max_threshold": 35.0,
    "max_weekly_loss_pct": 5.0,
    "max_positions_per_sector": 5,
    "sector_drawdown_halt_pct": -12.0,
    "min_win_rate_pct": 40.0,
    "daily_profit_cap_pct": 10.0,
    "re_engage_recovery_pct": 5.0,
    "re_engage_min_days": 3,
    "require_ftd_to_re_engage": False,
    "max_data_staleness_days": 2,
}


def test_check_all_fails_closed_when_a_check_raises_non_db_exception():
    cb = CircuitBreaker(config=dict(CONFIG))
    cur = MagicMock()
    cur.fetchone.return_value = None
    cur.fetchall.return_value = []

    def raiser(current_date, cur):
        raise ValueError("simulated bad algo_config value")

    # self._checks binds each _check_* method by reference at __init__ time, so
    # patch.object(cb, "_check_daily_loss", ...) after construction would NOT reach this -
    # must overwrite the registry entry itself to actually inject the failure.
    cb._checks["daily_loss"] = raiser

    result = cb.check_all(current_date=date(2026, 7, 24))

    assert result["halted"] is True
    assert any("daily_loss" in r.lower() or "check error" in r.lower() for r in result["halt_reasons"])


def test_check_all_fails_closed_when_a_non_db_exception_escapes_the_whole_method():
    """Exercises the OUTER except (wrapping the entire per-check loop + _log_halt), not just
    the per-check inner one - e.g. a bug in results-aggregation itself, not in a single check."""
    cb = CircuitBreaker(config=dict(CONFIG))
    cur = MagicMock()
    cur.fetchone.return_value = None
    cur.fetchall.return_value = []

    def malformed_state(current_date, cur):
        # Missing the required "halted" key - check_all() itself raises ValueError for this,
        # from inside the outer try block (after the per-check inner except already handled
        # the call, so this is genuinely testing the OUTER handler, not the inner one).
        return {"reason": "no halted key"}

    cb._checks["daily_loss"] = malformed_state

    result = cb.check_all(current_date=date(2026, 7, 24))

    assert result["halted"] is True
