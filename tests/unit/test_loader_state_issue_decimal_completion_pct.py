"""Regression test for the 2026-08-17 fix: _classify_loader_state_issue
(lambda/api/routes/algo_handlers/market.py) used
`isinstance(completion_pct, (int, float, str))` to gate the float() conversion, but
data_loader_status.completion_pct is a NUMERIC column - psycopg2 returns it as
decimal.Decimal, which that isinstance check does not match. Every real (non-None)
completion_pct value was silently forced to 0, so any loader running past 30 minutes was
falsely reported as "TIMEOUT: running Xh at 0%" regardless of true progress.

Live-confirmed 2026-08-17: current_reports_8k was genuinely 32.45% complete
(1600/4930 symbols, via symbols_loaded/symbol_count) but /api/algo/data-status reported
loader_state_issue="TIMEOUT: running 0.6h at 0%" for the same row - because the sibling
`completion_pct` output field (line ~919) converts with plain `float(completion_pct)` (no
isinstance gate) while this classifier's `completion_float` used the buggy gate.
"""

import importlib
from datetime import datetime, timedelta, timezone
from decimal import Decimal

market_module = importlib.import_module("lambda.api.routes.algo_handlers.market")


def test_decimal_completion_pct_not_treated_as_zero():
    """A NUMERIC completion_pct arriving as Decimal must not collapse to 0%."""
    started = datetime.now(timezone.utc) - timedelta(minutes=45)

    result = market_module._classify_loader_state_issue("RUNNING", 0, started, None, Decimal("32.45"))

    assert result == "RUNNING: 32% complete"


def test_decimal_completion_pct_above_5_percent_is_not_a_false_timeout():
    """>30min elapsed with genuine >=5% progress (as Decimal) must not report TIMEOUT."""
    started = datetime.now(timezone.utc) - timedelta(minutes=45)

    result = market_module._classify_loader_state_issue("RUNNING", 0, started, None, Decimal("32.45"))

    assert "TIMEOUT" not in result


def test_genuine_stall_still_reports_timeout():
    """A loader truly stuck near 0% past 30 minutes must still be flagged - not overcorrected."""
    started = datetime.now(timezone.utc) - timedelta(minutes=45)

    result = market_module._classify_loader_state_issue("RUNNING", 0, started, None, Decimal("0.00"))

    assert result is not None
    assert result.startswith("TIMEOUT")
