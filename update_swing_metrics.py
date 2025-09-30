#!/usr/bin/env python3
"""
Post-processor for buy_sell_daily/weekly/monthly tables
Calculates and updates swing trading metrics after initial signal generation
Implements O'Neill CAN SLIM and Minervini SEPA principles
"""

import json
import logging
import os
import sys
from datetime import datetime, timedelta

import boto3
import psycopg2
from psycopg2.extras import RealDictCursor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)

# Get DB credentials from AWS Secrets Manager
SECRET_ARN = os.environ.get("DB_SECRET_ARN")
if not SECRET_ARN:
    logging.error("DB_SECRET_ARN not set")
    sys.exit(1)

sm_client = boto3.client("secretsmanager")
secret_resp = sm_client.get_secret_value(SecretId=SECRET_ARN)
creds = json.loads(secret_resp["SecretString"])

DB_CONFIG = {
    'host': creds["host"],
    'port': int(creds.get("port", 5432)),
    'user': creds["username"],
    'password': creds["password"],
    'dbname': creds["dbname"],
}


def get_db_connection():
    return psycopg2.connect(**DB_CONFIG)


def update_swing_metrics_for_symbol(cur, symbol, date, timeframe='daily'):
    """
    Calculate and update swing trading metrics for a specific symbol/date
    """
    try:
        # Get signal data
        cur.execute(f"""
            SELECT symbol, date, signal, buylevel, stoplevel, close as current_price,
                   open, high, low, volume, inposition
            FROM buy_sell_{timeframe}
            WHERE symbol = %s AND date = %s AND timeframe = %s
        """, (symbol, date, timeframe))

        signal_data = cur.fetchone()
        if not signal_data:
            return

        symbol, date, signal, buylevel, stoplevel, current_price, open_price, high, low, volume, inposition = signal_data

        # Get technical data
        cur.execute("""
            SELECT sma_20, sma_50, sma_150, sma_200, ema_21, rsi, adx, atr
            FROM technical_data_daily
            WHERE symbol = %s AND date::date = %s
            ORDER BY date DESC LIMIT 1
        """, (symbol, date))

        tech_data = cur.fetchone()
        if not tech_data:
            logging.warning(f"No technical data for {symbol} on {date}")
            return

        sma_20, sma_50, sma_150, sma_200, ema_21, rsi, adx, atr = tech_data

        # Get previous SMAs for slope calculation
        prev_date = date - timedelta(days=5)
        cur.execute("""
            SELECT sma_50, sma_200
            FROM technical_data_daily
            WHERE symbol = %s AND date::date <= %s
            ORDER BY date DESC LIMIT 1 OFFSET 5
        """, (symbol, prev_date))

        prev_smas = cur.fetchone()
        sma_50_prev = prev_smas[0] if prev_smas else sma_50
        sma_200_prev = prev_smas[1] if prev_smas else sma_200

        # Get 50-day average volume
        cur.execute("""
            SELECT AVG(volume)::BIGINT as volume_avg_50
            FROM price_daily
            WHERE symbol = %s AND date <= %s
            ORDER BY date DESC LIMIT 50
        """, (symbol, date))

        volume_avg_result = cur.fetchone()
        volume_avg_50 = volume_avg_result[0] if volume_avg_result and volume_avg_result[0] else volume

        # Calculate metrics
        # 1. Sell level (opposite of buy)
        selllevel = buylevel if signal == 'SELL' else None

        # 2. Target price (Minervini: 25% for buys, 15% for shorts)
        if signal == 'BUY' and buylevel:
            target_price = buylevel * 1.25
        elif signal == 'SELL' and buylevel:
            target_price = buylevel * 0.85
        else:
            target_price = None

        # 3. Risk/Reward ratio
        if signal == 'BUY' and buylevel and stoplevel and target_price:
            risk = buylevel - stoplevel
            reward = target_price - buylevel
            risk_reward_ratio = reward / risk if risk > 0 else None
        elif signal == 'SELL' and buylevel and stoplevel and target_price:
            risk = stoplevel - buylevel
            reward = buylevel - target_price
            risk_reward_ratio = reward / risk if risk > 0 else None
        else:
            risk_reward_ratio = None

        # 4. Market stage (call PostgreSQL function)
        cur.execute("""
            SELECT calculate_weinstein_stage(%s, %s, %s, %s, %s, %s, %s, %s)
        """, (current_price, sma_50, sma_200, sma_50_prev, sma_200_prev, adx, volume, volume_avg_50))
        market_stage = cur.fetchone()[0]

        # 5. Distance from moving averages
        pct_from_ema_21 = ((current_price - ema_21) / ema_21 * 100) if ema_21 else None
        pct_from_sma_50 = ((current_price - sma_50) / sma_50 * 100) if sma_50 else None
        pct_from_sma_200 = ((current_price - sma_200) / sma_200 * 100) if sma_200 else None

        # 6. Volume analysis
        volume_ratio = volume / volume_avg_50 if volume_avg_50 > 0 else 1.0
        daily_change_pct = ((current_price - open_price) / open_price * 100) if open_price else 0

        if volume_ratio >= 2.0 and daily_change_pct > 0:
            volume_analysis = 'Pocket Pivot'
        elif volume_ratio >= 1.5 and daily_change_pct > 2:
            volume_analysis = 'Volume Surge'
        elif volume_ratio < 0.7:
            volume_analysis = 'Volume Dry-up'
        else:
            volume_analysis = 'Normal Volume'

        # 7. Entry Quality Score (0-100)
        entry_quality_score = 0
        if market_stage == 'Stage 2 - Advancing':
            entry_quality_score += 40
        if pct_from_ema_21 and abs(pct_from_ema_21) <= 2:
            entry_quality_score += 20
        if volume_ratio >= 1.5:
            entry_quality_score += 20
        if rsi and 40 <= rsi <= 70:
            entry_quality_score += 20

        # 8. Profit targets
        profit_target_8pct = buylevel * 1.08 if buylevel else None
        profit_target_20pct = buylevel * 1.20 if buylevel else None

        # 9. Current gain/loss if in position
        if inposition and buylevel:
            current_gain_loss_pct = ((current_price - buylevel) / buylevel * 100)
        else:
            current_gain_loss_pct = None

        # 10. Risk %
        if buylevel and stoplevel:
            risk_pct = ((buylevel - stoplevel) / buylevel * 100)
        else:
            risk_pct = None

        # 11. Position size (risk 1% of $100k portfolio)
        if buylevel and stoplevel:
            risk_per_share = buylevel - stoplevel
            position_size_recommendation = 1000.0 / risk_per_share if risk_per_share > 0 else None
        else:
            position_size_recommendation = None

        # 12. Minervini Trend Template
        passes_minervini_template = False
        if all([current_price, sma_50, sma_150, sma_200, pct_from_sma_200]):
            if (current_price > sma_50 and current_price > sma_150 and
                current_price > sma_200 and sma_50 > sma_150 and
                sma_150 > sma_200 and 0 <= pct_from_sma_200 <= 30):
                passes_minervini_template = True

        # 13. Daily range %
        daily_range_pct = ((high - low) / low * 100) if low > 0 else None

        # Update the record
        update_sql = f"""
            UPDATE buy_sell_{timeframe} SET
                selllevel = %s,
                target_price = %s,
                current_price = %s,
                risk_reward_ratio = %s,
                market_stage = %s,
                pct_from_ema_21 = %s,
                pct_from_sma_50 = %s,
                pct_from_sma_200 = %s,
                volume_ratio = %s,
                volume_analysis = %s,
                entry_quality_score = %s,
                profit_target_8pct = %s,
                profit_target_20pct = %s,
                current_gain_loss_pct = %s,
                risk_pct = %s,
                position_size_recommendation = %s,
                passes_minervini_template = %s,
                rsi = %s,
                adx = %s,
                atr = %s,
                daily_range_pct = %s
            WHERE symbol = %s AND date = %s AND timeframe = %s
        """

        cur.execute(update_sql, (
            selllevel, target_price, current_price, risk_reward_ratio,
            market_stage, pct_from_ema_21, pct_from_sma_50, pct_from_sma_200,
            volume_ratio, volume_analysis, entry_quality_score,
            profit_target_8pct, profit_target_20pct, current_gain_loss_pct,
            risk_pct, position_size_recommendation, passes_minervini_template,
            rsi, adx, atr, daily_range_pct,
            symbol, date, timeframe
        ))

        logging.info(f"Updated swing metrics for {symbol} on {date}: Stage={market_stage}, Quality={entry_quality_score}")

    except Exception as e:
        logging.error(f"Error updating {symbol} on {date}: {e}")
        raise


def main():
    """
    Update swing metrics for recent signals
    Run this after loadbuyselldaily.py completes
    """
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        # Get all symbols/dates from last 30 days
        cur.execute("""
            SELECT DISTINCT symbol, date, timeframe
            FROM buy_sell_daily
            WHERE date >= CURRENT_DATE - INTERVAL '30 days'
            ORDER BY date DESC, symbol
        """)

        records = cur.fetchall()
        logging.info(f"Found {len(records)} records to update")

        for symbol, date, timeframe in records:
            update_swing_metrics_for_symbol(cur, symbol, date, timeframe)
            conn.commit()

        logging.info("✅ Swing metrics update complete")

    except Exception as e:
        conn.rollback()
        logging.error(f"❌ Failed to update swing metrics: {e}")
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
