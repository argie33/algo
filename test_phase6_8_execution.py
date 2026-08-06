#!/usr/bin/env python3
"""Test Phase 6 & 8 REAL execution during market hours simulation.

Objective: Find actual bugs in exit/entry execution that escape dry-run mode.
"""

import os
import sys
os.environ.setdefault('LOCAL_MODE', 'true')
os.environ.setdefault('ENVIRONMENT', 'development')

from utils.dotenv_loader import load_env_local
load_env_local()

from datetime import date as _date
import logging

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

from algo.infrastructure.config.main import AlgoConfig
from algo.orchestration.orchestrator import AlgoOrchestrator
from algo.reporting import AlertManager
from utils.db.context import DatabaseContext

# CRITICAL: Test with dry_run=False (REAL execution mode)
config = AlgoConfig()
alerts = AlertManager()
run_date = _date.today()

logger.info("=" * 80)
logger.info("PHASE 6 & 8 REAL EXECUTION TEST (DRY_RUN=FALSE)")
logger.info("=" * 80)

# Create orchestrator with dry_run=FALSE to test real execution logic
orchestrator = AlgoOrchestrator(
    config=config,
    alerts=alerts,
    run_date=run_date,
    verbose=True,
    dry_run=False,  # REAL mode
    run_type="evening",  # Standard evening run
)

logger.info(f"\n[Setup] Orchestrator created with dry_run=False")
logger.info(f"  Config: execution_mode={config.get('execution_mode')}")
logger.info(f"  Config: alpaca_paper_trading={config.get('alpaca_paper_trading')}")

# Check open positions before execution
logger.info(f"\n[Check] Open positions before execution:")
with DatabaseContext("read") as cur:
    cur.execute("SELECT id, symbol, quantity, entry_price, stop_loss FROM algo_positions WHERE status='open'")
    positions = cur.fetchall()
    for pos in positions:
        logger.info(f"  - {pos[1]}: {pos[2]} shares @ ${pos[3]} (stop ${pos[4]})")

    if not positions:
        logger.info("  (No open positions)")
        position_count = 0
    else:
        position_count = len(positions)

# Run orchestrator
logger.info(f"\n[Exec] Running orchestrator with DRY_RUN=FALSE...")
try:
    result = orchestrator.run()
    logger.info(f"\n[Result] Orchestrator completed: {result}")
except Exception as e:
    logger.error(f"[ERROR] Orchestrator failed: {e}")
    import traceback
    traceback.print_exc()

# Detailed Phase 6 check - should show actual exit logic
logger.info(f"\n[Phase 6 Check] Exit execution details:")
with DatabaseContext("read") as cur:
    cur.execute("""
        SELECT COUNT(*) as exit_count FROM algo_trades
        WHERE type='EXIT' AND status='filled' AND created_at::date = %s
    """, (run_date,))
    exits = cur.fetchone()[0] if cur.fetchone() else 0
    logger.info(f"  Exits executed today: {exits}")

    cur.execute("""
        SELECT COUNT(*) as sr_count FROM algo_trades
        WHERE type='STOP_RAISE' AND status='filled' AND created_at::date = %s
    """, (run_date,))
    stop_raises = cur.fetchone()[0] if cur.fetchone() else 0
    logger.info(f"  Stop-raises executed today: {stop_raises}")

# Detailed Phase 8 check - should show entry logic
logger.info(f"\n[Phase 8 Check] Entry execution details:")
with DatabaseContext("read") as cur:
    cur.execute("""
        SELECT COUNT(*) as entry_count FROM algo_trades
        WHERE type='ENTRY' AND status IN ('filled', 'open') AND created_at::date = %s
    """, (run_date,))
    entries = cur.fetchone()[0] if cur.fetchone() else 0
    logger.info(f"  Entries executed today: {entries}")

    # Check for execution errors in trades
    cur.execute("""
        SELECT COUNT(*) as error_count FROM algo_trades
        WHERE error_message IS NOT NULL AND created_at::date = %s
    """, (run_date,))
    errors = cur.fetchone()[0] if cur.fetchone() else 0
    logger.info(f"  Trades with errors: {errors}")

    if errors > 0:
        cur.execute("""
            SELECT symbol, type, error_message FROM algo_trades
            WHERE error_message IS NOT NULL AND created_at::date = %s
            LIMIT 10
        """, (run_date,))
        for trade in cur.fetchall():
            logger.info(f"    - {trade[0]} ({trade[1]}): {trade[2]}")

# Final status
logger.info(f"\n[Summary]")
logger.info(f"  Positions at start: {position_count}")
logger.info(f"  Exits executed: {exits}")
logger.info(f"  Stop-raises: {stop_raises}")
logger.info(f"  Entries executed: {entries}")
logger.info(f"  Execution errors: {errors}")

logger.info("\n" + "=" * 80)
if errors > 0:
    logger.error(f"EXECUTION ERRORS FOUND: {errors} trades have errors - investigate above")
    sys.exit(1)
else:
    logger.info("SUCCESS: No execution errors detected")
    sys.exit(0)
