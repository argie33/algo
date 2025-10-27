#!/usr/bin/env python3
"""
Diagnostic script to check database connectivity, schema, and data availability
"""
import os
import sys
import json
import logging
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

def get_db_config():
    """Get database configuration"""
    return {
        "host": os.environ.get("DB_HOST", "localhost"),
        "port": int(os.environ.get("DB_PORT", 5432)),
        "user": os.environ.get("DB_USER", "postgres"),
        "password": os.environ.get("DB_PASSWORD", "password"),
        "dbname": os.environ.get("DB_NAME", "stocks")
    }

def test_connection():
    """Test database connection"""
    cfg = get_db_config()
    try:
        conn = psycopg2.connect(
            host=cfg["host"],
            port=cfg["port"],
            user=cfg["user"],
            password=cfg["password"],
            dbname=cfg["dbname"]
        )
        logger.info("✅ Database connection successful")
        return conn
    except Exception as e:
        logger.error(f"❌ Database connection failed: {e}")
        return None

def check_tables(conn):
    """Check which tables exist and have data"""
    tables_to_check = [
        'stock_symbols',
        'price_daily',
        'technical_data_daily',
        'economic_data',
        'buy_sell_signals_daily',
        'analyst_sentiment_analysis',
        'quality_metrics',
        'growth_metrics',
        'value_metrics',
        'momentum_metrics',
        'scores',
        'sectors',
        'earnings_estimates',
        'earnings_history',
    ]

    logger.info("\n" + "="*60)
    logger.info("📊 TABLE STATUS CHECK")
    logger.info("="*60)

    results = {}

    for table in tables_to_check:
        try:
            # Create new cursor for each query to avoid transaction issues
            cur = conn.cursor(cursor_factory=RealDictCursor)
            # Check if table exists and get row count
            cur.execute(f"""
                SELECT COUNT(*) as cnt
                FROM {table}
            """)
            row = cur.fetchone()
            count = row['cnt'] if row else 0

            # Get last updated info if available
            last_updated = None
            try:
                cur.execute(f"""
                    SELECT MAX(date) as last_date
                    FROM {table}
                    WHERE date IS NOT NULL
                """)
                result = cur.fetchone()
                if result and result['last_date']:
                    last_updated = result['last_date']
            except:
                pass

            cur.close()

            status = "✅" if count > 0 else "⚠️"
            results[table] = {
                "status": status,
                "rows": count,
                "last_updated": str(last_updated) if last_updated else "N/A"
            }
            logger.info(f"{status} {table:40} | {count:10} rows | Last: {last_updated}")

        except psycopg2.ProgrammingError:
            conn.rollback()
            results[table] = {"status": "❌", "rows": 0, "exists": False}
            logger.warning(f"❌ {table:40} | TABLE NOT FOUND")
        except Exception as e:
            conn.rollback()
            logger.error(f"❌ {table:40} | Error: {str(e)[:50]}")

    return results

def check_critical_data(conn):
    """Check critical data availability"""
    logger.info("\n" + "="*60)
    logger.info("🎯 CRITICAL DATA CHECKS")
    logger.info("="*60)

    # Check stock symbols
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT COUNT(*) as cnt FROM stock_symbols")
    symbol_count = cur.fetchone()['cnt']
    cur.close()
    logger.info(f"📍 Stock symbols: {symbol_count} total")

    # Check for major indices
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT symbol FROM stock_symbols WHERE symbol IN ('SPY', 'QQQ', 'IWM') ORDER BY symbol")
    indices = [r['symbol'] for r in cur.fetchall()]
    cur.close()
    logger.info(f"📊 Major indices available: {', '.join(indices) if indices else 'MISSING'}")

    # Check price data for SPY
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""
        SELECT COUNT(*) as cnt, MAX(date) as latest
        FROM price_daily
        WHERE symbol = 'SPY'
    """)
    result = cur.fetchone()
    cur.close()
    logger.info(f"📈 Price data (SPY): {result['cnt']} records, Latest: {result['latest']}")

    # Check technical data
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""
        SELECT COUNT(*) as cnt, MAX(date) as latest
        FROM technical_data_daily
        WHERE symbol = 'SPY'
    """)
    result = cur.fetchone()
    cur.close()
    logger.info(f"📊 Technical data (SPY): {result['cnt']} records, Latest: {result['latest']}")

    # Check economic data
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""
        SELECT COUNT(DISTINCT series_id) as series_cnt, MAX(date) as latest
        FROM economic_data
    """)
    result = cur.fetchone()
    cur.close()
    logger.info(f"📉 Economic data: {result['series_cnt']} series, Latest: {result['latest']}")

    # Check buy/sell signals
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""
        SELECT COUNT(*) as cnt, COUNT(DISTINCT symbol) as symbols
        FROM buy_sell_signals_daily
    """)
    result = cur.fetchone()
    cur.close()
    logger.info(f"🔄 Buy/Sell signals: {result['cnt']} total, {result['symbols']} symbols")

    # Check analyst sentiment
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""
        SELECT COUNT(*) as cnt, MAX(date) as latest
        FROM analyst_sentiment_analysis
    """)
    result = cur.fetchone()
    cur.close()
    if result['cnt'] > 0:
        logger.info(f"👥 Analyst sentiment: {result['cnt']} records, Latest: {result['latest']}")
    else:
        logger.warning(f"⚠️  Analyst sentiment: NO DATA")

    # Check metrics
    for metric_table in ['quality_metrics', 'growth_metrics', 'value_metrics', 'momentum_metrics']:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(f"""
            SELECT COUNT(*) as cnt
            FROM {metric_table}
        """)
        count = cur.fetchone()['cnt']
        cur.close()
        status = "✅" if count > 0 else "⚠️"
        logger.info(f"{status} {metric_table}: {count} records")

    # Check scores
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""
        SELECT COUNT(*) as cnt, MAX(date) as latest
        FROM scores
    """)
    result = cur.fetchone()
    cur.close()
    if result['cnt'] > 0:
        logger.info(f"⭐ Stock scores: {result['cnt']} records, Latest: {result['latest']}")
    else:
        logger.warning(f"⚠️  Stock scores: NO DATA")

def check_recently_updated(conn):
    """Check which loaders have recently run"""
    logger.info("\n" + "="*60)
    logger.info("⏰ LOADER RUN HISTORY (Last 30 days)")
    logger.info("="*60)

    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT script_name, last_run
            FROM last_updated
            WHERE last_run > NOW() - INTERVAL '30 days'
            ORDER BY last_run DESC
        """)

        results = cur.fetchall()
        cur.close()

        if results:
            for r in results:
                age_hours = (datetime.now() - r['last_run']).total_seconds() / 3600
                if age_hours < 24:
                    status = "🟢"
                elif age_hours < 72:
                    status = "🟡"
                else:
                    status = "🔴"
                logger.info(f"{status} {r['script_name']:40} | {r['last_run'].strftime('%Y-%m-%d %H:%M:%S')} ({age_hours:.0f}h ago)")
        else:
            logger.warning("⚠️  No recent loader runs found")
    except Exception as e:
        logger.error(f"❌ Error checking loader history: {e}")

def identify_missing_data(conn):
    """Identify which data is missing and needs loaders"""
    logger.info("\n" + "="*60)
    logger.info("🔍 MISSING DATA ANALYSIS")
    logger.info("="*60)

    missing_loaders = []
    today = datetime.now().date()

    # Check if we have recent price data
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""
        SELECT MAX(date) as latest FROM price_daily
    """)
    result = cur.fetchone()
    cur.close()
    latest_price = result['latest'] if result else None

    if not latest_price or (today - latest_price).days > 1:
        missing_loaders.append("loadpricedaily.py")
        logger.warning(f"⚠️  Price data is stale (latest: {latest_price})")
    else:
        logger.info(f"✅ Price data is current (latest: {latest_price})")

    # Check technical data
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""
        SELECT MAX(date) as latest FROM technical_data_daily
    """)
    result = cur.fetchone()
    cur.close()
    latest_tech = result['latest'] if result else None

    if not latest_tech or (today - latest_tech).days > 1:
        missing_loaders.append("loadtechnicalsdaily.py")
        logger.warning(f"⚠️  Technical data is stale (latest: {latest_tech})")
    else:
        logger.info(f"✅ Technical data is current (latest: {latest_tech})")

    # Check buy/sell signals
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""
        SELECT MAX(date) as latest FROM buy_sell_signals_daily
    """)
    result = cur.fetchone()
    cur.close()
    latest_signals = result['latest'] if result else None

    if not latest_signals or (today - latest_signals).days > 1:
        missing_loaders.append("loadbuyselldaily.py")
        logger.warning(f"⚠️  Buy/Sell signals are stale (latest: {latest_signals})")
    else:
        logger.info(f"✅ Buy/Sell signals are current (latest: {latest_signals})")

    # Check analyst sentiment
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""
        SELECT COUNT(*) as cnt FROM analyst_sentiment_analysis
    """)
    result = cur.fetchone()
    cur.close()
    if result['cnt'] == 0:
        missing_loaders.append("loadanalystsentiment.py")
        logger.warning("⚠️  Analyst sentiment data is MISSING")
    else:
        logger.info(f"✅ Analyst sentiment data available ({result['cnt']} records)")

    # Check metrics
    for metric_loader in [
        ('quality_metrics', 'loadqualitymetrics.py'),
        ('growth_metrics', 'loadgrowthmetrics.py'),
        ('value_metrics', 'loadvaluemetrics.py'),
        ('momentum_metrics', 'loadmomentum.py'),
    ]:
        table, loader = metric_loader
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(f"SELECT COUNT(*) as cnt FROM {table}")
        result = cur.fetchone()
        cur.close()
        if result['cnt'] == 0:
            missing_loaders.append(loader)
            logger.warning(f"⚠️  {table} is EMPTY")

    # Check scores
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT COUNT(*) as cnt FROM scores")
    result = cur.fetchone()
    cur.close()
    if result['cnt'] == 0:
        missing_loaders.append("loadscores.py")
        logger.warning("⚠️  Stock scores are MISSING")

    logger.info("\n" + "-"*60)
    logger.info(f"🔧 LOADERS TO RUN: {len(missing_loaders)} needed")
    for loader in missing_loaders:
        logger.info(f"  → {loader}")

    return missing_loaders

def main():
    logger.info("🔧 DATABASE DIAGNOSTIC CHECK")
    logger.info("="*60)

    conn = test_connection()
    if not conn:
        logger.error("Cannot proceed without database connection")
        sys.exit(1)

    check_tables(conn)
    check_critical_data(conn)
    check_recently_updated(conn)
    missing = identify_missing_data(conn)

    conn.close()

    logger.info("\n" + "="*60)
    logger.info("✅ DIAGNOSTIC COMPLETE")
    logger.info("="*60)

    if missing:
        logger.info(f"\n📋 Run these loaders via GitHub Actions:")
        logger.info(f"   Select these loaders in the workflow: {', '.join([l.replace('.py', '') for l in missing])}")

    return 0 if not missing else 1

if __name__ == "__main__":
    sys.exit(main())
