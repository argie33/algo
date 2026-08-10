"""Regression test for a CRITICAL safety bug in the manual operator kill switch
(scripts/manage_halt_flag.py), live-reproduced 2026-08-10.

set_halt_flag() is "sticky to the first trigger" by design (see _set_halt_flag_rds's
docstring) - if a halt is already active, a second set_halt_flag() call preserves the
ORIGINAL triggered_by/reason instead of overwriting them. This is correct behavior between
automated phases (Phase 9 halting later in a run Phase 2 already halted must not hide the
original cause), but it silently broke the manual kill switch: live-reproduced by setting an
automated halt (triggered_by="phase2_circuit_breaker"), then calling
scripts/manage_halt_flag.py --set - the flag remained tagged "phase2_circuit_breaker" and
get_halt_triggered_by() never returned "manual_operator" at all, despite the script printing
"Trading is now halted until explicitly cleared". Phase 2's own self-clear logic (which only
checks `current_trigger == "phase2_circuit_breaker"`) would then silently clear the flag - and
the operator's manual halt with it - the next time Phase 2's circuit breaker recovered.

Fixed: set_halt_flag(..., force=True) unconditionally overwrites triggered_by/reason/
triggered_at instead of preserving the existing ones. scripts/manage_halt_flag.py's --set now
always passes force=True (see test_manage_halt_flag_script.py).
"""

from unittest.mock import MagicMock, patch

from algo.orchestration.halt_flag_manager import HaltFlagManager


def _manager() -> HaltFlagManager:
    return HaltFlagManager(alerts=MagicMock(), log_phase_result=MagicMock())


def _mock_db_context():
    cur = MagicMock()
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=cur)
    ctx.__exit__ = MagicMock(return_value=False)
    return ctx, cur


class TestSetHaltFlagForceOverride:
    def test_force_true_uses_unconditional_overwrite_sql(self):
        """force=True must not gate the overwrite on the existing row's halt_flag - the whole
        point is to overwrite even when a halt (set by someone else) is already active."""
        manager = _manager()
        ctx, cur = _mock_db_context()

        with patch("algo.orchestration.halt_flag_manager.DatabaseContext", return_value=ctx):
            manager._set_halt_flag_rds(
                "Operator: keep halted regardless",
                __import__("datetime").datetime.now(__import__("datetime").timezone.utc),
                __import__("datetime").datetime.now(),
                triggered_by="manual_operator",
                force=True,
            )

        insert_call = next(c for c in cur.execute.call_args_list if "INSERT INTO algo_runtime_state" in c.args[0])
        sql = insert_call.args[0]
        assert "CASE WHEN FALSE THEN" in sql, (
            f"force=True must use an unconditional (CASE WHEN FALSE) overwrite, got: {sql}"
        )
        params = insert_call.args[1]
        assert params[-1] == "manual_operator", "updated_by must reflect the real triggered_by, not a hardcoded value"

    def test_force_false_preserves_sticky_first_trigger_sql(self):
        """Default (force=False) behavior must be unchanged: still gated on the existing row's
        halt_flag, so automated phases can't clobber each other's halt reason."""
        manager = _manager()
        ctx, cur = _mock_db_context()

        with patch("algo.orchestration.halt_flag_manager.DatabaseContext", return_value=ctx):
            manager._set_halt_flag_rds(
                "Phase 9 governance halt",
                __import__("datetime").datetime.now(__import__("datetime").timezone.utc),
                __import__("datetime").datetime.now(),
                triggered_by="phase9_reconciliation_governance",
                force=False,
            )

        insert_call = next(c for c in cur.execute.call_args_list if "INSERT INTO algo_runtime_state" in c.args[0])
        sql = insert_call.args[0]
        assert "CASE WHEN algo_runtime_state.halt_flag THEN" in sql, (
            f"force=False must preserve the sticky-first-trigger guard, got: {sql}"
        )
