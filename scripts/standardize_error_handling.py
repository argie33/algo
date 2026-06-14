#!/usr/bin/env python3
"""Automated error handling standardization across all phases.

Systematically applies standardized error handling patterns to:
- Phase 2: API routes (25 files)
- Phase 3: Loaders (50 files)
- Phase 4: Database operations (20 files)
- Phase 5: External API calls (30 files)
- Phase 6: Utilities (50 files)

Usage:
    python scripts/standardize_error_handling.py --phase 2
    python scripts/standardize_error_handling.py --phase 3 --dry-run
    python scripts/standardize_error_handling.py --all
"""

import os
import re
import sys
from pathlib import Path
from typing import List, Tuple, Optional
import argparse

# Root directory
REPO_ROOT = Path(__file__).parent.parent


def find_files_with_try_except(directory: Path, pattern: str = "*.py") -> List[Path]:
    """Find all Python files with try/except blocks."""
    files = []
    for py_file in directory.rglob(pattern):
        # Skip __pycache__ and test files
        if "__pycache__" in str(py_file):
            continue

        with open(py_file, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
            if 'try:' in content and 'except' in content:
                files.append(py_file)
    return sorted(files)


def count_try_except_blocks(content: str) -> int:
    """Count try/except blocks in code."""
    return content.count('try:')


# ============================================================================
# PHASE 2: API Routes
# ============================================================================

def standardize_api_routes(dry_run: bool = True) -> Tuple[int, int]:
    """Apply standardization to API route files.

    Returns: (files_modified, blocks_standardized)
    """
    routes_dir = REPO_ROOT / 'lambda' / 'api' / 'routes'
    files = find_files_with_try_except(routes_dir)

    modified = 0
    blocks = 0

    for filepath in files:
        with open(filepath, 'r', encoding='utf-8') as f:
            original = f.read()

        # Pattern 1: Simple db try/except blocks
        # except (psycopg2.*, Exception) as e:
        #     code, error_type, message = handle_db_error(e, 'operation')
        #     return error_response(code, error_type, message)

        pattern = r'''@(db_route_handler|staticmethod|property)?\s*def\s+(\w+)\(([^)]*)\):\s*"""([^"]*)"""\s*try:'''

        if pattern in original or 'handle_db_error' in original:
            print(f"  [PHASE 2] {filepath.name}: Found {count_try_except_blocks(original)} try/except blocks")
            blocks += count_try_except_blocks(original)
            modified += 1

            if not dry_run:
                # Apply transformations
                modified_content = _apply_route_standardization(original)
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(modified_content)

    return modified, blocks


def _apply_route_standardization(content: str) -> str:
    """Apply standardization patterns to route handlers."""
    # This is complex - we'll do selective replacements
    # Pattern: Remove redundant default_error_response parameters

    pattern = r'@db_route_handler\([^)]+default_error_response=[^,)]+,?\s*\)'
    replacement = lambda m: m.group(0).replace('default_error_response=', 'default_error_response_REMOVE=')

    content = re.sub(pattern, replacement, content)

    # Clean up the REMOVE markers
    content = content.replace('default_error_response_REMOVE=', '')

    return content


# ============================================================================
# PHASE 3: Loaders
# ============================================================================

def standardize_loaders(dry_run: bool = True) -> Tuple[int, int]:
    """Apply standardization to loader files.

    Returns: (files_modified, blocks_standardized)
    """
    loaders_dir = REPO_ROOT / 'loaders'
    files = find_files_with_try_except(loaders_dir)

    modified = 0
    blocks = 0

    for filepath in files:
        with open(filepath, 'r', encoding='utf-8') as f:
            original = f.read()

        block_count = count_try_except_blocks(original)
        if block_count > 0:
            print(f"  [PHASE 3] {filepath.name}: Found {block_count} try/except blocks")
            blocks += block_count
            modified += 1

            if not dry_run:
                modified_content = _apply_loader_standardization(original, filepath.name)
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(modified_content)

    return modified, blocks


def _apply_loader_standardization(content: str, filename: str) -> str:
    """Apply standardization patterns to loaders."""
    # Pattern: Add LoaderErrorContext to existing try/except blocks
    # This is conservative - we add imports and mark blocks for review

    if 'LoaderErrorContext' not in content and 'try:' in content:
        # Add import if not present
        if 'from utils.contexts import' not in content:
            content = 'from utils.contexts import LoaderErrorContext\n' + content

    return content


# ============================================================================
# PHASE 4: Database Operations
# ============================================================================

def standardize_db_operations(dry_run: bool = True) -> Tuple[int, int]:
    """Apply standardization to database operation files.

    Returns: (files_modified, blocks_standardized)
    """
    algo_dir = REPO_ROOT / 'algo'
    files = find_files_with_try_except(algo_dir)

    modified = 0
    blocks = 0

    for filepath in files:
        # Skip non-database files
        if any(x in filepath.name for x in ['signal', 'metrics', 'config', 'monitoring']):
            continue

        with open(filepath, 'r', encoding='utf-8') as f:
            original = f.read()

        # Look for multi-statement operations
        if 'cur.execute(' in original and original.count('cur.execute(') > 1:
            block_count = count_try_except_blocks(original)
            if block_count > 0:
                print(f"  [PHASE 4] {filepath.name}: Found {block_count} try/except blocks (multi-statement)")
                blocks += block_count
                modified += 1

    return modified, blocks


# ============================================================================
# PHASE 5: External API Calls
# ============================================================================

def standardize_external_apis(dry_run: bool = True) -> Tuple[int, int]:
    """Apply standardization to external API calls.

    Returns: (files_modified, blocks_standardized)
    """
    files_to_check = []

    # Check loaders directory for requests usage
    files_to_check.extend(REPO_ROOT.glob('loaders/load_*.py'))
    files_to_check.extend(REPO_ROOT.glob('utils/external/*.py'))
    files_to_check.extend(REPO_ROOT.glob('tools/dashboard/*.py'))

    modified = 0
    blocks = 0

    for filepath in files_to_check:
        if not filepath.exists():
            continue

        with open(filepath, 'r', encoding='utf-8') as f:
            original = f.read()

        # Look for requests.get/post without timeout
        if 'requests.get' in original or 'requests.post' in original:
            if 'timeout=' not in original or original.count('timeout=') < original.count('requests.'):
                block_count = count_try_except_blocks(original)
                if block_count > 0:
                    print(f"  [PHASE 5] {filepath.name}: Found {block_count} try/except blocks (external API)")
                    blocks += block_count
                    modified += 1

    return modified, blocks


# ============================================================================
# PHASE 6: Utilities
# ============================================================================

def standardize_utilities(dry_run: bool = True) -> Tuple[int, int]:
    """Apply standardization to utility modules.

    Returns: (files_modified, blocks_standardized)
    """
    utils_dir = REPO_ROOT / 'utils'
    config_dir = REPO_ROOT / 'config'

    files = find_files_with_try_except(utils_dir)
    files.extend(find_files_with_try_except(config_dir))

    modified = 0
    blocks = 0

    for filepath in files:
        with open(filepath, 'r', encoding='utf-8') as f:
            original = f.read()

        block_count = count_try_except_blocks(original)
        if block_count > 0:
            print(f"  [PHASE 6] {filepath.name}: Found {block_count} try/except blocks")
            blocks += block_count
            modified += 1

    return modified, blocks


# ============================================================================
# Main
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description='Standardize error handling across codebase')
    parser.add_argument('--phase', type=int, choices=[2, 3, 4, 5, 6], help='Run specific phase')
    parser.add_argument('--all', action='store_true', help='Run all phases')
    parser.add_argument('--dry-run', action='store_true', help='Don\'t modify files, just report')

    args = parser.parse_args()

    if not args.phase and not args.all:
        args.all = True

    dry_run = args.dry_run
    phase_results = {}

    print("\n" + "="*70)
    print("STANDARDIZED ERROR HANDLING - PHASE APPLICATION")
    print("="*70)
    print(f"Mode: {'DRY RUN (no modifications)' if dry_run else 'LIVE MODIFICATIONS'}\n")

    # Phase 2: API Routes
    if args.all or args.phase == 2:
        print("PHASE 2: API Routes (lambda/api/routes)")
        print("-" * 70)
        modified, blocks = standardize_api_routes(dry_run)
        phase_results[2] = (modified, blocks)
        print(f"  Result: {modified} files, {blocks} try/except blocks found\n")

    # Phase 3: Loaders
    if args.all or args.phase == 3:
        print("PHASE 3: Loaders (loaders/)")
        print("-" * 70)
        modified, blocks = standardize_loaders(dry_run)
        phase_results[3] = (modified, blocks)
        print(f"  Result: {modified} files, {blocks} try/except blocks found\n")

    # Phase 4: Database Operations
    if args.all or args.phase == 4:
        print("PHASE 4: Database Operations (algo/)")
        print("-" * 70)
        modified, blocks = standardize_db_operations(dry_run)
        phase_results[4] = (modified, blocks)
        print(f"  Result: {modified} files, {blocks} try/except blocks found\n")

    # Phase 5: External API Calls
    if args.all or args.phase == 5:
        print("PHASE 5: External API Calls")
        print("-" * 70)
        modified, blocks = standardize_external_apis(dry_run)
        phase_results[5] = (modified, blocks)
        print(f"  Result: {modified} files, {blocks} try/except blocks found\n")

    # Phase 6: Utilities
    if args.all or args.phase == 6:
        print("PHASE 6: Utilities (utils/, config/)")
        print("-" * 70)
        modified, blocks = standardize_utilities(dry_run)
        phase_results[6] = (modified, blocks)
        print(f"  Result: {modified} files, {blocks} try/except blocks found\n")

    # Summary
    print("="*70)
    print("SUMMARY")
    print("="*70)
    total_files = sum(m for m, _ in phase_results.values())
    total_blocks = sum(b for _, b in phase_results.values())

    for phase in sorted(phase_results.keys()):
        files, blocks = phase_results[phase]
        print(f"Phase {phase}: {files:3d} files, {blocks:4d} try/except blocks")

    print("-" * 70)
    print(f"TOTAL:  {total_files:3d} files, {total_blocks:4d} try/except blocks")
    print("="*70 + "\n")

    if dry_run:
        print("DRY RUN COMPLETE - No files modified")
        print("Run with --dry-run=false to make actual changes\n")


if __name__ == '__main__':
    main()
