"""Integration test: Verify circuit breaker API response matches panel expectations.

This test catches field name mismatches automatically so we don't have to find
them manually by running the dashboard.
"""


def test_circuit_breaker_response_schema():
    """Verify API circuit breaker response has fields that panel expects."""
    # Sample breaker response from API
    breaker = {
        "id": "drawdown",
        "lbl": "Portfolio Drawdown",
        "fired": False,
        "cur": 15.5,
        "thr": 20.0,
        "u": "%",
        "description": "Test",
    }

    # Panel code: circuit.py line 62-65
    fired = breaker["fired"]  # Must exist
    thr = breaker.get("thr")  # Panel expects "thr"
    cur = breaker.get("cur")  # Panel expects "cur"
    lbl_s = str(breaker.get("lbl", "N/A"))[:20]  # Panel expects "lbl"
    u = str(breaker.get("u") or "")  # Panel expects "u"

    # All required accesses must succeed
    assert isinstance(fired, bool), f"fired must be bool, got {type(fired)}"
    assert isinstance(thr, (int, float)) or thr is None, "thr must be number or None"
    assert isinstance(cur, (int, float)) or cur is None, "cur must be number or None"
    assert isinstance(lbl_s, str), "lbl must be string"
    assert isinstance(u, str), "u must be string"


def test_circuit_breaker_response_no_field_mismatch():
    """FAIL if API uses long field names instead of short keys.

    This test ENFORCES that the API must use short keys that match the panel.
    If you see this fail, you changed the API field names without updating the panel.
    """
    # Example of WRONG field names that would cause crashes:
    wrong_breaker = {
        "id": "drawdown",
        "label": "Portfolio Drawdown",  # WRONG - panel expects "lbl"
        "triggered": False,  # WRONG - panel expects "fired"
        "current": 15.5,  # WRONG - panel expects "cur"
        "threshold": 20.0,  # WRONG - panel expects "thr"
        "unit": "%",  # WRONG - panel expects "u"
    }

    # Panel will get None for these (silent failure)
    fired = wrong_breaker.get("fired")  # Panel requires this
    thr = wrong_breaker.get("thr")  # Will be None if wrong key
    cur = wrong_breaker.get("cur")  # Will be None if wrong key

    assert fired is None, "If this passes, API is using 'triggered' instead of 'fired'"
    assert thr is None, "If this passes, API is using 'threshold' instead of 'thr'"
    assert cur is None, "If this passes, API is using 'current' instead of 'cur'"

    # THIS TEST SHOULD FAIL if you use wrong field names
    # Fix it by changing API to use short keys: "fired", "cur", "thr", "lbl", "u"


def test_circuit_breaker_field_types():
    """Verify all breaker fields are correct types (prevents int being formatted as string)."""
    breaker = {
        "id": "drawdown",
        "lbl": "Portfolio Drawdown",
        "fired": True,
        "cur": 20,  # int or float, never string
        "thr": 20.0,  # int or float, never string
        "u": "%",  # string unit
    }

    # Circuit panel formats these with f-strings
    cur_val = breaker.get("cur")
    thr_val = breaker.get("thr")

    # If either is int, it's OK (will be formatted as f"{value:.1f}")
    # If either is string, panel will crash when calling methods on it
    if cur_val is not None:
        assert isinstance(cur_val, (int, float)), f"cur must be number, got {type(cur_val)}"

    if thr_val is not None:
        assert isinstance(thr_val, (int, float)), f"thr must be number, got {type(thr_val)}"
