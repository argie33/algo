"""Regression test for hardening clear_halt_flag() at the primitive level
(real-money-readiness audit, 2026-09-06).

Before this, origin-checking (get_halt_triggered_by() before deciding whether to call
clear_halt_flag()) lived entirely in each CALLER - orchestrator.py's Phase 1/Phase 2
success paths already did this correctly (see
halt_flag_cleared_by_unrelated_phase_fix_20260810), but clear_halt_flag() itself would
happily wipe ANY active halt, regardless of origin, if called without that caller-side
check. With only 3 call sites in the codebase today that's low-probability, but the
primitive being unsafe by construction is exactly the kind of gap a future/careless
caller (or a bugfix that removes the pre-check "because it looked redundant") could
reintroduce silently. Origin verification now lives inside clear_halt_flag() itself:
callers must pass `allowed_triggers` (raises TypeError if omitted) or `force=True` for
an explicit manual override.
"""

import pytest

from algo.orchestration.halt_flag_manager import HaltFlagManager


def _manager():
    return HaltFlagManager.__new__(HaltFlagManager)


def test_bare_call_with_neither_arg_raises_type_error():
    manager = _manager()
    with pytest.raises(TypeError, match="allowed_triggers"):
        manager.clear_halt_flag("some reason")


def test_mismatched_trigger_refuses_to_clear_without_raising(monkeypatch):
    manager = _manager()
    monkeypatch.setattr(manager, "get_halt_triggered_by", lambda: "phase9_reconciliation_governance")
    result = manager.clear_halt_flag("reason", allowed_triggers=frozenset({"phase1_data_freshness", None}))
    assert result is False


def test_force_bypasses_the_check_entirely(monkeypatch):
    manager = _manager()
    monkeypatch.setattr(manager, "get_halt_triggered_by", lambda: "phase9_reconciliation_governance")
    monkeypatch.setattr(manager, "_clear_halt_flag_rds", lambda reason: True)
    monkeypatch.setenv("LOCAL_MODE", "true")
    result = manager.clear_halt_flag("manual override", force=True)
    assert result is True


def test_matching_trigger_proceeds_to_clear(monkeypatch):
    manager = _manager()
    monkeypatch.setattr(manager, "get_halt_triggered_by", lambda: "phase1_data_freshness")
    monkeypatch.setattr(manager, "_clear_halt_flag_rds", lambda reason: True)
    monkeypatch.setenv("LOCAL_MODE", "true")
    result = manager.clear_halt_flag("reason", allowed_triggers=frozenset({"phase1_data_freshness", None}))
    assert result is True
