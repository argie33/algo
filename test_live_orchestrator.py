#!/usr/bin/env python3
"""
Quick test to verify orchestrator initializes with live Alpaca config
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

os.environ['ORCHESTRATOR_EXECUTION_MODE'] = 'auto'
os.environ['ORCHESTRATOR_DRY_RUN'] = 'false'

from algo.algo_config import get_config
from algo.algo_orchestrator import Orchestrator
from datetime import date as _date

def test_orchestrator_init():
    """Test orchestrator initializes successfully with live config"""
    print("\n=== Testing Orchestrator Initialization ===")

    config = get_config()

    # Verify live trading config
    print(f"[OK] Config loaded")
    print(f"  - execution_mode: {config._config.get('execution_mode')}")
    print(f"  - orchestrator_dry_run: {config._config.get('orchestrator_dry_run')}")
    print(f"  - alpaca_paper_trading: {config._config.get('alpaca_paper_trading')}")
    print(f"  - alpaca_api_base_url: {config._config.get('alpaca_api_base_url')}")

    assert config._config.get('alpaca_paper_trading') == False, "[ERROR] Should be LIVE trading (paper_trading=false)"
    assert 'paper-api' not in config._config.get('alpaca_api_base_url', ''), "[ERROR] Should use LIVE API, not paper API"
    print(f"[OK] Live Alpaca trading enabled")

    # Try to initialize orchestrator in dry-run mode (no DB access required)
    try:
        print(f"\n[OK] Attempting to initialize Orchestrator (dry-run mode)...")
        orch = Orchestrator(config=config, run_date=_date.today(), dry_run=True, verbose=False)
        print(f"[OK] Orchestrator initialized successfully")
        print(f"  - run_id: {orch.run_id}")
        print(f"  - dry_run: {orch.dry_run}")
        print(f"  - execution_mode: {orch.config._config.get('execution_mode')}")
    except Exception as e:
        print(f"[ERROR] Failed to initialize orchestrator: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    test_orchestrator_init()
    print("\n[SUCCESS] All orchestrator initialization checks passed!")
