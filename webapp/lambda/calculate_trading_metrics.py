#!/usr/bin/env python3
"""
Calculate missing trading metrics for buy_sell_daily table
Updates risk_reward_ratio, current_gain_pct, days_in_position, and other derived metrics
"""

import os
import psycopg2
from psycopg2.extras import execute_values
from datetime import datetime, timedelta
import sys

# Database connection
def get_connection():
    return psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=os.getenv('DB_PORT', 5432),
        database=os.getenv('DB_NAME', 'stocks'),
        user=os.getenv('DB_USER', 'postgres'),
        password=os.getenv('DB_PASSWORD', 'postgres')
    )

def calculate_metrics():
    """Calculate and populate trading metrics for all signals"""
    conn = get_connection()
    cur = conn.cursor()

    try:
        print("🔄 Starting trading metrics calculation...")

        # Get all records that need metric calculation
        cur.execute("""
            SELECT
                id, symbol, date, signal, close,
                buylevel, stoplevel,
                strength, rs_rating
            FROM buy_sell_daily
            WHERE signal IN ('Buy', 'Sell')
            ORDER BY date DESC
        """)

        # Use SQL-based calculation for efficiency and consistency
        print("📊 Calculating metrics using SQL...")

        # Execute comprehensive SQL metric calculations
        cur.execute("""
            BEGIN;

            -- Update profit targets
            UPDATE buy_sell_daily
            SET
              profit_target_8pct = CASE
                WHEN signal = 'Buy' AND close > 0 AND close < 10000 THEN (close * 1.08)::real
                WHEN signal = 'Sell' AND close > 0 AND close < 10000 THEN (close * 0.92)::real
              END,
              profit_target_20pct = CASE
                WHEN signal = 'Buy' AND close > 0 AND close < 10000 THEN (close * 1.20)::real
                WHEN signal = 'Sell' AND close > 0 AND close < 10000 THEN (close * 0.80)::real
              END,
              profit_target_25pct = CASE
                WHEN signal = 'Buy' AND close > 0 AND close < 10000 THEN (close * 1.25)::real
                WHEN signal = 'Sell' AND close > 0 AND close < 10000 THEN (close * 0.75)::real
              END
            WHERE signal IN ('Buy', 'Sell') AND close > 0;

            -- Update risk_pct
            UPDATE buy_sell_daily
            SET risk_pct = CASE
              WHEN signal = 'Buy' AND buylevel > 0 AND stoplevel > 0 AND buylevel < 10000 THEN
                (((buylevel - stoplevel) / buylevel) * 100)::real
              WHEN signal = 'Sell' AND buylevel > 0 AND stoplevel > 0 AND buylevel < 10000 THEN
                (((stoplevel - buylevel) / buylevel) * 100)::real
            END
            WHERE signal IN ('Buy', 'Sell') AND buylevel > 0 AND stoplevel IS NOT NULL;

            -- Calculate target_price
            UPDATE buy_sell_daily
            SET target_price = CASE
              WHEN signal = 'Buy' AND buylevel > 0 AND stoplevel > 0 AND buylevel < 10000 THEN
                (buylevel + (buylevel - stoplevel) * 3)::real
              WHEN signal = 'Sell' AND buylevel > 0 AND stoplevel > 0 AND buylevel < 10000 THEN
                (buylevel - (stoplevel - buylevel) * 3)::real
            END
            WHERE signal IN ('Buy', 'Sell') AND buylevel > 0 AND stoplevel > 0;

            -- Update risk_reward_ratio
            UPDATE buy_sell_daily
            SET risk_reward_ratio = CASE
              WHEN signal = 'Buy' AND buylevel > 0 AND buylevel < 10000 AND stoplevel > 0 AND target_price > 0 AND ABS(buylevel - stoplevel) > 0.01 THEN
                LEAST(99.99, GREATEST(0.01, ((target_price - buylevel) / (buylevel - stoplevel))::real))
              WHEN signal = 'Sell' AND buylevel > 0 AND buylevel < 10000 AND stoplevel > 0 AND target_price > 0 AND ABS(stoplevel - buylevel) > 0.01 THEN
                LEAST(99.99, GREATEST(0.01, ((buylevel - target_price) / (stoplevel - buylevel))::real))
              ELSE NULL
            END
            WHERE signal IN ('Buy', 'Sell') AND target_price IS NOT NULL;

            -- Update entry_quality_score
            UPDATE buy_sell_daily
            SET entry_quality_score = CASE
              WHEN strength IS NOT NULL AND rs_rating IS NOT NULL THEN
                ((strength * 100) * 0.4 + rs_rating * 0.6)::integer
              ELSE NULL
            END
            WHERE strength IS NOT NULL OR rs_rating IS NOT NULL;

            -- Update current_price
            UPDATE buy_sell_daily
            SET current_price = close
            WHERE close IS NOT NULL;

            -- Update current_gain_pct
            UPDATE buy_sell_daily
            SET current_gain_pct = CASE
              WHEN signal = 'Buy' AND buylevel > 0 AND buylevel < 10000 AND close > 0 AND close < 10000 THEN
                (((close - buylevel) / buylevel) * 100)::real
              WHEN signal = 'Sell' AND buylevel > 0 AND buylevel < 10000 AND close > 0 AND close < 10000 THEN
                (((buylevel - close) / buylevel) * 100)::real
            END
            WHERE signal IN ('Buy', 'Sell') AND buylevel > 0 AND close > 0;

            -- Update days_in_position
            UPDATE buy_sell_daily
            SET days_in_position = GREATEST(0, (CURRENT_DATE - date))
            WHERE date IS NOT NULL;

            COMMIT;
        """)
        conn.commit()

        print(f"✅ Successfully calculated metrics for all signals!")

        # Verify results
        cur.execute("""
            SELECT
                COUNT(*) as total,
                COUNT(CASE WHEN profit_target_8pct > 0 THEN 1 END) as with_8pct,
                COUNT(CASE WHEN profit_target_20pct > 0 THEN 1 END) as with_20pct,
                COUNT(CASE WHEN risk_pct > 0 THEN 1 END) as with_risk_pct,
                COUNT(CASE WHEN risk_reward_ratio > 0 THEN 1 END) as with_rrr,
                COUNT(CASE WHEN entry_quality_score > 0 THEN 1 END) as with_quality,
                COUNT(CASE WHEN current_gain_pct IS NOT NULL THEN 1 END) as with_current_gain,
                COUNT(CASE WHEN days_in_position >= 0 THEN 1 END) as with_days
            FROM buy_sell_daily
            WHERE signal IN ('Buy', 'Sell')
        """)

        results = cur.fetchone()
        total, with_8pct, with_20pct, with_risk_pct, with_rrr, with_quality, with_current_gain, with_days = results

        print(f"\n📊 METRICS VERIFICATION REPORT")
        print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print(f"   Total signals: {total}")
        print(f"   Profit targets (8%): {with_8pct} ({round(with_8pct/total*100, 1)}%)")
        print(f"   Profit targets (20%): {with_20pct} ({round(with_20pct/total*100, 1)}%)")
        print(f"   Risk %: {with_risk_pct} ({round(with_risk_pct/total*100, 1)}%)")
        print(f"   Risk/Reward Ratio: {with_rrr} ({round(with_rrr/total*100, 1)}%)")
        print(f"   Entry Quality Score: {with_quality} ({round(with_quality/total*100, 1)}%)")
        print(f"   Current Gain %: {with_current_gain} ({round(with_current_gain/total*100, 1)}%)")
        print(f"   Days in Position: {with_days} ({round(with_days/total*100, 1)}%)")

        print("\n✅ Trading metrics calculation and population complete!")

    except Exception as e:
        print(f"❌ Error calculating metrics: {e}")
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

if __name__ == '__main__':
    calculate_metrics()
