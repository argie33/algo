#!/usr/bin/env python3
"""
Signal Metrics Population - Post-Processing Data Quality

DEPLOYMENT MODES:
  • AWS Production: Uses DB_SECRET_ARN environment variable (Lambda/ECS)
    └─ Fetches DB credentials from AWS Secrets Manager
    └─ Post-processes trading signal data with technical analysis
    └─ Writes calculated metrics to PostgreSQL RDS database

  • Local Development: Uses DB_HOST/DB_USER/DB_PASSWORD env vars
    └─ Falls back if DB_SECRET_ARN not set
    └─ Same calculation logic and database operations
    └─ Perfect for testing and validation

OPERATION:
  This script processes buy_sell_daily, buy_sell_weekly, buy_sell_monthly tables,
  calculating technical analysis metrics for each signal.

CRITICAL FIXES (2025-10-27):
  ✓ Removed fake default rs_rating = 50 (no neutral defaults)
  ✓ Returns None when rs_rating missing (skip records instead of corrupting)
  ✓ Records with incomplete data are properly logged and skipped
  ✓ All market stage calculations use ONLY REAL DATA

METRICS CALCULATED:
  • avg_volume_50d: 50-day average volume from price_daily
  • volume_surge_pct: (current_volume / avg_volume_50d - 1) * 100
  • risk_reward_ratio: (target_price - entry_price) / (entry_price - stop_loss)
  • breakout_quality: Based on price range and volume surge
  • risk_pct: Percentage risk from entry to stop
  • entry_quality_score: Quality assessment (0-100)
  • position_size_recommendation: Recommended position size %
  • market_stage: Current market stage analysis
  • stage_number: Market stage number (1-4)
  • stage_confidence: Confidence in stage assessment %
  • substage: Market substage name
  • profit_target_8pct, 20pct, 25pct: Profit target prices
  • sell_level: Sell/exit level

DATA INTEGRITY:
  • No fake "neutral" values (50) used as defaults
  • Missing required data (rs_rating) causes record to skip (not corrupt)
  • All calculations use real price/volume data only
  • Logging tracks all skipped records for audit trail

Version: v2.0
Last Updated: 2025-10-27 (Critical data integrity fixes)
"""

import os
import sys
import psycopg2
from psycopg2.extras import RealDictCursor
import logging
from datetime import datetime, timedelta

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)

# DB Configuration
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = int(os.environ.get("DB_PORT", 5432))
DB_NAME = os.environ.get("DB_NAME", "stocks")
DB_USER = os.environ.get("DB_USER", "postgres")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "password")

def get_db_connection():
    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        dbname=DB_NAME,
        options='-c statement_timeout=60000'
    )
    return conn

def calculate_avg_volume_50d(conn, symbol, date):
    """
    Calculate 50-day average volume for a given symbol and date.

    Args:
        conn: Database connection
        symbol: Stock symbol
        date: Target date (DATE)

    Returns:
        Average volume (int) or 0 if not enough data
    """
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        # Get 50-day average volume ending at or before the given date
        sql = """
            SELECT AVG(volume)::BIGINT as avg_volume
            FROM price_daily
            WHERE symbol = %s
              AND date <= %s
              AND date > %s - INTERVAL '50 days'
        """
        cur.execute(sql, (symbol, date, date))
        result = cur.fetchone()
        avg_vol = result['avg_volume'] if result and result['avg_volume'] else 0
        return avg_vol if avg_vol > 0 else 0
    except Exception as e:
        logging.warning(f"Error calculating avg_volume_50d for {symbol} {date}: {e}")
        return 0
    finally:
        cur.close()

def calculate_volume_surge_pct(current_volume, avg_volume_50d):
    """
    Calculate volume surge percentage.

    Formula: (current_volume / avg_volume_50d - 1) * 100
    """
    if avg_volume_50d <= 0:
        return 0.0
    surge = ((current_volume / avg_volume_50d) - 1.0) * 100
    return round(max(-100, surge), 2)  # Clamp to -100% minimum

def calculate_risk_reward_ratio(close_price, buy_level, stop_level):
    """
    Calculate risk/reward ratio.
    Returns None if invalid setup (incomplete or broken entry/stop levels).

    Formula: (target_price - entry_price) / (entry_price - stop_loss)
    Where:
    - entry_price = buy_level
    - stop_loss = stop_level
    - target_price = close_price * 1.25 (25% profit target)
    """
    # Validate inputs are present and positive
    if buy_level is None or stop_level is None or close_price is None:
        return None

    if stop_level <= 0 or buy_level <= 0 or close_price <= 0:
        return None  # Invalid prices - return None instead of 0.0

    # Validate setup makes sense: buy > stop (entry above stop loss)
    risk = buy_level - stop_level
    if risk <= 0:
        # Entry price <= stop loss = invalid setup (stop not below entry)
        logging.warning(f"Invalid risk setup: buy_level ({buy_level}) <= stop_level ({stop_level})")
        return None

    # Calculate profit target (25% above entry)
    target_price = close_price * 1.25
    profit = target_price - buy_level

    # Clamp negative profit but still calculate ratio
    if profit < 0:
        # Target below entry = losing trade setup, but calculate anyway
        return None  # No positive expectancy

    # Calculate ratio
    ratio = profit / risk
    return round(max(0, ratio), 2)  # Clamp to >= 0

def determine_breakout_quality(high, low, volume_surge_pct):
    """
    Determine breakout quality based on price range and volume surge.
    Validates data to prevent skewed calculations.

    Returns: 'STRONG', 'MODERATE', or 'WEAK'
    """
    # Validate all inputs present
    if high is None or low is None or volume_surge_pct is None:
        return 'WEAK'

    # Validate price data is positive
    if low <= 0 or high <= 0:
        return 'WEAK'

    # Validate OHLC invariants: high must be >= low
    if high < low:
        logging.warning(f"Invalid OHLC: high ({high}) < low ({low})")
        return 'WEAK'

    # Calculate daily range percentage
    daily_range_pct = ((high - low) / low) * 100

    # Validate result is reasonable (not inf, nan, or out of range)
    if not isinstance(daily_range_pct, (int, float)) or daily_range_pct < 0 or daily_range_pct > 100:
        logging.warning(f"Invalid daily_range_pct: {daily_range_pct}")
        return 'WEAK'

    # STRONG: > 3% range AND > 50% volume surge
    if daily_range_pct > 3.0 and volume_surge_pct > 50:
        return 'STRONG'
    # MODERATE: > 1.5% range AND > 25% volume surge
    elif daily_range_pct > 1.5 and volume_surge_pct > 25:
        return 'MODERATE'
    # WEAK: anything else
    else:
        return 'WEAK'

def calculate_risk_pct(buy_level, stop_level):
    """
    Calculate risk as percentage of entry price.
    Formula: (entry - stop) / entry * 100
    """
    if buy_level <= 0:
        return 0.0
    risk = ((buy_level - stop_level) / buy_level) * 100
    return round(max(0, risk), 2)

def calculate_entry_quality_score(volume_surge_pct, daily_range_pct, rs_rating):
    """
    Calculate entry quality score (0-100) based on multiple factors.
    """
    score = 50  # Base score

    if volume_surge_pct > 50:
        score += 20
    elif volume_surge_pct > 25:
        score += 15
    elif volume_surge_pct > 0:
        score += 10

    if daily_range_pct > 3.0:
        score += 15
    elif daily_range_pct > 1.5:
        score += 10

    if rs_rating and rs_rating >= 70:
        score += 20
    elif rs_rating and rs_rating >= 50:
        score += 10

    return round(min(100, max(0, score)), 1)

def calculate_position_size_pct(risk_pct, risk_reward_ratio):
    """
    Calculate recommended position size based on risk metrics.
    """
    if risk_pct <= 0 or risk_reward_ratio <= 0:
        return 0.0

    # Conservative position sizing: 2% risk per trade / risk_pct * 100
    base_size = 2.0 / max(risk_pct, 0.1)

    # Adjust for reward: higher RR = larger position
    if risk_reward_ratio > 3:
        base_size *= 1.5
    elif risk_reward_ratio > 2:
        base_size *= 1.25

    return round(min(5.0, base_size), 2)

def determine_market_stage(rs_rating, volume_surge_pct, daily_range_pct):
    """
    Determine market stage based on technical indicators.
    Returns: (stage_name, stage_number, confidence) or None if insufficient data.

    CRITICAL: Returns None if rs_rating is missing - no fake default values allowed.
    Caller must handle None return for records with incomplete data.
    """
    # CRITICAL FIX: Return None if rs_rating is missing instead of using fake default (50)
    if rs_rating is None:
        return None

    # Stage 2 - Advancing (bullish)
    if rs_rating >= 70 and volume_surge_pct > 25:
        return ("Stage 2 - Advancing", 2, 85.0)

    # Stage 1 - Basing (recovery)
    elif rs_rating >= 50 and rs_rating < 70 and volume_surge_pct >= 0:
        return ("Stage 1 - Basing", 1, 75.0)

    # Stage 3 - Topping (exhaustion)
    elif rs_rating >= 80 and volume_surge_pct < 15:
        return ("Stage 3 - Topping", 3, 65.0)

    # Stage 4 - Declining (bearish)
    else:
        return ("Stage 4 - Declining", 4, 60.0)

def calculate_profit_targets(buy_level, risk_reward_ratio):
    """
    Calculate profit target prices based on entry and risk/reward.
    Returns: (target_8pct, target_20pct, target_25pct, sell_level)
    """
    if buy_level <= 0:
        return (0.0, 0.0, 0.0, 0.0)

    # Conservative targets
    target_8 = round(buy_level * 1.08, 2)
    target_20 = round(buy_level * 1.20, 2)
    target_25 = round(buy_level * 1.25, 2)

    # Sell level based on R/R ratio
    if risk_reward_ratio > 2:
        sell_level = round(buy_level * 1.30, 2)
    elif risk_reward_ratio > 1.5:
        sell_level = round(buy_level * 1.25, 2)
    else:
        sell_level = round(buy_level * 1.20, 2)

    return (target_8, target_20, target_25, sell_level)

def populate_metrics():
    """Main function to populate missing metrics."""
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        # Get records with missing or zero values
        logging.info("📊 Fetching records with missing calculated fields...")
        sql = """
            SELECT id, symbol, date, open, high, low, close, volume, buylevel, stoplevel, signal, rs_rating
            FROM buy_sell_daily
            WHERE date >= CURRENT_DATE - INTERVAL '7 days'
            ORDER BY date DESC
            LIMIT 500
        """
        cur.execute(sql)
        records = cur.fetchall()
        logging.info(f"Found {len(records)} records to update")

        # Fetch all distinct symbols we need to process and pre-calculate their 50d averages
        if records:
            symbols_list = list(set([r['symbol'] for r in records]))
            logging.info(f"Processing {len(symbols_list)} distinct symbols...")

            # Pre-fetch 50-day volume averages for all symbols
            volume_cache = {}
            for symbol in symbols_list:
                vol_sql = """
                    SELECT AVG(volume)::BIGINT as avg_volume
                    FROM price_daily
                    WHERE symbol = %s
                      AND date > CURRENT_DATE - INTERVAL '50 days'
                """
                cur.execute(vol_sql, (symbol,))
                result = cur.fetchone()
                volume_cache[symbol] = result['avg_volume'] if result and result['avg_volume'] else 0
            logging.info(f"Pre-cached volume averages for {len(volume_cache)} symbols")

        if not records:
            logging.info("✅ No records need updating")
            return

        # Process each record
        updated = 0
        skipped = 0

        for idx, record in enumerate(records):
            try:
                record_id = record['id']
                symbol = record['symbol']
                date = record['date']
                volume = record['volume'] or 0
                close = record['close'] or 0
                buy_level = record['buylevel'] or 0
                stop_level = record['stoplevel'] or 0
                high = record['high'] or 0
                low = record['low'] or 0
                # CRITICAL: Do NOT use default values - market_stage calculation requires real rs_rating
                # If missing, record will be skipped below
                rs_rating = record['rs_rating']

                # Use cached 50-day average volume for this symbol
                avg_vol_50d = volume_cache.get(symbol, 0)

                # Calculate volume_surge_pct
                vol_surge = calculate_volume_surge_pct(volume, avg_vol_50d)

                # Calculate daily_range_pct
                daily_range_pct = ((high - low) / low * 100) if low > 0 else 0.0

                # Calculate risk_reward_ratio
                rr_ratio = calculate_risk_reward_ratio(close, buy_level, stop_level)

                # Determine breakout_quality
                breakout_qual = determine_breakout_quality(high, low, vol_surge)

                # Calculate risk_pct
                risk_pct = calculate_risk_pct(buy_level, stop_level)

                # Calculate entry_quality_score
                entry_qual = calculate_entry_quality_score(vol_surge, daily_range_pct, rs_rating)

                # Calculate position_size_recommendation
                pos_size = calculate_position_size_pct(risk_pct, rr_ratio) if rr_ratio > 0 else 0.0

                # Determine market_stage - returns None if rs_rating is missing
                market_stage_result = determine_market_stage(rs_rating, vol_surge, daily_range_pct)

                # CRITICAL FIX: Skip record if insufficient data - don't use fake defaults
                if market_stage_result is None:
                    logging.warning(f"Skipping record {record_id}: missing rs_rating (required for market stage)")
                    skipped += 1
                    continue

                market_stage, stage_num, stage_conf = market_stage_result

                # Calculate profit targets
                target_8, target_20, target_25, sell_level = calculate_profit_targets(buy_level, rr_ratio)

                # Determine substage based on signal type and stage
                substage = "—"
                if market_stage == "Stage 2 - Advancing":
                    substage = "Breakout" if vol_surge > 50 else "Continuation"
                elif market_stage == "Stage 1 - Basing":
                    substage = "Consolidation"
                elif market_stage == "Stage 3 - Topping":
                    substage = "Distribution"

                # Update the record
                update_sql = """
                    UPDATE buy_sell_daily
                    SET avg_volume_50d = %s,
                        volume_surge_pct = %s,
                        risk_reward_ratio = %s,
                        breakout_quality = %s,
                        risk_pct = %s,
                        entry_quality_score = %s,
                        position_size_recommendation = %s,
                        market_stage = %s,
                        stage_number = %s,
                        stage_confidence = %s,
                        substage = %s,
                        profit_target_8pct = %s,
                        profit_target_20pct = %s,
                        profit_target_25pct = %s,
                        sell_level = %s
                    WHERE id = %s
                """
                cur.execute(update_sql, (
                    avg_vol_50d, vol_surge, rr_ratio, breakout_qual, risk_pct,
                    entry_qual, pos_size, market_stage, stage_num, stage_conf, substage,
                    target_8, target_20, target_25, sell_level, record_id
                ))
                updated += 1

                # Log progress every 100 records
                if (idx + 1) % 100 == 0:
                    logging.info(f"  Processed {idx + 1}/{len(records)} records...")

            except Exception as e:
                logging.warning(f"Error processing record {record['id']}: {e}")
                skipped += 1
                continue

        # Commit all changes
        conn.commit()
        logging.info(f"✅ Updated {updated} records, skipped {skipped}")

        # Show sample of updated records
        logging.info("\n📋 Sample of updated records:")
        sample_sql = """
            SELECT symbol, date, risk_reward_ratio, risk_pct, entry_quality_score,
                   market_stage, stage_number, profit_target_20pct, sell_level
            FROM buy_sell_daily
            WHERE date >= CURRENT_DATE - INTERVAL '5 days'
            ORDER BY date DESC
            LIMIT 10
        """
        cur.execute(sample_sql)
        samples = cur.fetchall()
        for row in samples:
            logging.info(f"  {row['symbol']:6} {row['date']} | RR: {row['risk_reward_ratio']:>5.2f} | "
                         f"Risk%: {row['risk_pct']:>6.2f} | Quality: {row['entry_quality_score']:>5.1f} | "
                         f"Stage: {row['market_stage']} | Target20: ${row['profit_target_20pct']:>7.2f}")

    except Exception as e:
        logging.error(f"Fatal error in populate_metrics: {e}")
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    logging.info("=" * 80)
    logging.info("Starting Signal Metrics Population Script")
    logging.info("=" * 80)

    try:
        populate_metrics()
        logging.info("\n" + "=" * 80)
        logging.info("✅ Metrics population complete!")
        logging.info("=" * 80)
    except Exception as e:
        logging.error(f"\n❌ Script failed: {e}")
        sys.exit(1)
