#!/usr/bin/env python3
"""Quick scan for remaining code quality and functional issues."""
import os
import re
from pathlib import Path

print("=" * 70)
print("REMAINING ISSUES SCAN")
print("=" * 70)

# 1. Check for hardcoded values that should be config
print("\n[1] Hardcoded values in critical modules:")
hardcoded_patterns = [
    (r"'localhost'", "Hardcoded localhost"),
    (r'"localhost"', "Hardcoded localhost"),
    (r"5432", "Hardcoded port"),
    (r"os\.getenv\(['\"].*['\"]\s*,\s*['\"][^'\"]*['\"]", "Default fallback"),
]

count = 0
for pattern, desc in hardcoded_patterns:
    for py_file in Path('.').glob('algo_*.py'):
        matches = re.findall(pattern, py_file.read_text())
        if matches and count < 5:
            print(f"  {py_file.name}: {desc}")
            count += 1

# 2. Check for missing error handling
print("\n[2] Potential missing error handling:")
risky_patterns = [
    (r'\.execute\([^)]*\)', "SQL execute without try/except"),
    (r'\.connect\(\)', "DB connect without try/except"),
]

count = 0
for pattern, desc in risky_patterns:
    for py_file in Path('.').glob('algo_*.py'):
        content = py_file.read_text()
        matches = re.findall(pattern, content)
        if matches and 'try:' not in content and count < 3:
            print(f"  {py_file.name}: {desc} ({len(matches)} occurrences)")
            count += 1

# 3. Check for TODO/FIXME/HACK comments
print("\n[3] Code comments indicating incomplete work:")
for py_file in list(Path('.').glob('algo_*.py'))[:20]:
    content = py_file.read_text()
    todos = re.findall(r'#.*(?:TODO|FIXME|HACK|XXX|BUG).*', content)
    if todos:
        for todo in todos[:2]:
            print(f"  {py_file.name}: {todo.strip()}")

# 4. Check for logging consistency
print("\n[4] Logging setup (checking for proper config):")
logging_issues = 0
for py_file in list(Path('.').glob('algo_*.py'))[:30]:
    content = py_file.read_text()
    if 'import logging' in content and 'logger = logging.getLogger' not in content:
        print(f"  {py_file.name}: imports logging but no logger configured")
        logging_issues += 1
        if logging_issues >= 3:
            break

# 5. Check for unused imports
print("\n[5] Potential unused imports (sample):")
unused_count = 0
for py_file in list(Path('.').glob('algo_*.py'))[:15]:
    content = py_file.read_text()
    imports = re.findall(r'^(?:from|import)\s+(\w+)', content, re.MULTILINE)
    for imp in imports[:3]:
        if imp not in content[content.find('\n'):]:  # Skip first line
            print(f"  {py_file.name}: possibly unused '{imp}'")
            unused_count += 1
            if unused_count >= 3:
                break
    if unused_count >= 3:
        break

# 6. Check for potential SQL injection vulnerabilities
print("\n[6] Potential SQL injection risks:")
sql_risks = 0
for py_file in list(Path('.').glob('algo_*.py'))[:20]:
    content = py_file.read_text()
    # Look for string formatting in SQL (bad) vs parameterized (good)
    if re.search(r'f["\'].*%s.*["\'].*execute|\.format\(.*execute', content):
        print(f"  {py_file.name}: possible SQL string formatting")
        sql_risks += 1
        if sql_risks >= 3:
            break

print("\n" + "=" * 70)
print("Scan complete. Top priorities: error handling, logging consistency")
print("=" * 70)
