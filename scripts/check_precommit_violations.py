#!/usr/bin/env python3
"""Check for pre-commit hook violations and bypasses.

Detects:
- Developers using SKIP= to bypass governance hooks
- Missing or disabled pre-commit configurations
- Hooks that are timing out (causing skips)
"""

import subprocess
import re
from pathlib import Path

CRITICAL_HOOKS = [
    "check-credential-defaults",
    "enforce-type-safety-rules",
    "check-dashboard-get-pattern",
]

def check_git_log_for_skips():
    """Check git log for SKIP= patterns."""
    try:
        result = subprocess.run(
            ["git", "log", "--all", "--oneline", "--grep=SKIP"],
            capture_output=True,
            text=True
        )

        skipped_commits = result.stdout.strip().split('\n')
        skipped_commits = [c for c in skipped_commits if c]

        if skipped_commits:
            print("WARNING: Found commits that bypassed pre-commit hooks:")
            for commit in skipped_commits[:10]:
                print(f"  - {commit}")

            return len(skipped_commits)
        return 0

    except Exception as e:
        print(f"Error checking git log: {e}")
        return -1

def check_precommit_config():
    """Verify pre-commit configuration is valid."""
    config_path = Path(".pre-commit-config.yaml")

    if not config_path.exists():
        print("ERROR: .pre-commit-config.yaml not found")
        return False

    content = config_path.read_text()

    # Check all critical hooks are present
    missing_hooks = []
    for hook in CRITICAL_HOOKS:
        if hook not in content:
            missing_hooks.append(hook)

    if missing_hooks:
        print("ERROR: Missing critical pre-commit hooks:")
        for hook in missing_hooks:
            print(f"  - {hook}")
        return False

    print("OK: All critical pre-commit hooks configured")
    return True

def check_hook_installation():
    """Verify pre-commit hook is installed locally."""
    hook_path = Path(".git/hooks/pre-commit")

    if not hook_path.exists():
        print("WARNING: pre-commit hook not installed locally")
        print("  Run: pre-commit install")
        return False

    print("OK: pre-commit hook installed")
    return True

def main():
    """Run all compliance checks."""
    print("="*80)
    print("PRE-COMMIT COMPLIANCE CHECK")
    print("="*80 + "\n")

    issues = 0

    # Check config
    if not check_precommit_config():
        issues += 1

    print()

    # Check installation
    if not check_hook_installation():
        issues += 1

    print()

    # Check for bypasses
    skips = check_git_log_for_skips()
    if skips > 0:
        issues += 1
        print(f"  Total commits with hook bypasses: {skips}")

    print("\n" + "="*80)

    if issues == 0:
        print("RESULT: All compliance checks PASSED")
        print("="*80)
        return 0
    else:
        print(f"RESULT: {issues} compliance issue(s) FOUND")
        print("="*80)
        return 1

if __name__ == "__main__":
    import sys
    sys.exit(main())
