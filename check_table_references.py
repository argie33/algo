#!/usr/bin/env python3
import os
import re

# Check for direct table references in code
tables_to_check = [
    'earnings_estimate_revisions', 'earnings_estimate_trends', 'can_slim_metrics',
    'factor_metrics', 'algo_champion_challenger', 'algo_information_coefficient',
    'algo_model_registry', 'community_signups', 'sentiment', 'sentiment_social',
    'options_chains', 'options_greeks', 'ttm_cash_flow', 'ttm_income_statement',
    'index_metrics', 'relative_performance', 'signal_themes',
]

for table in tables_to_check:
    count = 0
    for root, dirs, files in os.walk('.'):
        if 'node_modules' in root or '.git' in root:
            continue
        for file in files:
            if file.endswith(('.py', '.js', '.sql')):
                path = os.path.join(root, file)
                try:
                    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                        if table in f.read():
                            count += 1
                except:
                    pass
    
    if count == 0:
        print(f"[NOT FOUND] {table}")
    elif count == 1:
        print(f"[MINIMAL] {table} (referenced in {count} file)")
    else:
        print(f"[OK] {table} (referenced in {count} files)")
