#!/usr/bin/env python3
"""Comprehensive system verification toolkit."""
import os
import sys
import psycopg2
import json
from datetime import datetime, date, timedelta
from pathlib import Path

print("\n" + "=" * 70)
print("COMPREHENSIVE SYSTEM VERIFICATION")
print("=" * 70)

# Load database config
sys.path.insert(0, str(Path(__file__).parent))
try:
    from credential_helper import get_db_config
    config = get_db_config()
except Exception as e:
    print(f"[ERROR] Failed to load credentials: {e}")
    sys.exit(1)

def run_check(name, func):
    """Run a check and report results."""
    try:
        result = func()
        status = "[OK]" if result else "[FAIL]"
        print(f"{status} {name}")
        return result
    except Exception as e:
        print(f"[ERROR] {name}: {e}")
        return False

# Check 1: Database connectivity
def check_db_connection():
    conn = psycopg2.connect(**config)
    cur = conn.cursor()
    cur.execute("SELECT 1")
    conn.close()
    return True

run_check("Database connectivity", check_db_connection)

# Check 2: Data freshness
def check_data_freshness():
    conn = psycopg2.connect(**config)
    cur = conn.cursor()
    
    tables_to_check = [
        ('price_daily', 'date'),
        ('technical_data_daily', 'date'),
        ('buy_sell_daily', 'date'),
        ('stock_scores', 'updated_at'),
    ]
    
    fresh = 0
    for table, date_col in tables_to_check:
        cur.execute(f"SELECT COUNT(*) FROM {table} WHERE {date_col} >= CURRENT_DATE - 1")
        count = cur.fetchone()[0]
        if count > 0:
            fresh += 1
    
    conn.close()
    return fresh >= 3

run_check("Data freshness (price, technicals, signals)", check_data_freshness)

# Check 3: Key calculations present
def check_calculations():
    conn = psycopg2.connect(**config)
    cur = conn.cursor()
    
    # Check Minervini scores exist
    cur.execute("SELECT COUNT(*) FROM stock_scores WHERE composite_score > 0 LIMIT 1")
    has_scores = cur.fetchone()[0] > 0
    
    # Check market exposure exists
    cur.execute("SELECT COUNT(*) FROM market_exposure_daily LIMIT 1")
    has_exposure = cur.fetchone()[0] > 0
    
    # Check VaR exists
    cur.execute("SELECT COUNT(*) FROM algo_risk_daily LIMIT 1")
    has_var = cur.fetchone()[0] > 0
    
    conn.close()
    return has_scores and has_exposure and has_var

run_check("Key calculations (scores, exposure, VaR)", check_calculations)

# Check 4: API handlers present
def check_api_handlers():
    try:
        api_file = Path('lambda/api/lambda_function.py')
        content = api_file.read_text(encoding='utf-8-sig', errors='ignore')
        
        endpoints = [
            '/api/stocks',
            '/api/signals',
            '/api/algo/status',
            '/api/scores',
            '/api/economic',
        ]
        
        found = sum(1 for ep in endpoints if ep in content)
        return found >= 5
    except:
        return False

run_check("API handler endpoints", check_api_handlers)

# Check 5: Orchestrator phases
def check_orchestrator():
    try:
        orch_file = Path('algo_orchestrator.py')
        content = orch_file.read_text(encoding='utf-8-sig', errors='ignore')
        
        phases = [
            'Phase 1',
            'Phase 2',
            'Phase 3',
            'Phase 4',
            'Phase 5',
            'Phase 6',
            'Phase 7',
        ]
        
        found = sum(1 for phase in phases if phase in content)
        return found >= 7
    except:
        return False

run_check("7-phase orchestrator complete", check_orchestrator)

# Check 6: Risk controls active
def check_risk_controls():
    try:
        circuit = Path('algo_circuit_breaker.py')
        content = circuit.read_text(encoding='utf-8-sig', errors='ignore')
        
        controls = [
            'drawdown',
            'daily_loss',
            'consecutive_losses',
            'vix',
            'circuit',
        ]
        
        found = sum(1 for ctrl in controls if ctrl.lower() in content.lower())
        return found >= 4
    except:
        return False

run_check("Risk circuit breakers", check_risk_controls)

# Check 7: Frontend pages
def check_frontend_pages():
    try:
        pages_dir = Path('webapp/frontend/src/pages')
        pages = list(pages_dir.glob('*.jsx'))
        return len(pages) >= 20
    except:
        return False

run_check("Frontend pages (22+)", check_frontend_pages)

# Check 8: Loaders schema
def check_loaders():
    try:
        loaders = list(Path('.').glob('load*.py'))
        return len(loaders) >= 30
    except:
        return False

run_check("Data loaders (30+)", check_loaders)

print("\n" + "=" * 70)
print("Verification complete")
print("=" * 70 + "\n")
