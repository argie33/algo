#!/usr/bin/env python3
"""Regression test: both stop-raise UPDATE statements in phase6_exit_execution.py must be
DB-level monotonic (never lower current_stop_price), not just guarded at the point the new
value is computed.

Bug (found 2026-08-10): exposure_policy.py's tighten_winners_at_r and position_monitor.py's
RAISE_STOP recommendation both only guarantee `new_stop >= active_stop` against the active_stop
*snapshot* they read earlier in the Phase 5/3 -> Phase 6 pipeline. The actual writes in
phase6_exit_execution.py were unconditional (`SET current_stop_price = %s`), so a stale
snapshot applied after some OTHER path (e.g. ExitEngine's own breakeven/chandelier raise)
already committed a HIGHER current_stop_price earlier in the same run would silently overwrite
it with the older, lower value - a real risk-management regression (loosening a stop), not a
cosmetic race.

A third stop-raise write site, algo/trading/executor_exit_handler.py, already had this exact
protection (both an explicit `if new_stop_price <= existing_stop: reject` AND a
`WHERE ... AND %s > p.current_stop_price` guard) - this fix brings the other two call sites up
to that same established standard, using `GREATEST(current_stop_price, %s)` so the write itself
can never decrease the value regardless of what stale value the caller passes.

Verifies via source inspection (the run() function is too large/DB-heavy to unit-test end to
end) that both UPDATE statements use GREATEST(), not a bare `= %s` assignment.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE = (REPO_ROOT / "algo" / "orchestrator" / "phase6_exit_execution.py").read_text(encoding="utf-8")


class TestPhase6StopRaiseWritesAreMonotonic:
    def test_both_stop_raise_writes_use_greatest(self):
        occurrences = SOURCE.count("SET current_stop_price = GREATEST(current_stop_price, %s)")
        assert occurrences == 2, (
            f"expected exactly 2 monotonic stop-raise UPDATE statements (tighten_stop and "
            f"RAISE_STOP), found {occurrences} - both must use GREATEST(current_stop_price, %s) "
            f"so a stale new_stop snapshot can never overwrite a higher, already-committed stop"
        )

    def test_raise_stop_write_still_scopes_to_open_positions(self):
        """Sanity check: the GREATEST() fix must not have dropped the existing
        `AND status = %s` (open-position) scoping on the RAISE_STOP write."""
        assert (
            'GREATEST(current_stop_price, %s) "\n                                        "WHERE id = %s AND status = %s'
            in SOURCE
            or ("WHERE id = %s AND status = %s" in SOURCE)
        ), "RAISE_STOP's UPDATE must still scope to `id = %s AND status = %s`"

    def test_no_bare_unconditional_current_stop_price_assignment_remains(self):
        """Catch a future regression that reintroduces `= %s` instead of `GREATEST(...)`."""
        assert "current_stop_price = %s" not in SOURCE, (
            "found a bare `current_stop_price = %s` assignment - every write to this column "
            "in this file must go through GREATEST(current_stop_price, %s) to stay monotonic"
        )
