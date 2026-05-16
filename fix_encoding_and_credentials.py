#!/usr/bin/env python3
"""Fix encoding issues and credential calls in remaining files."""
import os
import re
from pathlib import Path

SKIP_DIRS = {'.git', '__pycache__', '.venv', 'webapp', 'tests', 'lambda', 'terraform'}
FILES_TO_FIX = [
    'algo_continuous_monitor.py',
    'algo_dry_run_simulator.py',
    'algo_orchestrator.py',
    'algo_pnl_leakage_monitor.py',
    'algo_position_monitor.py',
    'algo_quality_trends.py',
    'algo_rolling_sharpe_monitor.py',
    'algo_stress_test_runner.py',
    'credential_validator.py',
    'enable_timescaledb.py',
    'gemini-review.py',
    'init_database.py',
    'lambda_function.py',
    'loadaaiidata.py',
    'loadfeargreed.py',
    'loadnaaim.py',
    'migrate_timescaledb.py',
    'run_quick_wins_full.py',
    'safeguard_cli.py',
    'schema_validator.py',
    'setup_test_db.py',
    'validate_schema_queries.py',
    'verify_deployment.py',
]

fixed = 0
for filename in FILES_TO_FIX:
    filepath = Path(filename)
    if not filepath.exists():
        continue
    
    try:
        # Try to read with different encodings
        content = None
        for encoding in ['utf-8-sig', 'utf-8', 'latin-1', 'cp1252']:
            try:
                content = filepath.read_text(encoding=encoding)
                break
            except:
                continue
        
        if not content:
            print(f"[SKIP] {filename}: Could not decode")
            continue
        
        original = content
        
        # Fix credential calls
        if 'credential_manager.get_db_credentials()' in content:
            content = re.sub(
                r'credential_manager\.get_db_credentials\(\)\["password"\]',
                'get_db_password()',
                content
            )
            content = re.sub(
                r'credential_manager\.get_db_credentials\(\)',
                'get_db_config()',
                content
            )
            
            if 'from credential_helper import' not in content:
                lines = content.split('\n')
                import_idx = 0
                for i, line in enumerate(lines[:30]):
                    if line.startswith('import ') or line.startswith('from '):
                        import_idx = i + 1
                lines.insert(import_idx, 'from credential_helper import get_db_password, get_db_config')
                content = '\n'.join(lines)
        
        # Write back with UTF-8
        if content != original:
            filepath.write_text(content, encoding='utf-8')
            print(f"[OK] {filename}")
            fixed += 1
        else:
            print(f"[SKIP] {filename}: No changes needed")
    except Exception as e:
        print(f"[ERROR] {filename}: {e}")

print(f"\nFixed {fixed} files with encoding/credential issues")
