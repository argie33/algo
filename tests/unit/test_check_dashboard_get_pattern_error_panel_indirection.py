"""Regression test for a 2026-08-23 false-positive fix in check-dashboard-get-pattern.py:
its has_error() scope check only ever matched a literal `has_error(` substring written
directly in the scanned function's own body. dashboard/panels/portfolio.py's panel_portfolio
and panel_performance_spark both already correctly implement the fail-fast error-boundary
pattern via `_error_panel(data_name, data, title)` (dashboard/panels/_helpers.py), which calls
`error_boundary.has_error(data)` internally on the caller's behalf - but the naive regex never
recognized that established, already-conventional indirection, so a commit that never touched
either function's .get() calls at all failed pre-commit with a false CRITICAL violation.
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


def test_error_panel_indirection_satisfies_the_has_error_check():
    violations = check_dashboard_get_pattern.check_dashboard_patterns("dashboard/panels/portfolio.py")
    flagged_functions = {v for v in violations if "panel_portfolio" in v or "panel_performance_spark" in v}
    assert flagged_functions == set(), (
        "panel_portfolio/panel_performance_spark both start with an _error_panel(...) call "
        "that internally calls has_error() - they must not be flagged just because the check "
        f"was looking for a literal has_error( substring. Got: {flagged_functions}"
    )


def test_check_still_catches_real_violations_in_the_same_file_scope():
    """Guard against over-correcting: dashboard/panels/health.py has real, pre-existing
    .get()-without-has_error()-or-_error_panel() violations (see .pre-commit-config.yaml's
    exclude list for this hook) and must still be flagged by the underlying check function -
    only the pre-commit config layer excludes it pending a dedicated remediation pass, not
    this function's own detection logic.
    """
    violations = check_dashboard_get_pattern.check_dashboard_patterns("dashboard/panels/health.py")
    assert violations != []
