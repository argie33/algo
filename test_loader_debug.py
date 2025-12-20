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
    
    # Get the first few rows to debug
    with conn.cursor() as cur:
        cur.execute("SELECT MAX(data_date) FROM options_chains WHERE option_type = 'call';")
        recent_date = cur.fetchone()[0]
        
        # Simplified query from the loader
        query = """
            WITH latest_technicals AS (
                SELECT DISTINCT ON (symbol)
                    symbol, close FROM buy_sell_daily
                WHERE date >= CURRENT_DATE - INTERVAL '7 days'
                ORDER BY symbol, date DESC
            )
            SELECT
                oc.symbol, oc.strike, og.stock_price, oc.bid, oc.ask,
                oc.expiration_date
            FROM options_chains oc
            INNER JOIN options_greeks og ON oc.contract_symbol = og.contract_symbol
            LEFT JOIN latest_technicals lt ON oc.symbol = lt.symbol
            WHERE oc.option_type = 'call'
              AND oc.data_date = %s
              AND oc.expiration_date > CURRENT_DATE
              AND oc.expiration_date <= CURRENT_DATE + INTERVAL '60 days'
              AND oc.strike >= og.stock_price * 1.01
              AND oc.strike <= og.stock_price * 1.15
              AND oc.bid > 0
            LIMIT 1
        """
        
        cur.execute(query, (recent_date,))
        row = cur.fetchone()
        
        if row:
            symbol, strike, stock_price, bid, ask, exp_date = row
            print(f"First row:")
            print(f"  symbol: {symbol} (type: {type(symbol)})")
            print(f"  strike: {strike} (type: {type(strike)})")
            print(f"  stock_price: {stock_price} (type: {type(stock_price)})")
            print(f"  bid: {bid} (type: {type(bid)})")
            print(f"  ask: {ask} (type: {type(ask)})")
            print(f"  exp_date: {exp_date} (type: {type(exp_date)})")
            print(f"  exp_date - date.today(): {exp_date} - {date.today()}")
            
            if isinstance(exp_date, datetime):
                print(f"  exp_date is datetime, converting to date...")
                exp_date_obj = exp_date.date()
                print(f"  exp_date.date() - date.today() = {(exp_date_obj - date.today()).days}")
    
    conn.close()
    
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
