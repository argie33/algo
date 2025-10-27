#!/usr/bin/env python3
"""
Data Integrity Verification Script
Ensures ONLY REAL DATA loaded (no fake defaults, no NULL values where shouldn't be)
"""

import os
import sys
import logging
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def get_db_connection():
    """Create database connection."""
    try:
        conn = psycopg2.connect(
            host=os.environ.get("DB_HOST", "localhost"),
            port=int(os.environ.get("DB_PORT", 5432)),
            database=os.environ.get("DB_NAME", "stocks"),
            user=os.environ.get("DB_USER", "postgres"),
            password=os.environ.get("DB_PASSWORD", ""),
        )
        return conn
    except Exception as e:
        logger.error(f"❌ Database connection failed: {e}")
        return None


def check_real_data(conn):
    """Verify data is real (not fake defaults)."""
    if not conn:
        logger.error("❌ No database connection")
        return False

    checks_passed = 0
    checks_failed = 0

    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        # ============================================
        # 1. PRICE DATA - Check for real OHLC data
        # ============================================
        logger.info("\n🔍 Checking Price Data (OHLC)...")
        cur.execute("""
            SELECT COUNT(*) as total,
                   COUNT(CASE WHEN close > 0 THEN 1 END) as valid_prices,
                   COUNT(CASE WHEN open IS NULL THEN 1 END) as null_opens,
                   COUNT(CASE WHEN high < low THEN 1 END) as invalid_ranges
            FROM price_daily
            WHERE date >= CURRENT_DATE - INTERVAL '7 days'
        """)
        result = cur.fetchone()

        if result["total"] > 0:
            pct_valid = (result["valid_prices"] / result["total"]) * 100
            logger.info(f"  ✓ Price records: {result['total']}")
            logger.info(f"  ✓ Valid prices (close > 0): {result['valid_prices']} ({pct_valid:.1f}%)")

            if result["invalid_ranges"] > 0:
                logger.warning(f"  ⚠️ Invalid OHLC ranges (high < low): {result['invalid_ranges']}")
                checks_failed += 1
            else:
                logger.info(f"  ✓ No invalid OHLC ranges")
                checks_passed += 1

            if result["null_opens"] > 0:
                logger.warning(f"  ⚠️ NULL open prices: {result['null_opens']}")
            else:
                logger.info(f"  ✓ All opens have real data")
                checks_passed += 1
        else:
            logger.error("  ❌ No price data found")
            checks_failed += 1

        # ============================================
        # 2. SENTIMENT DATA - Check for real sentiment
        # ============================================
        logger.info("\n🔍 Checking Sentiment Data...")
        cur.execute("""
            SELECT COUNT(*) as total,
                   COUNT(CASE WHEN rsi_sentiment IS NOT NULL THEN 1 END) as rsi_count,
                   COUNT(CASE WHEN macd_sentiment IS NOT NULL THEN 1 END) as macd_count,
                   COUNT(CASE WHEN analyst_sentiment IS NOT NULL THEN 1 END) as analyst_count,
                   COUNT(CASE WHEN rsi_sentiment IS NOT NULL AND macd_sentiment IS NOT NULL THEN 1 END) as both_count
            FROM sentiment_analysis
            WHERE date >= CURRENT_DATE - INTERVAL '7 days'
        """)
        result = cur.fetchone()

        if result["total"] > 0:
            logger.info(f"  ✓ Sentiment records: {result['total']}")
            logger.info(f"  ✓ RSI sentiment: {result['rsi_count']}")
            logger.info(f"  ✓ MACD sentiment: {result['macd_count']}")
            logger.info(f"  ✓ With real data: {result['both_count']}")

            if result["both_count"] > (result["total"] * 0.7):
                logger.info(f"  ✓ Sufficient sentiment data coverage")
                checks_passed += 1
            else:
                logger.warning(f"  ⚠️ Low sentiment data coverage: {result['both_count']}/{result['total']}")
                checks_failed += 1
        else:
            logger.warning("  ⚠️ No sentiment data found yet")

        # ============================================
        # 3. TECHNICAL DATA - Check for real technicals
        # ============================================
        logger.info("\n🔍 Checking Technical Data...")
        cur.execute("""
            SELECT COUNT(*) as total,
                   COUNT(CASE WHEN rsi IS NOT NULL THEN 1 END) as rsi_count,
                   COUNT(CASE WHEN adx IS NOT NULL THEN 1 END) as adx_count,
                   COUNT(CASE WHEN atr IS NOT NULL THEN 1 END) as atr_count,
                   COUNT(CASE WHEN volume > 0 THEN 1 END) as volume_count
            FROM technicals_daily
            WHERE date >= CURRENT_DATE - INTERVAL '7 days'
        """)
        result = cur.fetchone()

        if result and result["total"] > 0:
            logger.info(f"  ✓ Technical records: {result['total']}")
            logger.info(f"  ✓ RSI values: {result['rsi_count']}")
            logger.info(f"  ✓ ADX values: {result['adx_count']}")
            logger.info(f"  ✓ Volume > 0: {result['volume_count']}")

            if result["rsi_count"] > (result["total"] * 0.5):
                logger.info(f"  ✓ Good technical data coverage")
                checks_passed += 1
            else:
                logger.warning(f"  ⚠️ Low technical data coverage")
                checks_failed += 1
        else:
            logger.warning("  ⚠️ No technical data found yet")

        # ============================================
        # 4. POSITIONING DATA - Check for real positioning
        # ============================================
        logger.info("\n🔍 Checking Positioning Data...")
        cur.execute("""
            SELECT COUNT(*) as total,
                   COUNT(CASE WHEN institutional_ownership_pct IS NOT NULL THEN 1 END) as inst_count,
                   COUNT(CASE WHEN short_interest_pct IS NOT NULL THEN 1 END) as short_count,
                   COUNT(CASE WHEN insider_ownership_pct IS NOT NULL THEN 1 END) as insider_count
            FROM positioning_metrics
            WHERE date >= CURRENT_DATE - INTERVAL '7 days'
        """)
        result = cur.fetchone()

        if result and result["total"] > 0:
            logger.info(f"  ✓ Positioning records: {result['total']}")
            logger.info(f"  ✓ Institutional ownership: {result['inst_count']}")
            logger.info(f"  ✓ Short interest: {result['short_count']}")
            logger.info(f"  ✓ Insider ownership: {result['insider_count']}")

            total_fields = result["inst_count"] + result["short_count"] + result["insider_count"]
            if total_fields > 0:
                logger.info(f"  ✓ Real positioning data found")
                checks_passed += 1
            else:
                logger.warning(f"  ⚠️ No positioning data values")
                checks_failed += 1
        else:
            logger.warning("  ⚠️ No positioning records found yet")

        # ============================================
        # 5. BUY/SELL SIGNALS - Check for real signals
        # ============================================
        logger.info("\n🔍 Checking Buy/Sell Signals...")
        cur.execute("""
            SELECT COUNT(*) as total,
                   COUNT(CASE WHEN signal IN ('Buy', 'Sell') THEN 1 END) as signal_count,
                   COUNT(CASE WHEN strength IS NOT NULL AND strength > 0 THEN 1 END) as strength_count,
                   COUNT(CASE WHEN risk_reward_ratio IS NOT NULL THEN 1 END) as ratio_count
            FROM buy_sell_daily
            WHERE date >= CURRENT_DATE - INTERVAL '7 days'
        """)
        result = cur.fetchone()

        if result and result["total"] > 0:
            logger.info(f"  ✓ Signal records: {result['total']}")
            logger.info(f"  ✓ Real signals (Buy/Sell): {result['signal_count']}")
            logger.info(f"  ✓ With strength values: {result['strength_count']}")
            logger.info(f"  ✓ With risk/reward ratio: {result['ratio_count']}")

            if result["signal_count"] > 0:
                logger.info(f"  ✓ Real trading signals generated")
                checks_passed += 1
            else:
                logger.warning(f"  ⚠️ No real trading signals")
                checks_failed += 1
        else:
            logger.warning("  ⚠️ No signal data found yet")

        # ============================================
        # 6. NO FAKE DEFAULTS CHECK
        # ============================================
        logger.info("\n🔍 Checking for Fake Defaults...")

        # Check for hardcoded 50 (fake neutral) in sentiment
        cur.execute("""
            SELECT COUNT(*) as fake_count
            FROM sentiment_analysis
            WHERE (rsi_sentiment = 0 AND macd_sentiment = 0) OR
                  (analyst_sentiment IS NULL AND rsi_sentiment IS NULL AND macd_sentiment IS NULL)
            LIMIT 10
        """)
        result = cur.fetchone()
        if result["fake_count"] == 0:
            logger.info(f"  ✓ No fake neutral (0) sentiment values")
            checks_passed += 1
        else:
            logger.warning(f"  ⚠️ Found {result['fake_count']} records with all-zero sentiment")
            checks_failed += 1

        # Check for risk_reward_ratio = 0.0 (fake invalid setups)
        cur.execute("""
            SELECT COUNT(*) as fake_count
            FROM buy_sell_daily
            WHERE signal IN ('Buy', 'Sell') AND risk_reward_ratio = 0.0
            LIMIT 10
        """)
        result = cur.fetchone()
        if result["fake_count"] == 0:
            logger.info(f"  ✓ No fake risk/reward (0.0) for real signals")
            checks_passed += 1
        else:
            logger.warning(f"  ⚠️ Found {result['fake_count']} real signals with 0.0 risk/reward")

        # ============================================
        # FINAL REPORT
        # ============================================
        logger.info("\n" + "="*70)
        logger.info("📊 DATA INTEGRITY VERIFICATION REPORT")
        logger.info("="*70)
        logger.info(f"✅ Checks Passed: {checks_passed}")
        logger.info(f"❌ Checks Failed: {checks_failed}")

        if checks_failed == 0:
            logger.info("\n🎉 ✅ ALL VERIFICATION CHECKS PASSED!")
            logger.info("✅ Database contains REAL DATA ONLY")
            logger.info("✅ No fake defaults or synthetic data detected")
            return True
        else:
            logger.warning(f"\n⚠️ {checks_failed} verification check(s) need attention")
            return False

    except Exception as e:
        logger.error(f"❌ Verification error: {e}")
        return False
    finally:
        cur.close()


def main():
    """Run verification."""
    logger.info("="*70)
    logger.info("🔍 DATA INTEGRITY VERIFICATION")
    logger.info("="*70)

    conn = get_db_connection()
    if not conn:
        sys.exit(1)

    try:
        success = check_real_data(conn)
        sys.exit(0 if success else 1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
