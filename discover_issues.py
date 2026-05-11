#!/usr/bin/env python3
"""
Issue Discovery Script - Find patterns indicating bugs, gaps, or improvements

Scans codebase for:
1. Print statements that should be logger calls
2. Missing error handling in critical paths
3. Hardcoded values that should be config
4. Missing data validation
5. Incomplete function implementations
6. Inconsistent patterns across modules
"""

import re
from pathlib import Path
from collections import defaultdict

def scan_for_issues():
    """Comprehensive code pattern scanning"""

    issues = {
        'print_statements': [],
        'hardcoded_values': [],
        'missing_config': [],
        'missing_validation': [],
        'incomplete_functions': [],
        'inconsistent_patterns': defaultdict(list),
    }

    # Scan Python files
    for py_file in Path(".").glob("algo*.py"):
        if py_file.name in ["algo_config.py", "algo_test.py"]:
            continue

        with open(py_file, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
            lines = content.split("\n")

            for i, line in enumerate(lines, 1):
                # Issue 1: Print statements in non-test files
                if re.search(r'^\s*print\s*\(', line) and "logger" not in content[:content.find(line)]:
                    issues['print_statements'].append({
                        'file': py_file.name,
                        'line': i,
                        'code': line.strip()[:60]
                    })

                # Issue 2: Hardcoded numeric thresholds (likely should be config)
                if re.search(r'(>|<|==)\s*\d+\.*\d*\s*(#|$|\)|,)', line):
                    if any(kw in line for kw in ['if ', 'and ', 'or ']):
                        # Check if it's obviously a magic number
                        if not any(skip in line for skip in ['for i in range', 'len(', '[0]', '[1]']):
                            issues['hardcoded_values'].append({
                                'file': py_file.name,
                                'line': i,
                                'code': line.strip()[:80]
                            })

                # Issue 3: Broad exception handlers that don't log the exception
                if 'except Exception:' in line and 'pass' in lines[i] if i < len(lines) else False:
                    issues['incomplete_functions'].append({
                        'file': py_file.name,
                        'line': i,
                        'issue': 'Silent exception catch (except Exception: pass)'
                    })

    # Find inconsistencies
    issues['inconsistent_patterns']['print_vs_logger'] = check_logging_consistency()
    issues['inconsistent_patterns']['missing_error_handling'] = check_error_handling_gaps()

    return issues

def check_logging_consistency():
    """Check if modules mix print() and logger calls"""
    findings = []
    for py_file in Path(".").glob("algo*.py"):
        with open(py_file, "r") as f:
            content = f.read()
            has_print = 'print(' in content
            has_logger = 'logger' in content

            if has_print and has_logger:
                # Count them
                print_count = len(re.findall(r'print\s*\(', content))
                logger_count = len(re.findall(r'logger\.\w+', content))

                if print_count > logger_count:
                    findings.append({
                        'file': py_file.name,
                        'print_count': print_count,
                        'logger_count': logger_count,
                        'recommendation': 'Replace print() with logger calls'
                    })
    return findings

def check_error_handling_gaps():
    """Find functions without error handling"""
    findings = []
    for py_file in Path(".").glob("algo*.py"):
        with open(py_file, "r") as f:
            content = f.read()
            # Find function definitions
            for match in re.finditer(r'def (\w+)\(self.*?\):', content):
                func_name = match.group(1)

                # Check if function has try/except
                func_body_start = match.end()
                # Find next function or end of file
                next_func = re.search(r'\n    def \w+\(', content[func_body_start:])
                func_body_end = next_func.start() + func_body_start if next_func else len(content)
                func_body = content[func_body_start:func_body_end]

                # If function uses self.cur and has no try/except, flag it
                if 'self.cur' in func_body and 'try:' not in func_body and len(func_body) > 100:
                    findings.append({
                        'file': py_file.name,
                        'function': func_name,
                        'issue': 'DB operation without try/except'
                    })
    return findings[:5]  # Limit to top 5

def print_report(issues):
    """Print formatted issue report"""
    print("\n" + "="*80)
    print("COMPREHENSIVE CODE ISSUE DISCOVERY")
    print("="*80)

    # Print statements
    if issues['print_statements']:
        print(f"\n🔴 PRINT STATEMENTS ({len(issues['print_statements'])} found):")
        print("-" * 80)
        for issue in issues['print_statements'][:10]:
            print(f"  {issue['file']}:{issue['line']}: {issue['code']}")
        if len(issues['print_statements']) > 10:
            print(f"  ... and {len(issues['print_statements']) - 10} more")

    # Hardcoded values
    if issues['hardcoded_values']:
        print(f"\n⚠️  HARDCODED VALUES ({len(issues['hardcoded_values'])} potential):")
        print("-" * 80)
        for issue in issues['hardcoded_values'][:5]:
            print(f"  {issue['file']}:{issue['line']}: {issue['code']}")
        if len(issues['hardcoded_values']) > 5:
            print(f"  ... and {len(issues['hardcoded_values']) - 5} more")

    # Incomplete functions
    if issues['incomplete_functions']:
        print(f"\n❌ INCOMPLETE ERROR HANDLING ({len(issues['incomplete_functions'])} found):")
        print("-" * 80)
        for issue in issues['incomplete_functions'][:5]:
            print(f"  {issue['file']}:{issue['line']}: {issue['issue']}")

    # Inconsistencies
    if issues['inconsistent_patterns']['print_vs_logger']:
        print(f"\n🔀 INCONSISTENT LOGGING:")
        print("-" * 80)
        for finding in issues['inconsistent_patterns']['print_vs_logger'][:5]:
            print(f"  {finding['file']}: {finding['print_count']} print() vs {finding['logger_count']} logger calls")

    if issues['inconsistent_patterns']['missing_error_handling']:
        print(f"\n🚫 MISSING ERROR HANDLING:")
        print("-" * 80)
        for finding in issues['inconsistent_patterns']['missing_error_handling']:
            print(f"  {finding['file']}:{finding['function']}: {finding['issue']}")

    print("\n" + "="*80)
    print("SUMMARY: Run specific fixes below")
    print("="*80 + "\n")

if __name__ == "__main__":
    issues = scan_for_issues()
    print_report(issues)
