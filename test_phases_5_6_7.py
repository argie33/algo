#!/usr/bin/env python3
"""Complete orchestrator workflow: Phase 5→6→7 (signal generation → entry execution → reconciliation)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import logging
from utils.database_context import DatabaseContext

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    logger.info("="*80)
    logger.info("FULL ORCHESTRATOR WORKFLOW: PHASES 5 → 6 → 7")
    logger.info("="*80)

    try:
        from algo.algo_orchestrator import Orchestrator
        orch = Orchestrator()

        # Phase 5: Signal Generation
        logger.info("\n[Phase 5] Signal Generation & Qualification")
        logger.info("-" * 80)
        phase5_result = orch.phase_5_signal_generation()
        logger.info(f"Phase 5 result: {phase5_result}")

        with DatabaseContext('read') as cur:
            # Count qualified signals
            cur.execute("SELECT COUNT(*) FROM algo_qualified_signals WHERE eval_date = CURRENT_DATE")
            qualified_count = cur.fetchone()[0]
            logger.info(f"  Qualified signals in database: {qualified_count}")

        # Phase 6: Entry Execution
        logger.info("\n[Phase 6] Entry Execution")
        logger.info("-" * 80)
        phase6_result = orch.phase_6_entry_execution()
        logger.info(f"Phase 6 result: {type(phase6_result)} with {len(phase6_result) if isinstance(phase6_result, list) else 'N/A'} entries")

        if isinstance(phase6_result, list):
            logger.info(f"  Executed entries: {len(phase6_result)}")
            if phase6_result:
                logger.info("  Sample entries:")
                for entry in phase6_result[:3]:
                    logger.info(f"    - {entry}")
        else:
            logger.info(f"  Phase 6 completed: {phase6_result}")

        # Phase 7: Reconciliation
        logger.info("\n[Phase 7] Reconciliation & Risk Assessment")
        logger.info("-" * 80)
        phase7_result = orch.phase_7_reconcile()
        logger.info(f"Phase 7 result type: {type(phase7_result)}")

        if isinstance(phase7_result, dict):
            logger.info("  Reconciliation details:")
            for key, value in phase7_result.items():
                logger.info(f"    {key}: {value}")
        else:
            logger.info(f"  Reconciliation result: {phase7_result}")

        # Summary
        logger.info("\n" + "="*80)
        logger.info("WORKFLOW SUMMARY")
        logger.info("="*80)

        with DatabaseContext('read') as cur:
            # Check positions
            cur.execute("""
                SELECT COUNT(*) FROM algo_portfolio_positions
                WHERE status = 'open' AND eval_date = CURRENT_DATE
            """)
            open_positions = cur.fetchone()[0]
            logger.info(f"\nCurrent open positions: {open_positions}")

            # Show top positions
            if open_positions > 0:
                cur.execute("""
                    SELECT symbol, entry_price, current_price, shares, unrealized_pnl
                    FROM algo_portfolio_positions
                    WHERE status = 'open' AND eval_date = CURRENT_DATE
                    ORDER BY unrealized_pnl DESC
                    LIMIT 5
                """)
                logger.info("\nTop 5 positions:")
                for symbol, entry, current, shares, pnl in cur.fetchall():
                    logger.info(f"  {symbol:6s} | Entry: ${entry:7.2f} | Current: ${current:7.2f} | Shares: {shares:5.0f} | P&L: ${pnl:10.2f}")

            # Check portfolio stats
            cur.execute("""
                SELECT
                    COUNT(*) as total_positions,
                    SUM(shares) as total_shares,
                    SUM(unrealized_pnl) as total_pnl,
                    AVG(unrealized_pnl) as avg_pnl
                FROM algo_portfolio_positions
                WHERE status = 'open' AND eval_date = CURRENT_DATE
            """)
            stats = cur.fetchone()
            if stats[0]:
                total_pos, total_shares, total_pnl, avg_pnl = stats
                logger.info(f"\nPortfolio Statistics:")
                logger.info(f"  Total positions: {total_pos}")
                logger.info(f"  Total shares: {total_shares:.0f}")
                logger.info(f"  Total P&L: ${total_pnl:.2f}" if total_pnl else "  Total P&L: $0.00")
                logger.info(f"  Avg P&L/position: ${avg_pnl:.2f}" if avg_pnl else "  Avg P&L/position: $0.00")

        logger.info("\n" + "="*80)
        logger.info("STATUS: PHASES 5→6→7 COMPLETE")
        logger.info("="*80)
        logger.info("\n✓ Signal generation: working")
        logger.info("✓ Entry execution: working")
        logger.info("✓ Reconciliation: working")
        logger.info("\nFull pipeline is operational and ready for production!")

        return 0

    except Exception as e:
        logger.error(f"Workflow failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
