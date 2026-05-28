#!/usr/bin/env python3
"""
Load S&P 500 constituents and mark them in stock_symbols table.

Fetches the current S&P 500 constituent list from Wikipedia and updates
the is_sp500 flag in stock_symbols to identify which symbols are in the index.
"""
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.db_connection import get_db_connection
import pandas as pd
import requests
from io import StringIO

logging.basicConfig(level=logging.INFO, format="%(asctime)s] %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("load_sp500_constituents")

# S&P 500 Wikipedia table URL
SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"

def get_sp500_symbols():
    """Fetch S&P 500 constituent symbols from Wikipedia."""
    try:
        logger.info("Fetching S&P 500 constituents from Wikipedia")

        # Use proper User-Agent to avoid 403 Forbidden
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }

        # Fetch the page with proper headers, then parse with pandas
        response = requests.get(SP500_URL, headers=headers, timeout=15)
        response.raise_for_status()

        # Parse tables from the response text
        tables = pd.read_html(StringIO(response.text))
        if not tables:
            logger.error("Could not find S&P 500 table on Wikipedia")
            return None

        # The main S&P 500 constituents table is typically the first one
        df = tables[0]

        # Extract symbols (column name varies but usually "Symbol" or "Ticker")
        if "Symbol" in df.columns:
            symbols = df["Symbol"].str.strip().tolist()
        elif "Ticker" in df.columns:
            symbols = df["Ticker"].str.strip().tolist()
        else:
            logger.error(f"Could not find symbol column. Columns: {df.columns.tolist()}")
            return None

        logger.info(f"Fetched {len(symbols)} S&P 500 constituents from Wikipedia")
        return symbols
    except Exception as e:
        logger.error(f"Error fetching S&P 500 list: {e}")
        return None

def mark_sp500_symbols(conn, symbols):
    """Mark symbols in stock_symbols table as S&P 500 members."""
    if not symbols:
        logger.warning("No S&P 500 symbols to mark")
        return 0

    try:
        with conn.cursor() as cur:
            # First, reset all is_sp500 flags to FALSE
            cur.execute("UPDATE stock_symbols SET is_sp500 = FALSE")
            reset_count = cur.rowcount
            logger.info(f"Reset is_sp500 flag for {reset_count} symbols")

            # Add benchmark index symbols that aren't in constituents list
            benchmark_symbols = ['SPY', '^GSPC']
            all_symbols = symbols + benchmark_symbols

            # Now mark the S&P 500 symbols
            # Use a subquery to avoid SQL injection
            placeholders = ",".join(["%s"] * len(all_symbols))
            sql = f"""
                UPDATE stock_symbols
                SET is_sp500 = TRUE
                WHERE symbol IN ({placeholders})
            """
            cur.execute(sql, all_symbols)
            marked_count = cur.rowcount
            logger.info(f"Marked {marked_count} symbols as S&P 500 members (including {len(benchmark_symbols)} benchmark symbols)")

            # Verify: check how many symbols are now marked
            cur.execute("SELECT COUNT(*) FROM stock_symbols WHERE is_sp500 = TRUE")
            total_marked = cur.fetchone()[0]
            logger.info(f"Total symbols marked as S&P 500: {total_marked}")

            conn.commit()
            return marked_count
    except Exception as e:
        logger.error(f"Error marking S&P 500 symbols: {e}")
        conn.rollback()
        return 0

def main():
    """Main entry point."""
    symbols = get_sp500_symbols()
    if not symbols:
        logger.error("Failed to fetch S&P 500 symbols")
        return False

    try:
        conn = get_db_connection()
        marked = mark_sp500_symbols(conn, symbols)
        conn.close()

        if marked > 0:
            logger.info(f"Successfully marked {marked} symbols as S&P 500 constituents")
            return True
        else:
            logger.warning("No symbols were marked as S&P 500")
            return False
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
