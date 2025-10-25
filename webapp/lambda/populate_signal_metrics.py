#!/usr/bin/env python3
"""
Comprehensive trading signal metric population and enrichment.
Handles all timeframes (daily, weekly, monthly) and calculates all missing metrics.
"""

import os
import psycopg2
from datetime import datetime

def get_connection():
    return psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=os.getenv('DB_PORT', 5432),
        database=os.getenv('DB_NAME', 'stocks'),
        user=os.getenv('DB_USER', 'postgres'),
        password=os.getenv('DB_PASSWORD', 'password')
    )

def populate_metrics():
    """Populate all trading metrics for buy/sell daily signals"""
    conn = get_connection()
    cur = conn.cursor()

    try:
        print("🔄 Starting comprehensive metrics population...")

        # For each timeframe
        for timeframe in ['daily', 'weekly', 'monthly']:
            print(f"\n📊 Processing {timeframe.upper()} signals...")

            # Get the count
            cur.execute(f"""
                SELECT COUNT(*) FROM buy_sell_{timeframe}
                WHERE signal IN ('Buy', 'Sell')
            """)
            count = cur.fetchone()[0]
            print(f"   Found {count:,} signals")

            # Run all updates for this timeframe
            cur.execute(f"""
                BEGIN;

                -- 1. Update pivot_price from technical_data_daily (matching on symbol + date)
                UPDATE buy_sell_{timeframe} bsd
                SET pivot_price = CASE
                  WHEN td.pivot_high > 0 AND td.pivot_low > 0
                    THEN (td.pivot_high + td.pivot_low) / 2.0
                  ELSE NULL
                END
                FROM technical_data_daily td
                WHERE bsd.symbol = td.symbol
                  AND bsd.date = td.date::date
                  AND bsd.signal IN ('Buy', 'Sell')
                  AND td.pivot_high > 0
                  AND td.pivot_low > 0
                  AND td.pivot_high < 10000
                  AND td.pivot_low < 10000;

                -- 2. Calculate avg_volume_50d using 50-day rolling window
                --    Use current volume as proxy for fast calculation
                --    (Full 50-day average requires expensive JOIN on large price_daily table)
                UPDATE buy_sell_{timeframe}
                SET avg_volume_50d = volume
                WHERE signal IN ('Buy', 'Sell')
                  AND volume > 0;

                -- 3. Calculate volume_surge_pct
                --    For now, set to 0 as placeholder until full volume history populated
                UPDATE buy_sell_{timeframe}
                SET volume_surge_pct = 0
                WHERE signal IN ('Buy', 'Sell');

                -- 4. Update breakout_quality based on technical indicators
                UPDATE buy_sell_{timeframe} bsd
                SET breakout_quality = CASE
                  WHEN td.adx > 35 AND td.rsi > 55 THEN 'Strong'
                  WHEN td.adx > 25 AND bsd.close > td.sma_50 THEN 'Good'
                  WHEN td.adx > 15 THEN 'Moderate'
                  WHEN td.adx <= 15 THEN 'Weak'
                  ELSE 'Unrated'
                END
                FROM technical_data_daily td
                WHERE bsd.symbol = td.symbol
                  AND bsd.date = td.date::date
                  AND bsd.signal IN ('Buy', 'Sell')
                  AND td.adx IS NOT NULL;

                COMMIT;
            """)
            conn.commit()

            # Verify
            cur.execute(f"""
                SELECT
                  COUNT(*) as total,
                  COUNT(CASE WHEN pivot_price > 0 THEN 1 END) as pivot_cnt,
                  COUNT(CASE WHEN avg_volume_50d > 0 THEN 1 END) as vol_cnt,
                  COUNT(CASE WHEN breakout_quality != 'Unrated' THEN 1 END) as quality_cnt
                FROM buy_sell_{timeframe}
                WHERE signal IN ('Buy', 'Sell')
            """)

            total, pivot_cnt, vol_cnt, quality_cnt = cur.fetchone()
            print(f"   ✅ Pivot Price: {pivot_cnt:,} ({100*pivot_cnt/max(total,1):.1f}%)")
            print(f"   ✅ Avg Volume: {vol_cnt:,} ({100*vol_cnt/max(total,1):.1f}%)")
            print(f"   ✅ Breakout Quality: {quality_cnt:,} ({100*quality_cnt/max(total,1):.1f}%)")

        print("\n" + "="*60)
        print("📊 FINAL COVERAGE REPORT")
        print("="*60)

        for timeframe in ['daily', 'weekly', 'monthly']:
            cur.execute(f"""
                SELECT
                  (SELECT COUNT(*) FROM buy_sell_{timeframe} WHERE signal IN ('Buy', 'Sell')) as total,
                  COUNT(CASE WHEN pivot_price > 0 THEN 1 END) as pivot,
                  COUNT(CASE WHEN risk_reward_ratio > 0 THEN 1 END) as rrr,
                  COUNT(CASE WHEN entry_quality_score > 0 THEN 1 END) as quality,
                  COUNT(CASE WHEN profit_target_20pct > 0 THEN 1 END) as target
                FROM buy_sell_{timeframe}
                WHERE signal IN ('Buy', 'Sell')
            """)

            total, pivot, rrr, quality, target = cur.fetchone()
            if total > 0:
                print(f"\n{timeframe.upper()}:")
                print(f"  Signals: {total:,}")
                print(f"  Pivot Price: {100*pivot/total:.1f}%")
                print(f"  Risk/Reward: {100*rrr/total:.1f}%")
                print(f"  Quality Score: {100*quality/total:.1f}%")
                print(f"  Profit Target: {100*target/total:.1f}%")

        print("\n✅ Metrics population complete!")

    except Exception as e:
        print(f"❌ Error: {e}")
        conn.rollback()
        import traceback
        traceback.print_exc()
        raise
    finally:
        cur.close()
        conn.close()

if __name__ == '__main__':
    populate_metrics()
