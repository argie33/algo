#!/usr/bin/env python3
"""
Comprehensive fixer for unsafe float() calls.
Handles multi-line calls, already-corrupted calls, and complex patterns.
"""

import re
from pathlib import Path


def sanitize_smart_quotes(text: str) -> str:
    """Fix UTF-8 smart quotes and other encoding issues."""
    replacements = [
        ('"', '"'),  # U+201C left quote
        ('"', '"'),  # U+201D right quote
        (''', "'"),  # U+2018 left single
        (''', "'"),  # U+2019 right single
    ]
    for old, new in replacements:
        text = text.replace(old, new)
    return text


def clean_corrupted_lines(text: str) -> str:
    """Remove corrupted safe_float lines with repeated prefixes."""
    # Match lines like: safe_safe_safe_safe_safe_float(...)
    text = re.sub(
        r'safe_(safe_)+float',
        'safe_float',
        text
    )
    return text


def add_safe_float_import(content: str) -> str:
    """Add safe_float import if not already present."""
    # Check if already imported
    if 'from utils.safe_data_conversion import safe_float' in content:
        return content

    if 'from utils.safe_data_conversion import' in content:
        # Already has the import but maybe not safe_float
        if 'safe_float' in content:
            return content
        # Add to existing import
        content = re.sub(
            r'from utils\.safe_data_conversion import ([^)\n]*)',
            r'from utils.safe_data_conversion import \1, safe_float',
            content
        )
        if 'safe_float' in content:
            return content

    # Find insertion point (after last import statement)
    lines = content.split('\n')
    last_import_idx = -1

    for i, line in enumerate(lines):
        if line.startswith(('from ', 'import ')):
            last_import_idx = i

    if last_import_idx >= 0:
        lines.insert(last_import_idx + 1, 'from utils.safe_data_conversion import safe_float')
        return '\n'.join(lines)

    return content


def fix_float_calls_comprehensive(text: str) -> str:
    """
    Replace all float() calls with safe_float().
    Handles multi-line calls, nested calls, and dict access.
    """

    # Helper to extract balanced parentheses (currently unused - kept for future enhancements)
    def extract_balanced_paren(s: str, start: int) -> tuple:
        """Extract content between balanced parentheses starting at position start."""
        if start >= len(s) or s[start] != '(':
            return None, None

        depth = 0
        for i in range(start, len(s)):
            if s[i] == '(':
                depth += 1
            elif s[i] == ')':
                depth -= 1
                if depth == 0:
                    return start + 1, i
        return None, None

    # Handle multi-line float calls
    # First: normalize multi-line to single-line for processing
    # Match: float(\n ... \n) → float(...)
    text = re.sub(r'float\s*\(\s*\n\s*', 'float(', text)
    text = re.sub(r'\n\s*\)', ')', text)

    # Replace all float() calls with safe_float()
    def replace_float(match):
        inner = match.group(1)
        # Truncate context for readability
        context = inner[:40].replace('\n', ' ')
        return f'safe_float({inner}, default=0.0, context="{context}")'

    # Match float(...) where ... can contain nested parens, spaces, newlines
    # Use a multi-line capable pattern
    pattern = r'float\s*\(([^)]*(?:\([^)]*\)[^)]*)*)\)'

    # Iterative replacement to handle nested float() calls
    max_iterations = 10
    prev = text
    for _ in range(max_iterations):
        text = re.sub(pattern, replace_float, text)
        if text == prev:
            break
        prev = text

    return text


def process_file(fpath: str) -> tuple[int, bool]:
    """
    Process one file.
    Returns: (count_of_replacements, has_errors)
    """
    p = Path(fpath)
    if not p.exists():
        return 0, False

    try:
        with open(p, encoding='utf-8', errors='replace') as f:
            original = f.read()
    except Exception as e:
        print(f"    ERROR reading: {e}")
        return 0, True

    # Clean up
    content = sanitize_smart_quotes(original)
    content = clean_corrupted_lines(content)

    # Count float() calls before
    count_before = len(re.findall(r'\bfloat\s*\(', content))

    if count_before == 0:
        return 0, False

    # Add import
    content = add_safe_float_import(content)

    # Fix float calls
    content = fix_float_calls_comprehensive(content)

    # Count float() calls after
    count_after = len(re.findall(r'\bfloat\s*\(', content))
    count_replaced = count_before - count_after

    # Write back if changes
    if content != original:
        try:
            with open(p, 'w', encoding='utf-8') as f:
                f.write(content)
            return count_replaced, False
        except Exception as e:
            print(f"    ERROR writing: {e}")
            return 0, True

    return 0, False


def main():
    """Process priority files with highest conversion counts."""
    priority_files = [
        "tools/dashboard/fetchers.py",  # 57
        "lambda/api/routes/market.py",  # 36
        "loaders/load_stock_scores.py",  # 32
        "algo/trading/executor.py",  # 18 -> but many multi-line
        "algo/trading/exit_engine.py",  # 38
        "loaders/load_buy_sell_daily.py",  # 27
        "algo/infrastructure/config.py",  # 25
        "algo/infrastructure/reconciliation.py",  # 21
        "algo/risk/circuit_breaker.py",  # 21
        "tools/dashboard/panels/signals.py",  # 19
        "tools/dashboard/panels/health.py",  # 18
        "lambda/api/routes/risk_dashboard.py",  # 17
        "loaders/load_market_health_daily.py",  # 17
        "algo/monitoring/position_monitor.py",  # 17
        "utils/signals/metrics_fetcher.py",  # 15
        "tools/dashboard/panels/trades.py",  # 15
        "algo/risk/market_exposure.py",  # 14
        "algo/reporting/daily_report.py",  # 14
        "config/thresholds.py",  # 14
    ]

    print("=" * 70)
    print("COMPREHENSIVE FLOAT CONVERSION FIXER")
    print("=" * 70)
    print()

    total_fixed = 0
    total_errors = 0

    for fpath in priority_files:
        count, has_error = process_file(fpath)
        status = f"FIXED {count}" if count > 0 else "SKIP"
        if has_error:
            status = "ERROR"
            total_errors += 1

        print(f"{fpath:50} {status:12}")
        total_fixed += count

    print()
    print("=" * 70)
    print(f"TOTAL FIXED: {total_fixed} float() conversions")
    if total_errors > 0:
        print(f"ERRORS: {total_errors}")
    print("=" * 70)


if __name__ == "__main__":
    main()
