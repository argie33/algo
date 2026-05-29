#!/usr/bin/env python3
"""Fix files broken by the migration script - revert to get_db_connection pattern."""

import re
from pathlib import Path

problem_files = [
    'algo/algo_earnings_blackout.py',
    'algo/algo_var.py',
    'algo/orchestrator/phase4_exit_execution.py',
    'loaders/load_signal_quality_scores.py',
    'loaders/load_signal_themes.py',
    'loaders/load_stability_metrics.py',
    'loaders/load_stock_scores.py',
    'tests/integration_test_e2e.py',
    'utils/loader_history_tracker.py',
]

algo_root = Path(__file__).parent.parent

for file_path in problem_files:
    full_path = algo_root / file_path
    if not full_path.exists():
        print(f"File not found: {file_path}")
        continue

    with open(full_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Revert import: DatabaseContext -> get_db_connection
    content = re.sub(
        r'from utils\.database_context import DatabaseContext(?:, get_db_connection)?',
        'from utils.db_connection import get_db_connection',
        content
    )

    # Fix: with DatabaseContext() as cur: with blank line after -> conn = get_db_connection()
    # This is a bandaid - but it will at least make the syntax valid
    content = re.sub(
        r'with DatabaseContext\(\) as cur:\s*\n\s*\n\s*try:',
        'conn = get_db_connection()\n    cur = conn.cursor()\n    try:',
        content
    )

    # Also fix standalone "with DatabaseContext()" patterns
    content = re.sub(
        r'with DatabaseContext\(\) as cur:\s*\n(\s+)([\w])',
        lambda m: f'conn = get_db_connection()\n    cur = conn.cursor()\n{m.group(1)}{m.group(2)}',
        content
    )

    with open(full_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"Reverted: {file_path}")

print("\nDone. These files have been reverted to use get_db_connection().")
print("They can be properly migrated to DatabaseContext in a follow-up pass.")
