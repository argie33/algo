#!/usr/bin/env python3
"""
Run orchestrator and analyze all phases for issues.
Focus on understanding the deadlock and position limit problems.
"""
import subprocess
import sys
import logging
from datetime import datetime
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

def run_orchestrator():
    """Run the orchestrator and capture output."""
    logger.info("="*80)
    logger.info("RUNNING ORCHESTRATOR (AFTERNOON MODE, FRESH RUN)")
    logger.info("="*80)

    log_file = Path(f"orch_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")

    cmd = ["python", "start_dashboard_dev.py"]
    # Actually, let's use the test orchestrator script
    cmd = ["python", "scripts/run_local_orchestrator.py", "--afternoon", "--force"]

    try:
        result = subprocess.run(cmd, capture_output=False, text=True, timeout=300)
        logger.info(f"Orchestrator exit code: {result.returncode}")
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        logger.error("Orchestrator timed out after 5 minutes")
        return False
    except Exception as e:
        logger.error(f"Failed to run orchestrator: {e}")
        return False

def check_database_state():
    """Check the current state of positions and trades."""
    logger.info("\n" + "="*80)
    logger.info("DATABASE STATE CHECK")
    logger.info("="*80)

    try:
        import psycopg2
        from pathlib import Path
        import os
        from dotenv import load_dotenv

        env_file = Path('.env.local')
        if env_file.exists():
            load_dotenv(env_file)

        conn = psycopg2.connect(os.environ.get('DATABASE_URL', 'postgresql://postgres:postgres@localhost/algo'))

        with conn.cursor() as cur:
            # Check position count
            cur.execute("SELECT COUNT(*) FROM algo_positions WHERE status = 'open'")
            open_pos = cur.fetchone()[0]

            # Check if we can exit today
            cur.execute("""
                SELECT COUNT(*) FROM algo_positions
                WHERE status = 'open'
                AND DATE(entry_date) = CURRENT_DATE
            """)
            today_pos = cur.fetchone()[0]

            # Check min_hold_days config
            cur.execute("SELECT value FROM algo_config WHERE key = 'min_hold_days'")
            min_hold_result = cur.fetchone()
            min_hold = min_hold_result[0] if min_hold_result else "NOT SET (default=1)"

            logger.info(f"Open positions: {open_pos}")
            logger.info(f"Positions entered today: {today_pos}")
            logger.info(f"min_hold_days config: {min_hold}")

            if today_pos > 0 and today_pos == open_pos:
                logger.warning(f"WARNING: ALL {open_pos} open positions entered today -> DEADLOCK RISK")
                logger.warning(f"  Exit engine will skip these due to min_hold_days={min_hold}")
                logger.warning(f"  Phase 8 will be blocked from entering new positions")

        conn.close()

    except Exception as e:
        logger.error(f"Database check failed: {e}")

if __name__ == "__main__":
    check_database_state()
    success = run_orchestrator()
    check_database_state()

    if not success:
        logger.error("\nOrchestrator run failed")
        sys.exit(1)
