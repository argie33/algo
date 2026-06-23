#!/usr/bin/env python3
"""Comprehensive audit of testing and validation gaps across the project.

This tool systematically identifies:
1. Unsafe data access patterns (not caught by mypy/pylint)
2. Missing edge case tests (tests with malformed data)
3. Missing type validation in critical paths
4. Missing integration tests that exercise real code paths
5. Data transformation points where type info is lost
"""

import re
import subprocess
from pathlib import Path
from collections import defaultdict

PROJECT_ROOT = Path(__file__).parent.parent


def find_unsafe_dict_access():
    """Find dict/attribute access without type validation."""
    unsafe_patterns = [
        (r'\.get\([^)]+\)\s*\[', 'Chained access: .get()[...]'),
        (r'\.get\([^)]+\)\.', 'Chained access: .get().method'),
        (r'\[[^\]]+\]\s*\[', 'Chained bracket access: [][...]'),
        (r'dict\([^)]*\)\.get\(', 'Unsafe dict() creation then get'),
        (r'\.split\([^)]*\)\.get\(', 'Split then get without list check'),
    ]

    findings = defaultdict(list)

    for py_file in PROJECT_ROOT.rglob('*.py'):
        if '.claude' in str(py_file) or '__pycache__' in str(py_file):
            continue

        try:
            content = py_file.read_text()
            for pattern, desc in unsafe_patterns:
                for match in re.finditer(pattern, content):
                    line_num = content[:match.start()].count('\n') + 1
                    findings[str(py_file)].append((line_num, desc, match.group()))
        except Exception:
            pass

    return findings


def find_unvalidated_arithmetic():
    """Find arithmetic operations on unvalidated values."""
    patterns = [
        (r'if\s+\w+\s*[<>=!]=*\s*\d+:', 'Direct comparison without validation'),
        (r'\w+\s*[+\-*/]\s*\d+', 'Arithmetic without validation'),
        (r'\w+\s*%\s*\d+', 'Modulo without validation'),
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
                    # Check if safe_float/safe_int are used
                    line_start = content.rfind('\n', 0, match.start()) + 1
                    line_end = content.find('\n', match.end())
                    line_text = content[line_start:line_end]

                    if 'safe_float' not in line_text and 'safe_int' not in line_text:
                        findings[str(py_file)].append((line_num, desc, line_text.strip()))
        except Exception:
            pass

    return findings


def find_missing_malformed_data_tests():
    """Find test files that don't test with malformed/corrupted data."""
    findings = []

    for test_file in PROJECT_ROOT.rglob('test_*.py'):
        if '.claude' in str(test_file):
            continue

        try:
            content = test_file.read_text()
            # Check if it tests with malformed data
            has_malformed = any(keyword in content for keyword in [
                'malformed',
                'corrupted',
                'wrong_type',
                'TypeError',
                'dict.*instead',
                'list.*instead',
                'string.*instead',
            ])

            # Check if it tests error cases
            has_error_tests = 'pytest.raises' in content or 'assertRaises' in content

            if not has_malformed and not has_error_tests:
                findings.append(f"{test_file}: No malformed/corrupted data tests")
        except Exception:
            pass

    return findings


def find_api_response_validation():
    """Find API response handling without type validation."""
    findings = defaultdict(list)

    for py_file in PROJECT_ROOT.rglob('*.py'):
        py_file_str = str(py_file)
        if '.claude' in py_file_str or '__pycache__' in py_file_str:
            continue

        if 'lambda' not in py_file_str and 'api' not in py_file_str.lower():
            continue

        try:
            content = py_file.read_text()
            # Look for response handling
            for match in re.finditer(r'response\[[\'\"](\w+)[\'\"]\]', content):
                line_num = content[:match.start()].count('\n') + 1
                line_start = content.rfind('\n', 0, match.start()) + 1
                line_end = content.find('\n', match.end())
                line_text = content[line_start:line_end]

                # Check if there's validation
                if 'safe_float' not in line_text and 'safe_int' not in line_text and 'isinstance' not in line_text:
                    findings[str(py_file)].append((line_num, f"Unvalidated response access: {match.group()}"))
        except Exception:
            pass

    return findings


def find_data_transformation_points():
    """Find where data types might be lost (str->dict, dict->list, etc)."""
    patterns = [
        r'json\.loads\(',
        r'json\.dumps\(',
        r'pickle\.',
        r'yaml\.',
        r'csv\.',
        r'\.decode\(',
        r'\.encode\(',
        r'str\(',
        r'dict\(',
        r'list\(',
    ]

    findings = defaultdict(list)

    for py_file in PROJECT_ROOT.rglob('*.py'):
        py_file_str = str(py_file)
        if '.claude' in py_file_str or '__pycache__' in py_file_str:
            continue

        try:
            content = py_file.read_text()
            for pattern in patterns:
                for match in re.finditer(pattern, content):
                    line_num = content[:match.start()].count('\n') + 1
                    findings[str(py_file)].append((line_num, f"Data transformation: {match.group()}"))
        except Exception:
            pass

    return findings


def main():
    print("=" * 80)
    print("COMPREHENSIVE VALIDATION GAPS AUDIT")
    print("=" * 80)

    print("\n[1/5] Finding unsafe dict access patterns...")
    unsafe_access = find_unsafe_dict_access()
    if unsafe_access:
        print(f"  Found in {len(unsafe_access)} files:")
        for file, issues in list(unsafe_access.items())[:5]:
            print(f"    {file}:")
            for line, desc, code in issues[:2]:
                print(f"      Line {line}: {desc}")
    else:
        print("  OK: No obvious unsafe patterns found")

    print("\n[2/5] Finding unvalidated arithmetic operations...")
    unvalidated_arith = find_unvalidated_arithmetic()
    if unvalidated_arith:
        print(f"  Found in {len(unvalidated_arith)} files:")
        for file, issues in list(unvalidated_arith.items())[:5]:
            print(f"    {file}:")
            for line, desc, code in issues[:2]:
                print(f"      Line {line}: {desc}")
                print(f"        {code[:60]}")
    else:
        print("  OK: All arithmetic appears validated")

    print("\n[3/5] Finding tests missing malformed data coverage...")
    missing_tests = find_missing_malformed_data_tests()
    if missing_tests:
        print(f"  Found {len(missing_tests)} test files without malformed data tests:")
        for issue in missing_tests[:10]:
            print(f"    {issue}")
    else:
        print("  OK: All tests include malformed data coverage")

    print("\n[4/5] Finding unvalidated API response access...")
    api_issues = find_api_response_validation()
    if api_issues:
        print(f"  Found in {len(api_issues)} files:")
        for file, issues in list(api_issues.items())[:5]:
            print(f"    {file}:")
            for line, desc in issues[:2]:
                print(f"      Line {line}: {desc}")
    else:
        print("  OK: API responses appear validated")

    print("\n[5/5] Finding data transformation points (high risk)...")
    transforms = find_data_transformation_points()
    print(f"  Found {sum(len(v) for v in transforms.values())} transformation points")
    print(f"  These need careful type validation:")
    for file, issues in list(transforms.items())[:3]:
        print(f"    {file}: {len(issues)} transformations")

    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Unsafe access patterns: {sum(len(v) for v in unsafe_access.values())}")
    print(f"Unvalidated arithmetic: {sum(len(v) for v in unvalidated_arith.values())}")
    print(f"Tests missing malformed data: {len(missing_tests)}")
    print(f"Unvalidated API responses: {sum(len(v) for v in api_issues.values())}")
    print(f"Data transformations (need review): {sum(len(v) for v in transforms.values())}")

    print("\n" + "=" * 80)
    print("RECOMMENDATIONS")
    print("=" * 80)
    print("""
1. ADD PROPERTY-BASED TESTING:
   Use hypothesis library to generate random malformed data and test robustness

2. IMPLEMENT DATA FLOW ANALYSIS:
   Track type information through data transformations (json.loads, etc)

3. CREATE VALIDATION MIDDLEWARE:
   Wrap all dict/list access at data boundaries with automatic type checking

4. ADD RUNTIME ASSERTIONS:
   Use assert statements at critical points to catch type mismatches

5. EXPAND MALFORMED DATA TESTS:
   All test files should include test_with_malformed_data() cases

6. CREATE DATA VALIDATION RULES:
   Define strict schemas for all API responses and database records

7. AUTOMATE PATTERN DETECTION:
   Run this audit script in CI/CD to catch new gaps before merging
    """)


if __name__ == '__main__':
    main()
