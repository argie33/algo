"""Regression test for a 2026-08-25 false-positive fix in check-dashboard-get-pattern.py:
its has_error() scope check only ever matched `has_error(` or `_error_panel(` literal
substrings. dashboard/fetchers_market.py's fetch_market/fetch_exp_factors/fetch_risk_metrics/
fetch_sector_rotation all already correctly implement fail-fast via
`FetcherValidator.check_api_error(data)` (dashboard/fetcher_validator.py) before any .get()
call - a third, equivalent spelling of the same real fail-fast intent this check exists to
enforce, never recognized by the regex. Because check_dashboard_patterns scans a function's
ENTIRE current body (not the diff), this was a genuine whole-file blocker: any future commit
touching dashboard/fetchers_market.py at all - even a single unrelated line - would fail this
hook on 3 functions nobody touched, same false-CRITICAL-failure shape as the 2026-08-23
_error_panel indirection fix this mirrors.
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


def test_check_api_error_indirection_satisfies_the_has_error_check():
    violations = check_dashboard_get_pattern.check_dashboard_patterns("dashboard/fetchers_market.py")
    assert violations == [], (
        "fetch_market/fetch_exp_factors/fetch_risk_metrics/fetch_sector_rotation all start "
        "with a FetcherValidator.check_api_error(...) call - they must not be flagged just "
        f"because the check was looking for a literal has_error(/_error_panel( substring. Got: {violations}"
    )


def test_check_still_catches_real_violations_in_the_same_file_scope():
    """Guard against over-correcting: dashboard/panels/health_status_panel.py (one of the
    health_*.py files health.py split into 2026-09-05 - see .pre-commit-config.yaml's
    exclude list for this hook) has real, pre-existing
    .get()-without-has_error()-or-_error_panel()-or-check_api_error() violations and must
    still be flagged by the underlying check function."""
    violations = check_dashboard_get_pattern.check_dashboard_patterns("dashboard/panels/health_status_panel.py")
    assert violations != []
