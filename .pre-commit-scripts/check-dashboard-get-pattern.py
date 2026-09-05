#!/usr/bin/env python3
"""Pre-commit check: Detect problematic .get() patterns in finance-critical code.

Dashboard panels should use fail-fast pattern:
  1. Check error_boundary.has_error(data) once
  2. Use direct access for validated fields
  3. Only .get() for optional fields (no default or default=None)

Loaders should avoid:
  - .get() with numeric defaults (0, 0.0) for price/financial data
  - .get() with dict defaults ({}) for financial records
  - .get() with string defaults that mask missing data

Pattern violations to catch:
  - Multiple .get() calls on same data dict in same function
  - .get() without checking has_error() first (dashboard only)
  - .get() with numeric/dict defaults in finance-critical data
  - .get() in nested loops over data items
"""

import re
import sys


def check_get_patterns_with_defaults(filepath: str) -> list[str]:
    """Check for problematic .get() calls with numeric/dict defaults.

    Finance-critical paths should not silently default to 0, 0.0, {}, etc.
    These patterns hide missing data.
    """
    violations = []

    finance_paths = ("loaders/", "algo/trading/", "algo/risk/", "algo/signals/")
    if not filepath.endswith(".py") or not any(fp in filepath for fp in finance_paths):
        return violations

    try:
        with open(filepath, encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
    except Exception as e:
        return [f"Could not read file: {e}"]

    # Pattern: .get("key", numeric/dict/problematic_default)
    problem_patterns = [
        (r'\.get\s*\(\s*["\'][\w_]+["\']\s*,\s*0(?:\.\d+)?\s*\)', "numeric default (hides missing price data)"),
        (r'\.get\s*\(\s*["\'][\w_]+["\']\s*,\s*\{\s*\}\s*\)', "dict default (hides missing record)"),
        (r'\.get\s*\(\s*["\'][\w_]+["\']\s*,\s*""\s*\)', "empty string default (hides missing data)"),
    ]

    for i, line in enumerate(lines, 1):
        for pattern, description in problem_patterns:
            if re.search(pattern, line):
                default_val = description.split("(")[1].split(")")[0]
                violations.append(
                    f"  Line {i}: {description} in .get() call. "
                    f"Finance paths must fail on missing data, not default to {default_val}."
                )

    return violations


def check_dashboard_patterns(filepath: str) -> list[str]:
    """Check file for dashboard .get() antipatterns.

    Returns list of violations with line numbers.
    """
    violations = []

    # BUG FOUND 2026-08-11: this matched "dashboard" as a bare substring anywhere in the
    # path, so it fired on lambda/api/routes/algo_handlers/dashboard.py - a Lambda API
    # handler that has nothing to do with the TUI dashboard package and doesn't import
    # error_boundary/has_error() at all (it uses @db_route_handler/@validate_api_response
    # instead). The has_error() convention this check enforces is defined in
    # dashboard/error_boundary.py and only applies to the dashboard/ TUI package - scope to
    # that specifically, not any file whose path happens to contain the word "dashboard".
    #
    # BUG FOUND 2026-09-05: the "/dashboard/" in normalized fallback (added for this
    # exact reason above) is ITSELF the same bug class one level down - it matches any
    # nested directory anywhere in the repo that happens to be *named* "dashboard", not
    # just the real repo-root TUI package. Confirmed live when
    # lambda/api/routes/algo_handlers/dashboard.py was split into a package (file-size-
    # ratchet bloater decomposition) and became lambda/api/routes/algo_handlers/dashboard/
    # - "/dashboard/" is a substring of that path too, so its new positions.py/status.py
    # submodules (same non-TUI Lambda API handlers as before, still no error_boundary/
    # has_error() import) got flagged. The real TUI package is always at the repo root, so
    # anchor to that: only the first path segment may be "dashboard".
    normalized = filepath.replace("\\", "/")
    first_segment = normalized.split("/", 1)[0]
    if not filepath.endswith(".py") or first_segment != "dashboard":
        return violations

    try:
        with open(filepath, encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
    except Exception as e:
        return [f"Could not read file: {e}"]

    # Pattern 1: Function with 5+ .get() calls without has_error() check
    # BUG FOUND 2026-08-24 (real-money-readiness goal, dashboard.py panel sweep): this
    # matched ANY `def`, indented or not, so a nested helper function (e.g.
    # panel_circuit's own `def fmt_b(br):`, defined inside panel_circuit's body after it
    # already called `_error_panel(...)`) reset the has_error_check tracker to False and
    # got scanned as if it were its own top-level function - flagging its .get() calls as
    # unchecked even though the ENCLOSING function's check already covers every item
    # `fmt_b` is called on. Same false-positive class as the 2026-08-23 fix just above
    # (panel_portfolio/panel_performance_spark's `_error_panel` indirection) - this time
    # via nesting instead of indirection. Anchoring to column 0 (`^def`, no `\s*` prefix)
    # means only genuine top-level function definitions reset the tracker; a nested `def`
    # (always indented in valid Python) is treated as part of its enclosing function's
    # own body, inheriting whatever has_error()/_error_panel() check already fired there.
    func_pattern = re.compile(r"^def\s+(\w+)\s*\(")
    get_pattern = re.compile(r"\.get\(")
    # FALSE POSITIVE FIXED 2026-08-23 (goal session): dashboard/panels/portfolio.py's
    # panel_portfolio and panel_performance_spark both already correctly implement the
    # fail-fast error-boundary pattern this check exists to enforce - they call
    # `_error_panel(data_name, data, title)` (dashboard/panels/_helpers.py), which calls
    # `error_boundary.has_error(data)` internally and returns an error Panel on the
    # caller's behalf. This regex only ever matched a literal `has_error(` substring
    # written directly in the scanned function's own body, so it never recognized that
    # equivalent, already-established indirection - live-confirmed false CRITICAL failure
    # on a commit that never touched either function's .get() calls at all. Same false-
    # positive class as the "dashboard" bare-substring bug already fixed in this same file
    # 2026-08-11 (see check_dashboard_patterns' own comment above) - naive text matching
    # missing a real, equivalent pattern instead of the literal one it was written for.
    #
    # FALSE POSITIVE FIXED 2026-08-25 (money-% goal session): a third equivalent pattern -
    # dashboard/fetchers_market.py's fetch_market/fetch_risk_metrics/fetch_sector_rotation
    # (and every other fetcher in that file) already correctly implement fail-fast via
    # `FetcherValidator.check_api_error(data)` (dashboard/fetcher_validator.py) before any
    # .get() call, immediately returning on API-level failure - same real intent as
    # has_error()/_error_panel(), just a third literal spelling this regex never recognized.
    # This was a genuine, live, whole-file blocker: because check_dashboard_patterns scans
    # a function's ENTIRE current body (not the diff), any future commit touching
    # dashboard/fetchers_market.py at all - even a single unrelated line - would fail this
    # hook on 3 functions nobody touched, regardless of what that commit actually changed.
    has_error_pattern = re.compile(r"has_error\(|_error_panel\(|check_api_error\(")

    in_function = None
    func_start_line = 0
    get_count = 0
    has_error_check = False

    for i, line in enumerate(lines, 1):
        func_match = func_pattern.match(line)
        if func_match:
            # New function: check if previous one had issues
            if in_function and get_count >= 5 and not has_error_check:
                violations.append(
                    f"  Line {func_start_line} ({in_function}): {get_count} .get() calls, no has_error() check"
                )
            in_function = func_match.group(1)
            func_start_line = i
            get_count = 0
            has_error_check = False

        if has_error_pattern.search(line):
            has_error_check = True

        if get_pattern.search(line):
            get_count += 1

    # Check last function
    if in_function and get_count >= 5 and not has_error_check:
        violations.append(f"  Line {func_start_line} ({in_function}): {get_count} .get() calls, no has_error() check")

    return violations


if __name__ == "__main__":
    all_violations = []

    for filepath in sys.argv[1:]:
        # Check for problematic defaults in loaders
        violations = check_get_patterns_with_defaults(filepath)
        if violations:
            all_violations.append(f"{filepath} (loader/finance checks):")
            all_violations.extend(violations)

        # Check for dashboard fail-fast pattern violations
        violations = check_dashboard_patterns(filepath)
        if violations:
            all_violations.append(f"{filepath} (dashboard checks):")
            all_violations.extend(violations)

    if all_violations:
        print("[FAIL-FAST VIOLATION] .get() pattern violations found:")
        print("\n".join(all_violations))
        print(
            "\nFix:\n"
            "  Dashboard: Use error_boundary.has_error() + direct access (see panels/data_extractors.py)\n"
            "  Loaders: Remove numeric/dict defaults from .get() - use strict validation or raise\n"
            "  Finance paths: Missing data must be visible (fail fast), not silently defaulted"
        )
        sys.exit(1)

    sys.exit(0)
