#!/usr/bin/env python3
import os
import sys
import logging
from datetime import date as _date

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s:%(name)s:%(message)s'
)

# Set environment before any imports
os.environ['LOCAL_MODE'] = 'true'
os.environ['ENVIRONMENT'] = 'development'
os.environ['ALPACA_PAPER_TRADING'] = 'true'
os.environ['LOG_LEVEL'] = 'INFO'
os.environ['ALLOW_OUTSIDE_MARKET_HOURS'] = 'true'  # Allow testing outside market hours

# Load credentials
from scripts.load_credentials import ensure_credentials_loaded
ensure_credentials_loaded()

# Run the orchestrator on Tuesday 8/12
from algo.infrastructure.config import get_config
from algo.orchestration.orchestrator import Orchestrator

try:
    config = get_config()
    config.set("execution_mode", "paper", "string")

    print("\n" + "="*70)
    print("RUNNING ORCHESTRATOR ON 2026-08-12 (TUESDAY - TRADING DAY)")
    print("="*70 + "\n")

    # Run on a simulated trading day
    orch = Orchestrator(
        config=config,
        run_id='LOCAL-TEST-20260812-FULLRUN',
        dry_run=False,  # Allow real (paper) orders
        run_date=_date.fromisoformat('2026-08-12'),  # Tuesday, trading day
    )
    result = orch.run()

    print("\n" + "="*70)
    print(f"ORCHESTRATOR EXECUTION COMPLETE")
    if isinstance(result, dict):
        print(f"Result: {result}")
    else:
        print(f"Result type: {type(result)}")
        print(f"Result: {result}")
    print("="*70)

except Exception as e:
    print(f"ORCHESTRATOR FAILED: {e}", file=sys.stderr)
    import traceback
    traceback.print_exc()
    sys.exit(1)
