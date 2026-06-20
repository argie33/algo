#!/usr/bin/env python3
"""
Comprehensive safe float conversion v2.
Process all remaining files with proven conservative patterns.
"""

import ast
import re
from pathlib import Path


def sanitize_smart_quotes(text: str) -> str:
    """Fix UTF-8 smart quotes."""
    replacements = [
        ('"', '"'), ('"', '"'), (''', "'"), (''', "'"),
    ]
    for old, new in replacements:
        text = text.replace(old, new)
    return text


def add_safe_float_import(lines: list) -> list:
    """Add safe_float import if not already present."""
    last_import_idx = -1
    for i, line in enumerate(lines):
        if line.strip().startswith(('from ', 'import ')):
            last_import_idx = i

    if last_import_idx >= 0:
        import_section = '\n'.join(lines[:last_import_idx + 1])
        if 'safe_float' not in import_section:
            lines.insert(last_import_idx + 1, 'from utils.safe_data_conversion import safe_float')

    return lines


def fix_simple_float_calls(text: str) -> tuple:
    """Replace float() with safe_float() - conservative patterns only."""
    count = 0

    # Pattern 1: float(identifier)
    def replace_var(match):
        nonlocal count
        count += 1
        var = match.group(1)
        return f'safe_float({var}, default=0.0)'

    text = re.sub(r'\bfloat\(([a-zA-Z_][a-zA-Z0-9_]*)\)', replace_var, text)

    # Pattern 2: float(dict.get(...))
    def replace_access(match):
        nonlocal count
        count += 1
        expr = match.group(1)
        return f'safe_float({expr}, default=0.0)'

    text = re.sub(
        r'\bfloat\(([a-zA-Z_][a-zA-Z0-9_]*\.get\([^)]+\))\)',
        replace_access,
        text
    )

    # Pattern 3: float(row[...])
    text = re.sub(
        r'\bfloat\(([a-zA-Z_][a-zA-Z0-9_]*\[[^\]]+\])\)',
        replace_access,
        text
    )

    # Pattern 4: float(number)
    def replace_literal(match):
        nonlocal count
        count += 1
        num = match.group(1)
        return f'safe_float({num}, default=0.0)'

    text = re.sub(r'\bfloat\(([0-9]+\.?[0-9]*)\)', replace_literal, text)

    # Pattern 5: float(string literal)
    text = re.sub(r'\bfloat\(("(?:[^"\\]|\\.)*")\)', replace_literal, text)
    text = re.sub(r"\bfloat\(('(?:[^'\\]|\\.)*')\)", replace_literal, text)

    return text, count


def validate_syntax(text: str) -> bool:
    """Check if text is valid Python."""
    try:
        ast.parse(text)
        return True
    except SyntaxError:
        return False


def process_file(fpath: str) -> tuple:
    """Process one file. Returns: (count, status)."""
    p = Path(fpath)
    if not p.exists():
        return 0, "NOT_FOUND"

    try:
        with open(p, encoding='utf-8', errors='replace') as f:
            original = f.read()
    except Exception:
        return 0, "ERROR"

    # Don't sanitize - keep original encoding
    content = original

    # Count float() before
    count_before = len(re.findall(r'\bfloat\s*\(', content))
    if count_before == 0:
        return 0, "NO"

    lines = content.split('\n')
    lines = add_safe_float_import(lines)
    content = '\n'.join(lines)

    content, count_fixed = fix_simple_float_calls(content)

    # Validate syntax
    if not validate_syntax(content):
        return 0, "SYN"

    # Write only if valid
    if content != original and count_fixed > 0:
        try:
            with open(p, 'w', encoding='utf-8') as f:
                f.write(content)
            return count_fixed, "OK"
        except Exception:
            return 0, "WRT"

    return 0, "NC"


def main():
    """Process comprehensive list of remaining files."""
    # Find all .py files with float() calls
    all_py_files = []
    for p in Path('.').rglob('*.py'):
        if '.git' in str(p) or 'scripts' in str(p) or 'test' in str(p):
            continue
        try:
            content = p.read_text(encoding='utf-8', errors='replace')
            if 'float(' in content and 'safe_float(' not in content:
                all_py_files.append(str(p).lstrip('.\\').replace('\\', '/'))
        except:
            pass

    print("=" * 75)
    print("COMPREHENSIVE SAFE FLOAT CONVERSION")
    print(f"Processing {len(all_py_files)} files with unsafe float() calls")
    print("=" * 75)
    print()

    total = 0
    successes = 0
    for fpath in sorted(all_py_files)[:50]:  # Process first 50
        count, status = process_file(fpath)
        if count > 0:
            print(f"{fpath:55} OK  (+{count})")
            total += count
            successes += 1
        elif status == "NO":
            pass  # Skip silent
        else:
            if status != "NC":
                print(f"{fpath:55} {status:3}")

    print()
    print(f"TOTAL FIXED: {total} conversions across {successes} files")
    print("=" * 75)


if __name__ == "__main__":
    main()
