"""Regression test for a 2026-08-24 false-positive fix in check-dashboard-get-pattern.py:
its function-boundary regex (`^\\s*def\\s+`) matched ANY `def`, indented or not, so a nested
helper function (e.g. panel_circuit's own `def fmt_b(br):`, defined inside panel_circuit's
body AFTER it already called `_error_panel(...)`) reset the has_error_check tracker and got
scanned as if it were its own top-level function - flagging its .get() calls as unchecked even
though the enclosing function's check already covers every item the helper is called on.

Same false-positive class as the 2026-08-23 fix (see
test_check_dashboard_get_pattern_error_panel_indirection.py) - that one was about indirection
through `_error_panel()`, this one is about nesting.
"""

import importlib.util
import sys
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "check_dashboard_get_pattern",
    Path(__file__).resolve().parents[2] / ".pre-commit-scripts" / "check-dashboard-get-pattern.py",
)
assert _SPEC and _SPEC.loader
check_dashboard_get_pattern = importlib.util.module_from_spec(_SPEC)
sys.modules["check_dashboard_get_pattern"] = check_dashboard_get_pattern
_SPEC.loader.exec_module(check_dashboard_get_pattern)


def test_nested_helper_inherits_enclosing_functions_has_error_check():
    violations = check_dashboard_get_pattern.check_dashboard_patterns("dashboard/panels/circuit.py")
    flagged = {v for v in violations if "fmt_b" in v}
    assert flagged == set(), (
        "fmt_b is nested inside panel_circuit, which already calls _error_panel(...) before "
        f"ever calling fmt_b - it must not be flagged as its own unchecked scope. Got: {flagged}"
    )


def test_check_still_catches_real_violations_in_the_same_file_scope():
    """Guard against over-correcting: dashboard/panels/health_status_panel.py (one of the
    health_*.py files health.py split into 2026-09-05) has real, pre-existing
    .get()-without-has_error()-or-_error_panel() violations at the TOP level (not nested) and
    must still be flagged.
    """
    violations = check_dashboard_get_pattern.check_dashboard_patterns("dashboard/panels/health_status_panel.py")
    assert violations != []
