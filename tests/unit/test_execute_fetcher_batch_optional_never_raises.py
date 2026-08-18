"""Regression test for a 2026-08-18 finding: dashboard/fetchers.py's _execute_fetcher_batch()
used to hardcode its own local `critical_fetchers` set internally, duplicating (and silently
diverging from) load_all()'s own critical/optional categorization.

Commit 52260089b (2026-07-11, "Optimize dashboard load time by moving circuit-breaker to
optional fetchers") moved "cb" (circuit breakers) from load_all()'s critical set to its
optional set specifically because the circuit-breaker Lambda endpoint routinely returns 503
with a 12+ second exponential retry backoff, and "is not required for dashboard function;
panels handle missing data gracefully" - but never updated _execute_fetcher_batch()'s own
hardcoded copy of "critical fetchers", which still listed "cb" among them. Since "cb" is
dispatched through load_all()'s *optional* batch call, the function's own (still-critical)
set caught it on every timeout/error and raised a fatal RuntimeError, taking down the ENTIRE
dashboard (data unavailable, critical) instead of just the circuit-breaker panel showing an
error - exactly the failure mode the 07-11 fix set out to prevent, silently reintroduced by
this leftover duplicate and live for over a month.

Fixed by making _execute_fetcher_batch() take `critical_fetchers` as an explicit parameter
instead of re-deriving its own copy, and passing set() for load_all()'s optional-batch call
so nothing dispatched through it can ever raise.
"""

from typing import Any

from dashboard.fetchers import _execute_fetcher_batch


def _failing_fetcher(name: str, fn: Any, timeout: float) -> tuple[str, dict[str, Any]]:
    raise RuntimeError("simulated transient failure")


def test_failure_in_critical_set_raises() -> None:
    try:
        _execute_fetcher_batch(
            {"cb"},
            max_workers=1,
            timeout_sec=5,
            one_func=_failing_fetcher,
            fetcher_timeout_dict={"cb": 5.0},
            batch_name="test-critical",
            critical_fetchers={"cb"},
        )
        raise AssertionError("expected RuntimeError for a fetcher in the critical set")
    except RuntimeError as e:
        assert "cb" in str(e)


def test_failure_outside_critical_set_degrades_instead_of_raising() -> None:
    """This is the actual regression: "cb" must NOT raise when dispatched through the
    optional batch (critical_fetchers=set()), matching load_all()'s real call site."""
    result = _execute_fetcher_batch(
        {"cb"},
        max_workers=1,
        timeout_sec=5,
        one_func=_failing_fetcher,
        fetcher_timeout_dict={"cb": 5.0},
        batch_name="test-optional",
        critical_fetchers=set(),
    )

    assert "cb" in result
    assert "_error" in result["cb"], f"expected a degraded _error entry, got {result['cb']!r}"
