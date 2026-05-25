#!/usr/bin/env python3
"""
Comprehensive system health check - validates all components are operational.
Output: JSON report with status of each component.
"""

import json
import sys
import os
from datetime import datetime
from pathlib import Path

# Add repo root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

def check_database():
    """Verify database connectivity and schema."""
    try:
        from utils.db_connection import get_db_connection
        conn = get_db_connection()
        cur = conn.cursor()

        # Check critical tables exist
        tables = ['stock_symbols', 'price_daily', 'technical_data_daily',
                 'buy_sell_daily', 'stock_scores', 'algo_positions', 'algo_trades',
                 'data_patrol_log', 'data_loader_status']

        missing_tables = []
        for table in tables:
            cur.execute(f"SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name='{table}')")
            if not cur.fetchone()[0]:
                missing_tables.append(table)

        cur.close()
        conn.close()

        if missing_tables:
            return {'status': 'FAIL', 'message': f'Missing tables: {missing_tables}'}
        return {'status': 'PASS', 'message': 'All critical tables exist'}
    except Exception as e:
        return {'status': 'FAIL', 'message': str(e)}

def check_orchestrator():
    """Verify orchestrator can be imported and initialized."""
    try:
        from algo.algo_orchestrator import Orchestrator
        orch = Orchestrator(dry_run=True, verbose=False)
        return {'status': 'PASS', 'message': 'Orchestrator initializes successfully'}
    except Exception as e:
        return {'status': 'FAIL', 'message': str(e)}

def check_api_lambda():
    """Verify API Lambda handler can be imported."""
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent / 'lambda' / 'api'))
        import lambda_function
        return {'status': 'PASS', 'message': 'API Lambda handler imports successfully'}
    except Exception as e:
        return {'status': 'FAIL', 'message': str(e)}

def check_loaders():
    """Verify loader modules can be imported."""
    try:
        loaders_dir = Path(__file__).parent.parent / 'loaders'
        loader_files = list(loaders_dir.glob('load_*.py'))

        if not loader_files:
            return {'status': 'FAIL', 'message': 'No loaders found'}

        # Try importing a few critical ones
        critical = ['load_stock_prices_daily', 'load_technical_data_daily', 'load_signals_daily']
        failed = []

        for loader in critical:
            try:
                __import__(f'loaders.{loader}', fromlist=[loader])
            except Exception as e:
                failed.append(f'{loader}: {str(e)[:50]}')

        if failed:
            return {'status': 'FAIL', 'message': f'Failed loaders: {failed}'}

        return {'status': 'PASS', 'message': f'{len(loader_files)} loaders found, {len(critical)} critical loaders OK'}
    except Exception as e:
        return {'status': 'FAIL', 'message': str(e)}

def check_frontend():
    """Verify frontend is built."""
    try:
        dist_dir = Path(__file__).parent.parent / 'webapp' / 'frontend' / 'dist'
        config_file = dist_dir / 'config.js'
        index_file = dist_dir / 'index.html'

        if not dist_dir.exists():
            return {'status': 'FAIL', 'message': 'dist/ directory not found'}

        if not config_file.exists():
            return {'status': 'FAIL', 'message': 'config.js not found'}

        if not index_file.exists():
            return {'status': 'FAIL', 'message': 'index.html not found'}

        return {'status': 'PASS', 'message': f'Frontend built ({dist_dir.stat().st_mtime})'}
    except Exception as e:
        return {'status': 'FAIL', 'message': str(e)}

def check_config_files():
    """Verify critical config files exist and are valid."""
    try:
        required_files = [
            'steering/algo.md',
            'CLAUDE.md',
            'terraform/main.tf',
            'lambda/api/lambda_function.py',
            'algo/algo_orchestrator.py'
        ]

        repo_root = Path(__file__).parent.parent
        missing = []

        for file in required_files:
            path = repo_root / file
            if not path.exists():
                missing.append(file)

        if missing:
            return {'status': 'FAIL', 'message': f'Missing files: {missing}'}

        return {'status': 'PASS', 'message': f'All {len(required_files)} critical files present'}
    except Exception as e:
        return {'status': 'FAIL', 'message': str(e)}

def check_git_status():
    """Verify git repository is clean or has expected uncommitted files."""
    try:
        import subprocess

        result = subprocess.run(['git', 'status', '--porcelain'],
                              capture_output=True, text=True, cwd=Path(__file__).parent.parent)

        if result.returncode != 0:
            return {'status': 'FAIL', 'message': 'git status failed'}

        # Allow test_results.json to be modified
        lines = [l for l in result.stdout.strip().split('\n') if l and not l.endswith('test_results.json')]

        if lines:
            return {'status': 'WARNING', 'message': f'Uncommitted changes: {len(lines)} files', 'files': lines[:5]}

        return {'status': 'PASS', 'message': 'Git repository clean (or only test_results.json modified)'}
    except Exception as e:
        return {'status': 'FAIL', 'message': str(e)}

def check_tests():
    """Verify test suite passes."""
    try:
        import subprocess

        result = subprocess.run(['python3', '-m', 'pytest', 'tests/', '-q', '--tb=no'],
                              capture_output=True, text=True, cwd=Path(__file__).parent.parent,
                              timeout=120)

        output = result.stdout + result.stderr

        # Extract pass/fail counts
        if result.returncode == 0:
            return {'status': 'PASS', 'message': f'All tests pass: {output.split(chr(10))[-2]}'}
        else:
            return {'status': 'FAIL', 'message': f'Tests failing: {output.split(chr(10))[-2]}'}
    except subprocess.TimeoutExpired:
        return {'status': 'FAIL', 'message': 'Test suite timeout'}
    except Exception as e:
        return {'status': 'FAIL', 'message': str(e)}

def main():
    """Run all checks and generate report."""
    checks = {
        'Database Connectivity': check_database,
        'Orchestrator': check_orchestrator,
        'API Lambda Handler': check_api_lambda,
        'Data Loaders': check_loaders,
        'Frontend Build': check_frontend,
        'Configuration Files': check_config_files,
        'Git Repository': check_git_status,
        'Test Suite': check_tests,
    }

    results = {}
    all_pass = True

    print('Running system health checks...\n')

    for check_name, check_func in checks.items():
        try:
            result = check_func()
            results[check_name] = result
            status = result['status']
            message = result.get('message', '')

            symbol = 'PASS' if status == 'PASS' else 'WARN' if status == 'WARNING' else 'FAIL'
            print(f'[{symbol}] {check_name}')
            if message:
                print(f'      {message}')

            if status in ('FAIL', 'WARNING'):
                all_pass = False
        except Exception as e:
            results[check_name] = {'status': 'ERROR', 'message': str(e)}
            print(f'[ERROR] {check_name}: {str(e)[:50]}')
            all_pass = False

    # Generate JSON report
    report = {
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'overall_status': 'PASS' if all_pass else 'FAIL',
        'checks': results
    }

    print('\n' + '='*60)
    print(json.dumps(report, indent=2))

    return 0 if all_pass else 1

if __name__ == '__main__':
    sys.exit(main())
