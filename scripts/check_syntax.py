#!/usr/bin/env python3
"""Check all Python files for syntax errors."""

import py_compile
from pathlib import Path

algo_root = Path(__file__).parent.parent
errors = []

for py_file in sorted(algo_root.rglob('*.py')):
    if 'scripts' in str(py_file) or '__pycache__' in str(py_file):
        continue
    try:
        py_compile.compile(str(py_file), doraise=True)
    except py_compile.PyCompileError as e:
        errors.append((py_file.relative_to(algo_root), str(e)))

if errors:
    print(f"Found {len(errors)} syntax errors:")
    for file, error in errors[:10]:
        print(f"\nERROR: {file}")
        print(f"  {error.split(chr(10))[0]}")
else:
    print("All Python files have valid syntax!")
