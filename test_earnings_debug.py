#!/usr/bin/env python3
import os
import psycopg2
from datetime import date, datetime

def get_db_config():
    return {
        "host": os.environ.get("DB_HOST", "localhost"),
        "port": int(os.environ.get("DB_PORT", "5432")),
        "user": os.environ.get("DB_USER", "stocks"),
        "password": os.environ.get("DB_PASSWORD", "bed0elAn"),
        "dbname": os.environ.get("DB_NAME", "stocks")
    }

try:
    conn = psycopg2.connect(**get_db_config())
    
    # Test the earnings date lateral join
    with conn.cursor() as cur:
        query = """
        SELECT
            oc.symbol,
            ce.next_earnings_date
        FROM options_chains oc
        LEFT JOIN LATERAL (
            SELECT start_date AS next_earnings_date
            FROM calendar_events
            WHERE symbol = oc.symbol
                AND event_type = 'earnings'
                AND start_date > CURRENT_DATE
            ORDER BY start_date ASC
            LIMIT 1
        ) ce ON true
        WHERE oc.option_type = 'call'
          AND oc.data_date = (SELECT MAX(data_date) FROM options_chains WHERE option_type = 'call')
        LIMIT 5
        """
        
        cur.execute(query)
        rows = cur.fetchall()
        
        for symbol, next_earnings in rows:
            print(f"{symbol}: {next_earnings} (type: {type(next_earnings)})")
    
    conn.close()
    
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
