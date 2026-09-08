#!/usr/bin/env python3
"""Regression test: real-money-readiness audit (2026-09-07) found the entry side has recorded
every fill's execution quality via TCAEngine.record_fill() since 2026-08-xx
(executor_entry_handler.py's _record_entry_phase), but no exit path ever called it - stop-loss/
profit-target/time exits (the fills most likely to slip, especially a market-order stop in a
fast decline) were completely invisible to slippage measurement and TCA alerting.

Static source check, matching the established precedent for this exact function (see
test_executor_exit_handler_partial_exit_resizes_bracket_leg_20260824.py's own docstring):
_execute_exit has a large dependency graph (guards, lock/fetch, bracket cancellation, order
submission, position update) impractical to mock end-to-end.
"""

from pathlib import Path

SOURCE = (Path(__file__).parent.parent.parent / "algo" / "trading" / "executor_exit_handler.py").read_text()

_TCA_MARKER = "self.context.tca.record_fill("


def _tca_block(source: str) -> str:
    assert _TCA_MARKER in source, "expected to find the exit-side TCA record_fill() call"
    start = source.index(_TCA_MARKER)
    return source[start - 900 : start + 900]


def test_tca_record_fill_is_called_on_the_exit_path():
    assert _TCA_MARKER in SOURCE


def test_tca_call_only_fires_for_a_real_confirmed_fill_not_a_pending_placeholder():
    block = _tca_block(SOURCE)
    assert "if not is_estimated_price:" in block, (
        "must skip TCA recording when actual_fill_price is just the evaluation-time quote "
        "(the PENDING_FILL_RECONCILIATION placeholder path), not a real broker fill"
    )


def test_tca_call_uses_sell_side():
    block = _tca_block(SOURCE)
    assert 'side="SELL"' in block


def test_tca_call_passes_requested_and_filled_quantities_separately():
    block = _tca_block(SOURCE)
    assert "shares_requested=int(requested_shares_to_exit)" in block
    assert "shares_filled=int(shares_to_exit)" in block


def test_requested_shares_captured_before_any_partial_fill_reconciliation():
    """requested_shares_to_exit must be captured right after _calculate_exit_shares(), before
    shares_to_exit is later overwritten with the broker-verified actual fill quantity -
    otherwise TCA's fill_rate_pct would always read 100% (comparing the reconciled value to
    itself), the exact bug already found and fixed on the entry side."""
    capture_idx = SOURCE.index("requested_shares_to_exit = shares_to_exit")
    calc_idx = SOURCE.index("shares_to_exit, full_exit = self._calculate_exit_shares(current_qty, exit_fraction)")
    verify_idx = SOURCE.index("shares_to_exit = verified_filled_qty")
    assert calc_idx < capture_idx < verify_idx


def test_tca_failure_does_not_raise():
    """Same non-blocking contract as the entry side and every other TCA call site in this
    file: the sale has already happened for real by this point - a TCA recording failure
    must never revert an already-committed trade."""
    block = _tca_block(SOURCE)
    raise_statements = [line for line in block.splitlines() if line.strip().startswith("raise ")]
    assert not raise_statements, f"exit-side TCA recording must fail open (log, don't raise): {raise_statements}"
    assert "except Exception as e:" in block
    assert "non-blocking" in block
