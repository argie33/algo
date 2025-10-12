#!/usr/bin/env python3
"""
Momentum Metrics Calculator
Calculates RS Rating and momentum scores for all stocks
Based on multi-timeframe momentum methodology
"""

import os
import sys
from datetime import datetime, timedelta
import psycopg2
from psycopg2.extras import RealDictCursor
import numpy as np

# Database configuration
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "database": os.getenv("DB_NAME", "stocks"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", "password"),
    "port": int(os.getenv("DB_PORT", 5432))
}


def get_db_connection():
    """Establish database connection"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        return conn
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        sys.exit(1)


def calculate_rs_rating(conn):
    """
    Calculate RS Rating (Relative Strength Rating) for all stocks
    Uses weighted multi-timeframe approach:
    - 40% weight on 12-month (252d) ROC
    - 20% weight on 9-month (189d) ROC
    - 20% weight on 6-month (120d) ROC
    - 20% weight on 3-month (60d) ROC

    Returns percentile rank (0-99) where 99 is strongest momentum
    """
    print("📊 Calculating RS Ratings...")

    cursor = conn.cursor(cursor_factory=RealDictCursor)

    # Get latest technical data with all ROC periods
    cursor.execute("""
        SELECT
            symbol,
            roc_252d,
            roc_189d,
            roc_120d,
            roc_60d,
            date
        FROM technical_data_daily
        WHERE date = (SELECT MAX(date) FROM technical_data_daily)
        AND roc_252d IS NOT NULL
        AND roc_189d IS NOT NULL
        AND roc_120d IS NOT NULL
        AND roc_60d IS NOT NULL
    """)

    stocks = cursor.fetchall()

    if not stocks:
        print("⚠️  No stocks found with complete ROC data")
        return {}

    # Calculate composite momentum score for each stock
    momentum_scores = {}
    for stock in stocks:
        # Weighted average of ROC periods
        composite = (
            0.40 * stock['roc_252d'] +
            0.20 * stock['roc_189d'] +
            0.20 * stock['roc_120d'] +
            0.20 * stock['roc_60d']
        )
        momentum_scores[stock['symbol']] = composite

    # Calculate percentile ranks (0-99)
    symbols = list(momentum_scores.keys())
    scores = np.array(list(momentum_scores.values()))

    # Convert to percentile rank
    rs_ratings = {}
    for symbol, score in momentum_scores.items():
        # Calculate what percentile this score falls into
        # Count how many scores are less than this score
        percentile = (np.sum(scores < score) / len(scores)) * 100
        # Convert to 0-99 scale
        rs_rating = min(99, max(0, int(percentile)))
        rs_ratings[symbol] = rs_rating

    print(f"✅ Calculated RS Ratings for {len(rs_ratings)} stocks")

    # Show some examples
    sorted_ratings = sorted(rs_ratings.items(), key=lambda x: x[1], reverse=True)
    print(f"\n🔝 Top 10 RS Ratings:")
    for symbol, rating in sorted_ratings[:10]:
        print(f"   {symbol}: {rating}")

    cursor.close()
    return rs_ratings


def calculate_momentum_score(conn, rs_ratings):
    """
    Calculate final momentum score (0-100) combining:
    - Core momentum (70%): weighted ROC + Mansfield RS
    - Regime confirmation (30%): RSI >60, price > SMA_200, volume surge
    """
    print("\n📈 Calculating momentum scores...")

    cursor = conn.cursor(cursor_factory=RealDictCursor)

    # Get latest technical data with all momentum indicators
    cursor.execute("""
        SELECT
            t.symbol,
            t.roc_252d,
            t.roc_120d,
            t.mansfield_rs,
            t.rsi,
            t.sma_200,
            t.volume_surge,
            t.close as current_price,
            t.date
        FROM technical_data_daily t
        WHERE t.date = (SELECT MAX(date) FROM technical_data_daily)
        AND t.roc_252d IS NOT NULL
        AND t.roc_120d IS NOT NULL
    """)

    stocks = cursor.fetchall()

    momentum_scores = {}

    for stock in stocks:
        symbol = stock['symbol']

        # Core momentum (70%): Z-scores of momentum components
        # Get z-score of ROC_252d
        all_roc_252 = [s['roc_252d'] for s in stocks if s['roc_252d'] is not None]
        roc_252_zscore = (stock['roc_252d'] - np.mean(all_roc_252)) / (np.std(all_roc_252) + 1e-10)

        # Get z-score of ROC_120d
        all_roc_120 = [s['roc_120d'] for s in stocks if s['roc_120d'] is not None]
        roc_120_zscore = (stock['roc_120d'] - np.mean(all_roc_120)) / (np.std(all_roc_120) + 1e-10)

        # Get z-score of Mansfield RS
        all_mansfield = [s['mansfield_rs'] for s in stocks if s['mansfield_rs'] is not None]
        mansfield_zscore = (stock['mansfield_rs'] - np.mean(all_mansfield)) / (np.std(all_mansfield) + 1e-10) if stock['mansfield_rs'] is not None else 0

        # Core momentum score (weighted average of z-scores)
        core_momentum = (
            0.40 * roc_252_zscore +
            0.30 * roc_120_zscore +
            0.30 * mansfield_zscore
        )

        # Regime confirmation (30%): Boolean filters
        rsi_regime = 1.0 if (stock['rsi'] and stock['rsi'] > 60) else 0.5
        trend_strength = 1.0 if (stock['sma_200'] and stock['current_price'] > stock['sma_200']) else 0.5
        volume_surge_signal = 1.0 if (stock['volume_surge'] and stock['volume_surge'] > 1.0) else 0.5

        # Average regime confirmation
        regime_boost = (0.4 * rsi_regime + 0.3 * trend_strength + 0.3 * volume_surge_signal)

        # Combine: core momentum (70%) + regime boost (30%)
        raw_score = core_momentum * 0.7 + regime_boost * 0.3

        # Convert z-score to 0-100 scale
        # Z-scores typically range from -3 to +3, so we normalize
        normalized_score = ((raw_score + 3) / 6) * 100

        # Clip to 0-100
        final_score = max(0, min(100, normalized_score))

        momentum_scores[symbol] = {
            'momentum_score': round(final_score, 2),
            'rs_rating': rs_ratings.get(symbol, 50),
            'core_momentum': round(core_momentum, 4),
            'regime_boost': round(regime_boost, 4)
        }

    print(f"✅ Calculated momentum scores for {len(momentum_scores)} stocks")

    # Show some examples
    sorted_scores = sorted(momentum_scores.items(), key=lambda x: x[1]['momentum_score'], reverse=True)
    print(f"\n🔝 Top 10 Momentum Scores:")
    for symbol, data in sorted_scores[:10]:
        print(f"   {symbol}: {data['momentum_score']:.1f} (RS Rating: {data['rs_rating']})")

    cursor.close()
    return momentum_scores


def update_momentum_scores(conn, momentum_scores):
    """
    Update stock_scores table with new momentum scores and RS ratings
    """
    print("\n💾 Updating momentum scores in database...")

    cursor = conn.cursor()

    updated_count = 0
    for symbol, data in momentum_scores.items():
        try:
            # Update momentum_score in stock_scores table
            cursor.execute("""
                UPDATE stock_scores
                SET
                    momentum_score = %s,
                    last_updated = NOW()
                WHERE symbol = %s
            """, (
                data['momentum_score'],
                symbol
            ))

            if cursor.rowcount > 0:
                updated_count += 1

        except Exception as e:
            print(f"⚠️  Error updating {symbol}: {e}")
            continue

    conn.commit()
    cursor.close()

    print(f"✅ Updated momentum scores for {updated_count} stocks")
    return updated_count


def store_rs_ratings(conn, rs_ratings):
    """
    Store RS Ratings in a dedicated table for historical tracking
    """
    print("\n💾 Storing RS Ratings...")

    cursor = conn.cursor()

    # Create RS ratings table if it doesn't exist
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS rs_ratings (
            symbol VARCHAR(10),
            rs_rating INTEGER,
            date DATE,
            created_at TIMESTAMP DEFAULT NOW(),
            PRIMARY KEY (symbol, date)
        )
    """)

    # Insert today's RS ratings
    today = datetime.now().date()

    inserted_count = 0
    for symbol, rating in rs_ratings.items():
        try:
            cursor.execute("""
                INSERT INTO rs_ratings (symbol, rs_rating, date)
                VALUES (%s, %s, %s)
                ON CONFLICT (symbol, date)
                DO UPDATE SET rs_rating = EXCLUDED.rs_rating
            """, (symbol, rating, today))

            inserted_count += 1

        except Exception as e:
            print(f"⚠️  Error storing RS rating for {symbol}: {e}")
            continue

    conn.commit()
    cursor.close()

    print(f"✅ Stored RS ratings for {inserted_count} stocks")
    return inserted_count


def main():
    """Main execution function"""
    print("=" * 80)
    print("🚀 Momentum Metrics Calculator")
    print("=" * 80)

    conn = get_db_connection()

    try:
        # Step 1: Calculate RS Ratings (percentile ranks)
        rs_ratings = calculate_rs_rating(conn)

        if not rs_ratings:
            print("❌ Failed to calculate RS Ratings")
            return

        # Step 2: Store RS Ratings for historical tracking
        store_rs_ratings(conn, rs_ratings)

        # Step 3: Calculate momentum scores
        momentum_scores = calculate_momentum_score(conn, rs_ratings)

        if not momentum_scores:
            print("❌ Failed to calculate momentum scores")
            return

        # Step 4: Update stock_scores table
        update_momentum_scores(conn, momentum_scores)

        print("\n" + "=" * 80)
        print("✅ Momentum metrics calculation complete!")
        print("=" * 80)

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

    finally:
        conn.close()


if __name__ == "__main__":
    main()
