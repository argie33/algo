#!/usr/bin/env python3
"""Add type hints to critical modules."""

import sys
import re

# Define type hints for each module's methods
HINTS = {
    'algo_exit_engine.py': {
        'check_and_execute_exits': '-> int',
        '_evaluate_position': '-> Dict[str, Any] | None',
        'connect': '-> None',
        'disconnect': '-> None',
        '_fetch_recent_prices': '-> tuple[float | None, float | None]',
        '_fetch_market_dist_days': '-> int',
        '_is_pulling_back': '-> bool',
        '_rs_line_breaking': '-> bool',
        '_eight_week_rule_active': '-> bool',
        '_chandelier_or_ema_stop': '-> tuple[float | None, bool]',
        '_is_td_sequential_top': '-> bool',
        '_get_td_state': '-> Dict[str, Any]',
        '_is_minervini_break': '-> bool',
        '_check_exit_conditions': '-> Dict[str, Any]',
    },
    'algo_filter_pipeline.py': {
        'run': '-> List[Dict[str, Any]]',
        'filter_by_universe': '-> List[str]',
        'apply_sector_filter': '-> List[str]',
        'apply_technical_filter': '-> List[str]',
        'apply_fundamentals_filter': '-> List[str]',
        'apply_volatility_filter': '-> List[str]',
        'apply_momentum_filter': '-> List[str]',
        'apply_quality_filter': '-> List[str]',
        'apply_valuation_filter': '-> List[str]',
        'apply_liquidity_filter': '-> List[str]',
        'apply_custom_filter': '-> List[str]',
        '_get_universe': '-> List[str]',
        '_evaluate_quality': '-> Dict[str, Any]',
        '_fetch_sector_pe': '-> float',
        '_calculate_momentum_score': '-> float',
    },
}

def add_type_hints(filepath, method_hints):
    """Add type hints to a file."""
    print(f"\nProcessing: {filepath}")
    print("=" * 70)

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Check if typing is imported
    has_typing = 'from typing import' in content or 'import typing' in content

    if not has_typing:
        # Add typing import after regular imports
        lines = content.split('\n')
        insert_pos = 0
        for i, line in enumerate(lines):
            if line.startswith('#!') or (i == 0 and line.startswith('"""')):
                continue
            if line.startswith('import ') or line.startswith('from '):
                insert_pos = i + 1

        # Insert typing import
        lines.insert(insert_pos, 'from typing import Dict, List, Any, Optional, Tuple')
        content = '\n'.join(lines)
        print("[+] Added: from typing import Dict, List, Any, Optional, Tuple")

    # Now add return type hints to methods
    added_count = 0
    for method_name, return_type in method_hints.items():
        # Find method definition and add return type if not present
        pattern = rf'(\n[^\S\n]*def {method_name}\([^)]*)\):'

        def replacer(match):
            nonlocal added_count
            full_match = match.group(0)
            # Check if return type already present
            if '->' in full_match:
                return full_match

            # Add return type
            added_count += 1
            return full_match[:-2] + f') {return_type}:'

        content = re.sub(pattern, replacer, content)

    if added_count > 0:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"[+] Added {added_count} type annotations")

        # Verify file syntax
        try:
            compile(content, filepath, 'exec')
            print("[OK] Syntax valid")
            return True
        except SyntaxError as e:
            print(f"[ERROR] Syntax error: {e}")
            return False
    else:
        print("[-] No methods matched for type hints")
        return False

if __name__ == '__main__':
    if len(sys.argv) > 1:
        filepath = sys.argv[1]
        if filepath in HINTS:
            success = add_type_hints(filepath, HINTS[filepath])
            sys.exit(0 if success else 1)
        else:
            print(f"No hints defined for {filepath}")
            sys.exit(1)
    else:
        # Process all defined files
        for filepath in HINTS.keys():
            try:
                add_type_hints(filepath, HINTS[filepath])
            except Exception as e:
                print(f"Error processing {filepath}: {e}")
