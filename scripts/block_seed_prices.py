#!/usr/bin/env python3
"""Pre-commit hook: Block seed_prices in orchestrator Lambda handler.

Prevents accidental addition of seed_prices feature to production
orchestrator Lambda. Price seeding must be in separate test Lambda only.

Usage: Called automatically by pre-commit framework
"""

import sys
from pathlib import Path


def check_file(filepath: str) -> bool:
    """Check if file contains seed_prices handling.

    Args:
        filepath: Path to file to check

    Returns:
        True if file is safe, False if seed_prices detected
    """
    path = Path(filepath)
    if not path.exists():
        return True  # File doesn't exist (probably being deleted)

    try:
        content = path.read_text()
    except Exception as e:
        print(f"[WARNING] Could not read {filepath}: {e}")
        return True  # Warn but don't block

    # Check for seed_prices handling in this file
    if 'event.get("seed_prices")' in content or "seed_prices" in content:
        # Exception: allow in test seed prices Lambda
        if "test-seed-prices" in filepath or "test_seed" in filepath:
            return True  # Safe location

        # Exception: allow in comments/documentation
        if filepath.endswith((".md", ".txt", ".rst")):
            return True  # Documentation is okay

        # BLOCK: seed_prices in orchestrator Lambda is not allowed
        if "orchestrator" in filepath and "lambda" in filepath.lower():
            return False

    return True


def main() -> int:
    """Entry point for pre-commit hook.

    Returns:
        0 if all files pass, 1 if any blocked
    """
    # Get list of files from command line (passed by pre-commit framework)
    files = sys.argv[1:]

    if not files:
        return 0  # No files to check

    failed = []
    for filepath in files:
        if not check_file(filepath):
            failed.append(filepath)
            print(
                f"[BLOCKED] {filepath}\n"
                f"  ✗ seed_prices feature detected in orchestrator Lambda\n"
                f"  → Price seeding must be in separate test Lambda\n"
                f"  → Location: lambda/test-seed-prices/lambda_function.py\n"
                f"  → Docs: steering/TEST_DATA_GOVERNANCE.md\n"
            )

    if failed:
        print(f"\n[FAILED] {len(failed)} file(s) failed pre-commit check")
        print("Remove seed_prices from orchestrator Lambda handler before committing.")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
