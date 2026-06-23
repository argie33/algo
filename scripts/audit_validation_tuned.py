#!/usr/bin/env python3
"""Tuned validation gaps audit - filters false positives and provides actionable findings."""

import re
import subprocess
from pathlib import Path
from collections import defaultdict

PROJECT_ROOT = Path(__file__).parent.parent

def find_real_unsafe_dict_access():
    """Find dict/attribute access without validation - more precise."""
    # These patterns are higher confidence for actual issues
    patterns = [
        (r'\.get\([^)]+\)\s*\[', 'Chained access: .get()[...] - could return None then index'),
        (r'\.get\([^)]+\)\.', 'Chained access: .get().method - method might be called on None'),
    ]

    findings = defaultdict(list)

    for py_file in PROJECT_ROOT.rglob('*.py'):
        if '.claude' in str(py_file) or '__pycache__' in str(py_file):
            continue

        try:
            content = py_file.read_text()
            for pattern, desc in patterns:
                for match in re.finditer(pattern, content):
                    line_num = content[:match.start()].count('\n') + 1
                    # Get the full line for context
                    line_start = content.rfind('\n', 0, match.start()) + 1
                    line_end = content.find('\n', match.end())
                    line_text = content[line_start:line_end].strip()

                    # Skip if already has safety check nearby
                    if 'or' in line_text or 'if' in line_text or 'safe_' in line_text:
                        continue

                    findings[str(py_file)].append((line_num, desc, line_text))
        except Exception:
            pass

    return findings

def find_real_unvalidated_arithmetic():
    """Find arithmetic on unvalidated values - filter out false positives (comments)."""
    findings = defaultdict(list)

    for py_file in PROJECT_ROOT.rglob('*.py'):
        if '.claude' in str(py_file) or '__pycache__' in str(py_file):
            continue

        try:
            content = py_file.read_text()

            # Look for comparisons where the value might not be validated
            # Pattern: if variable < number where variable comes from external source
            for match in re.finditer(r'if\s+(\w+)\s*[<>=!]+\s*\d+:', content):
                line_num = content[:match.start()].count('\n') + 1
                var_name = match.group(1)

                # Get context - look for where this variable comes from
                line_start = content.rfind('\n', 0, match.start()) + 1
                line_end = content.find('\n', match.end())
                line_text = content[line_start:line_end].strip()

                # Skip if:
                # - Already in a validation/safety context
                # - The variable is clearly validated on the same line
                # - Inside a comment
                if any(x in line_text for x in ['safe_', 'isinstance', 'assert', 'try:', '#']):
                    continue

                # Find where this variable comes from (look back 5 lines)
                look_back_start = max(0, match.start() - 500)
                look_back_text = content[look_back_start:match.start()]

                # If comes from unsafe source (API, dict.get without default, etc)
                if f'{var_name} =' in look_back_text:
                    if '.get(' in look_back_text and 'safe_' not in look_back_text:
                        findings[str(py_file)].append((
                            line_num,
                            'Comparison on unvalidated value (from .get())',
                            line_text
                        ))
        except Exception:
            pass

    return findings

def find_missing_malformed_data_tests_for_real():
    """Find test files that process external data but lack malformed data tests."""
    findings = []

    for test_file in PROJECT_ROOT.rglob('test_*.py'):
        if '.claude' in str(test_file):
            continue

        try:
            content = test_file.read_text()

            # Skip if already has malformed data tests
            if any(kw in content for kw in ['malformed', 'corrupted', 'TypeError']):
                continue

            # Only flag if it tests response handling or data access
            has_response_testing = any(kw in content for kw in [
                '_unwrap', 'validate_', 'api_', 'response', 'fetch', 'loader', 'data_'
            ])

            if has_response_testing:
                findings.append(str(test_file))
        except Exception:
            pass

    return findings

def report():
    """Generate tuned audit report."""
    print("=" * 80)
    print("VALIDATION GAPS AUDIT - TUNED REPORT")
    print("(Filtered for actionable findings, false positives removed)")
    print("=" * 80)

    print("\n[1/3] HIGH-CONFIDENCE UNSAFE ACCESS PATTERNS")
    unsafe = find_real_unsafe_dict_access()
    if unsafe:
        count = sum(len(v) for v in unsafe.values())
        print(f"Found {count} high-confidence issues in {len(unsafe)} files:")
        for file, issues in list(unsafe.items())[:5]:
            print(f"\n  {Path(file).name}:")
            for line_num, desc, text in issues[:3]:
                print(f"    Line {line_num}: {desc}")
                print(f"      {text[:70]}")
    else:
        print("✓ No high-confidence unsafe patterns found!")

    print("\n[2/3] UNVALIDATED ARITHMETIC (Real Issues Only)")
    arith = find_real_unvalidated_arithmetic()
    if arith:
        count = sum(len(v) for v in arith.values())
        print(f"Found {count} real issues in {len(arith)} files:")
        for file, issues in list(arith.items())[:5]:
            print(f"\n  {Path(file).name}:")
            for line_num, desc, text in issues[:3]:
                print(f"    Line {line_num}: {desc}")
                print(f"      {text[:70]}")
    else:
        print("✓ No unvalidated arithmetic on external data found!")

    print("\n[3/3] TEST FILES MISSING MALFORMED DATA COVERAGE")
    missing_tests = find_missing_malformed_data_tests_for_real()
    if missing_tests:
        print(f"Found {len(missing_tests)} test files that should add malformed data tests:")
        for test_file in missing_tests[:10]:
            print(f"  - {Path(test_file).name}")
        print(f"\n  Priority: Add malformed data tests for external data processing tests")
    else:
        print("✓ All data-processing test files have malformed data coverage!")

    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Unsafe patterns: {sum(len(v) for v in unsafe.values())}")
    print(f"Arithmetic issues: {sum(len(v) for v in arith.values())}")
    print(f"Tests needing coverage: {len(missing_tests)}")

    if not (unsafe or arith or missing_tests):
        print("\n✓ EXCELLENT: No critical validation gaps detected!")
    else:
        print("\nACTION ITEMS:")
        if unsafe:
            print("1. Review and fix high-confidence unsafe patterns")
        if arith:
            print("2. Add validation for arithmetic operations")
        if missing_tests:
            print(f"3. Add malformed data tests to {len(missing_tests)} test files")

if __name__ == "__main__":
    report()
