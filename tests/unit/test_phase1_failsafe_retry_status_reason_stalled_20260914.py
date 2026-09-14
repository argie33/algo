"""Regression test: check_and_retry_incomplete_loaders() must accept "stalled" as a
legitimate retry status_reason, not treat it as a broken/unexpected retry-infrastructure
result.

BUG FOUND (real-money-readiness audit): monitor_loader_retry()'s own docstring documents
"stalled" (0% completion for 5+ minutes, subprocess likely hung/deadlocked) as a value it
legitimately returns, and its code really does return it (SESSION 103 FIX block, "Subprocess
stalled" critical log). But check_and_retry_incomplete_loaders()'s status_reason validation
only ever accepted "timeout"/"failed" - a genuinely-stalled critical loader raised a
misleading "Loader retry infrastructure may have changed. Check invoke_loader_retry()
implementation." CRITICAL alert instead of the accurate "subprocess stalled" diagnosis
monitor_loader_retry() had already made. The end result (halt_required=True for a critical
loader) was unaffected either way - this never let a stalled loader silently through - but
it sent whoever's paged chasing an "infrastructure broken" red herring instead of the real
"subprocess hung" cause.
"""

import psycopg2

from algo.orchestrator import phase1_failsafe_retry as mod


class _IncompleteLoaderCursor:
    """Returns exactly one incomplete-loader row for a real, currently-critical loader
    (price_daily), then answers the stock_scores-dependency-freshness follow-up query with
    "nothing newer" so that branch is a no-op."""

    def __init__(self):
        self._last_query = ""

    def execute(self, query, params=None):
        self._last_query = query

    def fetchall(self):
        assert "data_loader_status" in self._last_query
        return [
            (
                "price_daily",  # table_name
                "FAILED",  # status
                50.0,  # completion_pct
                50,  # symbols_loaded
                100,  # symbol_count
                "simulated crash",  # error_message
                None,  # execution_started
                None,  # last_updated
            )
        ]

    def fetchone(self):
        # The stock_scores-dependency-freshness follow-up query - "no upstream metric
        # updates" short-circuits that branch entirely.
        return (None,)


class _FakeDatabaseContext:
    def __enter__(self):
        return _IncompleteLoaderCursor()

    def __exit__(self, *exc):
        return False


def test_stalled_status_reason_does_not_raise_unexpected_status_reason_error(monkeypatch):
    monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _FakeDatabaseContext())
    monkeypatch.setattr(
        mod,
        "retry_loader",
        lambda loader_name, symbols_missing, is_critical: {
            "retried": True,
            "recovered": False,
            "final_completion_pct": 0.0,
            "status_reason": "stalled",
        },
    )

    results = mod.check_and_retry_incomplete_loaders(dry_run=False)

    assert "price_daily" in results["still_failing"]
    assert results["halt_required"] is True


def test_stalled_is_accepted_alongside_timeout_and_failed_in_source():
    """Static guard against regressing back to only two accepted values - see the
    check_and_retry_incomplete_loaders status_reason validation block."""
    import inspect

    source = inspect.getsource(mod.check_and_retry_incomplete_loaders)
    assert 'status_reason not in ("timeout", "failed", "stalled")' in source
    assert 'elif status_reason == "stalled":' in source
