#!/usr/bin/env python3
"""Check actual table content ages."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from datetime import datetime
from utils.database_context import DatabaseContext

# Critical tables for orchestrator
critical_tables = [
    ('price_daily', 'date'),
    ('etf_price_daily', 'date'),
    ('market_health_daily', 'date'),
    ('trend_template_data', 'date'),
    ('technical_data_daily', 'date'),
    ('buy_sell_daily', 'date'),
    ('signal_quality_scores', 'date'),
    ('swing_trader_scores', 'date'),
    ('economic_data', 'date'),
]

try:
    with DatabaseContext('read') as cur:
        print("Checking critical table content:\n")
        for table, date_col in critical_tables:
            try:
                cur.execute(f"""
                    SELECT COUNT(*), MAX({date_col})
                    FROM {table}
                    LIMIT 1
                """)
                count, max_date = cur.fetchone()
                if max_date:
                    age_days = (datetime.now().date() - max_date).days
                    print(f"{table:30s} - {count:>10} rows, latest={max_date} ({age_days}d old)")
                else:
                    print(f"{table:30s} - EMPTY (0 rows)")
            except Exception as e:
                print(f"{table:30s} - ERROR: {e}")

except Exception as e:
    print(f"[ERROR] Database error: {e}")
