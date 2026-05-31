#!/usr/bin/env python3
"""Remove ALL duplicate imports, including those inside functions."""

import os
import re

def remove_all_duplicate_imports(filepath):
    """Remove duplicate imports everywhere in the file."""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    lines = content.split('\n')

    # Extract all unique imports (for tracking)
    import_regex = r'^\s*(?:from\s+\S+\s+import\s+.+|import\s+.+)$'
    all_imports = {}

    for i, line in enumerate(lines):
        if re.match(import_regex, line):
            normalized = re.sub(r'\s+', ' ', line.strip())
            if normalized not in all_imports:
                all_imports[normalized] = i
            else:
                # Found a duplicate - mark for removal
                all_imports[normalized] = (all_imports[normalized], i)  # tuple = duplicate

    # Build list of lines to remove
    lines_to_remove = set()
    duplicates_found = 0

    for normalized, val in all_imports.items():
        if isinstance(val, tuple):
            # This import is duplicated
            first_line, second_line = val
            lines_to_remove.add(second_line)
            duplicates_found += 1

    if not lines_to_remove:
        return False, "No duplicates found"

    # Rebuild file without duplicate imports
    new_lines = []
    for i, line in enumerate(lines):
        if i not in lines_to_remove:
            new_lines.append(line)

    new_content = '\n'.join(new_lines)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(new_content)

    return True, f"Removed {duplicates_found} duplicate import(s)"


def main():
    files_to_fix = [
        'algo/algo_circuit_breaker.py',
        'algo/algo_config.py',
        'algo/algo_daily_reconciliation.py',
        'algo/algo_market_events.py',
        'algo/algo_orchestrator.py',
        'algo/algo_position_monitor.py',
        'algo/algo_signal_attribution.py',
        'algo/algo_var.py',
        'algo/orchestrator/phase1_data_freshness.py',
        'config/credential_manager.py',
        'loaders/load_analyst_sentiment_analysis.py',
        'loaders/load_analyst_upgrade_downgrade.py',
        'loaders/load_buy_sell_daily.py',
        'loaders/load_earnings_history.py',
        'loaders/load_market_health_daily.py',
        'loaders/load_prices.py',
        'loaders/load_technical_data_daily.py',
        'scripts/verify-trading-setup.py',
        'terraform/modules/database/rds_rotation_lambda.py',
        'tests/backtest/test_backtest_regression.py',
        'tests/unit/test_phase7_reconciliation.py',
        'utils/data_provenance_tracker.py',
        'utils/data_source_router.py',
        'utils/data_tick_validator.py',
        'utils/data_watermark_manager.py',
        'utils/loader_helpers.py',
        'utils/optimal_loader.py',
        'utils/sec_edgar_client.py',
        'utils/yfinance_wrapper.py',
    ]

    success_count = 0

    for filepath in files_to_fix:
        if os.path.exists(filepath):
            success, msg = remove_all_duplicate_imports(filepath)
            if success:
                print(f"[FIXED] {filepath}")
                success_count += 1
            else:
                print(f"[SKIP] {filepath}")

    print(f"\nFixed {success_count}/{len([f for f in files_to_fix if os.path.exists(f)])} files")


if __name__ == '__main__':
    main()
