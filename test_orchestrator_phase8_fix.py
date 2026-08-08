#!/usr/bin/env python3
import os
import sys
import logging
from datetime import date as _date

logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(name)s:%(message)s')

os.environ['LOCAL_MODE'] = 'true'
os.environ['ENVIRONMENT'] = 'development'
os.environ['ALPACA_PAPER_TRADING'] = 'true'
os.environ['LOG_LEVEL'] = 'INFO'
os.environ['ALLOW_OUTSIDE_MARKET_HOURS'] = 'true'

from scripts.load_credentials import ensure_credentials_loaded
ensure_credentials_loaded()

from algo.infrastructure.config import get_config
from algo.orchestration.orchestrator import Orchestrator

try:
    config = get_config()
    config.set("execution_mode", "paper", "string")

    print("\n" + "="*70)
    print("RUNNING ORCHESTRATOR ON 2026-08-07 (FRIDAY - DATA EXISTS)")
    print("Testing Phase 8 Entry Execution Fix")
    print("="*70 + "\n")

    # Run on a date with data available
    orch = Orchestrator(
        config=config,
        run_id='LOCAL-TEST-PHASE8-FIX',
        dry_run=False,
        run_date=_date.fromisoformat('2026-08-07'),
    )
    result = orch.run()

    print("\n" + "="*70)
    print(f"ORCHESTRATOR EXECUTION COMPLETE")
    if isinstance(result, dict):
        # Check Phase 8 result
        phases = result.get('phases', [])
        for phase in phases:
            if phase.get('phase') == 8:
                print(f"Phase 8 Status: {phase.get('status')}")
                print(f"Phase 8 Summary: {phase.get('summary')}")
                if phase.get('status') == 'error':
                    print("ERROR: Phase 8 still failing!")
                    sys.exit(1)
        print(f"Overall Result: {'SUCCESS' if result.get('success') else 'PARTIAL'}")
    else:
        print(f"Result type: {type(result)}")
    print("="*70)

except Exception as e:
    print(f"ORCHESTRATOR FAILED: {e}", file=sys.stderr)
    import traceback
    traceback.print_exc()
    sys.exit(1)
