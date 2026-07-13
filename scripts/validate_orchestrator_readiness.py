#!/usr/bin/env python3
"""Orchestrator readiness validation - checks all prerequisites for live trading execution.

PHASE 3 VALIDATION: Ensures system can execute orchestrator end-to-end without silent failures.
"""

import logging
import os
import sys

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def validate_environment():
    logger.info("=" * 70)
    logger.info("ORCHESTRATOR READINESS VALIDATION")
    logger.info("=" * 70)

    logger.info("\n[1/6] Validating environment variables...")

    required_vars = {
        "DB_HOST": "PostgreSQL host",
        "DB_PORT": "PostgreSQL port",
        "DB_NAME": "PostgreSQL database",
        "DB_USER": "PostgreSQL user",
        "DB_PASSWORD": "PostgreSQL password",
        "AWS_REGION": "AWS region",
    }

    # Optional variables with defaults
    optional_vars = {
        "ORCHESTRATOR_EXECUTION_MODE": ("paper", "Execution mode (paper/live)"),
        "ORCHESTRATOR_DRY_RUN": ("false", "Dry run mode (true/false)"),
    }

    missing = []
    for var, desc in required_vars.items():
        value = os.getenv(var)
        if not value:
            missing.append(f"  ✗ {var}: {desc}")
            logger.warning(f"  ✗ {var} not set")
        else:
            logger.info(f"  ✓ {var} is set")

    # Set optional variables with defaults if not set
    for var, (default_val, desc) in optional_vars.items():
        value = os.getenv(var)
        if not value:
            os.environ[var] = default_val
            logger.info(f"  ✓ {var} defaults to: {default_val}")
        else:
            logger.info(f"  ✓ {var} is set to: {value}")

    if missing:
        logger.error("\nMissing environment variables:")
        for m in missing:
            logger.error(m)
        return False

    logger.info("✓ All required environment variables present")
    return True

def validate_imports():
    logger.info("\n[2/6] Validating imports...")

    imports_to_test = [
        ("algo.orchestration", "Orchestrator"),
        ("algo.config.orchestrator_config", "OrchestratorConfig"),
        ("algo.config.environment_validation", "EnvironmentValidator"),
        ("utils.db", "DatabaseContext"),
    ]

    for module_name, class_name in imports_to_test:
        try:
            module = __import__(module_name, fromlist=[class_name])
            getattr(module, class_name)
            logger.info(f"  ✓ {module_name}.{class_name}")
        except Exception as e:
            logger.error(f"  ✗ {module_name}.{class_name}: {e}")
            return False

    logger.info("✓ All imports successful")
    return True

def validate_database():
    logger.info("\n[3/6] Validating database connection...")

    try:
        from utils.db import DatabaseContext

        with DatabaseContext("read", timeout=5) as cur:
            cur.execute("SELECT 1")
            result = cur.fetchone()
            if result:
                logger.info("  ✓ Database connection works")
                return True
            else:
                logger.error("  ✗ Database query returned no result")
                return False
    except Exception as e:
        logger.error(f"  ✗ Database connection failed: {e}")
        return False

def validate_required_tables():
    logger.info("\n[4/6] Validating required database tables...")

    required_tables = [
        "algo_config",
        "algo_positions",
        "algo_trades",
        "data_loader_status",
        "algo_orchestrator_runs",
    ]

    try:
        from utils.db import DatabaseContext

        for table in required_tables:
            try:
                with DatabaseContext("read", timeout=5) as cur:
                    cur.execute(f"SELECT 1 FROM {table} LIMIT 1")
                    logger.info(f"  ✓ {table} exists")
            except Exception as e:
                logger.error(f"  ✗ {table}: {e}")
                return False

        logger.info("✓ All required tables exist")
        return True
    except Exception as e:
        logger.error(f"✗ Error checking tables: {e}")
        return False

def validate_orchestrator_init():
    logger.info("\n[5/6] Validating orchestrator initialization...")

    try:
        from algo.infrastructure import get_config
        from algo.orchestration import Orchestrator

        config = get_config()
        orchestrator = Orchestrator(
            config=config,
            dry_run=True,
            verbose=False
        )

        logger.info(f"  ✓ Orchestrator initialized (run_id: {orchestrator.run_id})")
        logger.info(f"  ✓ Execution mode: {orchestrator.config.get('execution_mode')}")
        logger.info(f"  ✓ Dry run: {orchestrator.dry_run}")
        return True
    except Exception as e:
        logger.error(f"  ✗ Orchestrator initialization failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False

def validate_loaders():
    logger.info("\n[6/6] Validating loader infrastructure...")

    try:
        from utils.db import DatabaseContext

        with DatabaseContext("read", timeout=5) as cur:
            # Check if any critical loaders have run recently
            cur.execute("""
                SELECT COUNT(*) as count, MAX(last_updated) as latest
                FROM data_loader_status
                WHERE table_name IN ('price_daily', 'stock_scores', 'company_profile')
            """)
            result = cur.fetchone()

            if result:
                count = result.get('count', 0)
                latest = result.get('latest')

                if count > 0:
                    logger.info(f"  ✓ {count} critical loaders have run")
                    if latest:
                        logger.info(f"  ✓ Latest run: {latest}")
                    return True
                else:
                    logger.warning("  ⚠ No critical loaders have run yet")
                    logger.info("  → First run will need loader pipeline to complete")
                    return True
            else:
                logger.warning("  ⚠ Cannot query loader status (table might be empty)")
                return True
    except Exception as e:
        logger.error(f"  ✗ Loader validation failed: {e}")
        return False

def main():
    """Run all validations."""
    checks = [
        ("Environment Variables", validate_environment),
        ("Imports", validate_imports),
        ("Database Connection", validate_database),
        ("Required Tables", validate_required_tables),
        ("Orchestrator Initialization", validate_orchestrator_init),
        ("Loader Infrastructure", validate_loaders),
    ]

    results = []
    for name, check_fn in checks:
        try:
            result = check_fn()
            results.append((name, result))
        except Exception as e:
            logger.error(f"Validation failed with exception: {e}")
            results.append((name, False))

    logger.info("\n" + "=" * 70)
    logger.info("VALIDATION SUMMARY")
    logger.info("=" * 70)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        logger.info(f"{status}: {name}")

    logger.info(f"\nTotal: {passed}/{total} checks passed")

    if passed == total:
        logger.info("\n✓ ORCHESTRATOR IS READY FOR EXECUTION")
        return 0
    else:
        logger.error("\n✗ ORCHESTRATOR IS NOT READY - FIX FAILURES ABOVE")
        return 1

if __name__ == "__main__":
    sys.exit(main())
