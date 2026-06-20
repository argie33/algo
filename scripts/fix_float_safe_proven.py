#!/usr/bin/env python3
"""
Safe float() -> safe_float() converter using AST-aware replacement.
This version is conservative and handles one pattern at a time with validation.
"""

import ast
import re
from pathlib import Path


def sanitize_smart_quotes(text: str) -> str:
    """Fix UTF-8 smart quotes."""
    replacements = [
        ('"', '"'),  # U+201C left quote
        ('"', '"'),  # U+201D right quote
        (''', "'"),  # U+2018 left single
        (''', "'"),  # U+2019 right single
    ]
    for old, new in replacements:
        text = text.replace(old, new)
    return text


def add_safe_float_import(lines: list[str]) -> list[str]:
    """Add safe_float import to the file."""
    # Find last import line
    last_import_idx = -1
    for i, line in enumerate(lines):
        if line.strip().startswith(('from ', 'import ')):
            last_import_idx = i

    if last_import_idx >= 0:
        # Check if import already exists
        import_section = '\n'.join(lines[:last_import_idx + 1])
        if 'safe_float' not in import_section:
            lines.insert(last_import_idx + 1, 'from utils.safe_data_conversion import safe_float')

    return lines


def fix_simple_float_calls(text: str) -> tuple[str, int]:
    """
    Replace float() calls with safe_float() - one at a time to avoid corruption.
    Only handles the most common, safest patterns.
    """
    count = 0

    # Pattern 1: float(identifier) where identifier is a simple variable name
    # e.g., float(x), float(row), float(val)
    def replace_var(match):
        nonlocal count
        count += 1
        var = match.group(1)
        # Use safe defaults
        return f'safe_float({var}, default=0.0)'

    text = re.sub(r'\bfloat\(([a-zA-Z_][a-zA-Z0-9_]*)\)', replace_var, text)

    # Pattern 2: float(dict.get(...)) or float(row[...])
    # Only match if we can identify clear boundaries
    def replace_access(match):
        nonlocal count
        count += 1
        expr = match.group(1)
        return f'safe_float({expr}, default=0.0)'

    # Match float(x.get(...)) where ... doesn't have unbalanced parens
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

    # Pattern 4: float(number) where number is a literal
    def replace_literal(match):
        nonlocal count
        count += 1
        num = match.group(1)
        return f'safe_float({num}, default=0.0)'

    text = re.sub(r'\bfloat\(([0-9]+\.?[0-9]*)\)', replace_literal, text)

    # Pattern 5: float(string literal like "1.5")
    text = re.sub(r'\bfloat\(("(?:[^"\\]|\\.)*")\)', replace_literal, text)
    text = re.sub(r"\bfloat\(('(?:[^'\\]|\\.)*')\)", replace_literal, text)

    return text, count


def validate_syntax(text: str) -> bool:
    """Check if the text is valid Python syntax."""
    try:
        ast.parse(text)
        return True
    except SyntaxError:
        return False


def process_file(fpath: str) -> tuple[int, str]:
    """
    Process one file safely.
    Returns: (count_of_replacements, status_message)
    """
    p = Path(fpath)
    if not p.exists():
        return 0, "NOT_FOUND"

    try:
        with open(p, encoding='utf-8') as f:
            original = f.read()
    except Exception as e:
        return 0, f"READ_ERROR: {e}"

    # Sanitize encoding
    content = sanitize_smart_quotes(original)

    # Validate original is parseable
    if not validate_syntax(content):
        return 0, "SYNTAX_ERROR_BEFORE"

    # Count float() calls before
    count_before = len(re.findall(r'\bfloat\s*\(', content))
    if count_before == 0:
        return 0, "NO_CALLS"

    # Split into lines for import insertion
    lines = content.split('\n')
    lines = add_safe_float_import(lines)
    content = '\n'.join(lines)

    # Apply replacements
    content, count_fixed = fix_simple_float_calls(content)

    # Validate syntax after changes
    if not validate_syntax(content):
        return 0, "SYNTAX_ERROR_AFTER"


    # Only write if we actually fixed something and syntax is valid
    if content != original and count_fixed > 0:
        try:
            with open(p, 'w', encoding='utf-8') as f:
                f.write(content)
            return count_fixed, f"FIXED {count_fixed}/{count_before}"
        except Exception as e:
            return 0, f"WRITE_ERROR: {e}"

    return count_fixed, f"FIXED {count_fixed}/{count_before}"


def main():
    """Process priority files."""
    priority_files = [
        ("tools/dashboard/fetchers.py", 57),
        ("lambda/api/routes/market.py", 36),
        ("loaders/load_stock_scores.py", 32),
        ("algo/trading/exit_engine.py", 38),
        ("algo/trading/executor.py", 14),
        ("loaders/load_buy_sell_daily.py", 27),
        ("algo/infrastructure/config.py", 25),
        ("algo/infrastructure/reconciliation.py", 21),
        ("algo/risk/circuit_breaker.py", 21),
        ("tools/dashboard/panels/signals.py", 19),
        ("tools/dashboard/panels/health.py", 18),
        ("lambda/api/routes/risk_dashboard.py", 17),
        ("loaders/load_market_health_daily.py", 17),
        ("algo/monitoring/position_monitor.py", 17),
        ("utils/signals/metrics_fetcher.py", 15),
        ("tools/dashboard/panels/trades.py", 15),
        ("algo/risk/market_exposure.py", 14),
        ("algo/reporting/daily_report.py", 14),
        ("config/thresholds.py", 14),
    ]

    print("=" * 75)
    print("SAFE FLOAT CONVERSION FIXER (Syntax Validated)")
    print("=" * 75)
    print()

    total = 0
    for fpath, _estimated in priority_files:
        count, status = process_file(fpath)
        print(f"{fpath:50} {status:20}")
        total += count

    print()
    print("=" * 75)
    print(f"TOTAL FIXED: {total} float() conversions")
    print("=" * 75)


if __name__ == "__main__":
    main()
