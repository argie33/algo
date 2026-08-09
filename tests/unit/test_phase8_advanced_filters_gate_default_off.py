"""Regression test: the optional AdvancedFilters gate in Phase 8 must default to OFF and fail open.

AdvancedFilters.evaluate_candidate() was unwired dead code with real bugs (see
advanced_filters_dead_code_investigation memory) - those bugs are now fixed and verified
exception-safe at scale (300 real candidates, 0 crashes). Wired in as an OPTIONAL secondary
gate behind algo_config.enable_advanced_filters_gate, defaulting to False, so merging this
does not change current behavior (paper or auto) unless someone explicitly enables it.

This is a source check, not a mocked run() call - run() has ~15 injected dependencies with no
existing test harness (see test_phase8_duplicate_race_exception_handling.py's sibling note),
so this pins the properties that matter: default-off, placed after the existing always-on
health check (not replacing it), and fails open (never blocks/crashes on its own error) both
at initialization and per-candidate.
"""

import inspect

from algo.orchestrator import phase8_entry_execution as p8


def test_gate_defaults_to_off():
    source = inspect.getsource(p8.run)
    assert 'config.get("enable_advanced_filters_gate", False)' in source, (
        "The AdvancedFilters gate must default to False via config.get's default parameter - "
        "merging this integration must not change behavior unless explicitly enabled."
    )


def test_gate_is_placed_after_existing_health_check():
    source = inspect.getsource(p8.run)
    health_check_idx = source.index("PreEntryHealthValidator.validate(")
    gate_call_idx = source.index("advanced_filters.evaluate_candidate(")
    assert gate_call_idx > health_check_idx, (
        "AdvancedFilters must be wired in AFTER the existing always-on PreEntryHealthValidator "
        "check, as an additional layer - not replacing or preceding the established gate."
    )


def test_gate_init_failure_does_not_raise():
    source = inspect.getsource(p8.run)
    # The init block (config check through the per-candidate loop's health check, which comes
    # right after it) must wrap AdvancedFilters construction/load_market_context in a try/except
    # that logs and leaves advanced_filters as None, not one that lets an exception propagate.
    start = source.index('if config.get("enable_advanced_filters_gate", False):')
    end = source.index("PreEntryHealthValidator.validate(")
    init_section = source[start:end]
    assert "except Exception" in init_section, (
        "AdvancedFilters initialization must fail open (catch Exception, log, continue with "
        "advanced_filters=None) rather than crash Phase 8 if it can't initialize."
    )
    assert "advanced_filters = None" in init_section


def test_gate_per_candidate_failure_does_not_raise():
    source = inspect.getsource(p8.run)
    loop_section = source[source.index("for signal in qualified_trades:") :]
    gate_call_idx = loop_section.index("advanced_filters.evaluate_candidate(")
    # The nearest enclosing except after the evaluate_candidate() call must not re-raise -
    # it should log a warning and fall through, not `continue`/`raise` the candidate away
    # on an infrastructure error (as opposed to a real af_result["pass"] is False rejection).
    after_call = loop_section[gate_call_idx:gate_call_idx + 1500]
    assert "except Exception as e:" in after_call
    assert "failing open" in after_call.lower()
