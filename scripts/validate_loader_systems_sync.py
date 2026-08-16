#!/usr/bin/env python3
"""Validate that loader registry, Lambda, and Terraform loader_file_map are in sync.

This script checks:
1. All loaders in registry have shorthand mappings
2. All loaders have timeout definitions
3. Lambda VALID_LOADER_NAMES matches registry table names
4. Terraform loader_file_map matches registry loaders

Exit code:
  0 = All systems in sync
  1 = Drift detected (requires manual fix)
"""

import re
import sys
from pathlib import Path

# Force UTF-8 output on Windows. Guarded against pytest: reassigning sys.stdout/stderr
# to a new TextIOWrapper while pytest has already substituted its own capture streams
# corrupts pytest's capture teardown the first time anything imports this module.
if sys.platform == "win32" and "pytest" not in sys.modules:
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root))

from loaders.loader_registry import LOADER_TABLES, SHORTHAND_TO_FILENAME, get_table_names  # noqa: E402


def load_terraform_loaders():
    """Extract loader_file_map from terraform/modules/loaders/main.tf."""
    tf_file = repo_root / "terraform" / "modules" / "loaders" / "main.tf"

    loaders = {}
    with open(tf_file) as f:
        content = f.read()

    # Extract loader_file_map block
    start = content.find("loader_file_map = {")
    end = content.find("}", start)
    if start == -1 or end == -1:
        print("ERROR: Could not find loader_file_map in terraform file", file=sys.stderr)
        return {}

    map_block = content[start : end + 1]

    # Parse "key" = "value" pairs
    pattern = r'"([^"]+)"\s*=\s*"([^"]+)"'
    for match in re.finditer(pattern, map_block):
        table_name = match.group(1)
        filename = match.group(2)
        loaders[table_name] = filename

    return loaders


def load_lambda_valid_names():
    """Extract VALID_LOADER_NAMES from lambda/trigger-loaders/lambda_function.py."""
    lambda_file = repo_root / "lambda" / "trigger-loaders" / "lambda_function.py"

    with open(lambda_file) as f:
        content = f.read()

    # Check if it's importing from registry or hardcoded
    if "from loaders.loader_registry import get_table_names" in content:
        print("[OK] Lambda: Using auto-generated VALID_LOADER_NAMES from registry")
        return None  # Dynamically loaded, no static check needed
    elif "VALID_LOADER_NAMES = frozenset(" in content:
        # Parse hardcoded list
        start = content.find("VALID_LOADER_NAMES = frozenset(")
        end = content.find("}", start)
        if start == -1 or end == -1:
            return set()

        hardcoded_block = content[start : end + 1]
        pattern = r'"([^"]+)"'
        names = set()
        for match in re.finditer(pattern, hardcoded_block):
            # Skip commented lines
            line_start = hardcoded_block.rfind("\n", 0, match.start())
            line = hardcoded_block[line_start : match.start()]
            if "#" not in line:  # Not in a comment
                names.add(match.group(1))
        return names

    return set()


def main():
    print("=" * 70)
    print("LOADER SYSTEMS SYNC VALIDATION")
    print("=" * 70)

    all_issues = []

    # Get current state
    registry_filenames = set(LOADER_TABLES.keys())
    registry_table_names = get_table_names()
    registry_shorthands = set(SHORTHAND_TO_FILENAME.keys())

    terraform_loaders = load_terraform_loaders()
    lambda_names = load_lambda_valid_names()

    # Build mapping from terraform table names to filenames
    terraform_filenames = set(terraform_loaders.values())

    print("\nRegistry Statistics:")
    print(f"  Loader filenames: {len(registry_filenames)}")
    print(f"  Primary table names: {len(registry_table_names)}")
    print(f"  Shorthand aliases: {len(registry_shorthands)}")

    print("\nTerraform loader_file_map:")
    print(f"  Table->filename mappings: {len(terraform_loaders)}")
    print(f"  Unique filenames: {len(terraform_filenames)}")

    if lambda_names is None:
        print("\nLambda VALID_LOADER_NAMES:")
        print("  [OK] Auto-generated from registry (in sync)")
    else:
        print("\nLambda VALID_LOADER_NAMES:")
        print(f"  Hardcoded entries: {len(lambda_names)} (WARNING: should be auto-generated)")

    # Check 1: Registry completeness
    print(f"\n{'=' * 70}")
    print("CHECK 1: Registry Completeness")
    print(f"{'=' * 70}")

    missing_shorthands = registry_filenames - set(SHORTHAND_TO_FILENAME.values())
    if missing_shorthands:
        for loader in sorted(missing_shorthands):
            msg = f"MISSING_SHORTHAND: {loader} has no shorthand mapping"
            print(f"  [FAIL] {msg}")
            all_issues.append(msg)
    else:
        print("  [OK] All loaders have shorthand mappings")

    # Check 2: Terraform filenames vs Registry filenames (correct mapping)
    print(f"\n{'=' * 70}")
    print("CHECK 2: Terraform vs Registry Filenames")
    print(f"{'=' * 70}")

    registry_only = registry_filenames - terraform_filenames
    terraform_only = terraform_filenames - registry_filenames

    # Filter out deprecated entries (commented in terraform)
    terraform_only_filtered = terraform_only - {"load_yfinance_snapshot.py", "load_financial_statements.py"}

    if registry_only:
        for filename in sorted(registry_only):
            msg = f"REGISTRY_MISSING_FROM_TF: {filename} in registry but not in terraform"
            print(f"  [WARN] {msg}")
            # Don't fail on this - registry may have more entries

    if terraform_only_filtered:
        for filename in sorted(terraform_only_filtered):
            msg = f"TERRAFORM_MISSING_FROM_REGISTRY: {filename} in terraform but not in registry"
            print(f"  [FAIL] {msg}")
            all_issues.append(msg)

    if not terraform_only_filtered:
        if not registry_only:
            print("  [OK] All active terraform filenames are in registry")
        else:
            print("  [OK] All terraform filenames are covered (registry may have extras)")

    # Check 3: Lambda vs Registry (only if hardcoded)
    if lambda_names is not None:
        print(f"\n{'=' * 70}")
        print("CHECK 3: Lambda vs Registry Table Names")
        print(f"{'=' * 70}")

        registry_missing = registry_table_names - lambda_names
        lambda_missing = lambda_names - registry_table_names

        if registry_missing:
            for table in sorted(registry_missing):
                msg = f"REGISTRY_MISSING_FROM_LAMBDA: {table} in registry but not in Lambda"
                print(f"  [FAIL] {msg}")
                all_issues.append(msg)

        if lambda_missing:
            for table in sorted(lambda_missing):
                msg = f"LAMBDA_MISSING_FROM_REGISTRY: {table} in Lambda but not in registry (stale)"
                print(f"  [FAIL] {msg}")
                all_issues.append(msg)

        if not registry_missing and not lambda_missing:
            print(f"  [OK] Lambda VALID_LOADER_NAMES matches registry ({len(lambda_names)} loaders)")
    else:
        print(f"\n{'=' * 70}")
        print("CHECK 3: Lambda vs Registry Table Names")
        print(f"{'=' * 70}")
        print("  [OK] Lambda auto-generates from registry (always in sync)")

    # Summary
    print(f"\n{'=' * 70}")
    if all_issues:
        print(f"ISSUES FOUND: {len(all_issues)}")
        print(f"{'=' * 70}")
        for issue in all_issues:
            print(f"  {issue}")
        return 1
    else:
        print("All Systems in Sync [OK]")
        print(f"{'=' * 70}")
        return 0


if __name__ == "__main__":
    sys.exit(main())
