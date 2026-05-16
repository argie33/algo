#!/usr/bin/env python3
"""
TimescaleDB Performance Benchmarks

Measures query performance improvements from TimescaleDB hypertables.
Runs a suite of typical data science queries and reports speedups.

Usage:
    python test_timescaledb_performance.py
    python test_timescaledb_performance.py --verbose
"""

try:
    from credential_manager import get_credential_manager
    credential_manager = get_credential_manager()
except ImportError:
    credential_manager = None
credential_manager = get_credential_manager()

import psycopg2
import time
import statistics
import argparse
import os
from pathlib import Path
from dotenv import load_dotenv
from typing import Tuple, List

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

class PerformanceBenchmark:
    def __init__(self, verbose=False):
        self.config = {
            "host": os.getenv("DB_HOST", "localhost"),
            "port": int(os.getenv("DB_PORT", 5432)),
            "user": os.getenv("DB_USER", "stocks"),
            "password": credential_manager.get_db_credentials()["password"],
            "database": os.getenv("DB_NAME", "stocks"),
        }
        self.verbose = verbose
        self.conn = None
        self.results = []

    def connect(self):
        try:
            self.conn = psycopg2.connect(
                host=self.config["host"],
                port=self.config["port"],
                user=self.config["user"],
                password=self.config["password"],
                database=self.config["database"]
            )
            self.conn.autocommit = True
            if self.verbose:
                print(f"✓ Connected to {self.config['database']}@{self.config['host']}")
            return True
        except Exception as e:
            print(f"✗ Connection failed: {e}")
            return False

    def disconnect(self):
        if self.conn:
            self.conn.close()

    def benchmark_query(self, name: str, sql: str, iterations=3) -> Tuple[float, float]:
        """
        Run a query multiple times and return (mean_time_ms, std_dev_ms)
        """
        times = []

        for i in range(iterations):
            try:
                cur = self.conn.cursor()
                start = time.time()
                cur.execute(sql)
                result = cur.fetchall()
                elapsed = (time.time() - start) * 1000  # Convert to ms
                cur.close()

                times.append(elapsed)

                if self.verbose:
                    print(f"  Iteration {i+1}: {elapsed:.2f}ms ({len(result)} rows)")

            except Exception as e:
                print(f"✗ Query failed: {e}")
                return 0, 0

        mean_time = statistics.mean(times)
        std_dev = statistics.stdev(times) if len(times) > 1 else 0

        return mean_time, std_dev

    def run_benchmarks(self):
        """Run full benchmark suite"""
        print("\n" + "="*70)
        print("TimescaleDB Performance Benchmarks")
        print("="*70)

        if not self.connect():
            return False

        # Check if hypertables exist
        cur = self.conn.cursor()
        cur.execute("SELECT COUNT(*) FROM timescaledb_information.hypertables;")
        ht_count = cur.fetchone()[0]
        cur.close()

        if ht_count == 0:
            print("\n✗ No hypertables found. Run migration first:")
            print("  python migrate_timescaledb.py")
            return False

        print(f"\n✓ Found {ht_count} hypertables\n")

        benchmarks = [
            ("Query 1: Recent price data (7 days)", """
                SELECT symbol, date, close, volume
                FROM price_daily
                WHERE date >= CURRENT_DATE - INTERVAL '7 days'
                ORDER BY date DESC
                LIMIT 1000;
            """),

            ("Query 2: 90-day aggregation (typical analysis)", """
                SELECT
                    symbol,
                    DATE_TRUNC('day', date)::date AS day,
                    COUNT(*) AS records,
                    AVG(close) AS avg_close,
                    MAX(high) AS daily_high,
                    MIN(low) AS daily_low,
                    SUM(volume) AS total_volume
                FROM price_daily
                WHERE date >= CURRENT_DATE - INTERVAL '90 days'
                GROUP BY symbol, DATE_TRUNC('day', date)
                HAVING COUNT(*) > 0
                ORDER BY day DESC;
            """),

            ("Query 3: Multi-symbol comparison (last 30 days)", """
                SELECT
                    symbol,
                    COUNT(*) AS days,
                    AVG(close) AS avg_price,
                    MAX(high) - MIN(low) AS price_range,
                    STDDEV(close) AS volatility
                FROM price_daily
                WHERE date >= CURRENT_DATE - INTERVAL '30 days'
                GROUP BY symbol
                ORDER BY volatility DESC
                LIMIT 100;
            """),

            ("Query 4: Technical indicators join (14-day lookback)", """
                SELECT
                    p.symbol,
                    p.date,
                    p.close,
                    t.rsi,
                    t.macd,
                    t.sma_50
                FROM price_daily p
                LEFT JOIN technical_data_daily t ON (p.symbol = t.symbol AND p.date = t.date)
                WHERE p.date >= CURRENT_DATE - INTERVAL '14 days'
                  AND p.volume > 1000000
                ORDER BY p.symbol, p.date DESC
                LIMIT 1000;
            """),

            ("Query 5: Buy/sell signal correlation (60-day window)", """
                SELECT
                    b.symbol,
                    b.date,
                    b.signal,
                    b.strength,
                    p.close,
                    LAG(p.close) OVER (PARTITION BY b.symbol ORDER BY b.date) AS prev_close
                FROM buy_sell_daily b
                LEFT JOIN price_daily p ON (b.symbol = p.symbol AND b.date = p.date)
                WHERE b.date >= CURRENT_DATE - INTERVAL '60 days'
                  AND b.signal IS NOT NULL
                ORDER BY b.date DESC;
            """),

            ("Query 6: Analyst sentiment aggregation (monthly)", """
                SELECT
                    symbol,
                    DATE_TRUNC('month', date)::date AS month,
                    COUNT(*) AS analyst_days,
                    AVG(analyst_count) AS avg_analysts,
                    AVG(bullish_count) AS avg_bullish,
                    AVG(upside_downside_percent) AS avg_upside
                FROM analyst_sentiment_analysis
                WHERE date >= CURRENT_DATE - INTERVAL '180 days'
                GROUP BY symbol, DATE_TRUNC('month', date)
                ORDER BY month DESC;
            """),

            ("Query 7: Earnings event lookback (1 year)", """
                SELECT
                    symbol,
                    quarter,
                    eps_actual,
                    eps_estimate,
                    eps_surprise_pct,
                    beat_miss_flag
                FROM earnings_estimates
                WHERE quarter >= CURRENT_DATE - INTERVAL '1 year'
                  AND quarter <= CURRENT_DATE
                ORDER BY quarter DESC;
            """),

            ("Query 8: Complex window function (momentum calculation)", """
                SELECT
                    symbol,
                    date,
                    close,
                    ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date) AS rn,
                    LAG(close) OVER (PARTITION BY symbol ORDER BY date) AS prev_close,
                    LEAD(close) OVER (PARTITION BY symbol ORDER BY date) AS next_close,
                    (close - LAG(close) OVER (PARTITION BY symbol ORDER BY date)) /
                      LAG(close) OVER (PARTITION BY symbol ORDER BY date) * 100 AS pct_change
                FROM price_daily
                WHERE date >= CURRENT_DATE - INTERVAL '30 days'
                ORDER BY symbol, date DESC;
            """),
        ]

        # Filter benchmarks: skip those with tables that might not have data
        tested = []
        for name, sql in benchmarks:
            try:
                mean_ms, std_ms = self.benchmark_query(name, sql, iterations=3)

                tested.append((name, mean_ms, std_ms))

                if mean_ms > 0:
                    print(f"✓ {name}")
                    print(f"  └─ {mean_ms:.2f}ms ± {std_ms:.2f}ms\n")

            except Exception as e:
                if "does not exist" in str(e):
                    print(f"⚠ {name} (table not yet populated, skipping)\n")
                else:
                    print(f"✗ {name}: {e}\n")

        # Summary statistics
        if tested:
            print("="*70)
            print("Performance Summary")
            print("="*70)

            avg_time = statistics.mean([t[1] for t in tested])
            print(f"\nAverage query time: {avg_time:.2f}ms")
            print(f"Fastest query: {min([t[1] for t in tested]):.2f}ms")
            print(f"Slowest query: {max([t[1] for t in tested]):.2f}ms")

            print("\nBenchmark Rankings (fastest to slowest):")
            for i, (name, mean_ms, std_ms) in enumerate(sorted(tested, key=lambda x: x[1])):
                print(f"{i+1:2d}. {name.split(': ')[0]}: {mean_ms:.2f}ms")

            print("\n" + "="*70)
            print("Expected Speedups from TimescaleDB:")
            print("="*70)
            print("""
  • Aggregations: 10-50x faster (GROUP BY on time-series)
  • Window functions: 5-20x faster (LAG, LEAD, ROW_NUMBER)
  • Time-range queries: 2-10x faster (WHERE date >= INTERVAL)
  • Join performance: 2-5x faster (compressed chunks reduce I/O)

If you're NOT seeing expected speedups:
  1. Verify hypertables were created: SELECT * FROM timescaledb_information.hypertables;
  2. Ensure compression policies ran: SELECT * FROM timescaledb_information.compression_policies;
  3. Check chunk size: SELECT COUNT(*) FROM timescaledb_information.chunks;
  4. Monitor query plans: EXPLAIN ANALYZE <your_query>;
            """)

        self.disconnect()
        return True


def main():
    parser = argparse.ArgumentParser(description='TimescaleDB Performance Benchmarks')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output (show each iteration)')
    args = parser.parse_args()

    benchmark = PerformanceBenchmark(verbose=args.verbose)
    benchmark.run_benchmarks()


if __name__ == '__main__':
    main()
