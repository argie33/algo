"""Regression test for the 2026-08-11 fix: check-dashboard-get-pattern.py's has_error()
scope check matched "dashboard" as a bare substring anywhere in the file path, so it fired
false-positive violations on lambda/api/routes/algo_handlers/dashboard.py - a Lambda API
handler that has nothing to do with the TUI dashboard package and doesn't import
error_boundary/has_error() at all. The has_error() convention lives in
dashboard/error_boundary.py and only applies to the dashboard/ package - scoped to that.
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


def test_lambda_api_file_named_dashboard_is_not_scoped_in():
    violations = check_dashboard_get_pattern.check_dashboard_patterns("lambda/api/routes/algo_handlers/dashboard.py")
    assert violations == [], (
        "lambda/api/routes/algo_handlers/dashboard.py isn't part of the dashboard/ TUI "
        "package and doesn't use error_boundary.has_error() - it should never be scoped "
        "into this check just because 'dashboard' appears in its filename"
    )


def test_real_dashboard_package_file_is_still_scoped_in():
    violations = check_dashboard_get_pattern.check_dashboard_patterns("dashboard/panels/health.py")
    assert violations != [], (
        "a real file under dashboard/ with known .get()-without-has_error() violations "
        "must still be caught - the scope fix must not have over-corrected"
    )


def test_nested_dashboard_package_path_is_scoped_in():
    violations = check_dashboard_get_pattern.check_dashboard_patterns("dashboard/fetchers_market.py")
    assert violations != [], "files directly under dashboard/ must remain in scope"
