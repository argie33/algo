#!/usr/bin/env python3
"""Regression test: Phase 6's portfolio-rotation-safety-check must count and persist every
failure branch as an error, not just the exit_trade()-returned-failure case.

BUG FOUND (goal session, Phase 6 deep-review pass): this block only fires when the portfolio
is already full AND the exit engine's normal checks produced zero real exits - it exists
specifically to break that deadlock by force-closing the oldest position. Unlike every other
no-op/failure case in this file (tighten_stop rowcount==0, stop-raise rowcount==0, exposure
action failures - see the FIXED_VALIDATION/exposure_action_failed handling elsewhere in this
same file), three failure paths in THIS block used to only `logger.error(...)` with no
`errors += 1` and no `_persist_exit_check_error` call:
- `current_price is None` (refusing to force-close without a valid exit price)
- `not open_trade_ids` (position is 'open' but has no open trade_id)
- the whole block's outer `except Exception` (DB error, exit_trade() exception, etc.)

Since `errors` directly drives whether Phase 6 reports "ok" vs "degraded", any of these could
let Phase 6 report a clean run while the deadlock-breaking mechanism of last resort completely
failed - portfolio stuck full, zero exit capacity, no operator alert. A fourth silent no-op (the
oldest-position re-query returning no row - a benign concurrent-close race, not a failure) was
also given a warning log instead of vanishing entirely, though it deliberately does NOT count as
an `errors` increment since nothing actually failed.

Static source check (same technique/precedent as test_phase6_portfolio_rotation_writes_audit_log.py
for this same block - very large mocking surface for a full run() call).
"""

import re
from pathlib import Path

SOURCE = (Path(__file__).parent.parent.parent / "algo" / "orchestrator" / "phase6_exit_execution.py").read_text()


def _portfolio_rotation_block() -> str:
    # Spans from the initial oldest-position re-query through the end of the outer except
    # handler (up to the elif dry_run: that follows the whole try/except) - wide enough to
    # cover all four failure/no-op branches under test.
    match = re.search(
        r"oldest = cur_w\.fetchone\(\).*?elif dry_run:",
        SOURCE,
        re.DOTALL,
    )
    assert match, "expected to find the portfolio rotation safety check block - source may have been restructured"
    return match.group(0)


def test_null_current_price_branch_counts_error():
    block = _portfolio_rotation_block()
    idx = block.index("no current_price available")
    preceding = block[:idx]
    # The nearest `errors += 1` before this log line must belong to this branch, not some
    # unrelated earlier branch - check it's within a short distance (same if-block).
    last_errors_incr = preceding.rfind("errors += 1")
    assert last_errors_incr != -1 and idx - last_errors_incr < 400, (
        "the 'no current_price available' branch must increment `errors` - without it, a "
        "portfolio-rotation force-close skipped for a missing exit price is invisible to the "
        "phase_status calculation"
    )
    following = block[idx : idx + 400]
    assert "_persist_exit_check_error(" in following, (
        "the 'no current_price available' branch should also persist the failure via "
        "_persist_exit_check_error, matching this file's established pattern elsewhere"
    )


def test_no_open_trade_id_branch_counts_error():
    block = _portfolio_rotation_block()
    idx = block.index("has no open trade_id - cannot force-close")
    preceding = block[:idx]
    last_errors_incr = preceding.rfind("errors += 1")
    assert last_errors_incr != -1 and idx - last_errors_incr < 400, (
        "the 'no open trade_id' branch must increment `errors` - without it, a portfolio-"
        "rotation force-close skipped because the position has no trade_id is invisible to "
        "the phase_status calculation"
    )
    following = block[idx : idx + 400]
    assert "_persist_exit_check_error(" in following


def test_outer_exception_handler_counts_error():
    block = _portfolio_rotation_block()
    handler_idx = block.index("except Exception as e:")
    handler_body = block[handler_idx:]
    assert "errors += 1" in handler_body[:600], (
        "the outer except Exception handler around the whole portfolio-rotation block must "
        "increment `errors` - without it, ANY unexpected failure in this block (DB error, "
        "exit_trade() exception, etc.) is invisible to the phase_status calculation and Phase 6 "
        "can report a clean 'ok' run while the deadlock-breaking mechanism silently failed"
    )
    assert "_persist_exit_check_error(" in handler_body[:800]


def test_empty_oldest_query_result_is_logged_not_fully_silent():
    block = _portfolio_rotation_block()
    assert "if not oldest:" in block, (
        "the oldest-position re-query result must be explicitly checked (not just `if oldest:` "
        "with no else) - a race where the position was already closed between the COUNT and "
        "this SELECT must not vanish with zero log output"
    )
