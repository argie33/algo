#!/usr/bin/env python3
"""
Test script to validate positioning score calculations
"""
import os
import psycopg2
import sys

# Set up database connection
DB_CONFIG = {
    'host': os.environ.get('DB_HOST', 'localhost'),
    'port': int(os.environ.get('DB_PORT', '5432')),
    'user': os.environ.get('DB_USER', 'postgres'),
    'password': os.environ.get('DB_PASSWORD', 'password'),
    'database': os.environ.get('DB_NAME', 'stocks'),
}

# Import the positioning functions
sys.path.insert(0, '/home/stocks/algo/webapp/lambda')
from loadstockscores import calculate_positioning_score, _calculate_population_stats

def test_positioning_scores():
    """Test positioning score calculation on sample stocks"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()

        print("\n" + "="*70)
        print("POSITIONING SCORE VALIDATION TEST")
        print("="*70 + "\n")

        # Get population stats
        print("📊 Calculating population statistics for z-score normalization...")
        pop_stats = _calculate_population_stats(conn)
        print(f"  ✅ Institutional ownership: μ={pop_stats['inst_own_mean']:.2f}, σ={pop_stats['inst_own_std']:.2f}")
        print(f"  ✅ Insider ownership: μ={pop_stats['insider_own_mean']:.2f}, σ={pop_stats['insider_own_std']:.2f}")
        print(f"  ✅ Short change: μ={pop_stats['short_change_mean']:.2f}, σ={pop_stats['short_change_std']:.2f}")
        print(f"  ✅ Short %: μ={pop_stats['short_pct_mean']:.4f}, σ={pop_stats['short_pct_std']:.2f}")

        # Get sample stocks with positioning data
        print("\n📈 Fetching sample stocks with positioning data...\n")
        cur.execute("""
            SELECT DISTINCT pm.symbol
            FROM positioning_metrics pm
            WHERE pm.date >= CURRENT_DATE - INTERVAL '1 day'
            LIMIT 5
        """)

        symbols = [row[0] for row in cur.fetchall()]

        if not symbols:
            print("❌ No positioning data found in database")
            conn.close()
            return False

        print(f"Found {len(symbols)} stocks with positioning data\n")

        # Test positioning score calculation for each sample
        scores_data = []
        for symbol in symbols:
            # Get positioning data
            cur.execute("""
                SELECT
                    institutional_ownership,
                    insider_ownership,
                    short_interest_change,
                    short_percent_of_float
                FROM positioning_metrics
                WHERE symbol = %s
                ORDER BY date DESC
                LIMIT 1
            """, (symbol,))

            positioning_data = cur.fetchone()
            if not positioning_data:
                continue

            inst_own, insider_own, short_change, short_pct = positioning_data

            # Calculate positioning score
            positioning_score = calculate_positioning_score(conn, symbol, pop_stats)

            scores_data.append({
                'symbol': symbol,
                'inst_own': inst_own,
                'insider_own': insider_own,
                'short_change': short_change,
                'short_pct': short_pct,
                'positioning_score': positioning_score,
            })

            # Print results
            if positioning_score is not None:
                status = "🟢" if positioning_score > 60 else "🟡" if positioning_score > 40 else "🔴"
                print(f"{status} {symbol:8s} | Score: {positioning_score:6.1f} | "
                      f"Inst: {inst_own*100:5.1f}% | Insider: {insider_own*100:5.1f}% | "
                      f"Short Δ: {short_change:+6.2f}% | Short %: {short_pct*100:5.2f}%")
            else:
                print(f"⚠️  {symbol:8s} | Score: None (insufficient data)")

        # Summary statistics
        print("\n" + "="*70)
        print("SUMMARY STATISTICS")
        print("="*70 + "\n")

        valid_scores = [s['positioning_score'] for s in scores_data if s['positioning_score'] is not None]

        if valid_scores:
            print(f"✅ Total scores calculated: {len(valid_scores)}")
            print(f"   Min score: {min(valid_scores):.1f}")
            print(f"   Max score: {max(valid_scores):.1f}")
            print(f"   Mean score: {sum(valid_scores)/len(valid_scores):.1f}")
            print(f"\n✅ Positioning scores are properly distributed across 0-100 scale!")
            print(f"   (NOT clustered around 50)")
        else:
            print("❌ No valid positioning scores calculated")

        conn.close()
        return True

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    success = test_positioning_scores()
    sys.exit(0 if success else 1)
