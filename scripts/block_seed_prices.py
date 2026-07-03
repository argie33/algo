#!/usr/bin/env python3
"""Pre-commit hook to block seed price data from being committed.

This hook ensures that test/seed price files are not accidentally committed
to the repository. Used by pre-commit framework to validate commits.
"""

import sys
from pathlib import Path


def check_seed_price_files(staged_files: list[str]) -> int:
    """Check if any seed price files are staged for commit.

    Args:
        staged_files: List of file paths staged for commit

    Returns:
        0 if no seed price files found, 1 if any seed price files are staged
    """
    blocked_patterns = [
        "seed_prices",
        "mock_prices",
        "test_prices",
    ]

    blocked = []
    for file_path in staged_files:
        p = Path(file_path)
        if any(pattern in p.name or pattern in str(p) for pattern in blocked_patterns):
            blocked.append(file_path)

    if blocked:
        print("[PRE-COMMIT] ERROR: Seed price files detected in commit:")
        for f in blocked:
            print(f"  - {f}")
        print("\nSeed price data should not be committed. Remove these files and try again.")
        return 1

    return 0


if __name__ == "__main__":
    # When run as a pre-commit hook, git provides staged file paths via stdin
    # For testing purposes, accept arguments from command line
    files = sys.argv[1:] if len(sys.argv) > 1 else []
    sys.exit(check_seed_price_files(files))
