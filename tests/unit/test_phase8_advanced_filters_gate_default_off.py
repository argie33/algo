"""Regression test: the optional AdvancedFilters gate in Phase 8 must default to OFF, fail open
at initialization, and fail CLOSED per-candidate.

AdvancedFilters.evaluate_candidate() was unwired dead code with real bugs (see
advanced_filters_dead_code_investigation memory) - those bugs are now fixed and verified
exception-safe at scale (300 real candidates, 0 crashes). Wired in as an OPTIONAL secondary
gate behind algo_config.enable_advanced_filters_gate, defaulting to False, so merging this
does not change current behavior (paper or auto) unless someone explicitly enables it.

Per-candidate evaluation was originally also fail-open (2026-08-31), but the 2026-09-06
pre-real-money audit flagged that as inconsistent with every other risk/quality gate in the
system (pretrade_checks.py, circuit breakers), which all fail closed on error - a swallowed
exception mid-loop would silently let an unvetted candidate through with only a log line.
Fixed same day to reject just that one candidate on error instead. Initialization failure
(the gate can't even load market context) stays fail-open by design - an optional new gate
failing to load shouldn't halt all trading.

This is a source check, not a mocked run() call - run() has ~15 injected dependencies with no
existing test harness (see test_phase8_duplicate_race_exception_handling.py's sibling note),
so this pins the properties that matter: default-off, placed after the existing always-on
health check (not replacing it), fails open at initialization, and fails closed per-candidate.
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


def test_gate_per_candidate_failure_fails_closed():
    source = inspect.getsource(p8.run)
    loop_section = source[source.index("for signal in qualified_trades:") :]
    gate_call_idx = loop_section.index("advanced_filters.evaluate_candidate(")
    # The nearest enclosing except after the evaluate_candidate() call must not re-raise, but
    # must also not silently let the candidate through - it should log, record a rejection, and
    # `continue` (skip this candidate) rather than falling through to submit it, matching every
    # other risk/quality gate in the system (pretrade_checks.py, circuit breakers).
    after_call = loop_section[gate_call_idx : gate_call_idx + 2000]
    assert "except Exception as e:" in after_call
    assert "failing closed" in after_call.lower()
    except_idx = after_call.index("except Exception as e:")
    except_section = after_call[except_idx:]
    assert "continue" in except_section, (
        "A per-candidate AdvancedFilters error must `continue` (skip/reject this candidate), "
        "not fall through to submit it unvetted."
    )
    assert "skipped_count += 1" in except_section
