"""Regression test: MIN_ENTRY_PRICE must actually gate entries and audit the rejection.

See [[min_entry_price_dead_config_fixed_20260823]] in memory: MIN_ENTRY_PRICE was 0.0
(excluded nothing) and was never imported into phase8_entry_execution.py at all - every real
entry-price check here was a hardcoded `entry_price <= 0`, completely disconnected from the
"configurable" constant. Fixed 2026-08-23 by raising the threshold to 5.0 (SEC Rule 3a51-1
penny-stock definition) and wiring a real gate into the concentration_prefilter loop. That fix
shipped with no test covering this exact path (per its own memory entry: "no existing test
covered this path") - closing that gap here.

Like test_sizer_blocked_and_liquidity_skips_are_persisted_to_audit_table in
test_phase8_execution_failure_audit_gap.py, this is a source-inspection test rather than a
mocked run() call: run() has ~15 injected dependencies with no existing full-mock test harness
(that file's own docstring), so pinning the exact source shape of this branch is the
established pattern this codebase already uses for asserting correctness deep inside run()
without building that harness from scratch.
"""

import inspect

from algo.orchestrator import phase8_entry_execution as p8
from algo.orchestrator.validation_thresholds import MIN_ENTRY_PRICE


def test_min_entry_price_is_a_real_floor_not_the_old_dead_zero() -> None:
    # Locks in the actual fixed value so a future edit can't silently drift the floor back
    # toward "excludes nothing" without a deliberate, visible change here too.
    assert MIN_ENTRY_PRICE == 5.0


def test_run_imports_min_entry_price_from_validation_thresholds() -> None:
    # The original bug was structural: the constant existed but was never imported into this
    # module at all, so no code here could reference it even if someone tried. Pin the import
    # itself (not just module-attribute access, which mypy's implicit-reexport rule blocks
    # for a name this module only imports rather than defines).
    module_source = inspect.getsource(p8)
    assert "from algo.orchestrator.validation_thresholds import" in module_source
    import_line = [
        line for line in module_source.splitlines() if "from algo.orchestrator.validation_thresholds import" in line
    ][0]
    assert "MIN_ENTRY_PRICE" in import_line


def test_below_min_entry_price_is_skipped_not_raised_and_is_audited() -> None:
    source = inspect.getsource(p8.run)

    # Isolate the concentration_prefilter's MIN_ENTRY_PRICE branch specifically (not the
    # separate, later order-submission-path price check further down in run(), which is
    # deliberately a fatal RuntimeError for genuine data corruption - see that check's own
    # comment - and must never be confused with this business-rule rejection).
    branch = source.split("if entry_price < MIN_ENTRY_PRICE:")[1].split("continue", 1)[0]

    # Must be a skip (continue past this signal), never a raise - a sub-$5 signal is a
    # business-rule rejection, not data corruption, and must not halt the rest of Phase 8.
    assert "raise" not in branch

    # Must be counted and persisted to the audit trail, exactly like every other skip reason
    # in this loop (pretrade_check, duplicate_position, quality_gate, stop_too_tight, ...).
    assert 'skipped_reason_counts["below_min_entry_price"]' in branch
    assert "_log_signal_rejection(" in branch


def test_min_entry_price_gate_runs_before_stop_loss_is_calculated() -> None:
    """A sub-floor entry_price must never reach stop-loss math - _calculate_dynamic_stop_loss
    divides/compares against entry_price, and this gate exists specifically to keep
    numerically-degenerate or governance-invalid prices out of that calculation entirely."""
    source = inspect.getsource(p8.run)

    gate_pos = source.index("if entry_price < MIN_ENTRY_PRICE:")
    stop_loss_pos = source.index("stop_loss = _calculate_dynamic_stop_loss(entry_price, atr, sma_50)")
    assert gate_pos < stop_loss_pos
