#!/usr/bin/env python3
"""Check if Phase 7 can find signals on July 6"""
from utils.db.context import DatabaseContext
from datetime import datetime, timedelta, date

with DatabaseContext('read') as cur:
    # Simulate Phase 7 query for July 6
    run_date = date(2026, 7, 6)
    lookback_days = 7
    lookback_date = run_date - timedelta(days=lookback_days)
    min_score = 50
    min_close_quality = 0.3

    print(f"Phase 7 Simulation for {run_date}")
    print(f"Lookback period: {lookback_date} to {run_date}")
    print(f"Min composite score: {min_score}")

    # Query 1: Count signals in lookback period
    cur.execute("""
        SELECT COUNT(*) as count_buysell
        FROM buy_sell_daily
        WHERE signal_type = 'BUY'
          AND date >= %s
          AND date <= %s
    """, (lookback_date, run_date))
    count_result = cur.fetchone()
    print(f"\n1. Signals with signal_type='BUY' in lookback period: {count_result[0]}")

    # Query 2: What's the distribution by date?
    cur.execute("""
        SELECT date, COUNT(*) as count
        FROM buy_sell_daily
        WHERE signal_type = 'BUY'
          AND date >= %s
          AND date <= %s
        GROUP BY date
        ORDER BY date DESC
    """, (lookback_date, run_date))
    by_date = cur.fetchall()
    print(f"\n2. Signal distribution by date:")
    for row in by_date:
        print(f"   {row[0]}: {row[1]}")

    # Query 3: Check if stock_scores has data
    # First, find schema of stock_scores
    cur.execute("""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name='stock_scores'
        ORDER BY ordinal_position
        LIMIT 10
    """)
    cols = cur.fetchall()
    print(f"\n3. stock_scores schema (first 10 cols):")
    for c in cols:
        print(f"   {c[0]}: {c[1]}")

    # Check if we can find any stock_scores
    cur.execute("""
        SELECT COUNT(*) as cnt FROM stock_scores
    """)
    score_count = cur.fetchone()
    print(f"\n4. Total stock_scores rows: {score_count[0]}")

    # Query 4: Try Phase 7's main query but with a smaller subset
    print(f"\n5. Attempting Phase 7 main query:")
    cur.execute(
        """
        WITH ranked AS (
            SELECT
                bsd.symbol,
                COALESCE(ss.composite_score, bsd.strength * 20) AS composite_score,
                ss.quality_score,
                ss.growth_score,
                ss.momentum_score,
                ss.rs_percentile,
                p.close,
                p.high,
                p.low,
                sma.avg_close AS sma_50,
                atr_calc.atr_14,
                cp.sector,
                cp.industry,
                bsd.buylevel,
                bsd.stoplevel,
                bsd.strength AS signal_strength,
                bsd.volume_surge_pct,
                bsd.market_stage,
                bsd.date AS signal_date
            FROM (
                SELECT DISTINCT ON (symbol) *
                FROM buy_sell_daily
                WHERE signal_type = 'BUY'
                  AND date >= %s
                  AND date <= %s
                ORDER BY symbol, date DESC
            ) bsd
            LEFT JOIN stock_scores ss ON ss.symbol = bsd.symbol
            JOIN LATERAL (
                SELECT close, high, low
                FROM price_daily
                WHERE symbol = bsd.symbol AND date <= %s
                ORDER BY date DESC LIMIT 1
            ) p ON TRUE
            JOIN LATERAL (
                SELECT AVG(close) AS avg_close
                FROM (
                    SELECT close FROM price_daily
                    WHERE symbol = bsd.symbol AND date <= %s
                    ORDER BY date DESC LIMIT 50
                ) t
            ) sma ON TRUE
            JOIN LATERAL (
                SELECT AVG(tr) AS atr_14
                FROM (
                    SELECT
                        GREATEST(
                            high - low,
                            ABS(high - LAG(close) OVER (ORDER BY date)),
                            ABS(low - LAG(close) OVER (ORDER BY date))
                        ) AS tr,
                        ROW_NUMBER() OVER (ORDER BY date DESC) AS rn
                    FROM price_daily
                    WHERE symbol = bsd.symbol AND date <= %s
                ) t
                WHERE tr IS NOT NULL AND rn <= 14
            ) atr_calc ON TRUE
            LEFT JOIN company_profile cp ON cp.ticker = bsd.symbol
            WHERE COALESCE(ss.composite_score, bsd.strength * 20) >= %s
              AND (ss.data_completeness >= 70 OR ss.composite_score IS NULL)
              AND p.close > sma.avg_close
              AND p.high > p.low
              AND ((p.close - p.low) / (p.high - p.low)) > %s
              AND bsd.strength IS NOT NULL
        )
        SELECT COUNT(*) FROM ranked
        """,
        (
            lookback_date,
            run_date,
            run_date,
            run_date,
            run_date,
            min_score,
            min_close_quality,
        ),
    )
    final_count = cur.fetchone()
    print(f"   Candidates after Phase 7 filtering: {final_count[0]}")

    # If zero, check each filter step
    if final_count[0] == 0:
        print(f"\n6. Debugging - no candidates found. Checking filter steps:")

        # Step 1: After buy_sell_daily filter
        cur.execute("""
            SELECT COUNT(*) as cnt
            FROM buy_sell_daily
            WHERE signal_type = 'BUY'
              AND date >= %s
              AND date <= %s
        """, (lookback_date, run_date))
        step1 = cur.fetchone()[0]
        print(f"   After buy_sell_daily filter: {step1}")

        # Step 2: After DISTINCT ON (symbol)
        cur.execute("""
            SELECT COUNT(DISTINCT symbol) as cnt
            FROM buy_sell_daily
            WHERE signal_type = 'BUY'
              AND date >= %s
              AND date <= %s
        """, (lookback_date, run_date))
        step2 = cur.fetchone()[0]
        print(f"   Unique symbols: {step2}")

        # Step 3: After stock_scores join
        cur.execute("""
            SELECT COUNT(DISTINCT bsd.symbol) as cnt
            FROM (
                SELECT DISTINCT ON (symbol) *
                FROM buy_sell_daily
                WHERE signal_type = 'BUY'
                  AND date >= %s
                  AND date <= %s
                ORDER BY symbol, date DESC
            ) bsd
            LEFT JOIN stock_scores ss ON ss.symbol = bsd.symbol
            WHERE ss.symbol IS NOT NULL
        """, (lookback_date, run_date))
        step3 = cur.fetchone()[0]
        print(f"   After stock_scores join (has scores): {step3}")

        # Step 4: Check score threshold
        cur.execute("""
            SELECT COUNT(DISTINCT bsd.symbol) as cnt,
                   MIN(COALESCE(ss.composite_score, bsd.strength * 20)) as min_score,
                   MAX(COALESCE(ss.composite_score, bsd.strength * 20)) as max_score
            FROM (
                SELECT DISTINCT ON (symbol) *
                FROM buy_sell_daily
                WHERE signal_type = 'BUY'
                  AND date >= %s
                  AND date <= %s
                ORDER BY symbol, date DESC
            ) bsd
            LEFT JOIN stock_scores ss ON ss.symbol = bsd.symbol
        """, (lookback_date, run_date))
        step4 = cur.fetchone()
        print(f"   After score calc: {step4[0]} symbols (min={step4[1]}, max={step4[2]})")
