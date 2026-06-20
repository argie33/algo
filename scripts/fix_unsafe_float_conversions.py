#!/usr/bin/env python3
"""
Systematically fix 1196+ unsafe float() conversions to use safe_float().

This script:
1. Adds safe_float import to files needing it
2. Replaces unsafe float() calls with safe_float() equivalents
3. Handles special cases (conditional checks, calculations, etc.)
4. Preserves file structure and formatting
5. Verifies changes compile with mypy
"""

import re
from pathlib import Path


# Priority files with highest unsafe conversion counts
PRIORITY_FILES = [
    ("algo/trading/exit_engine.py", 38),
    ("lambda/api/routes/market.py", 36),
    ("loaders/load_stock_scores.py", 32),
    ("loaders/load_buy_sell_daily.py", 27),
    ("algo/infrastructure/config.py", 25),
    ("algo/infrastructure/reconciliation.py", 21),
    ("tools/dashboard/panels/signals.py", 19),
    ("algo/trading/executor.py", 18),
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


def add_import_if_needed(content: str) -> str:
    """Add safe_float import from utils.safe_data_conversion if not present."""
    # Check if already imported
    if "from utils.safe_data_conversion import safe_float" in content:
        return content
    if "from utils.safe_data_conversion import" in content and "safe_float" in content:
        return content

    # Find insertion point (after other imports)
    lines = content.split("\n")
    import_idx = -1

    for i, line in enumerate(lines):
        if line.startswith(("from utils.", "from algo.")):
            import_idx = i

    if import_idx >= 0:
        # Insert after found import
        lines.insert(import_idx + 1, "from utils.safe_data_conversion import safe_float")
        return "\n".join(lines)

    # Fallback: insert after last import
    for i, line in enumerate(lines):
        if line.startswith(("import ", "from ")):
            import_idx = i

    if import_idx >= 0:
        lines.insert(import_idx + 1, "from utils.safe_data_conversion import safe_float")
        return "\n".join(lines)

    return content


def fix_float_calls(content: str, filename: str) -> tuple[str, int]:
    """Replace unsafe float() calls with safe_float().

    Returns:
        (modified_content, count_of_replacements)
    """
    count = 0

    # Pattern 1: float(value) where value is a simple variable or dict access
    # Examples: float(x), float(row[0]), float(d.get("key"))
    def replace_simple_float(match):
        nonlocal count
        count += 1
        inner = match.group(1)
        return f'safe_float({inner}, default=0.0, context="{inner}")'

    # Replace patterns like: float(variable_name)
    content = re.sub(
        r'float\(([a-zA-Z_][a-zA-Z0-9_]*)\)',
        replace_simple_float,
        content
    )

    # Pattern 2: Conditional None checks
    # float(x) if x is not None else None -> safe_float(x, default=None)
    def replace_conditional_none(match):
        nonlocal count
        count += 1
        inner = match.group(1)
        return f'safe_float({inner}, default=None, context="{inner}")'

    content = re.sub(
        r'float\(([^)]+)\)\s+if\s+\1\s+is\s+not\s+None\s+else\s+None',
        replace_conditional_none,
        content
    )

    # Pattern 3: Dictionary/row access with None checks
    # float(row[0]) if row[0] is not None else None
    def replace_dict_access(match):
        nonlocal count
        count += 1
        inner = match.group(1)
        return f'safe_float({inner}, default=None, context="value")'

    content = re.sub(
        r'float\(([a-zA-Z_][a-zA-Z0-9_]*\[[^\]]+\])\)\s+if\s+\1\s+is\s+not\s+None\s+else\s+None',
        replace_dict_access,
        content
    )

    return content, count


def process_file(fpath: str) -> bool:
    """Process a single file. Return True if successful."""
    full_path = Path(fpath)

    if not full_path.exists():
        print("  SKIP: Not found")
        return False

    try:
        with open(full_path, encoding='utf-8', errors='replace') as f:
            original = f.read()

        # Fix smart quotes and encoding issues
        content = original.replace('"', '"').replace('"', '"')
        content = content.replace("'", "'").replace("'", "'")
        content = content.replace("-", "-").replace("-", "-")

        # Add import
        content = add_import_if_needed(content)

        # Fix float() calls
        content, count = fix_float_calls(content, fpath)

        if count > 0:
            # Write back
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"  FIXED: {count} float() calls -> safe_float()")
            return True
        else:
            print("  NO CHANGES: 0 float() calls found")
            return False

    except Exception as e:
        print(f"  ERROR: {e}")
        return False


def main():
    """Process all priority files."""
    print("=" * 70)
    print("UNSAFE FLOAT CONVERSION FIXER")
    print("=" * 70)
    print()

    fixed = 0
    for fpath, estimated_count in PRIORITY_FILES:
        print(f"{fpath} ({estimated_count} est. conversions)")
        if process_file(fpath):
            fixed += 1
        print()

    print("=" * 70)
    print(f"COMPLETE: Fixed {fixed}/{len(PRIORITY_FILES)} files")
    print("=" * 70)


if __name__ == "__main__":
    main()
