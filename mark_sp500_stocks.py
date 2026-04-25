#!/usr/bin/env python3
"""
Mark S&P 500 stocks in the database.
Fetches the official S&P 500 list and updates is_sp500 column.
"""
import psycopg2
import requests
import pandas as pd
import os
from dotenv import load_dotenv
from pathlib import Path

env_path = Path(__file__).parent / '.env.local'
if env_path.exists():
    load_dotenv(env_path)

def get_sp500_list():
    """Get S&P 500 list from Wikipedia"""
    try:
        url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
        tables = pd.read_html(url)
        df = tables[0]
        symbols = df['Symbol'].tolist()
        # Clean up symbols (remove notes, etc.)
        symbols = [s.split('\n')[0].strip() if isinstance(s, str) else s for s in symbols]
        print(f"✅ Fetched {len(symbols)} S&P 500 symbols from Wikipedia")
        return symbols
    except Exception as e:
        print(f"❌ Failed to fetch S&P 500 list: {e}")
        # Fallback: use well-known S&P 500 stocks
        return ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "BRK.B", "JNJ", "V",
                "WMT", "XOM", "JPM", "MA", "PG", "COST", "UNH", "HD", "MCD", "CRM"]

def mark_sp500(symbols):
    """Update is_sp500 column for S&P 500 stocks"""
    try:
        conn = psycopg2.connect(
            host=os.environ.get("DB_HOST", "localhost"),
            port=int(os.environ.get("DB_PORT", 5432)),
            user=os.environ.get("DB_USER", "stocks"),
            password=os.environ.get("DB_PASSWORD", ""),
            database=os.environ.get("DB_NAME", "stocks")
        )
        cur = conn.cursor()

        # First, reset all to FALSE
        cur.execute("UPDATE stock_symbols SET is_sp500 = FALSE")
        print(f"Reset all stocks to is_sp500 = FALSE")

        # Then, mark S&P 500 stocks as TRUE
        placeholders = ','.join(['%s'] * len(symbols))
        cur.execute(
            f"UPDATE stock_symbols SET is_sp500 = TRUE WHERE symbol IN ({placeholders})",
            symbols
        )
        conn.commit()
        print(f"✅ Marked {cur.rowcount} stocks as S&P 500")

        # Verify
        cur.execute("SELECT COUNT(*) FROM stock_symbols WHERE is_sp500 = TRUE")
        count = cur.fetchone()[0]
        print(f"✅ Database now has {count} S&P 500 stocks marked")

        conn.close()
        return True
    except Exception as e:
        print(f"❌ Database error: {e}")
        return False

if __name__ == "__main__":
    print("🔧 Marking S&P 500 stocks in database...")
    symbols = get_sp500_list()
    if symbols:
        success = mark_sp500(symbols)
        if success:
            print("✅ Done! S&P 500 stocks are now marked and will show in stock scores endpoint")
        else:
            print("❌ Failed to update database")
    else:
        print("❌ Failed to get S&P 500 list")
