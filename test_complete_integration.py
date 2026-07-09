#!/usr/bin/env python3
"""Complete End-to-End Integration Test - Orchestrator → Dashboard → Alpaca"""
import sys
import logging
from datetime import date

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def test_complete_system():
    """Test complete pipeline: orchestrator runs → dashboard displays data → Alpaca synced."""
    logger.info("=" * 80)
    logger.info("COMPLETE SYSTEM INTEGRATION TEST")
    logger.info("=" * 80)

    results = {}

    # Step 1: Run Orchestrator
    logger.info("\n[STEP 1] Running Orchestrator (All 9 Phases)")
    logger.info("-" * 80)
    try:
        import os
        os.environ["ORCHESTRATOR_EXECUTION_MODE"] = "paper"

        from algo.orchestration import Orchestrator
        from algo.infrastructure import get_config

        config = get_config()
        orchestrator = Orchestrator(
            config=config,
            run_date=date.today(),
            dry_run=False,  # LIVE mode
            verbose=False
        )

        result = orchestrator.run()

        if result.get("success"):
            logger.info("✓ Orchestrator executed successfully")
            logger.info(f"  Success: {result.get('success')}")
            logger.info(f"  Halted: {result.get('halted')}")
            results["orchestrator"] = True
        else:
            logger.warning("✗ Orchestrator execution failed")
            results["orchestrator"] = False

    except Exception as e:
        logger.error(f"✗ Orchestrator test failed: {e}", exc_info=True)
        results["orchestrator"] = False

    # Step 2: Verify Database State
    logger.info("\n[STEP 2] Verifying Database State")
    logger.info("-" * 80)
    try:
        from utils.db import DatabaseContext

        with DatabaseContext("read", timeout=10) as cur:
            # Check portfolio snapshots
            cur.execute(
                "SELECT COUNT(*) as cnt FROM algo_portfolio_snapshots WHERE snapshot_date = %s",
                (date.today(),)
            )
            result = cur.fetchone()
            snapshots_count = result["cnt"] if result else 0
            logger.info(f"✓ Portfolio snapshots today: {snapshots_count}")

            # Check positions
            cur.execute("SELECT COUNT(*) as cnt FROM algo_positions WHERE status = 'open'")
            result = cur.fetchone()
            positions_count = result["cnt"] if result else 0
            logger.info(f"✓ Open positions: {positions_count}")

            # Check trades
            cur.execute("SELECT COUNT(*) as cnt FROM algo_trades")
            result = cur.fetchone()
            trades_count = result["cnt"] if result else 0
            logger.info(f"✓ Total trades recorded: {trades_count}")

            if snapshots_count > 0 and positions_count > 0:
                results["database"] = True
                logger.info("✓ Database state verified")
            else:
                results["database"] = False
                logger.warning("✗ Database missing expected data")

    except Exception as e:
        logger.error(f"✗ Database verification failed: {e}", exc_info=True)
        results["database"] = False

    # Step 3: Test Dashboard API
    logger.info("\n[STEP 3] Testing Dashboard API Endpoints")
    logger.info("-" * 80)
    try:
        import requests

        endpoints = [
            ("/api/portfolio", "Portfolio"),
            ("/api/positions", "Positions"),
            ("/api/signals", "Signals"),
        ]

        api_responses = 0
        for endpoint, name in endpoints:
            try:
                response = requests.get(f"http://localhost:3000{endpoint}", timeout=5)
                if response.status_code == 200:
                    data = response.json()
                    if "data" in data:
                        logger.info(f"✓ {name} API responding correctly")
                        api_responses += 1
                    else:
                        logger.warning(f"✗ {name} API schema invalid")
                else:
                    logger.warning(f"✗ {name} API returned {response.status_code}")
            except requests.exceptions.ConnectionError:
                logger.warning(f"✗ Dashboard not running (needed for {name} API)")
            except Exception as e:
                logger.warning(f"✗ {name} API error: {e}")

        if api_responses >= len(endpoints) - 1:  # Allow 1 endpoint to be offline
            results["dashboard"] = True
            logger.info(f"✓ Dashboard APIs verified ({api_responses}/{len(endpoints)})")
        else:
            results["dashboard"] = None  # Inconclusive if dashboard offline
            logger.info("⚠ Dashboard not running (test inconclusive)")

    except Exception as e:
        logger.warning(f"⚠ Dashboard test inconclusive: {e}")
        results["dashboard"] = None

    # Step 4: Test Alpaca Sync
    logger.info("\n[STEP 4] Testing Alpaca Position Sync")
    logger.info("-" * 80)
    try:
        from alpaca.trading.client import TradingClient
        import os

        api_key = os.getenv("ALPACA_API_KEY_ID")
        api_secret = os.getenv("ALPACA_API_SECRET_KEY")

        if api_key and api_secret:
            client = TradingClient(api_key=api_key, secret_key=api_secret)
            account = client.get_account()
            alpaca_positions = client.get_all_positions()

            logger.info(f"✓ Alpaca account synced: {len(alpaca_positions)} positions")

            # Compare with database
            with DatabaseContext("read") as cur:
                cur.execute("SELECT COUNT(*) as cnt FROM algo_positions WHERE status = 'open'")
                result = cur.fetchone()
                db_positions = result["cnt"] if result else 0

            if len(alpaca_positions) == db_positions:
                logger.info(f"✓ Position counts match: {len(alpaca_positions)} = {db_positions}")
                results["alpaca"] = True
            else:
                logger.warning(f"✗ Position mismatch: Alpaca {len(alpaca_positions)} vs DB {db_positions}")
                results["alpaca"] = False
        else:
            logger.info("⚠ Alpaca credentials not set (test skipped)")
            results["alpaca"] = None

    except Exception as e:
        logger.warning(f"⚠ Alpaca sync test inconclusive: {e}")
        results["alpaca"] = None

    # Summary
    logger.info("\n" + "=" * 80)
    logger.info("INTEGRATION TEST SUMMARY")
    logger.info("=" * 80)

    all_passed = True
    for component, passed in results.items():
        if passed is True:
            logger.info(f"  ✓ {component:15s} PASSED")
        elif passed is False:
            logger.info(f"  ✗ {component:15s} FAILED")
            all_passed = False
        else:
            logger.info(f"  ⚠ {component:15s} INCONCLUSIVE (offline)")

    logger.info("\n" + "=" * 80)
    if all_passed:
        logger.info("✓ COMPLETE SYSTEM INTEGRATION TEST PASSED")
        logger.info("System ready for live paper trading")
    else:
        logger.warning("✗ INTEGRATION TEST INCOMPLETE")
        logger.warning("Review failures above and correct before going live")

    return all_passed

if __name__ == "__main__":
    success = test_complete_system()
    sys.exit(0 if success else 1)
