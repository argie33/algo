#!/usr/bin/env python3
import psycopg2
from datetime import date

# Get database connection
def get_db_config():
    import os
    return {
        "host": os.environ.get("DB_HOST", "localhost"),
        "port": int(os.environ.get("DB_PORT", "5432")),
        "user": os.environ.get("DB_USER", "stocks"),
        "password": os.environ.get("DB_PASSWORD", "bed0elAn"),
        "dbname": os.environ.get("DB_NAME", "stocks")
    }

conn = psycopg2.connect(**get_db_config())

# Get most recent date in options_chains
with conn.cursor() as cur:
    cur.execute("SELECT MAX(data_date) FROM options_chains WHERE option_type = 'call';")
    result = cur.fetchone()
    if result and result[0]:
        recent_date = result[0]
        print(f"Most recent data date: {recent_date}")
        
        # Count opportunities with quality filtering applied
        query = """
            WITH latest_technicals AS (
                SELECT DISTINCT ON (symbol) symbol, close FROM buy_sell_daily
                WHERE date >= %s - INTERVAL '7 days'
                ORDER BY symbol, date DESC
            )
            SELECT COUNT(*)
            FROM options_chains oc
            INNER JOIN options_greeks og ON oc.contract_symbol = og.contract_symbol
            LEFT JOIN latest_technicals lt ON oc.symbol = lt.symbol
            LEFT JOIN LATERAL (
                SELECT iv_percentile_30 AS iv_rank
                FROM iv_history WHERE symbol = oc.symbol
                ORDER BY date DESC LIMIT 1
            ) iv ON true
            LEFT JOIN LATERAL (
                SELECT composite_score, momentum_score
                FROM stock_scores WHERE symbol = oc.symbol
                ORDER BY calculated_at DESC LIMIT 1
            ) ss ON true
            WHERE oc.option_type = 'call'
              AND oc.data_date = %s
              AND oc.expiration_date > CURRENT_DATE
              AND oc.expiration_date <= CURRENT_DATE + INTERVAL '60 days'
              AND oc.strike >= og.stock_price * 1.01
              AND oc.strike <= og.stock_price * 1.15
              AND oc.bid > 0
              AND (ss.composite_score IS NULL OR ss.composite_score >= 40)
              AND (ss.momentum_score IS NULL OR ss.momentum_score >= 30)
        """
        
        with conn.cursor() as cur2:
            cur2.execute(query, (recent_date, recent_date))
            count = cur2.fetchone()[0]
            print(f"Candidates matching criteria: {count}")
    else:
        print("No call options data found")

conn.close()
