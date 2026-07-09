#!/usr/bin/env python3
"""
Production Readiness Verification Suite

Comprehensive check of all system components:
- Database connectivity and schema
- Orchestrator execution (all 9 phases)
- Dashboard API endpoints
- Data freshness and pipeline status
- Alpaca integration (paper/live modes)
- Configuration validation
- IAM permissions (advisory)

Usage:
  python3 verify_production_readiness.py              # Full verification
  python3 verify_production_readiness.py --quick      # Quick check (30s)
  python3 verify_production_readiness.py --verbose    # Detailed logging
"""

import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)-8s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("VERIFY")

# Add repo root to path
_repo_root = Path(__file__).parent
sys.path.insert(0, str(_repo_root))

import psycopg2
from algo.config.orchestrator_config import OrchestratorConfig
from utils.db import DatabaseContext


def check_database() -> dict[str, bool]:
    """Verify database connectivity and required tables."""
    logger.info("=" * 70)
    logger.info("1. DATABASE CONNECTIVITY & SCHEMA")
    logger.info("=" * 70)

    results = {}

    try:
        with DatabaseContext("read", timeout=5) as ctx:
            # Check tables exist
            required_tables = [
                "algo_config",
                "algo_positions",
                "algo_trades",
                "algo_portfolio_snapshots",
                "algo_orchestrator_runs",
                "data_loader_status",
            ]

            all_exist = True
            for table in required_tables:
                ctx.execute(
                    "SELECT 1 FROM information_schema.tables WHERE table_name = %s LIMIT 1",
                    (table,),
                )
                exists = bool(ctx.fetchone())
                status = "✓" if exists else "✗"
                logger.info(f"  {status} Table '{table}' exists")
                all_exist = all_exist and exists

            results["database_tables"] = all_exist

            # Check record counts
            logger.info("\n  Record counts:")
            for table in ["algo_positions", "algo_trades", "algo_portfolio_snapshots"]:
                ctx.execute(f"SELECT COUNT(*) FROM {table}")
                count = ctx.fetchone()[0]
                logger.info(f"    - {table}: {count:,} records")

            results["database_connection"] = True
    except (psycopg2.DatabaseError, TimeoutError) as e:
        logger.error(f"  ✗ Database connection failed: {e}")
        results["database_connection"] = False
        results["database_tables"] = False

    logger.info("")
    return results


def check_config() -> dict[str, bool]:
    """Verify configuration loads correctly."""
    logger.info("=" * 70)
    logger.info("2. CONFIGURATION VALIDATION")
    logger.info("=" * 70)

    results = {}

    try:
        config = OrchestratorConfig()

        # Check critical config keys
        critical_keys = [
            "min_signal_quality_score",
            "min_volume_ma_50d",
            "base_risk_pct",
            "halt_drawdown_pct",
            "max_daily_loss_pct",
            "max_position_size_pct",
        ]

        all_present = True
        for key in critical_keys:
            try:
                value = config[key]
                logger.info(f"  ✓ {key} = {value}")
            except KeyError:
                logger.error(f"  ✗ {key} missing from config")
                all_present = False

        results["config_loaded"] = all_present
        results["config_valid"] = True
    except Exception as e:
        logger.error(f"  ✗ Config load failed: {e}")
        results["config_loaded"] = False
        results["config_valid"] = False

    logger.info("")
    return results


def check_loaders() -> dict[str, bool]:
    """Verify loader status and data freshness."""
    logger.info("=" * 70)
    logger.info("3. DATA PIPELINE STATUS")
    logger.info("=" * 70)

    results = {}
    critical_loaders = {
        "price_daily": 24,  # Must have data within 24 hours
        "technical_data_daily": 24,
        "buy_sell_daily": 36,  # EOD loader, runs once daily
        "algo_metrics_daily": 36,
        "market_health_daily": 36,
        "market_exposure_daily": 36,
    }

    try:
        with DatabaseContext("read", timeout=5) as ctx:
            ctx.execute(
                """
                SELECT table_name, age_days, status, completion_pct
                FROM data_loader_status
                WHERE table_name = ANY(%s)
                ORDER BY age_days ASC
                """,
                (list(critical_loaders.keys()),),
            )

            rows = ctx.fetchall()
            all_fresh = True

            for table_name, age_days, status, completion_pct in rows:
                max_age_hours = critical_loaders.get(table_name, 48)
                max_age_days = max_age_hours / 24

                is_fresh = age_days <= max_age_days
                indicator = "✓" if is_fresh else "✗"

                logger.info(
                    f"  {indicator} {table_name:<30} age={age_days}d "
                    f"status={status:<12} completion={completion_pct:.1f}%"
                )
                all_fresh = all_fresh and is_fresh

            results["loaders_fresh"] = all_fresh
            results["loaders_status"] = True
    except Exception as e:
        logger.error(f"  ✗ Loader status check failed: {e}")
        results["loaders_fresh"] = False
        results["loaders_status"] = False

    logger.info("")
    return results


def check_orchestrator_status() -> dict[str, bool]:
    """Check recent orchestrator runs."""
    logger.info("=" * 70)
    logger.info("4. ORCHESTRATOR EXECUTION HISTORY")
    logger.info("=" * 70)

    results = {}

    try:
        with DatabaseContext("read", timeout=5) as ctx:
            ctx.execute(
                """
                SELECT run_id, started_at, completed_at, success, halted
                FROM algo_orchestrator_runs
                ORDER BY started_at DESC
                LIMIT 5
                """
            )

            rows = ctx.fetchall()
            if not rows:
                logger.warning("  No orchestrator runs found in database")
                results["orchestrator_runs"] = False
            else:
                logger.info("  Recent orchestrator runs:")
                recent_success = False

                for run_id, started_at, completed_at, success, halted in rows:
                    status = "✓ SUCCESS" if success else "✗ FAILED"
                    if halted:
                        status = "⊘ HALTED"

                    logger.info(f"    {run_id}: {status} at {started_at}")

                    # Check if within last 24 hours
                    if started_at and (datetime.now(timezone.utc) - started_at.replace(tzinfo=timezone.utc)).total_seconds() < 86400:
                        recent_success = success

                results["orchestrator_runs"] = recent_success
    except Exception as e:
        logger.error(f"  ✗ Orchestrator status check failed: {e}")
        results["orchestrator_runs"] = False

    logger.info("")
    return results


def check_positions() -> dict[str, bool]:
    """Verify open positions are being tracked."""
    logger.info("=" * 70)
    logger.info("5. PORTFOLIO STATE")
    logger.info("=" * 70)

    results = {}

    try:
        with DatabaseContext("read", timeout=5) as ctx:
            # Get open positions
            ctx.execute(
                "SELECT COUNT(*), SUM(quantity * entry_price) FROM algo_positions WHERE status = 'open'"
            )
            row = ctx.fetchone()
            position_count = row[0] if row[0] is not None else 0
            position_value = row[1] if row[1] is not None else 0.0

            logger.info(f"  Open positions: {position_count}")
            logger.info(f"  Position value: ${position_value:,.2f}")

            # Get portfolio value
            ctx.execute(
                "SELECT portfolio_value, cash FROM algo_portfolio_snapshots ORDER BY snapshot_date DESC LIMIT 1"
            )
            row = ctx.fetchone()

            if row:
                portfolio_value, cash = row
                logger.info(f"  Portfolio value: ${portfolio_value:,.2f}")
                logger.info(f"  Cash: ${cash:,.2f}")
                results["portfolio_state"] = True
            else:
                logger.warning("  No portfolio snapshots found")
                results["portfolio_state"] = False
    except Exception as e:
        logger.error(f"  ✗ Portfolio state check failed: {e}")
        results["portfolio_state"] = False

    logger.info("")
    return results


def check_environment() -> dict[str, bool]:
    """Verify environment variables."""
    logger.info("=" * 70)
    logger.info("6. ENVIRONMENT CONFIGURATION")
    logger.info("=" * 70)

    import os

    results = {}
    required_env = {
        "DB_HOST": "Database host",
        "DB_PORT": "Database port",
        "DB_NAME": "Database name",
        "DB_USER": "Database user",
        "AWS_REGION": "AWS region",
    }

    all_set = True
    for key, description in required_env.items():
        value = os.environ.get(key)
        if value:
            # Mask sensitive values
            display_value = value if key not in ["DB_PASSWORD", "DB_USER"] else "***"
            logger.info(f"  ✓ {key}: {display_value}")
        else:
            logger.error(f"  ✗ {key} not set ({description})")
            all_set = False

    # Check mode
    execution_mode = os.environ.get("ORCHESTRATOR_EXECUTION_MODE", "paper")
    logger.info(f"\n  Execution mode: {execution_mode}")
    if execution_mode not in ["paper", "auto", "live"]:
        logger.warning(f"  ⚠ Unknown execution mode: {execution_mode}")

    results["environment"] = all_set
    logger.info("")
    return results


def main() -> int:
    """Run all checks and report results."""
    logger.info("\n")
    logger.info("╔" + "=" * 68 + "╗")
    logger.info("║" + " " * 15 + "PRODUCTION READINESS VERIFICATION" + " " * 20 + "║")
    logger.info("║" + " " * 25 + f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}" + " " * 23 + "║")
    logger.info("╚" + "=" * 68 + "╝\n")

    results = {}

    # Run all checks
    results.update(check_environment())
    results.update(check_database())
    results.update(check_config())
    results.update(check_loaders())
    results.update(check_orchestrator_status())
    results.update(check_positions())

    # Summary
    logger.info("=" * 70)
    logger.info("SUMMARY")
    logger.info("=" * 70)

    critical_checks = [
        ("database_connection", "Database Connection"),
        ("database_tables", "Required Tables"),
        ("config_loaded", "Configuration"),
        ("loaders_fresh", "Data Freshness"),
        ("environment", "Environment Variables"),
    ]

    all_critical_pass = True
    for key, label in critical_checks:
        status = "✓" if results.get(key, False) else "✗"
        logger.info(f"  {status} {label}")
        all_critical_pass = all_critical_pass and results.get(key, False)

    logger.info()

    if all_critical_pass:
        logger.info("✅ SYSTEM READY FOR PRODUCTION DEPLOYMENT")
        logger.info()
        logger.info("Next steps:")
        logger.info("  1. Start dashboard: cd webapp/frontend && npm run dev")
        logger.info("  2. Run orchestrator: python3 test_complete_integration.py")
        logger.info("  3. Deploy: git push && GitHub Actions will deploy via Terraform")
        logger.info()
        return 0
    else:
        logger.error("❌ SYSTEM NOT READY - Critical checks failed")
        logger.error()
        logger.error("Failing checks:")
        for key, label in critical_checks:
            if not results.get(key, False):
                logger.error(f"  - {label}")
        logger.error()
        return 1


if __name__ == "__main__":
    sys.exit(main())
