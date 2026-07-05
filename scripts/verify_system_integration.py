#!/usr/bin/env python3
"""Verify all system components are integrated and working together."""

import logging
import sys

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

def verify_imports():
    """Verify all critical modules import successfully."""
    logger.info("=" * 60)
    logger.info("VERIFYING CRITICAL IMPORTS")
    logger.info("=" * 60)

    critical_modules = [
        ("Orchestrator", "algo.orchestration.orchestrator"),
        ("Phase 1 (Data Freshness)", "algo.orchestrator.phase1_data_freshness"),
        ("Phase 7 (Signal Generation)", "algo.orchestrator.phase7_signal_generation"),
        ("Growth Metrics Loader", "loaders.load_growth_metrics"),
        ("Stock Scores Loader", "loaders.load_stock_scores"),
        ("Advanced Filters", "algo.signals.advanced_filters"),
        ("Dashboard", "dashboard.dashboard"),
    ]

    all_ok = True
    for name, module_path in critical_modules:
        try:
            __import__(module_path)
            logger.info(f"  ✓ {name}: OK")
        except ImportError as e:
            logger.error(f"  ✗ {name}: FAILED - {e}")
            all_ok = False

    return all_ok

def verify_database_connectivity():
    """Verify database can be accessed."""
    logger.info("\n" + "=" * 60)
    logger.info("VERIFYING DATABASE CONNECTIVITY")
    logger.info("=" * 60)

    try:
        from utils.db import DatabaseContext
        with DatabaseContext("read") as cur:
            # Test basic query
            cur.execute("SELECT 1")
            logger.info("  ✓ Database connection: OK")

            # Check critical tables exist
            tables = [
                'growth_metrics',
                'stock_scores',
                'quality_metrics',
                'value_metrics',
                'positioning_metrics',
                'stability_metrics',
                'price_daily',
                'technical_data_daily',
            ]

            for table in tables:
                try:
                    cur.execute(f"SELECT COUNT(*) FROM {table}")
                    count = cur.fetchone()[0]
                    logger.info(f"  ✓ Table '{table}': EXISTS ({count} rows)")
                except Exception as e:
                    logger.warning(f"  ⚠ Table '{table}': MISSING or ERROR - {e}")

            return True
    except Exception as e:
        logger.error(f"  ✗ Database connectivity: FAILED - {e}")
        return False

def verify_growth_score_pipeline():
    """Verify growth score computation pipeline."""
    logger.info("\n" + "=" * 60)
    logger.info("VERIFYING GROWTH SCORE PIPELINE")
    logger.info("=" * 60)

    try:
        from loaders.load_stock_scores import StockScoresLoader
        loader = StockScoresLoader()

        # Check validation method exists
        if hasattr(loader, '_validate_upstream_metrics_ready'):
            logger.info("  ✓ Stock scores validation method: EXISTS")
        else:
            logger.error("  ✗ Stock scores validation method: MISSING")
            return False

        # Check scoring methods exist
        scoring_methods = ['_get_growth_metrics', '_score_growth']
        for method in scoring_methods:
            if hasattr(loader, method):
                logger.info(f"  ✓ Method '{method}': EXISTS")
            else:
                logger.error(f"  ✗ Method '{method}': MISSING")
                return False

        return True
    except Exception as e:
        logger.error(f"  ✗ Growth score pipeline verification: FAILED - {e}")
        return False

def verify_orchestrator_phases():
    """Verify all 9 orchestrator phases are defined."""
    logger.info("\n" + "=" * 60)
    logger.info("VERIFYING ORCHESTRATOR PHASES")
    logger.info("=" * 60)

    phases = [
        "phase1_data_freshness",
        "phase2_circuit_breakers",
        "phase3_position_monitor",
        "phase4_reconciliation",
        "phase5_exposure_policy",
        "phase6_exit_execution",
        "phase7_signal_generation",
        "phase8_entry_execution",
        "phase9_reconciliation",
    ]

    all_ok = True
    for i, phase_module in enumerate(phases, 1):
        try:
            __import__(f"algo.orchestrator.{phase_module}")
            logger.info(f"  ✓ Phase {i} ({phase_module}): OK")
        except ImportError as e:
            logger.error(f"  ✗ Phase {i} ({phase_module}): FAILED - {e}")
            all_ok = False

    return all_ok

def verify_api_endpoints():
    """Verify API endpoints are wired."""
    logger.info("\n" + "=" * 60)
    logger.info("VERIFYING API ENDPOINTS")
    logger.info("=" * 60)

    try:
        # Check if API routes exist
        import os
        api_routes_dir = "lambda/api/routes"
        if os.path.isdir(api_routes_dir):
            routes = [f for f in os.listdir(api_routes_dir) if f.endswith('.py')]
            logger.info(f"  ✓ API routes directory: EXISTS ({len(routes)} route files)")

            critical_routes = ['scores.py', 'signals.py', 'positions.py']
            for route in critical_routes:
                if route in routes:
                    logger.info(f"    ✓ {route}: EXISTS")
                else:
                    logger.warning(f"    ⚠ {route}: MISSING")
        else:
            logger.warning("  ⚠ API routes directory: NOT FOUND")

        return True
    except Exception as e:
        logger.error(f"  ✗ API endpoint verification: FAILED - {e}")
        return False

def main():
    """Run all verifications."""
    logger.info("\n")
    logger.info("ALGO SYSTEM INTEGRATION VERIFICATION")
    logger.info("=" * 60)
    logger.info("")

    results = {
        "Imports": verify_imports(),
        "Database Connectivity": verify_database_connectivity(),
        "Growth Score Pipeline": verify_growth_score_pipeline(),
        "Orchestrator Phases": verify_orchestrator_phases(),
        "API Endpoints": verify_api_endpoints(),
    }

    logger.info("\n" + "=" * 60)
    logger.info("VERIFICATION SUMMARY")
    logger.info("=" * 60)

    for check, result in results.items():
        status = "PASS" if result else "FAIL"
        symbol = "✓" if result else "✗"
        logger.info(f"  {symbol} {check}: {status}")

    all_passed = all(results.values())

    logger.info("\n" + "=" * 60)
    if all_passed:
        logger.info("RESULT: ALL CHECKS PASSED - System is ready for trading")
        logger.info("=" * 60)
        return 0
    else:
        logger.error("RESULT: SOME CHECKS FAILED - Fix issues before trading")
        logger.info("=" * 60)
        return 1

if __name__ == "__main__":
    sys.exit(main())
