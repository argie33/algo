#!/usr/bin/env python3
"""Check data freshness in database."""
import psycopg2
import os
from datetime import datetime, date

db_host = os.getenv('DB_HOST', 'localhost')
db_user = os.getenv('DB_USER', 'postgres')
db_password = os.getenv('DB_PASSWORD', '')
db_name = os.getenv('DB_NAME', 'stocks')

try:
    conn = psycopg2.connect(
        host=db_host,
        user=db_user,
        password=db_password if db_password else None,
        database=db_name
    )
    cur = conn.cursor()

    print("\n=== LOADER STATUS ===")
    cur.execute('''
        SELECT table_name, latest_date, status, age_days
        FROM data_loader_status
        ORDER BY table_name
    ''')
    for row in cur.fetchall():
        name, last_date, status, age_days = row
        age_str = f"{age_days}d" if age_days else "?"
        date_str = str(last_date) if last_date else "NULL"
        print(f"{name:30} | {date_str:12} | {str(status):10} | {age_str:5}")

    print("\n=== CORE TABLE FRESHNESS ===")

    # Check prices
    cur.execute("SELECT MAX(date) as latest_date FROM price_daily")
    prices_date = cur.fetchone()[0]
    print(f"{'price_daily':30} | {str(prices_date):12}")

    # Check technicals
    cur.execute("SELECT MAX(date) as latest_date FROM technical_data_daily")
    tech_date = cur.fetchone()[0]
    print(f"{'technical_data_daily':30} | {str(tech_date):12}")

    # Check market health
    cur.execute("SELECT MAX(date) as latest_date FROM market_health_daily")
    health_date = cur.fetchone()[0]
    print(f"{'market_health_daily':30} | {str(health_date):12}")

    # Check trend template
    cur.execute("SELECT MAX(date) as latest_date FROM trend_template_data")
    trend_date = cur.fetchone()[0]
    print(f"{'trend_template_data':30} | {str(trend_date):12}")

    # Check buy/sell signals
    cur.execute("SELECT MAX(date) as latest_date FROM buy_sell_daily")
    signals_date = cur.fetchone()[0]
    print(f"{'buy_sell_daily':30} | {str(signals_date):12}")

    # Check signal quality scores
    cur.execute("SELECT MAX(date) as latest_date FROM signal_quality_scores")
    quality_date = cur.fetchone()[0]
    print(f"{'signal_quality_scores':30} | {str(quality_date):12}")

    # Check swing trader scores
    cur.execute("SELECT MAX(date) as latest_date FROM swing_trader_scores")
    swing_date = cur.fetchone()[0]
    print(f"{'swing_trader_scores':30} | {str(swing_date):12}")

    conn.close()
    print("\n✓ Data freshness check complete")

except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
