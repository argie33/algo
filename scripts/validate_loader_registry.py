#!/usr/bin/env python3
"""Validate loader registry consistency across all naming schemes.

This script checks for drift between:
1. LOADER_TABLES (loaders/loader_registry.py) - canonical registry
2. SHORTHAND_TO_FILENAME (loaders/loader_registry.py) - CLI shortcuts
3. LOADER_TIMEOUTS (scripts/local_loader_scheduler.py) - timeout definitions
4. PIPELINES (scripts/local_loader_scheduler.py) - scheduled loaders

Exit code 0: All checks pass
Exit code 1: Consistency issues found
"""

import os
import sys
import re
from pathlib import Path

# Add repo root to path so we can import modules
repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root))

try:
    from loaders.loader_registry import LOADER_TABLES, SHORTHAND_TO_FILENAME
except ImportError as e:
    print(f"ERROR: Could not import loader registry: {e}", file=sys.stderr)
    sys.exit(1)


def load_scheduler_config():
    """Load PIPELINES and LOADER_TIMEOUTS from scheduler."""
    pipelines = {}
    loader_timeouts = {}

    try:
        # Direct import
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "local_loader_scheduler",
            repo_root / "scripts" / "local_loader_scheduler.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        pipelines = module.PIPELINES

        # LOADER_TIMEOUTS is inside function, parse from file
        scheduler_file = repo_root / "scripts" / "local_loader_scheduler.py"
        with open(scheduler_file, 'r') as f:
            content = f.read()

        # Find LOADER_TIMEOUTS dict
        start = content.find("LOADER_TIMEOUTS = {")
        end = content.find("}", start)
        if start != -1 and end != -1:
            dict_lines = content[start:end+1]
            # Extract all timeout key names (shorthand names)
            shorthand_matches = re.findall(r'"([^"]+)":\s*\d+', dict_lines)
            # Convert shorthand to filenames
            for shorthand in shorthand_matches:
                if shorthand in SHORTHAND_TO_FILENAME:
                    loader_timeouts[SHORTHAND_TO_FILENAME[shorthand]] = True

        return pipelines, loader_timeouts
    except Exception as e:
        print(f"WARNING: Could not load scheduler config: {e}", file=sys.stderr)
        return pipelines, loader_timeouts


def main():
    pipelines, loader_timeouts = load_scheduler_config()

    print("=" * 70)
    print("LOADER REGISTRY CONSISTENCY AUDIT")
    print("=" * 70)

    all_loaders = set(LOADER_TABLES.keys())
    shorthand_loaders = set(SHORTHAND_TO_FILENAME.values())

    # Map timeout shorthand names to actual loader filenames
    timeout_loader_names = set()
    for shorthand_name in loader_timeouts.keys():
        if shorthand_name in SHORTHAND_TO_FILENAME:
            timeout_loader_names.add(SHORTHAND_TO_FILENAME[shorthand_name])
        else:
            # Timeout key doesn't map to any known shorthand (potential issue)
            timeout_loader_names.add(shorthand_name)

    # Convert pipelines to filenames
    pipeline_loaders = set()
    for pipeline_name, loaders_list in pipelines.items():
        for loader in loaders_list:
            # Convert shorthand to filename
            if loader in SHORTHAND_TO_FILENAME:
                pipeline_loaders.add(SHORTHAND_TO_FILENAME[loader])
            else:
                pipeline_loaders.add(loader)

    print(f"\nRegistry Statistics:")
    print(f"  Total loaders in LOADER_TABLES: {len(all_loaders)}")
    print(f"  Shorthand aliases (some point to same loader): {sum(1 for _ in loader_timeouts.keys())}")
    print(f"  Unique loaders with timeout definitions: {len(timeout_loader_names)}")
    print(f"  Loaders scheduled in PIPELINES: {len(pipeline_loaders)}")

    issues = []

    # Check 1: All loaders have shorthand mappings
    missing_shorthand = all_loaders - shorthand_loaders
    if missing_shorthand:
        for loader in sorted(missing_shorthand):
            issues.append(f"MISSING_SHORTHAND: {loader} has no shorthand mapping")
    else:
        print("\nCheck 1: All loaders have shorthand mappings [OK]")

    # Check 2: All shorthand mappings point to valid loaders
    invalid_shortcuts = shorthand_loaders - all_loaders
    if invalid_shortcuts:
        for loader in sorted(invalid_shortcuts):
            issues.append(f"INVALID_SHORTHAND: {loader} is not in LOADER_TABLES")
    else:
        print("Check 2: All shorthand mappings point to valid loaders [OK]")

    # Check 3: All loaders have timeout definitions
    missing_timeouts = all_loaders - timeout_loader_names
    if missing_timeouts:
        print(f"\nCheck 3: Loaders without explicit timeout (will use 30min default):")
        for loader in sorted(missing_timeouts):
            shorthand_names = [s for s, f in SHORTHAND_TO_FILENAME.items() if f == loader]
            print(f"  {loader}")
            if shorthand_names:
                print(f"    Shorthand: {', '.join(shorthand_names)}")
    else:
        print("Check 3: All loaders have timeout definitions [OK]")

    # Check 4: Warn about loaders not scheduled in any pipeline
    unscheduled = all_loaders - pipeline_loaders
    if unscheduled:
        print(f"\nCheck 4: Loaders not scheduled in any pipeline (can run manually):")
        for loader in sorted(unscheduled):
            shorthand_names = [s for s, f in SHORTHAND_TO_FILENAME.items() if f == loader]
            print(f"  {loader}")
            if shorthand_names:
                print(f"    Shorthand: {', '.join(shorthand_names)}")
    else:
        print("Check 4: All loaders are scheduled in at least one pipeline [OK]")

    if issues:
        print(f"\n{'=' * 70}")
        print(f"CONSISTENCY ISSUES FOUND: {len(issues)}")
        print(f"{'=' * 70}")
        for issue in issues:
            print(f"  {issue}")
        return 1
    else:
        print(f"\n{'=' * 70}")
        print("All consistency checks passed [OK]")
        print(f"{'=' * 70}")
        return 0


if __name__ == "__main__":
    sys.exit(main())
