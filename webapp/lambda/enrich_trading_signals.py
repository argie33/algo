#!/usr/bin/env python3
"""
Enrich trading signals with technical data from technical_data_daily and price_daily tables.
Populates pivot_price, avg_volume_50d, volume_surge_pct, and breakout_quality using optimized SQL.
"""

import os
import psycopg2
from datetime import datetime, timedelta
import sys

# Database connection
def get_connection():
    return psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=os.getenv('DB_PORT', 5432),
        database=os.getenv('DB_NAME', 'stocks'),
        user=os.getenv('DB_USER', 'postgres'),
        password=os.getenv('DB_PASSWORD', 'password')
    )

def enrich_signals():
    """Enrich buy_sell_daily with technical data from related tables"""
    conn = get_connection()
    cur = conn.cursor()

    try:
        print("🔄 Starting trading signal enrichment...")

        # Single optimized transaction for all updates
        print("📍 Enriching signals with technical data...")
        cur.execute("""
            BEGIN;

            -- Update pivot_price from technical_data_daily
            UPDATE buy_sell_daily bsd
            SET pivot_price = CASE
              WHEN td.pivot_high > 0 AND td.pivot_low > 0 THEN (td.pivot_high + td.pivot_low) / 2.0
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

            -- Create temp table for 50-day volume averages (optimized with window function)
            CREATE TEMP TABLE volume_averages AS
            SELECT
              symbol,
              date,
              CAST(
                AVG(volume) OVER (
                  PARTITION BY symbol
                  ORDER BY date
                  ROWS BETWEEN 49 PRECEDING AND CURRENT ROW
                ) AS BIGINT
              ) as avg_vol_50d
            FROM price_daily
            WHERE volume > 0;

            -- Update avg_volume_50d using temp table
            UPDATE buy_sell_daily bsd
            SET avg_volume_50d = va.avg_vol_50d
            FROM volume_averages va
            WHERE bsd.symbol = va.symbol
              AND bsd.date = va.date
              AND bsd.signal IN ('Buy', 'Sell');

            -- Update volume_surge_pct: (current_volume / avg_50d - 1) * 100
            UPDATE buy_sell_daily bsd
            SET volume_surge_pct = CASE
              WHEN bsd.avg_volume_50d > 0 AND bsd.volume > 0 THEN
                ((bsd.volume::real / bsd.avg_volume_50d - 1.0) * 100.0)::real
              ELSE 0
            END
            WHERE bsd.signal IN ('Buy', 'Sell')
              AND bsd.avg_volume_50d > 0;

            -- Update breakout_quality based on technical indicators
            UPDATE buy_sell_daily bsd
            SET breakout_quality = CASE
              -- Strong breakout: High ADX + High RSI momentum
              WHEN td.adx > 35 AND td.rsi > 55 THEN 'Strong'
              -- Good breakout: Moderate ADX + Above SMA
              WHEN td.adx > 25 AND bsd.close > td.sma_50 THEN 'Good'
              -- Moderate breakout: Some trend + Volume confirmation
              WHEN td.adx > 15 AND bsd.volume_surge_pct > 50 THEN 'Moderate'
              -- Weak breakout: Low ADX or below key levels
              WHEN td.adx < 15 THEN 'Weak'
              ELSE 'Unrated'
            END
            FROM technical_data_daily td
            WHERE bsd.symbol = td.symbol
              AND bsd.date = td.date::date
              AND bsd.signal IN ('Buy', 'Sell')
              AND td.adx IS NOT NULL;

            DROP TABLE volume_averages;

            COMMIT;
        """)
        conn.commit()

        print("✅ Successfully enriched signals with technical data!")

        # Verification report
        cur.execute("""
            SELECT
                COUNT(*) as total,
                COUNT(CASE WHEN pivot_price > 0 THEN 1 END) as with_pivot_price,
                COUNT(CASE WHEN avg_volume_50d > 0 THEN 1 END) as with_avg_volume,
                COUNT(CASE WHEN volume_surge_pct IS NOT NULL THEN 1 END) as with_volume_surge,
                COUNT(CASE WHEN breakout_quality IS NOT NULL AND breakout_quality != 'Unrated' THEN 1 END) as with_breakout_quality
            FROM buy_sell_daily
            WHERE signal IN ('Buy', 'Sell')
        """)

        results = cur.fetchone()
        total, pivot_cnt, avg_vol_cnt, vol_surge_cnt, breakout_cnt = results

        print(f"\n📊 ENRICHMENT VERIFICATION REPORT")
        print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print(f"   Total Buy/Sell signals: {total:,}")
        print(f"   Pivot Price: {pivot_cnt:,} ({round(pivot_cnt/total*100, 1)}%)")
        print(f"   Avg Volume 50d: {avg_vol_cnt:,} ({round(avg_vol_cnt/total*100, 1)}%)")
        print(f"   Volume Surge %: {vol_surge_cnt:,} ({round(vol_surge_cnt/total*100, 1)}%)")
        print(f"   Breakout Quality: {breakout_cnt:,} ({round(breakout_cnt/total*100, 1)}%)")

        # Sample enriched data
        print(f"\n📊 SAMPLE ENRICHED DATA:")
        print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        cur.execute("""
            SELECT
                symbol, date, signal,
                pivot_price, avg_volume_50d, volume_surge_pct, breakout_quality
            FROM buy_sell_daily
            WHERE signal IN ('Buy', 'Sell')
              AND pivot_price > 0
              AND avg_volume_50d > 0
            LIMIT 5
        """)

        cols = [desc[0] for desc in cur.description]
        rows = cur.fetchall()

        # Print header
        print(f"  {cols[0]:10s} {cols[1]:12s} {cols[2]:8s} {cols[3]:15s} {cols[4]:18s} {cols[5]:16s} {cols[6]:15s}")
        print(f"  {'-'*10} {'-'*12} {'-'*8} {'-'*15} {'-'*18} {'-'*16} {'-'*15}")

        for row in rows:
            sym, date, signal, pivot, avg_vol, vol_surge, quality = row
            print(f"  {sym:10s} {str(date):12s} {signal:8s} {pivot:15.2f} {avg_vol:18,.0f} {vol_surge:16.2f} {quality:15s}")

        print(f"\n✅ Signal enrichment complete!")

    except Exception as e:
        print(f"❌ Error enriching signals: {e}")
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

if __name__ == '__main__':
    enrich_signals()
