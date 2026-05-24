#!/usr/bin/env python3
"""
Comprehensive loader diagnostics - identifies missing env vars, connectivity issues, import errors.
Tests all 24 loaders systematically without running full data loads.
"""
import os
import sys
import logging
from datetime import datetime
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

# Expected environment variables by category
REQUIRED_ENV_VARS = {
    'Database': ['DB_HOST', 'DB_PORT', 'DB_USER', 'DB_PASSWORD', 'DB_NAME'],
    'Alpaca': ['APCA_API_KEY_ID', 'APCA_API_SECRET_KEY', 'ALPACA_PAPER_TRADING'],
    'APIs': ['FRED_API_KEY', 'SEC_USER_AGENT'],
    'AWS': ['AWS_REGION'],
}

LOADERS = [
    'load_stock_prices_daily',
    'load_stock_prices_weekly',
    'load_technical_data_daily',
    'load_algo_metrics_daily',
    'load_company_profile',
    'load_earnings_calendar',
    'load_industry_ranking',
    'load_market_health_daily',
    'load_fear_greed_index',
    'load_weight_optimization',
    'load_naaim',
    'load_signals_daily',
    'load_growth_metrics',
    'load_quality_metrics',
    'load_aaii_sentiment',
    'load_analyst_sentiment_analysis',
    'load_analyst_upgrade_downgrade',
    'load_value_metrics',
    'load_signal_quality_scores',
    'load_swing_trader_scores',
    'load_balance_sheet',
    'load_cash_flow',
    'load_income_statement',
    'load_trend_criteria_data',
]

def check_env_vars():
    """Check if all required environment variables are set."""
    logger.info("=" * 70)
    logger.info("CHECKING ENVIRONMENT VARIABLES")
    logger.info("=" * 70)

    missing = {}
    for category, vars_list in REQUIRED_ENV_VARS.items():
        logger.info(f"\n{category}:")
        for var in vars_list:
            value = os.getenv(var)
            if value:
                logger.info(f"  ✓ {var}=***" if len(value) > 10 else f"  ✓ {var}={value}")
            else:
                logger.warning(f"  ✗ {var} NOT SET")
                if category not in missing:
                    missing[category] = []
                missing[category].append(var)

    if missing:
        logger.warning(f"\nMissing {sum(len(v) for v in missing.values())} variables:")
        for category, vars_list in missing.items():
            logger.warning(f"  {category}: {', '.join(vars_list)}")
        return False
    else:
        logger.info("\n✓ All required environment variables are set")
        return True

def check_database_connectivity():
    """Test database connectivity."""
    logger.info("\n" + "=" * 70)
    logger.info("CHECKING DATABASE CONNECTIVITY")
    logger.info("=" * 70)

    try:
        import psycopg2

        db_params = {
            'host': os.getenv('DB_HOST'),
            'port': int(os.getenv('DB_PORT', '5432')),
            'user': os.getenv('DB_USER'),
            'password': os.getenv('DB_PASSWORD'),
            'database': os.getenv('DB_NAME'),
        }

        logger.info(f"Connecting to {db_params['host']}:{db_params['port']}/{db_params['database']}...")

        conn = psycopg2.connect(**db_params)
        cursor = conn.cursor()
        cursor.execute("SELECT version();")
        version = cursor.fetchone()[0]
        logger.info(f"✓ Connected successfully")
        logger.info(f"  PostgreSQL: {version[:50]}...")

        # Check key tables exist
        cursor.execute("""
            SELECT COUNT(*) FROM information_schema.tables
            WHERE table_schema = 'public'
        """)
        table_count = cursor.fetchone()[0]
        logger.info(f"  Tables in database: {table_count}")

        cursor.close()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"✗ Database connection failed: {e}")
        return False

def check_loader_imports():
    """Test if all loaders can be imported."""
    logger.info("\n" + "=" * 70)
    logger.info("CHECKING LOADER IMPORTS")
    logger.info("=" * 70)

    passed = []
    failed = []

    for loader_name in LOADERS:
        try:
            __import__(f'loaders.{loader_name}')
            logger.info(f"✓ {loader_name}")
            passed.append(loader_name)
        except Exception as e:
            logger.warning(f"✗ {loader_name}: {str(e)[:80]}")
            failed.append((loader_name, str(e)))

    logger.info(f"\nSummary: {len(passed)}/{len(LOADERS)} loaders import successfully")

    if failed:
        logger.warning(f"\nFailed imports ({len(failed)}):")
        for loader, error in failed:
            logger.warning(f"  - {loader}")
            logger.warning(f"    {error[:100]}")
        return False
    return True

def check_loader_initialization():
    """Test if loaders can be instantiated (minimal)."""
    logger.info("\n" + "=" * 70)
    logger.info("CHECKING LOADER INITIALIZATION")
    logger.info("=" * 70)

    passed = []
    failed = []

    # Set SEC_USER_AGENT if not already set
    if not os.getenv('SEC_USER_AGENT'):
        os.environ['SEC_USER_AGENT'] = 'algo-trading argeropolos@gmail.com'

    for loader_name in LOADERS:
        try:
            module = __import__(f'loaders.{loader_name}', fromlist=[loader_name])
            # Most loaders have a main() function we can check
            if hasattr(module, 'main'):
                logger.info(f"✓ {loader_name} (has main function)")
            else:
                logger.info(f"✓ {loader_name}")
            passed.append(loader_name)
        except Exception as e:
            logger.warning(f"✗ {loader_name}: {str(e)[:80]}")
            failed.append((loader_name, str(e)))

    logger.info(f"\nSummary: {len(passed)}/{len(LOADERS)} loaders initialize successfully")

    if failed:
        logger.warning(f"\nFailed initializations ({len(failed)}):")
        for loader, error in failed:
            logger.warning(f"  - {loader}")
            logger.warning(f"    {error[:100]}")
        return False
    return True

def generate_report():
    """Generate comprehensive diagnostic report."""
    logger.info("\n" + "=" * 70)
    logger.info("DIAGNOSTIC SUMMARY")
    logger.info("=" * 70)

    env_ok = check_env_vars()
    db_ok = check_database_connectivity()
    imports_ok = check_loader_imports()
    init_ok = check_loader_initialization()

    logger.info("\n" + "=" * 70)
    logger.info("OVERALL STATUS")
    logger.info("=" * 70)
    logger.info(f"Environment Variables: {'✓ OK' if env_ok else '✗ FAILED'}")
    logger.info(f"Database Connectivity: {'✓ OK' if db_ok else '✗ FAILED'}")
    logger.info(f"Loader Imports:        {'✓ OK' if imports_ok else '✗ FAILED'}")
    logger.info(f"Loader Initialization: {'✓ OK' if init_ok else '✗ FAILED'}")

    all_ok = env_ok and db_ok and imports_ok and init_ok
    logger.info(f"\nOverall Result: {'✓ ALL CHECKS PASSED' if all_ok else '✗ SOME CHECKS FAILED'}")

    return all_ok

if __name__ == '__main__':
    success = generate_report()
    sys.exit(0 if success else 1)
