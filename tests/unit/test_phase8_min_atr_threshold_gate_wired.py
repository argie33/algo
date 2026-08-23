"""Regression test: the concentration_prefilter's ATR floor must use MIN_ATR_THRESHOLD, not a
bare `atr < 0`.

Same structural bug class as [[min_entry_price_dead_config_fixed_20260823]]: MIN_ATR_THRESHOLD
(0.01 in validation_thresholds.py) is documented as "values < 0.01 indicate stale/frozen data,"
but the concentration_prefilter's sanity-check gate only enforced `atr < 0` - a near-zero-but-
positive ATR (e.g. 0.001, a genuinely stale/frozen stock per that constant's own rationale)
passed this check and fed `_calculate_dynamic_stop_loss()` a degenerate volatility figure,
producing a stop-loss placed essentially at entry price. Fixed 2026-08-23 by widening the
comparison to `atr < MIN_ATR_THRESHOLD`.

Like test_phase8_min_entry_price_gate_wired_and_audited.py, this is a source-inspection test:
run() has ~15 injected dependencies with no existing full-mock test harness (see
test_phase8_execution_failure_audit_gap.py's own docstring on the same constraint).
"""

import inspect

from algo.orchestrator import phase8_entry_execution as p8
from algo.orchestrator.validation_thresholds import MIN_ATR_THRESHOLD


def test_min_atr_threshold_is_still_a_real_positive_floor() -> None:
    # Locks in that this constant stays a meaningful floor (not silently reset to 0, which
    # would make the fix below a no-op again).
    assert MIN_ATR_THRESHOLD > 0


def test_concentration_prefilter_atr_check_uses_the_documented_threshold() -> None:
    source = inspect.getsource(p8.run)

    # Isolate the concentration_prefilter's own combined NaN/degenerate-value gate (the one
    # that skips, not raises) via its unique preceding comment anchor, then confirm its ATR
    # comparison uses MIN_ATR_THRESHOLD, not a bare `atr < 0` that lets near-zero-but-positive
    # ATR through. Deliberately does NOT check the later real-order-submission path's own
    # (correctly still bare) `atr < 0` - that path is reserved for genuine corruption
    # (NaN/inf/negative), not this business-rule threshold.
    gate_block = source.split("BUG FOUND 2026-08-23 (same audit as MIN_ENTRY_PRICE)")[1].split("):", 1)[0]
    assert "atr < MIN_ATR_THRESHOLD" in gate_block
    assert "or atr < 0" not in gate_block


def test_module_imports_min_atr_threshold() -> None:
    module_source = inspect.getsource(p8)
    import_line = [
        line for line in module_source.splitlines() if "from algo.orchestrator.validation_thresholds import" in line
    ][0]
    assert "MIN_ATR_THRESHOLD" in import_line
