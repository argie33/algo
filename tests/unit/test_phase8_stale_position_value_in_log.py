"""Regression test: Phase 8's "BUY entry=... value=$..." log line used a stale variable.

Live-reproduced 2026-08-10 (run LOCAL-MORNING-20260810-213245-468229): the concentration
pre-filter loop (a structurally separate earlier pass over candidates, see
test_concentration_prefilter_skips_are_persisted_to_audit_table in
test_phase8_execution_failure_audit_gap.py) sets a local `position_value = Decimal(shares) *
Decimal(str(entry_price))` for each candidate it evaluates, and stops updating it once that
loop `break`s. The main per-signal execution loop later computes its OWN correct per-symbol
`position_value_float` (from freshly-looked-up shares/entry_price) for pre-trade validation,
but the "[PHASE 8] {symbol}: BUY entry=... value=$..." log line accidentally referenced the
leftover `position_value` name from the earlier loop instead. Confirmed live: three different
symbols (MSA, ERO, IBEX) with different entry prices and share counts all logged the exact
same "value=$2,324" - the last value the prefilter loop happened to compute before its
`break`, not each symbol's actual shares * entry_price. Order execution itself was unaffected
(it uses `shares` and `position_value_dec`/`position_value_float` directly, never the stale
name), but the log - the primary tool for verifying live trading behavior - was silently
lying about position sizes for every trade actually executed.
"""

import inspect

from algo.orchestrator import phase8_entry_execution as p8


def test_buy_log_line_uses_freshly_computed_position_value_not_stale_prefilter_leftover():
    source = inspect.getsource(p8.run)

    # The BUY entry log line (main execution loop) must reference position_value_float -
    # computed fresh per symbol just above it (position_value_dec/position_value_float) -
    # never the bare `position_value` name, which belongs to the earlier, structurally
    # separate concentration pre-filter loop and stops changing once that loop breaks.
    buy_log_line = source.split('f"[PHASE 8] {symbol}: BUY entry=')[1].split(")", 1)[0]
    assert "position_value_float" in buy_log_line, (
        "BUY log line must use position_value_float (fresh per-symbol value), not the stale "
        "position_value left over from the concentration pre-filter loop"
    )
    assert "value=${position_value:" not in buy_log_line, (
        "BUY log line regressed back to the stale pre-filter-loop position_value variable"
    )
