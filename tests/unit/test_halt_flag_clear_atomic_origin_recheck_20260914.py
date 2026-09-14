"""Regression test: clear_halt_flag()'s allowed_triggers origin check must be re-verified
ATOMICALLY with the actual write, not just at an earlier, unlocked pre-check.

BUG FOUND (real-money-readiness audit): clear_halt_flag()'s origin check called
get_halt_triggered_by() (a plain, unlocked read) and only THEN proceeded to the actual
clear write (DynamoDB put_item / RDS UPDATE under an advisory lock acquired separately,
afterward). A concurrent set_halt_flag() call - e.g. Phase 9 setting a
reconciliation-governance halt - could land in the window between the pre-check read and
the write, and get silently wiped anyway: exactly the vulnerability this origin check
exists to prevent (see halt_flag_cleared_by_unrelated_phase_fix_20260810).

Fixed by re-verifying the origin a second time, atomically with the write itself:
- DynamoDB: a ConditionExpression on the update_item requiring triggered_by to still be
  in allowed_triggers (or attribute_not_exists for None), raising
  _HaltFlagOriginMismatchError on ConditionalCheckFailedException.
- RDS: _clear_halt_flag_rds() re-reads triggered_by from algo_runtime_state WHILE holding
  the same advisory lock other concurrent set_halt_flag()/clear_halt_flag() calls
  serialize on, immediately before the UPDATE.

A refusal (_HaltFlagOriginMismatchError) must be treated as "correctly refused" - return
False - not as an infra failure worth retrying or falling back to the other backend for.
"""

from unittest.mock import MagicMock

from algo.orchestration.halt_flag_manager import HaltFlagManager, _HaltFlagOriginMismatchError


def _manager():
    return HaltFlagManager.__new__(HaltFlagManager)


def test_rds_atomic_recheck_refuses_when_origin_changed_since_precheck(monkeypatch):
    """The unlocked pre-check saw an allowed origin, but by the time _clear_halt_flag_rds
    acquires the lock and re-reads, a DIFFERENT halt is active - must refuse, not clear."""
    manager = _manager()
    monkeypatch.setenv("LOCAL_MODE", "true")
    monkeypatch.setattr(manager, "get_halt_triggered_by", lambda: "phase1_data_freshness")

    import json

    cur = MagicMock()
    cur.fetchone.return_value = (json.dumps({"halt_triggered_by": "phase9_reconciliation_governance"}),)
    db_ctx = MagicMock()
    db_ctx.__enter__.return_value = cur
    db_ctx.__exit__.return_value = False
    monkeypatch.setattr(
        "algo.orchestration.halt_flag_manager.DatabaseContext",
        MagicMock(return_value=db_ctx),
    )

    result = manager.clear_halt_flag("reason", allowed_triggers=frozenset({"phase1_data_freshness", None}))

    assert result is False
    # The UPDATE that actually clears the flag must never have been reached.
    executed_sql = [call.args[0] for call in cur.execute.call_args_list]
    assert not any("UPDATE algo_runtime_state" in sql and "halt_flag = FALSE" in sql for sql in executed_sql)


def test_rds_atomic_recheck_proceeds_when_origin_still_matches(monkeypatch):
    manager = _manager()
    monkeypatch.setenv("LOCAL_MODE", "true")
    monkeypatch.setattr(manager, "get_halt_triggered_by", lambda: "phase1_data_freshness")

    import json

    cur = MagicMock()
    cur.fetchone.return_value = (json.dumps({"halt_triggered_by": "phase1_data_freshness"}),)
    db_ctx = MagicMock()
    db_ctx.__enter__.return_value = cur
    db_ctx.__exit__.return_value = False
    monkeypatch.setattr(
        "algo.orchestration.halt_flag_manager.DatabaseContext",
        MagicMock(return_value=db_ctx),
    )

    result = manager.clear_halt_flag("reason", allowed_triggers=frozenset({"phase1_data_freshness", None}))

    assert result is True
    executed_sql = [call.args[0] for call in cur.execute.call_args_list]
    assert any("UPDATE algo_runtime_state" in sql and "halt_flag = FALSE" in sql for sql in executed_sql)


def test_origin_mismatch_is_not_treated_as_an_infra_failure_worth_retrying(monkeypatch):
    """A refusal must return False immediately, not get retried or converted into the
    'both backends failed' RuntimeError."""
    manager = _manager()
    monkeypatch.setattr(manager, "get_halt_triggered_by", lambda: "phase1_data_freshness")

    def _raise_mismatch(reason, allowed_triggers=None, force=False):
        raise _HaltFlagOriginMismatchError("origin changed")

    monkeypatch.setattr(manager, "_clear_halt_flag_rds", _raise_mismatch)
    monkeypatch.setenv("LOCAL_MODE", "true")

    result = manager.clear_halt_flag("reason", allowed_triggers=frozenset({"phase1_data_freshness", None}))

    assert result is False


def test_force_skips_the_atomic_recheck(monkeypatch):
    """force=True (manual override / DynamoDB-authoritative RDS mirror) must not perform
    the re-read at all - it's an intentional, unconditional clear."""
    manager = _manager()
    monkeypatch.setenv("LOCAL_MODE", "true")

    cur = MagicMock()
    db_ctx = MagicMock()
    db_ctx.__enter__.return_value = cur
    db_ctx.__exit__.return_value = False
    monkeypatch.setattr(
        "algo.orchestration.halt_flag_manager.DatabaseContext",
        MagicMock(return_value=db_ctx),
    )

    result = manager.clear_halt_flag("reason", force=True)

    assert result is True
    executed_sql = [call.args[0] for call in cur.execute.call_args_list]
    # No SELECT of state_value for a re-check - force skips it entirely.
    assert not any("SELECT state_value" in sql for sql in executed_sql)
