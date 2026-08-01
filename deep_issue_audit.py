#!/usr/bin/env python3
"""Deep audit to find hidden issues in orchestrator logic."""

import logging
from utils.db.context import DatabaseContext
from algo.infrastructure.config import AlgoConfig

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

def audit_sector_concentration():
    """Check for over-concentrated sectors."""
    logger.info("\n" + "="*80)
    logger.info("DEEP AUDIT #1: Sector Concentration Risk")
    logger.info("="*80)

    config = AlgoConfig()
    max_per_sector = config.get("max_positions_per_sector")
    logger.info(f"Config max_positions_per_sector: {max_per_sector}")

    with DatabaseContext("read") as cur:
        cur.execute("""
        SELECT cs.sector, COUNT(*) as count
        FROM algo_positions ap
        JOIN company_profile cs ON ap.symbol = cs.symbol
        WHERE ap.status='open'
        GROUP BY cs.sector
        ORDER BY count DESC
        """)
        sectors = cur.fetchall()

        print("\nSector distribution:")
        over_limit = 0
        for sector, count in sectors:
            status = "OVER LIMIT!" if count > max_per_sector else "OK"
            print(f"  {sector:30} | {count:2} positions | {status}")
            if count > max_per_sector:
                over_limit += count - max_per_sector

    if over_limit > 0:
        logger.error(f"ERROR: {over_limit} positions over sector limits need forced exit!")
        return False
    else:
        logger.info(f"✓ Sector concentration within limits: PASS")
        return True

def audit_portfolio_concentration():
    """Check portfolio concentration by position size."""
    logger.info("\n" + "="*80)
    logger.info("DEEP AUDIT #2: Portfolio Concentration by Size")
    logger.info("="*80)

    config = AlgoConfig()
    max_pct = config.get("max_position_size_pct")
    logger.info(f"Config max_position_size_pct: {max_pct}%")

    with DatabaseContext("read") as cur:
        # Get total portfolio value
        cur.execute("SELECT SUM(position_value) FROM algo_positions WHERE status='open'")
        total_value = cur.fetchone()[0] or 0

        if total_value == 0:
            logger.warning("No open positions or zero total value")
            return True

        # Find positions exceeding limit
        cur.execute(f"""
        SELECT symbol, position_value, (position_value / %s * 100) as pct_of_portfolio
        FROM algo_positions
        WHERE status='open'
        ORDER BY position_value DESC
        """, (total_value,))
        positions = cur.fetchall()

        print(f"\nPortfolio total: ${total_value:,.2f}")
        print("Position sizes (top 5):")
        violations = 0
        for symbol, value, pct in positions[:5]:
            status = "OVER LIMIT!" if pct > max_pct else "OK"
            print(f"  {symbol:8} | ${value:10,.2f} | {pct:5.1f}% | {status}")
            if pct > max_pct:
                violations += 1

    if violations > 0:
        logger.error(f"ERROR: {violations} positions exceed {max_pct}% portfolio limit!")
        return False
    else:
        logger.info(f"✓ Position sizes within concentration limits: PASS")
        return True

def audit_stop_loss_placement():
    """Check if stop losses are properly placed."""
    logger.info("\n" + "="*80)
    logger.info("DEEP AUDIT #3: Stop Loss Placement")
    logger.info("="*80)

    with DatabaseContext("read") as cur:
        # Check for negative stop losses or other invalid placements
        cur.execute("""
        SELECT COUNT(*) FROM algo_positions
        WHERE status='open' AND stop_loss_price <= 0
        """)
        invalid_stops = cur.fetchone()[0]

        if invalid_stops > 0:
            logger.error(f"ERROR: {invalid_stops} positions have invalid stop losses (<= 0)!")
            return False

        # Check for stops above entry price (inverted)
        cur.execute("""
        SELECT COUNT(*) FROM algo_positions
        WHERE status='open' AND stop_loss_price > avg_entry_price
        """)
        inverted_stops = cur.fetchone()[0]

        if inverted_stops > 0:
            logger.error(f"ERROR: {inverted_stops} positions have stop ABOVE entry (take profit not stop loss)!")
            return False

        # Check for positions where price is below stop (should have exited)
        cur.execute("""
        SELECT COUNT(*), string_agg(symbol, ', ')
        FROM algo_positions
        WHERE status='open' AND current_price < stop_loss_price
        """)
        row = cur.fetchone()
        at_stop = row[0] if row and row[0] else 0
        symbols = row[1] if row and row[1] else ""

        if at_stop > 0:
            logger.error(f"ERROR: {at_stop} positions below stop loss ({symbols}): should have exited!")
            return False

    logger.info("✓ Stop losses properly placed: PASS")
    return True

def audit_data_completeness():
    """Check for missing critical position data."""
    logger.info("\n" + "="*80)
    logger.info("DEEP AUDIT #4: Data Completeness")
    logger.info("="*80)

    with DatabaseContext("read") as cur:
        # Check for NULL values in critical fields
        critical_fields = [
            ('avg_entry_price', 'Entry price'),
            ('current_price', 'Current price'),
            ('stop_loss_price', 'Stop loss'),
            ('quantity', 'Quantity'),
            ('position_value', 'Position value'),
        ]

        all_complete = True
        for field, label in critical_fields:
            cur.execute(f"""
            SELECT COUNT(*) FROM algo_positions
            WHERE status='open' AND {field} IS NULL
            """)
            nulls = cur.fetchone()[0]
            if nulls > 0:
                logger.error(f"ERROR: {nulls} positions missing {label}!")
                all_complete = False
            else:
                logger.info(f"✓ {label}: all {label.lower()}s present")

    if all_complete:
        logger.info("✓ Data completeness check: PASS")
        return True
    else:
        return False

def audit_position_monitoring_readiness():
    """Check if positions are ready for Phase 3 monitoring."""
    logger.info("\n" + "="*80)
    logger.info("DEEP AUDIT #5: Position Monitoring Readiness")
    logger.info("="*80)

    config = AlgoConfig()

    with DatabaseContext("read") as cur:
        # Get open positions count
        cur.execute("SELECT COUNT(*) FROM algo_positions WHERE status='open'")
        pos_count = cur.fetchone()[0]

        # Try to call PositionMonitor to ensure it works
        try:
            from algo.monitoring import PositionMonitor
            monitor = PositionMonitor(config)
            recs = monitor.review_positions()

            if len(recs) != pos_count:
                logger.error(f"ERROR: Monitor returned {len(recs)} recommendations but {pos_count} positions exist!")
                return False

            logger.info(f"✓ PositionMonitor reviewed all {pos_count} positions successfully")
            return True
        except Exception as e:
            logger.error(f"ERROR: PositionMonitor failed: {e}")
            return False

def audit_phase_interdependencies():
    """Check if phase dependencies are correct."""
    logger.info("\n" + "="*80)
    logger.info("DEEP AUDIT #6: Phase Interdependencies")
    logger.info("="*80)

    config = AlgoConfig()

    # Phase 1 should always pass (data freshness)
    try:
        from algo.orchestrator import phase1_data_freshness
        logger.info("✓ Phase 1 (data freshness) import: OK")
    except Exception as e:
        logger.error(f"ERROR: Phase 1 import failed: {e}")
        return False

    # Phase 3 must have position data
    try:
        from algo.orchestrator import phase3_position_monitor
        logger.info("✓ Phase 3 (position monitor) import: OK")
    except Exception as e:
        logger.error(f"ERROR: Phase 3 import failed: {e}")
        return False

    # Phase 6 must validate Phase 3
    try:
        from algo.orchestrator import phase6_exit_execution
        import inspect
        source = inspect.getsource(phase6_exit_execution.run)
        if "position_recs" not in source:
            logger.error("ERROR: Phase 6 doesn't reference position_recs from Phase 3!")
            return False
        logger.info("✓ Phase 6 (exit execution) has Phase 3 dependency: OK")
    except Exception as e:
        logger.error(f"ERROR: Phase 6 check failed: {e}")
        return False

    # Phase 8 must respect position limit
    try:
        from algo.orchestrator import phase8_entry_execution
        import inspect
        source = inspect.getsource(phase8_entry_execution.run)
        if "max_positions" not in source and "position_limit" not in source.lower():
            logger.error("ERROR: Phase 8 doesn't check position limit!")
            return False
        logger.info("✓ Phase 8 (entry execution) checks position limit: OK")
    except Exception as e:
        logger.error(f"ERROR: Phase 8 check failed: {e}")
        return False

    logger.info("✓ Phase interdependencies correct: PASS")
    return True

def main():
    logger.info("\n\n")
    logger.info("█" * 80)
    logger.info("DEEP ORCHESTRATOR AUDIT")
    logger.info("█" * 80)

    results = []

    try:
        results.append(("Sector Concentration", audit_sector_concentration()))
    except Exception as e:
        logger.error(f"Sector audit failed: {e}")
        results.append(("Sector Concentration", False))

    try:
        results.append(("Portfolio Concentration", audit_portfolio_concentration()))
    except Exception as e:
        logger.error(f"Portfolio audit failed: {e}")
        results.append(("Portfolio Concentration", False))

    try:
        results.append(("Stop Loss Placement", audit_stop_loss_placement()))
    except Exception as e:
        logger.error(f"Stop loss audit failed: {e}")
        results.append(("Stop Loss Placement", False))

    try:
        results.append(("Data Completeness", audit_data_completeness()))
    except Exception as e:
        logger.error(f"Data completeness audit failed: {e}")
        results.append(("Data Completeness", False))

    try:
        results.append(("Monitoring Readiness", audit_position_monitoring_readiness()))
    except Exception as e:
        logger.error(f"Monitoring readiness audit failed: {e}")
        results.append(("Monitoring Readiness", False))

    try:
        results.append(("Phase Dependencies", audit_phase_interdependencies()))
    except Exception as e:
        logger.error(f"Phase dependencies audit failed: {e}")
        results.append(("Phase Dependencies", False))

    # Summary
    logger.info("\n" + "="*80)
    logger.info("DEEP AUDIT SUMMARY")
    logger.info("="*80)

    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        logger.info(f"{status:10} | {name}")

    total_passed = sum(1 for _, p in results if p)
    total = len(results)

    logger.info("="*80)
    logger.info(f"Result: {total_passed}/{total} deep audits passed")
    logger.info("="*80)

if __name__ == "__main__":
    main()
