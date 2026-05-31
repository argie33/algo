#!/usr/bin/env python3
"""Remove duplicate imports from Python files."""

import os
import re
from collections import OrderedDict
from pathlib import Path

def extract_imports_and_code(lines):
    """Separate imports from code, preserving comments and blank lines at top."""
    import_section = []
    code_section = []
    seen_code = False
    import_end_idx = 0

    for i, line in enumerate(lines):
        stripped = line.lstrip()

        # Check if this is an import line
        is_import = stripped.startswith(('from ', 'import ', '__future__'))
        is_comment = stripped.startswith(('#', '"""', "'''"))
        is_blank = not stripped or stripped == '\n'

        if not seen_code:
            import_section.append(line)
            if is_import:
                import_end_idx = i
            elif not is_comment and not is_blank:
                seen_code = True
                import_section.pop()  # Remove the first code line from imports
                code_section.append(line)
        else:
            code_section.append(line)

    return import_section[:import_end_idx + 1], code_section


def deduplicate_imports(import_lines):
    """Remove duplicate imports, keeping first occurrence."""
    seen = OrderedDict()
    result = []

    for line in import_lines:
        stripped = line.rstrip()
        if not stripped or stripped.startswith('#'):
            result.append(line)
        elif stripped.startswith(('from ', 'import ', '__future__')):
            # Normalize import for comparison
            normalized = re.sub(r'\s+', ' ', stripped)
            if normalized not in seen:
                seen[normalized] = True
                result.append(line)

    return result


def cleanup_file(filepath):
    """Remove duplicate imports from a file."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        import_section, code_section = extract_imports_and_code(lines)
        dedup_imports = deduplicate_imports(import_section)

        # Check if anything changed
        original_imports = ''.join(import_section)
        new_imports = ''.join(dedup_imports)

        if original_imports == new_imports:
            return False, "No duplicates found"

        # Reconstruct file
        new_content = ''.join(dedup_imports) + ''.join(code_section)

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)

        removed = len(import_section) - len(dedup_imports)
        return True, f"Removed {removed} duplicate import lines"

    except Exception as e:
        return False, f"Error: {e}"


def main():
    # Files needing cleanup
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
    fail_count = 0

    for filepath in files_to_fix:
        if os.path.exists(filepath):
            success, msg = cleanup_file(filepath)
            status = "[CLEANED]" if success else "[SKIPPED]"
            print(f"{status} {filepath}: {msg}")
            if success:
                success_count += 1
            else:
                fail_count += 1
        else:
            print(f"[MISSING] {filepath}")
            fail_count += 1

    print(f"\nTotal: {success_count} cleaned, {fail_count} skipped/missing")


if __name__ == '__main__':
    main()
