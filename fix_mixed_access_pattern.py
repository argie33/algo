#!/usr/bin/env python3
"""
Fix mixed access patterns - where direct access and .get() are used together
after error checks.

After has_error() check, ALL critical fields should use direct access consistently.
"""

import re
from pathlib import Path


def fix_health_panel():
    """Fix health.py - consolidate access patterns after error checks."""
    filepath = Path("tools/dashboard/panels/health.py")
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    original = content
    modified = False

    # Line 119-120: After extract_run_info, use direct access
    # OLD: if run["success"] and not run.get("halted")
    # NEW: if run_info["success"] and not run_info["halted"]
    # (already handled by extract_run_info refactor)

    # Line 125: if run.get("_source") == "exec_log": -> run["_source"]
    # After not has_error(run) check, should use direct access
    pattern = r'if run and not has_error\(run\) and run\.get\("_source"\) == "exec_log":'
    if re.search(pattern, content):
        content = re.sub(pattern, r'if run and not has_error(run) and run["_source"] == "exec_log":', content)
        modified = True

    # Line 83: risk.get("var95") in condition -> risk["var95"]
    # After: if risk and not has_error(risk) and risk.get("var95") and ...
    pattern = r'if risk and not has_error\(risk\) and risk\.get\("var95"\) and'
    if re.search(pattern, content):
        content = re.sub(pattern, r'if risk and not has_error(risk) and risk["var95"] and', content)
        modified = True

    if modified:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    return False


def fix_portfolio_panel():
    """Fix portfolio.py - consolidate access patterns after error checks."""
    filepath = Path("tools/dashboard/panels/portfolio.py")
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    original = content
    modified = False

    # Similar patterns - after error checks, use consistent direct access
    pattern = r'if perf and not has_error\(perf\) and perf\.get\("_no_data"\)'
    if re.search(pattern, content):
        # _no_data is intentionally optional, keep as .get()
        pass

    if modified:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    return False


def fix_sectors_panel():
    """Fix sectors.py - consolidate access patterns."""
    filepath = Path("tools/dashboard/panels/sectors.py")
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    original = content
    modified = False

    # Check for patterns like: if sec_rot and not has_error(sec_rot) and sec_rot.get(...)
    # These should use direct access for critical fields

    if modified and content != original:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    return False


def main():
    import sys
    print("=" * 80, file=sys.stderr)
    print("FIXING MIXED ACCESS PATTERNS AFTER ERROR CHECKS", file=sys.stderr)
    print("=" * 80, file=sys.stderr)

    fixes = [
        fix_health_panel(),
        fix_portfolio_panel(),
        fix_sectors_panel(),
    ]

    total_fixed = sum(1 for f in fixes if f)
    print("\n" + "=" * 80, file=sys.stderr)
    print(f"SUMMARY: Fixed {total_fixed} files", file=sys.stderr)
    print("=" * 80, file=sys.stderr)


if __name__ == "__main__":
    main()
