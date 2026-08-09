#!/usr/bin/env python3
import os
os.environ.setdefault("LOCAL_MODE", "true")
os.environ.setdefault("ENVIRONMENT", "development")

from utils.dotenv_loader import load_env_local
load_env_local()

from utils.db.context import DatabaseContext

with DatabaseContext("read") as cur:
    cur.execute("""
        SELECT
            consecutive_positive_quarters, earnings_growth_4q_avg,
            quarterly_growth_momentum, eps_growth_stability, fcf_growth_yoy, eps_growth_5y
        FROM growth_metrics WHERE symbol = 'AAPL' ORDER BY updated_at DESC LIMIT 1
    """)
    row = cur.fetchone()

print("\nAPPL Growth Metrics:")
print(f"  consecutive_positive_quarters: {row[0]}")
print(f"  earnings_growth_4q_avg: {row[1]}")
print(f"  quarterly_growth_momentum: {row[2]}")
print(f"  eps_growth_stability: {row[3]}")
print(f"  fcf_growth_yoy: {row[4]}")
print(f"  eps_growth_5y: {row[5]}")

# Check if any of these are 0% null coverage
with DatabaseContext("read") as cur:
    cur.execute("""
        SELECT
            COUNT(CASE WHEN consecutive_positive_quarters IS NOT NULL THEN 1 END) as cpq_count,
            COUNT(CASE WHEN earnings_growth_4q_avg IS NOT NULL THEN 1 END) as e4q_count,
            COUNT(CASE WHEN quarterly_growth_momentum IS NOT NULL THEN 1 END) as qgm_count,
            COUNT(CASE WHEN eps_growth_stability IS NOT NULL THEN 1 END) as egs_count,
            COUNT(CASE WHEN fcf_growth_yoy IS NOT NULL THEN 1 END) as fcf_count,
            COUNT(CASE WHEN eps_growth_5y IS NOT NULL THEN 1 END) as eps5_count,
            COUNT(*) as total
        FROM growth_metrics
    """)
    stats = cur.fetchone()

print("\nGrowth Metrics Coverage (universe):")
print(f"  consecutive_positive_quarters: {stats[0]}/{stats[6]} ({100*stats[0]/stats[6]:.1f}%)")
print(f"  earnings_growth_4q_avg: {stats[1]}/{stats[6]} ({100*stats[1]/stats[6]:.1f}%)")
print(f"  quarterly_growth_momentum: {stats[2]}/{stats[6]} ({100*stats[2]/stats[6]:.1f}%)")
print(f"  eps_growth_stability: {stats[3]}/{stats[6]} ({100*stats[3]/stats[6]:.1f}%)")
print(f"  fcf_growth_yoy: {stats[4]}/{stats[6]} ({100*stats[4]/stats[6]:.1f}%)")
print(f"  eps_growth_5y: {stats[5]}/{stats[6]} ({100*stats[5]/stats[6]:.1f}%)")
