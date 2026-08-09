#!/usr/bin/env python3
import os
os.environ.setdefault("LOCAL_MODE", "true")
os.environ.setdefault("ENVIRONMENT", "development")

from utils.dotenv_loader import load_env_local
load_env_local()

from utils.db.context import DatabaseContext

with DatabaseContext("read") as cur:
    cur.execute("""
        SELECT consecutive_positive_quarters, earnings_growth_4q_avg, eps_growth_stability
        FROM quality_metrics WHERE symbol = 'AAPL' ORDER BY updated_at DESC LIMIT 1
    """)
    row = cur.fetchone()

print("AAPL Quality Metrics (just loaded):")
print(f"  consecutive_positive_quarters: {row[0]}")
print(f"  earnings_growth_4q_avg: {row[1]}")
print(f"  eps_growth_stability: {row[2]}")

# Check coverage
with DatabaseContext("read") as cur:
    cur.execute("""
        SELECT
            COUNT(CASE WHEN consecutive_positive_quarters IS NOT NULL THEN 1 END) as cpq,
            COUNT(CASE WHEN earnings_growth_4q_avg IS NOT NULL THEN 1 END) as e4q,
            COUNT(CASE WHEN eps_growth_stability IS NOT NULL THEN 1 END) as egs,
            COUNT(*) as total
        FROM quality_metrics
    """)
    stats = cur.fetchone()

print(f"\nQuality Metrics Coverage:")
print(f"  consecutive_positive_quarters: {stats[0]}/{stats[3]} ({100*stats[0]/stats[3]:.1f}%)")
print(f"  earnings_growth_4q_avg: {stats[1]}/{stats[3]} ({100*stats[1]/stats[3]:.1f}%)")
print(f"  eps_growth_stability: {stats[2]}/{stats[3]} ({100*stats[2]/stats[3]:.1f}%)")
