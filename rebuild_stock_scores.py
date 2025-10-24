#!/usr/bin/env python3
"""
Rebuild stock_scores table from fresh feeder data.
Runs AFTER all individual score loaders (momentum, sentiment, value, quality, growth, stability) are complete.
"""

import psycopg2
import logging
import os
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)

def get_db_connection():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", 5432)),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", "password"),
        dbname=os.getenv("DB_NAME", "stocks")
    )

def main():
    conn = get_db_connection()
    cur = conn.cursor()

    logging.info("=" * 80)
    logging.info("STOCK SCORES REBUILD")
    logging.info("=" * 80)

    # Step 1: Clear stock_scores
    logging.info("\nStep 1: Clearing stock_scores table...")
    try:
        cur.execute("DELETE FROM stock_scores")
        conn.commit()
        logging.info("✅ Cleared stock_scores")
    except Exception as e:
        logging.error(f"❌ Error clearing stock_scores: {e}")
        conn.rollback()
        sys.exit(1)

    # Step 2: Get all unique symbols from company_profile
    logging.info("\nStep 2: Loading all symbols from company_profile...")
    cur.execute("""
        SELECT DISTINCT ticker as symbol
        FROM company_profile
        WHERE ticker IS NOT NULL
        ORDER BY ticker
    """)
    symbols = [row[0] for row in cur.fetchall()]
    logging.info(f"Found {len(symbols)} symbols to rebuild")

    # Step 3: Insert base records with all symbols
    logging.info(f"\nStep 3: Inserting {len(symbols)} base records...")
    try:
        base_insert = """
            INSERT INTO stock_scores (symbol, composite_score, momentum_score,
                                     value_score, quality_score, growth_score,
                                     sentiment_score, stability_score, last_updated)
            VALUES (%s, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, CURRENT_TIMESTAMP)
        """
        for symbol in symbols:
            cur.execute(base_insert, (symbol,))

        conn.commit()
        logging.info(f"✅ Inserted {len(symbols)} base records")
    except Exception as e:
        logging.error(f"❌ Error inserting base records: {e}")
        conn.rollback()
        sys.exit(1)

    # Step 4: Sync momentum scores from momentum_metrics (using multiple momentum inputs)
    logging.info("\nStep 4: Syncing momentum scores (multiple inputs)...")
    try:
        cur.execute("""
            UPDATE stock_scores ss
            SET momentum_score = ROUND(
                CASE
                    WHEN m.jt_momentum_12_1 IS NULL THEN 0.0
                    ELSE GREATEST(0, LEAST(100,
                        (COALESCE(m.jt_momentum_12_1, 0) * 0.30 +
                         COALESCE(m.momentum_6_1, 0) * 0.20 +
                         COALESCE(m.momentum_3_1, 0) * 0.15 +
                         COALESCE(m.momentum_1m, 0) * 0.15 +
                         COALESCE(m.volume_weighted_momentum, 0) * 0.10 +
                         COALESCE(m.momentum_persistence, 0) * 0.10) / 100 * 100 + 50
                    ))
                END::NUMERIC, 2)
            FROM momentum_metrics m
            WHERE ss.symbol = m.symbol
            AND m.date = (
                SELECT MAX(date) FROM momentum_metrics
                WHERE symbol = m.symbol
            )
        """)
        updated = cur.rowcount
        conn.commit()
        logging.info(f"✅ Updated {updated} momentum scores")
    except Exception as e:
        logging.error(f"❌ Error syncing momentum: {e}")
        conn.rollback()

    # Step 5: Sync sentiment scores (if available)
    logging.info("\nStep 5: Syncing sentiment scores...")
    try:
        cur.execute("""
            UPDATE stock_scores ss
            SET sentiment_score = ROUND(COALESCE(s.sentiment_score, 0.0)::NUMERIC, 2)
            FROM (
                SELECT DISTINCT ON (symbol) symbol, sentiment_score
                FROM stock_sentiment
                ORDER BY symbol, score_date DESC
            ) s
            WHERE ss.symbol = s.symbol
        """)
        updated = cur.rowcount
        conn.commit()
        logging.info(f"✅ Updated {updated} sentiment scores")
    except Exception as e:
        logging.warning(f"⚠️  Sentiment sync skipped: {e}")
        conn.rollback()

    # Step 6: Calculate composite score as weighted average
    logging.info("\nStep 6: Calculating composite scores...")
    try:
        # Weights: momentum=0.25, value=0.25, quality=0.25, growth=0.15, sentiment=0.05, stability=0.05
        cur.execute("""
            UPDATE stock_scores
            SET composite_score = ROUND((
                COALESCE(momentum_score, 0) * 0.25 +
                COALESCE(value_score, 0) * 0.25 +
                COALESCE(quality_score, 0) * 0.25 +
                COALESCE(growth_score, 0) * 0.15 +
                COALESCE(sentiment_score, 0) * 0.05 +
                COALESCE(stability_score, 0) * 0.05
            )::NUMERIC, 2),
            last_updated = CURRENT_TIMESTAMP
        """)
        conn.commit()
        logging.info("✅ Calculated composite scores")
    except Exception as e:
        logging.error(f"❌ Error calculating composite: {e}")
        conn.rollback()

    # Step 9: Verification
    logging.info("\n" + "=" * 80)
    logging.info("VERIFICATION")
    logging.info("=" * 80)

    cur.execute("""
        SELECT
            COUNT(*) as total,
            COUNT(CASE WHEN composite_score > 0 THEN 1 END) as with_composite,
            COUNT(CASE WHEN momentum_score > 0 THEN 1 END) as with_momentum,
            COUNT(CASE WHEN value_score > 0 THEN 1 END) as with_value,
            COUNT(CASE WHEN quality_score > 0 THEN 1 END) as with_quality,
            COUNT(CASE WHEN growth_score > 0 THEN 1 END) as with_growth,
            ROUND(AVG(composite_score)::NUMERIC, 2) as avg_composite
        FROM stock_scores
    """)

    stats = cur.fetchone()
    logging.info(f"Total stocks: {stats[0]:,}")
    logging.info(f"With composite score: {stats[1]:,}")
    logging.info(f"With momentum score: {stats[2]:,}")
    logging.info(f"With value score: {stats[3]:,}")
    logging.info(f"With quality score: {stats[4]:,}")
    logging.info(f"With growth score: {stats[5]:,}")
    logging.info(f"Average composite: {stats[6]}")

    # Top stocks
    logging.info("\n" + "=" * 80)
    logging.info("TOP 20 STOCKS BY COMPOSITE SCORE")
    logging.info("=" * 80)

    cur.execute("""
        SELECT symbol, composite_score, momentum_score, value_score, quality_score
        FROM stock_scores
        ORDER BY composite_score DESC
        LIMIT 20
    """)

    print(f"\n{'Symbol':<10} {'Composite':<12} {'Momentum':<12} {'Value':<12} {'Quality':<12}")
    print("-" * 60)
    for row in cur.fetchall():
        print(f"{row[0]:<10} {row[1]:<12.2f} {row[2]:<12.2f} {row[3]:<12.2f} {row[4]:<12.2f}")

    cur.close()
    conn.close()

    logging.info("\n" + "=" * 80)
    logging.info("✅ STOCK SCORES REBUILD COMPLETE")
    logging.info("=" * 80)

if __name__ == "__main__":
    main()
