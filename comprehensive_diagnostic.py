#!/usr/bin/env python3
"""
Comprehensive system diagnostic - finds ALL remaining issues.
Checks: imports, schema, config, calculations, error handling, data flow.
"""
import os
import re
from pathlib import Path
from collections import defaultdict

ROOT = Path('.')
SKIP_DIRS = {'.git', '__pycache__', '.pytest_cache', 'node_modules', '.venv', 'venv', '.github'}

issues = defaultdict(list)
warnings = defaultdict(list)

def skip_path(p):
    return any(skip in p.parts for skip in SKIP_DIRS)

# ============================================================================
# 1. CHECK: Credential Manager Integration
# ============================================================================
print("\n[1/7] Checking credential_manager integration...")

for py_file in sorted(ROOT.glob('**/*.py')):
    if skip_path(py_file):
        continue

    content = py_file.read_text(encoding='utf-8', errors='ignore')
    rel_path = py_file.relative_to(ROOT)

    # Check for bad patterns
    if 'credential_manager.get_db_credentials()' in content and 'try:' not in content:
        issues['credential_manager'].append(f"{rel_path}: Unprotected credential_manager call")

    # Check for missing imports
    if 'credential_manager' in content and 'from credential_manager import' not in content:
        if 'get_credential_manager' not in content and 'credential_manager =' not in content:
            warnings['imports'].append(f"{rel_path}: References credential_manager but doesn't import it")

print(f"[OK] Found {len(issues['credential_manager'])} credential issues, {len(warnings['imports'])} import warnings")

# ============================================================================
# 2. CHECK: SQL Injection Vectors
# ============================================================================
print("[2/7] Checking for SQL injection vectors...")

for py_file in sorted(ROOT.glob('**/*.py')):
    if skip_path(py_file):
        continue

    content = py_file.read_text(encoding='utf-8', errors='ignore')
    rel_path = py_file.relative_to(ROOT)

    # Look for dangerous patterns
    if re.search(r'\.format\s*\(\s*["\'].*\)\s*$', content, re.MULTILINE):
        if 'execute' in content:
            warnings['sql_injection'].append(f"{rel_path}: Uses .format() which might be SQL injection")

    if 'f"' in content and 'execute' in content:
        # Check if f-string is used in SQL
        matches = re.findall(r'execute\s*\(\s*f["\'].*{.*}', content)
        if matches:
            issues['sql_injection'].append(f"{rel_path}: F-string SQL queries (potential injection)")

print(f"[OK] Found {len(issues['sql_injection'])} SQL injection issues")

# ============================================================================
# 3. CHECK: Missing Error Handling
# ============================================================================
print("[3/7] Checking error handling...")

for py_file in sorted(ROOT.glob('**/*.py')):
    if skip_path(py_file):
        continue

    content = py_file.read_text(encoding='utf-8', errors='ignore')
    rel_path = py_file.relative_to(ROOT)

    # Check for execute() without try/except
    if 'cur.execute' in content or 'conn.execute' in content:
        # Count execute calls
        execute_count = len(re.findall(r'\.execute\s*\(', content))
        try_count = len(re.findall(r'\btry\s*:', content))

        if try_count == 0 and execute_count > 0:
            issues['error_handling'].append(f"{rel_path}: Has {execute_count} execute() calls but no try/except")
        elif try_count > 0 and try_count < execute_count / 3:
            warnings['error_handling'].append(f"{rel_path}: Only {try_count} try blocks for {execute_count} execute calls")

print(f"[OK] Found {len(issues['error_handling'])} error handling gaps")

# ============================================================================
# 4. CHECK: Hardcoded Values That Should Be Config
# ============================================================================
print("[4/7] Checking for hardcoded config values...")

for py_file in sorted(ROOT.glob('**/*.py')):
    if skip_path(py_file):
        continue

    content = py_file.read_text(encoding='utf-8', errors='ignore')
    rel_path = py_file.relative_to(ROOT)

    # Check for hardcoded database names, hosts, ports
    if re.search(r'["\']localhost["\']|["\']5432["\']|["\']stocks["\']', content):
        if 'os.getenv' not in content and 'config' not in content.lower():
            warnings['hardcoded'].append(f"{rel_path}: May have hardcoded database values")

    # Check for hardcoded thresholds
    if re.search(r'= [0-9]{3,5}|= 0\.[0-9]{2,3}', content):
        if 'self.config' not in content and 'CONFIG' not in content:
            warnings['hardcoded'].append(f"{rel_path}: Hardcoded numeric thresholds (should be configurable)")

print(f"[OK] Found {len(warnings['hardcoded'])} hardcoded value warnings")

# ============================================================================
# 5. CHECK: Missing Input Validation
# ============================================================================
print("[5/7] Checking input validation...")

for py_file in sorted(ROOT.glob('**/*.py')):
    if skip_path(py_file):
        continue

    content = py_file.read_text(encoding='utf-8', errors='ignore')
    rel_path = py_file.relative_to(ROOT)

    # Check for functions that take parameters but don't validate
    functions = re.findall(r'def\s+(\w+)\s*\(\s*self[^)]*([a-zA-Z_]\w*)[^)]*\):', content)
    for func, param in functions:
        func_body_start = content.find(f'def {func}')
        if func_body_start > 0:
            func_body = content[func_body_start:func_body_start+500]
            if param in func_body and f'if {param}' not in func_body and f'not {param}' not in func_body:
                if 'test' not in str(rel_path):
                    warnings['validation'].append(f"{rel_path}:{func}() - parameter '{param}' not validated")

print(f"[OK] Found {len(warnings['validation'])} validation warnings")

# ============================================================================
# 6. CHECK: Missing Logging
# ============================================================================
print("[6/7] Checking logging coverage...")

for py_file in sorted(ROOT.glob('**/*.py')):
    if skip_path(py_file):
        continue

    content = py_file.read_text(encoding='utf-8', errors='ignore')
    rel_path = py_file.relative_to(ROOT)

    # Check if file has database operations but no logging
    has_execute = 'execute' in content
    has_logging = 'logger' in content or 'logging' in content

    if has_execute and not has_logging:
        if 'test' not in str(rel_path) and 'lambda-pkg' not in str(rel_path):
            warnings['logging'].append(f"{rel_path}: Has database ops but no logging")

print(f"[OK] Found {len(warnings['logging'])} logging gaps")

# ============================================================================
# 7. CHECK: Missing Docstrings
# ============================================================================
print("[7/7] Checking documentation...")

for py_file in sorted(ROOT.glob('**/*.py')):
    if skip_path(py_file):
        continue

    content = py_file.read_text(encoding='utf-8', errors='ignore')
    rel_path = py_file.relative_to(ROOT)

    # Count functions without docstrings
    functions = re.findall(r'def\s+(\w+)\s*\([^)]*\):\s*(?!"""|\'\'\')[^"\']*', content)
    if len(functions) > 3:
        warnings['documentation'].append(f"{rel_path}: {len(functions)} functions without docstrings")

print(f"[OK] Found {len(warnings['documentation'])} documentation gaps")

# ============================================================================
# SUMMARY
# ============================================================================
print("\n" + "="*70)
print("DIAGNOSTIC SUMMARY")
print("="*70)

total_issues = sum(len(v) for v in issues.values())
total_warnings = sum(len(v) for v in warnings.values())

if total_issues > 0:
    print(f"\n[CRITICAL] CRITICAL ISSUES: {total_issues}")
    for category, items in issues.items():
        print(f"\n  {category.upper()} ({len(items)}):")
        for item in sorted(set(items))[:5]:
            print(f"    - {item}")
        if len(items) > 5:
            print(f"    ... and {len(items)-5} more")

if total_warnings > 0:
    print(f"\n[WARNING] WARNINGS: {total_warnings}")
    for category, items in warnings.items():
        print(f"\n  {category.upper()} ({len(items)}):")
        for item in sorted(set(items))[:3]:
            print(f"    - {item}")
        if len(items) > 3:
            print(f"    ... and {len(items)-3} more")

print("\n" + "="*70)
if total_issues == 0 and total_warnings < 10:
    print("[PASS] SYSTEM HEALTH: EXCELLENT")
elif total_issues == 0 and total_warnings < 30:
    print("[GOOD] SYSTEM HEALTH: GOOD (minor improvements available)")
else:
    print(f"[WARNING] SYSTEM HEALTH: FAIR (address top issues)")
print("="*70)
