#!/usr/bin/env python3
"""Batch fix unsafe float() calls systematically."""

import re
from pathlib import Path


def sanitize_content(text: str) -> str:
    """Remove problematic Unicode characters."""
    # All known variants of problematic characters
    replacements = [
        ('"', '"'),  # U+201C left quote
        ('"', '"'),  # U+201D right quote
        (''', "'"),  # U+2018 left single
        (''', "'"),  # U+2019 right single
    ]

    for old, new in replacements:
        text = text.replace(old, new)

    return text


def add_safe_float_import(content: str) -> str:
    """Add safe_float import if needed."""
    if 'from utils.safe_data_conversion import' in content and 'safe_float' in content:
        return content

    if 'from utils.safe_data_conversion import safe_float' in content:
        return content

    # Find last import and insert after
    lines = content.split('\n')
    last_import_idx = -1

    for i, line in enumerate(lines):
        if line.startswith(('from ', 'import ')):
            last_import_idx = i

    if last_import_idx >= 0:
        lines.insert(last_import_idx + 1, 'from utils.safe_data_conversion import safe_float')
        return '\n'.join(lines)

    return content


def replace_float_calls(content: str) -> str:
    """Replace float() calls with safe_float()."""

    # First pass: Replace float() calls with balanced parentheses
    # This handles: float(var), float(dict[key]), float(method()), etc.
    def replace_float_call(match):
        # Get the inner content
        inner = match.group(1)
        return f'safe_float({inner}, default=0.0, context="{inner[:30]}")'

    # Pattern: float(anything) where anything doesn't contain unbalanced parens
    # Match float( followed by balanced content, followed by )
    max_iterations = 5
    for _ in range(max_iterations):
        old_content = content
        # Match float(...) with simple inner content (no nested calls usually)
        content = re.sub(
            r'float\(([^()]+)\)',
            replace_float_call,
            content,
            count=1  # One at a time to handle nesting
        )
        if content == old_content:
            break

    return content


def process_file(fpath: str) -> int:
    """Process one file. Returns number of replacements."""
    p = Path(fpath)
    if not p.exists():
        return 0

    with open(p, encoding='utf-8') as f:
        original = f.read()

    # Sanitize
    content = sanitize_content(original)

    # Count float() before
    count_before = len(re.findall(r'\bfloat\s*\(', content))

    # Add import
    content = add_safe_float_import(content)

    # Replace
    content = replace_float_calls(content)

    # Count float() after
    count_after = len(re.findall(r'\bfloat\s*\(', content))
    count_replaced = count_before - count_after

    if content != original:
        with open(p, 'w', encoding='utf-8') as f:
            f.write(content)

    return count_replaced


if __name__ == '__main__':
    files = [
        "algo/trading/exit_engine.py",
        "lambda/api/routes/market.py",
        "loaders/load_stock_scores.py",
        "loaders/load_buy_sell_daily.py",
        "algo/infrastructure/config.py",
        "algo/infrastructure/reconciliation.py",
        "tools/dashboard/panels/signals.py",
        "algo/trading/executor.py",
        "tools/dashboard/panels/health.py",
        "lambda/api/routes/risk_dashboard.py",
        "loaders/load_market_health_daily.py",
        "algo/monitoring/position_monitor.py",
        "utils/signals/metrics_fetcher.py",
        "tools/dashboard/panels/trades.py",
        "algo/risk/market_exposure.py",
        "algo/reporting/daily_report.py",
        "config/thresholds.py",
    ]

    print("=" * 70)
    print("FIXING UNSAFE FLOAT CONVERSIONS")
    print("=" * 70)
    print()

    total = 0
    for fpath in files:
        count = process_file(fpath)
        status = f"FIXED {count}" if count > 0 else "SKIP"
        print(f"{fpath:50} {status:12}")
        total += count

    print()
    print("=" * 70)
    print(f"TOTAL FIXED: {total} float() conversions")
    print("=" * 70)
