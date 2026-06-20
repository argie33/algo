#!/usr/bin/env python3
"""
Batch 2+ float conversion using proven safe patterns.
Conservative approach that only handles common, safe patterns.
Target: 200+ more conversions toward 50% (400+/738).
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
    """
    Replace float() calls with safe_float() - conservative patterns only.
    """
    count = 0

    # Pattern 1: float(identifier) - simple variable
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

    # Pattern 3: float(row[...]) - dict/list access
    text = re.sub(
        r'\bfloat\(([a-zA-Z_][a-zA-Z0-9_]*\[[^\]]+\])\)',
        replace_access,
        text
    )

    # Pattern 4: float(number) - numeric literal
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
    """
    Process one file safely.
    Returns: (count, status)
    """
    p = Path(fpath)
    if not p.exists():
        return 0, "NOT_FOUND"

    try:
        with open(p, encoding='utf-8') as f:
            original = f.read()
    except Exception as e:
        return 0, "ERROR"

    content = sanitize_smart_quotes(original)

    # Count float() before
    count_before = len(re.findall(r'\bfloat\s*\(', content))
    if count_before == 0:
        return 0, "NO_CALLS"

    lines = content.split('\n')
    lines = add_safe_float_import(lines)
    content = '\n'.join(lines)

    content, count_fixed = fix_simple_float_calls(content)

    # Validate syntax
    if not validate_syntax(content):
        return 0, "SYNTAX_ERROR"

    # Write only if valid
    if content != original and count_fixed > 0:
        try:
            with open(p, 'w', encoding='utf-8') as f:
                f.write(content)
            return count_fixed, "FIXED"
        except Exception:
            return 0, "WRITE_ERROR"

    return 0, "NO_CHANGE"


def main():
    """Process Batch 2: loaders, executor, circuit breaker files."""
    priority_files = [
        # loaders
        "loaders/load_technical_data_daily.py",
        "loaders/load_signal_quality_scores.py",
        "loaders/load_swing_trader_scores.py",
        "loaders/load_swing_trader_scores_vectorized.py",
        "loaders/load_quality_metrics.py",
        "loaders/compute_circuit_breakers.py",
        "loaders/load_positioning_metrics.py",
        # API
        "lambda/api/routes/utils.py",
        # trading
        "algo/trading/executor.py",
        # risk
        "algo/risk/circuit_breaker.py",
    ]

    print("=" * 75)
    print("BATCH 2: SAFE FLOAT CONVERSION (Proven Conservative Patterns)")
    print("=" * 75)
    print()

    total = 0
    for fpath in priority_files:
        count, status = process_file(fpath)
        desc = f"FIXED {count}" if count > 0 else status
        print(f"{fpath:55} {desc:12}")
        total += count

    print()
    print(f"TOTAL FIXED: {total} conversions")
    print("=" * 75)


if __name__ == "__main__":
    main()
