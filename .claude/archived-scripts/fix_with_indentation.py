#!/usr/bin/env python3
"""Fix broken 'with DatabaseContext' indentation."""

import re
from pathlib import Path

def fix_with_indentation(filepath):
    """Fix broken with statement indentation."""
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    fixed = False
    i = 0
    while i < len(lines):
        line = lines[i]
        # Check if this is a 'with DatabaseContext' line followed by blank line
        if 'with DatabaseContext' in line and line.rstrip().endswith(':'):
            # Check if next line is blank or not properly indented
            if i + 1 < len(lines):
                next_line = lines[i + 1]
                # If next line is blank or has code at wrong indentation
                if next_line.strip() == '' or (next_line.strip() and not next_line.startswith(' ' * (len(line) - len(line.lstrip()) + 4))):
                    # Find the indentation level of the 'with' statement
                    with_indent = len(line) - len(line.lstrip())
                    expected_inner_indent = with_indent + 4

                    # Skip blank lines immediately after with
                    j = i + 1
                    while j < len(lines) and lines[j].strip() == '':
                        j += 1

                    # Re-indent subsequent non-blank lines until we hit a line with less indentation
                    while j < len(lines):
                        current_line = lines[j]
                        if current_line.strip() == '':
                            j += 1
                            continue

                        # Stop if we hit a line with less indentation than the with block
                        current_indent = len(current_line) - len(current_line.lstrip())
                        if current_indent < expected_inner_indent and current_indent <= with_indent:
                            break

                        # Re-indent the line if it's not already properly indented
                        if current_line.startswith(' ' * with_indent) and not current_line.startswith(' ' * expected_inner_indent):
                            # Remove with_indent spaces and add expected_inner_indent spaces
                            lines[j] = ' ' * expected_inner_indent + current_line[with_indent:]
                            fixed = True

                        j += 1
        i += 1

    if fixed:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.writelines(lines)
        return True
    return False

algo_root = Path(__file__).parent.parent
problem_files = [
    'algo/algo_earnings_blackout.py',
    'algo/algo_var.py',
    'algo/orchestrator/phase4_exit_execution.py',
    'loaders/load_sentiment.py',
    'loaders/load_signal_quality_scores.py',
    'loaders/load_signal_themes.py',
    'loaders/load_stability_metrics.py',
    'loaders/load_stock_scores.py',
    'tests/integration_test_e2e.py',
    'utils/loader_history_tracker.py',
]

fixed_count = 0
for file_path in problem_files:
    full_path = algo_root / file_path
    if full_path.exists():
        if fix_with_indentation(full_path):
            print(f"Fixed: {file_path}")
            fixed_count += 1
        else:
            print(f"No changes needed: {file_path}")
    else:
        print(f"File not found: {file_path}")

print(f"\nFixed {fixed_count}/{len(problem_files)} files")
