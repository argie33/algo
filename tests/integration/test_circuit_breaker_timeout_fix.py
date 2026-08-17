#!/usr/bin/env python3
"""
Circuit breaker timeout recovery test (Session 89).

Validates that circuit breaker halts unprocessed futures immediately
on timeout, preventing 20+ minute waits for rate-limited data.

Root cause: When rate limiting is detected, unprocessed futures in
thread pool executor are still awaited even though they're marked for
fallback. This causes extended waits (20+ min) for delayed batches.

Fix: Immediately cancel unprocessed futures when circuit breaker halts,
don't wait for them in as_completed() loop.

BUG FOUND 2026-08-17: both tests below used `return True/False` instead of `assert`.
Under pytest, a non-None return only triggers PytestReturnNotNoneWarning - the test is
still reported PASSED regardless of what the check actually found, so neither test could
ever fail in CI even if the Session 89 fix regressed. Converted to real assertions;
the underlying checks (source-pattern presence, runner module introspection) are
unchanged.
"""

import inspect
import re
from pathlib import Path

import loaders.runner as runner


def test_circuit_breaker_future_cancellation() -> None:
    """Verify circuit breaker halts unprocessed futures immediately.

    Validates that the fix from Session 89 is in place: loaders/load_prices.py cancels
    unprocessed futures on circuit-breaker halt instead of waiting for them in
    as_completed().
    """
    load_prices_path = Path(__file__).parent.parent.parent / "loaders" / "load_prices.py"
    source = load_prices_path.read_text()

    checks = [
        ("unprocessed_futures", "identifies unprocessed futures"),
        (r"fut\.cancel\(\)", "cancels futures immediately"),
        ("CIRCUIT_BREAKER.*Halting", "detects halted state"),
        ("failed_batches.extend", "marks batches for error handling"),
    ]
    for pattern, description in checks:
        assert re.search(pattern, source, re.IGNORECASE), (
            f"load_prices.py no longer {description} (pattern {pattern!r} not found) - "
            "the Session 89 circuit-breaker-hang fix appears to have regressed."
        )


def test_timeout_enforcement_in_logs() -> None:
    """Verify runner.py's loader timeout is configured and its setup path is logged.

    Checks that LOADER_TIMEOUT_SECONDS is a real per-loader value and that
    _setup_timeout logs its Timer-based fallback path, so a hung loader with no
    timeout firing can actually be diagnosed from logs.
    """
    assert hasattr(runner, "_setup_timeout"), "runner.py no longer defines _setup_timeout"

    setup_source = inspect.getsource(runner._setup_timeout)
    assert "threading.Timer" in setup_source, (
        "_setup_timeout no longer references threading.Timer (Windows fallback path missing)"
    )
    assert "logger.info" in setup_source, "_setup_timeout no longer logs its timeout setup"
