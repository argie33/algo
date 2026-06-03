#!/usr/bin/env python3
"""Run full pipeline test: deploy, load signals, score, and orchestrate."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import logging
from datetime import date
from utils.database_context import DatabaseContext

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def run_pipeline_test():
    """Run the full pipeline test."""
    try:
        # Step 1: Run buy_sell_daily for today
        logger.info("[1/5] Running buy_sell_daily loader for today...")
        import subprocess
        result = subprocess.run(
            ["python", "loaders/load_buy_sell_daily.py"],
            capture_output=True,
            text=True,
            timeout=300
        )
        if result.returncode != 0:
            logger.error(f"buy_sell_daily failed: {result.stderr}")
            return 1

        # Step 2: Check how many signals were generated today
        logger.info("[2/5] Checking signals for 2026-06-03...")
        with DatabaseContext('read') as cur:
            cur.execute(
                "SELECT COUNT(*) FROM buy_sell_daily WHERE date = %s AND signal IN ('BUY', 'SELL')",
                (date(2026, 6, 3),)
            )
            signal_count = cur.fetchone()[0]
            logger.info(f"  Total signals generated today: {signal_count}")

            # Show sample signals
            cur.execute(
                "SELECT symbol, signal, buylevel, strength FROM buy_sell_daily WHERE date = %s AND signal = 'BUY' LIMIT 5",
                (date(2026, 6, 3),)
            )
            buy_signals = cur.fetchall()
            logger.info(f"  Sample BUY signals: {len(buy_signals)}")
            for row in buy_signals[:3]:
                logger.info(f"    {row[0]}: ${row[2]:.2f} (strength={row[3]:.2f})")

        # Step 3: Run signal_quality_scores
        logger.info("[3/5] Running signal_quality_scores loader...")
        result = subprocess.run(
            ["python", "loaders/load_signal_quality_scores.py"],
            capture_output=True,
            text=True,
            timeout=300
        )
        if result.returncode != 0:
            logger.warning(f"signal_quality_scores had issues: {result.stderr[:200]}")

        # Step 4: Run swing_trader_scores
        logger.info("[4/5] Running swing_trader_scores loader...")
        result = subprocess.run(
            ["python", "loaders/load_swing_trader_scores.py"],
            capture_output=True,
            text=True,
            timeout=300
        )
        if result.returncode != 0:
            logger.warning(f"swing_trader_scores had issues: {result.stderr[:200]}")

        # Step 5: Check orchestrator Phase 5
        logger.info("[5/5] Running orchestrator Phase 5...")
        result = subprocess.run(
            ["python", "algo/algo_orchestrator.py", "--phase", "5", "--date", "2026-06-03"],
            capture_output=True,
            text=True,
            timeout=600
        )
        logger.info(f"Orchestrator output: {result.stdout[:500]}")
        if result.returncode != 0:
            logger.warning(f"Orchestrator had issues: {result.stderr[:300]}")

        # Check final trade count
        with DatabaseContext('read') as cur:
            cur.execute(
                "SELECT COUNT(*) FROM swing_trades WHERE entry_date = %s",
                (date(2026, 6, 3),)
            )
            trade_count = cur.fetchone()[0]
            logger.info(f"\n✓ Total trades qualified for entry on 2026-06-03: {trade_count}")

            if trade_count > 0:
                cur.execute(
                    "SELECT symbol, entry_level, stop_loss FROM swing_trades WHERE entry_date = %s LIMIT 5",
                    (date(2026, 6, 3),)
                )
                trades = cur.fetchall()
                logger.info(f"  Sample trades: {len(trades)}")
                for row in trades[:3]:
                    logger.info(f"    {row[0]}: Entry=${row[1]:.2f}, Stop=${row[2]:.2f}")

        return 0

    except Exception as e:
        logger.error(f"Pipeline test failed: {e}", exc_info=True)
        return 1

if __name__ == "__main__":
    sys.exit(run_pipeline_test())
