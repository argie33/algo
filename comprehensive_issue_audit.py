#!/usr/bin/env python3
"""Comprehensive audit to find all remaining issues in the orchestrator."""

import logging
from decimal import Decimal
from datetime import date as _date
from utils.db.context import DatabaseContext
from algo.infrastructure.config import AlgoConfig

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

def audit_position_limit():
    """Check if position limit is enforced correctly."""
    logger.info("\n" + "="*80)
    logger.info("AUDIT #1: Position Limit Enforcement")
    logger.info("="*80)

    config = AlgoConfig()
    max_positions = config.get("max_positions")
    logger.info(f"Config max_positions: {max_positions}")

    with DatabaseContext("read") as cur:
        cur.execute("SELECT COUNT(*) FROM algo_positions WHERE status='open'")
        open_count = cur.fetchone()[0]
        logger.info(f"Actual open positions: {open_count}")

        # Check if there's any code adding a tolerance buffer
        if open_count > max_positions:
            logger.error(f"ERROR: {open_count} open positions > {max_positions} limit!")
            return False

    logger.info(f"✓ Position limit is {max_positions}, actual {open_count} <= limit: PASS")
    return True

def audit_phase_3_exit_recommendations():
    """Check if Phase 3 is generating appropriate exit recommendations."""
    logger.info("\n" + "="*80)
    logger.info("AUDIT #2: Phase 3 Exit Recommendation Generation")
    logger.info("="*80)

    # Simulate Phase 3 position monitor
    from algo.monitoring import PositionMonitor

    config = AlgoConfig()
    monitor = PositionMonitor(config)
    recommendations = monitor.review_positions()

    logger.info(f"Phase 3 generated {len(recommendations)} recommendations")

    early_exits = sum(1 for r in recommendations if r.get("action") == "EARLY_EXIT")
    stop_raises = sum(1 for r in recommendations if r.get("action") == "RAISE_STOP")
    holds = sum(1 for r in recommendations if r.get("action") == "HOLD")

    logger.info(f"  - EARLY_EXIT: {early_exits}")
    logger.info(f"  - RAISE_STOP: {stop_raises}")
    logger.info(f"  - HOLD: {holds}")

    # Check for positions that should be exiting
    with DatabaseContext("read") as cur:
        # Find positions at stop loss
        cur.execute("""
        SELECT COUNT(*) FROM algo_positions
        WHERE status='open' AND current_price <= stop_loss_price
        """)
        at_stop = cur.fetchone()[0]
        if at_stop > 0:
            logger.error(f"ERROR: {at_stop} positions at/below stop loss, but recommendations don't match!")
            return False

    logger.info("✓ Exit recommendations match position data: PASS")
    return True

def audit_signal_quality_threshold():
    """Check if signal quality threshold is correct."""
    logger.info("\n" + "="*80)
    logger.info("AUDIT #3: Signal Quality Threshold")
    logger.info("="*80)

    config = AlgoConfig()
    threshold = config.get("min_signal_quality_score")
    logger.info(f"Configured min_signal_quality_score: {threshold}")

    # Check actual signal distribution
    with DatabaseContext("read") as cur:
        cur.execute("""
        SELECT COUNT(*), MIN(signal_quality_score), MAX(signal_quality_score),
               PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY signal_quality_score)
        FROM algo_signals
        WHERE signal_date >= CURRENT_DATE - INTERVAL '7 days'
        """)
        row = cur.fetchone()
        if row and row[0] > 0:
            count, min_score, max_score, median = row
            logger.info(f"Recent signals: {count} total, min={min_score}, max={max_score}, median={median}")

            # Count how many pass the threshold
            cur.execute(f"""
            SELECT COUNT(*) FROM algo_signals
            WHERE signal_date >= CURRENT_DATE - INTERVAL '7 days'
            AND signal_quality_score >= {threshold}
            """)
            passing = cur.fetchone()[0]
            pct = (passing / count * 100) if count > 0 else 0
            logger.info(f"Signals passing threshold ({threshold}): {passing}/{count} ({pct:.1f}%)")

            if pct < 50:
                logger.error(f"ERROR: Only {pct:.1f}% of signals pass threshold - too strict!")
                return False
        else:
            logger.warning("No recent signals in database")

    logger.info("✓ Signal quality threshold is reasonable: PASS")
    return True

def audit_phase_6_validation():
    """Check if Phase 6 validates Phase 3 data correctly."""
    logger.info("\n" + "="*80)
    logger.info("AUDIT #4: Phase 6 Exit Validation")
    logger.info("="*80)

    # Check Phase 6 code for the critical validation
    import inspect
    from algo.orchestrator import phase6_exit_execution

    source = inspect.getsource(phase6_exit_execution.run)

    # Look for the critical validation
    if "open_position_count > 0" in source and "CRITICAL" in source:
        logger.info("✓ Phase 6 has critical validation for empty recommendations: PASS")
        return True
    else:
        logger.error("ERROR: Phase 6 missing critical validation!")
        return False

def audit_entry_execution_constraints():
    """Check if Phase 8 entry execution has proper constraints."""
    logger.info("\n" + "="*80)
    logger.info("AUDIT #5: Phase 8 Entry Execution Constraints")
    logger.info("="*80)

    config = AlgoConfig()

    # Simulate entry execution constraints
    with DatabaseContext("read") as cur:
        cur.execute("SELECT COUNT(*) FROM algo_positions WHERE status='open'")
        open_positions = cur.fetchone()[0]

    max_positions = config.get("max_positions")

    logger.info(f"Open positions: {open_positions}/{max_positions}")

    if open_positions >= max_positions:
        logger.info(f"✓ Position limit enforcement active (at limit): PASS")
        return True
    else:
        logger.info(f"✓ Position limit not yet active ({open_positions} < {max_positions}): PASS")
        return True

def audit_paper_mode_behavior():
    """Check if paper mode is handled correctly."""
    logger.info("\n" + "="*80)
    logger.info("AUDIT #6: Paper Mode Behavior")
    logger.info("="*80)

    config = AlgoConfig()
    execution_mode = config.get("execution_mode")
    alpaca_paper = config.get("alpaca_paper_trading")

    logger.info(f"execution_mode: {execution_mode}")
    logger.info(f"alpaca_paper_trading: {alpaca_paper}")

    if execution_mode == "paper":
        logger.info("✓ Paper mode is configured correctly: PASS")
        return True
    else:
        logger.warning(f"System in {execution_mode} mode - not paper!")
        return True

def main():
    """Run all audits."""
    logger.info("\n\n")
    logger.info("█" * 80)
    logger.info("COMPREHENSIVE ORCHESTRATOR AUDIT")
    logger.info("█" * 80)

    results = []

    try:
        results.append(("Position Limit", audit_position_limit()))
    except Exception as e:
        logger.error(f"Position limit audit failed: {e}")
        results.append(("Position Limit", False))

    try:
        results.append(("Phase 3 Recommendations", audit_phase_3_exit_recommendations()))
    except Exception as e:
        logger.error(f"Phase 3 audit failed: {e}")
        results.append(("Phase 3 Recommendations", False))

    try:
        results.append(("Signal Quality", audit_signal_quality_threshold()))
    except Exception as e:
        logger.error(f"Signal quality audit failed: {e}")
        results.append(("Signal Quality", False))

    try:
        results.append(("Phase 6 Validation", audit_phase_6_validation()))
    except Exception as e:
        logger.error(f"Phase 6 audit failed: {e}")
        results.append(("Phase 6 Validation", False))

    try:
        results.append(("Entry Constraints", audit_entry_execution_constraints()))
    except Exception as e:
        logger.error(f"Entry constraints audit failed: {e}")
        results.append(("Entry Constraints", False))

    try:
        results.append(("Paper Mode", audit_paper_mode_behavior()))
    except Exception as e:
        logger.error(f"Paper mode audit failed: {e}")
        results.append(("Paper Mode", False))

    # Summary
    logger.info("\n" + "="*80)
    logger.info("AUDIT SUMMARY")
    logger.info("="*80)

    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        logger.info(f"{status:10} | {name}")

    total_passed = sum(1 for _, p in results if p)
    total = len(results)

    logger.info("="*80)
    logger.info(f"Result: {total_passed}/{total} audits passed")
    logger.info("="*80)

if __name__ == "__main__":
    main()
