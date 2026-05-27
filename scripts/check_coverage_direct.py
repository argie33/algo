#!/usr/bin/env python3
"""Direct database diagnostic without import dependencies."""
import os
import psycopg2
import logging
from datetime import datetime, date as _date

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

# Get credentials from environment
db_ssl = os.getenv('DB_SSL', 'require').lower()
sslmode = 'disable' if db_ssl in ('false', '0', 'no') else 'require'

db_config = {
    'host': os.getenv('DB_HOST'),
    'port': int(os.getenv('DB_PORT', '5432')),
    'database': os.getenv('DB_NAME'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'sslmode': sslmode
}

try:
    conn = psycopg2.connect(**db_config)
    cur = conn.cursor()

    logger.info("=" * 80)
    logger.info(f"DATA COVERAGE REPORT - {datetime.now().isoformat()}")
    logger.info("=" * 80)

    # Price data coverage
    cur.execute("""
        SELECT COUNT(DISTINCT symbol), MAX(date), COUNT(*)
        FROM price_daily
        WHERE date > NOW() - INTERVAL '7 days'
    """)
    symbols, latest_price_date, price_rows = cur.fetchone()
    price_staleness = (_date.today() - latest_price_date).days if latest_price_date else 999
    cur.execute("SELECT COUNT(*) FROM stock_symbols WHERE is_sp500 = TRUE")
    sp500_marked = cur.fetchone()[0]

    # Get actual S&P 500 count (should be 500)
    sp500_total = 500
    price_coverage_pct = (symbols / sp500_total * 100) if sp500_total else 0

    # Check stock_symbols status
    cur.execute("SELECT COUNT(*) FROM stock_symbols")
    total_symbols = cur.fetchone()[0]

    logger.info(f"\nPRICE DATA (price_daily)")
    logger.info(f"  Latest date: {latest_price_date}")
    logger.info(f"  Days stale: {price_staleness}")
    logger.info(f"  Symbols with prices: {symbols}")
    logger.info(f"  Total symbols in stock_symbols: {total_symbols}")
    logger.info(f"  S&P 500 marked symbols: {sp500_marked} (should be 500)")
    logger.info(f"  Status: {'FRESH' if price_staleness <= 1 else 'STALE' if price_staleness <= 3 else 'CRITICAL'}")
    if sp500_marked == 0:
        logger.info(f"  CRITICAL ISSUE: No symbols marked as S&P 500 in stock_symbols table!")

    # Technical data coverage
    cur.execute("""
        SELECT COUNT(DISTINCT symbol), MAX(date),
            SUM(CASE WHEN rsi IS NOT NULL THEN 1 ELSE 0 END)::FLOAT / NULLIF(COUNT(*), 0) as rsi_cov,
            SUM(CASE WHEN sma_50 IS NOT NULL THEN 1 ELSE 0 END)::FLOAT / NULLIF(COUNT(*), 0) as sma_cov,
            SUM(CASE WHEN atr IS NOT NULL THEN 1 ELSE 0 END)::FLOAT / NULLIF(COUNT(*), 0) as atr_cov
        FROM technical_data_daily
        WHERE date > NOW() - INTERVAL '7 days'
    """)
    tech_symbols, latest_tech_date, rsi_cov, sma_cov, atr_cov = cur.fetchone()
    min_tech_cov = min(rsi_cov or 0, sma_cov or 0, atr_cov or 0)

    logger.info(f"\nTECHNICAL DATA (technical_data_daily)")
    logger.info(f"  Latest date: {latest_tech_date}")
    logger.info(f"  Symbols with technicals: {tech_symbols}")
    logger.info(f"  RSI coverage: {(rsi_cov * 100 if rsi_cov else 0):.1f}%")
    logger.info(f"  SMA-50 coverage: {(sma_cov * 100 if sma_cov else 0):.1f}%")
    logger.info(f"  ATR coverage: {(atr_cov * 100 if atr_cov else 0):.1f}%")
    logger.info(f"  Status: {'COMPLETE' if min_tech_cov >= 0.95 else 'INCOMPLETE'}")

    # Market health
    cur.execute("""
        SELECT MAX(date), COUNT(*)
        FROM market_health_daily
        WHERE date > NOW() - INTERVAL '7 days'
    """)
    mh_date, mh_rows = cur.fetchone()
    mh_staleness = (_date.today() - mh_date).days if mh_date else 999

    logger.info(f"\nMARKET HEALTH (market_health_daily)")
    logger.info(f"  Latest date: {mh_date}")
    logger.info(f"  Days stale: {mh_staleness}")
    logger.info(f"  Rows: {mh_rows}")
    logger.info(f"  Status: {'AVAILABLE' if mh_rows > 0 and mh_staleness <= 1 else 'MISSING/STALE'}")

    # Economic data
    econ_date = None
    econ_count = 0
    try:
        cur.execute("""
            SELECT MAX(date), COUNT(*)
            FROM economic_data
            WHERE date > NOW() - INTERVAL '30 days'
        """)
        econ_date, econ_count = cur.fetchone()
    except Exception as e:
        logger.info(f"\nECONOMIC DATA (FRED) - ERROR checking table: {str(e)[:100]}")

    if econ_date:
        logger.info(f"\nECONOMIC DATA (FRED)")
        logger.info(f"  Latest date: {econ_date}")
        logger.info(f"  Rows: {econ_count}")
        logger.info(f"  Status: {'AVAILABLE' if econ_count > 0 else 'MISSING'}")

    # Loader health
    try:
        cur.execute("""
            SELECT COUNT(*) FROM information_schema.tables
            WHERE table_name = 'data_loader_status'
        """)
        if cur.fetchone()[0] > 0:
            cur.execute("""
                SELECT * FROM data_loader_status LIMIT 1
            """)
            cols = [desc[0] for desc in cur.description]
            logger.info(f"\nLOADER HEALTH")
            logger.info(f"  data_loader_status table columns: {cols}")
    except Exception as e:
        logger.info(f"\nLOADER HEALTH - table check error: {str(e)[:100]}")

    conn.close()

    logger.info("\n" + "=" * 80)

except Exception as e:
    logger.info(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
