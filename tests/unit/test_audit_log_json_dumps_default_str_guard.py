"""Regression test: json.dumps() calls persisting loosely-typed dicts to archival JSON audit
columns must use default=str, or a raw Decimal/datetime value anywhere in the payload raises
an uncaught TypeError - exactly the bug already found and fixed in
phase9_reconciliation.py's audit log insert ("Object of type date is not JSON serializable",
which marked the entire orchestrator run FAILED even though reconciliation itself succeeded).

Found 2026-08-17 via the same pattern in three more call sites:
- algo/risk/circuit_breaker.py::_log_halt (results dict is loosely typed, called from many
  _check_* methods - all currently return safe primitives, but nothing enforces that)
- algo/risk/market_exposure.py (result["factors"] is built via **eco-spreading sub-detector
  output, not guaranteed JSON-safe)
- algo/signals/sector_rotation.py (details_dict["sector_data"] is opaque; the existing
  try/except only guards the json.loads() re-parse check, not the json.dumps() call itself,
  so it never actually protects against this failure mode)

This test proves the exact failure mode (a raw datetime.date reaching json.dumps without
default=str raises TypeError) and confirms default=str prevents it.
"""

import json
from datetime import date

import pytest


def test_plain_json_dumps_raises_on_raw_date():
    """Confirms the failure mode this fix prevents actually exists."""
    payload = {"reason": "some halt reason", "as_of": date(2026, 8, 17)}
    with pytest.raises(TypeError):
        json.dumps(payload)


def test_json_dumps_with_default_str_survives_raw_date():
    payload = {"reason": "some halt reason", "as_of": date(2026, 8, 17)}
    result = json.dumps(payload, default=str)
    parsed = json.loads(result)
    assert parsed["as_of"] == "2026-08-17"
    assert parsed["reason"] == "some halt reason"


def test_circuit_breaker_log_halt_uses_default_str():
    import inspect

    from algo.risk.circuit_breaker import CircuitBreaker

    source = inspect.getsource(CircuitBreaker._log_halt)
    assert "default=str" in source, "_log_halt's json.dumps() must use default=str"


def test_market_exposure_uses_default_str():
    import inspect

    from algo.risk.market_exposure import MarketExposure

    source = inspect.getsource(MarketExposure)
    assert 'factors_json = json.dumps(result["factors"], default=str)' in source


def test_sector_rotation_uses_default_str():
    import inspect

    from algo.signals import sector_rotation

    source = inspect.getsource(sector_rotation)
    assert "details_json = json.dumps(details_dict, default=str)" in source
